import os
import random
import sys

import numpy as np
import torch
import torch.nn as nn
from sklearn.preprocessing import StandardScaler
from torch.nn.utils.parametrizations import weight_norm
from torch.utils.data import DataLoader, TensorDataset

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import RANDOM_STATE

# Must be set before any CUDA context is created (cuBLAS reads it at init) --
# required for torch.use_deterministic_algorithms(True) to cover matmul/linear
# ops on CUDA instead of raising RuntimeError. Harmless on CPU-only runs.
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")


class _Chomp1d(nn.Module):
    """Causal conv pads both sides to keep output length == input length;
    this chops off the extra right-side timesteps that would otherwise see
    into the future, restoring causality."""

    def __init__(self, chomp_size):
        super().__init__()
        self.chomp_size = chomp_size

    def forward(self, x):
        if self.chomp_size == 0:
            return x
        return x[:, :, :-self.chomp_size].contiguous()


class _TemporalBlock(nn.Module):
    def __init__(self, n_inputs, n_outputs, kernel_size, dilation, dropout):
        super().__init__()
        padding = (kernel_size - 1) * dilation

        self.conv1 = weight_norm(nn.Conv1d(n_inputs, n_outputs, kernel_size, padding=padding, dilation=dilation))
        self.chomp1 = _Chomp1d(padding)
        self.relu1 = nn.ReLU()
        self.dropout1 = nn.Dropout(dropout)

        self.conv2 = weight_norm(nn.Conv1d(n_outputs, n_outputs, kernel_size, padding=padding, dilation=dilation))
        self.chomp2 = _Chomp1d(padding)
        self.relu2 = nn.ReLU()
        self.dropout2 = nn.Dropout(dropout)

        self.net = nn.Sequential(
            self.conv1, self.chomp1, self.relu1, self.dropout1,
            self.conv2, self.chomp2, self.relu2, self.dropout2,
        )
        self.downsample = nn.Conv1d(n_inputs, n_outputs, 1) if n_inputs != n_outputs else None
        self.relu = nn.ReLU()
        self.init_weights()

    def init_weights(self):
        # Bai et al. (2018) init conv weights from N(0, 0.01), not PyTorch's
        # default fan_in-based init -- default init makes weight_norm's
        # initial magnitude ~10x too large, causing chaotic sensitivity to
        # floating-point rounding noise from multi-threaded conv ops.
        # conv1/conv2 go through weight_norm, so `.weight` is a *computed*
        # tensor (g * v/||v||); the actual learnable tensors are
        # `.parametrizations.weight.original0` (g) / `.original1` (v).
        with torch.no_grad():
            for conv in (self.conv1, self.conv2):
                v = conv.parametrizations.weight.original1
                v.normal_(0, 0.01)
                g = conv.parametrizations.weight.original0
                g.copy_(v.norm(dim=(1, 2), keepdim=True))
            if self.downsample is not None:
                self.downsample.weight.data.normal_(0, 0.01)

    def forward(self, x):
        out = self.net(x)
        res = x if self.downsample is None else self.downsample(x)
        return self.relu(out + res)


class _TCNNet(nn.Module):
    def __init__(self, input_size, num_channels, kernel_size, dropout):
        super().__init__()
        self.input_size = input_size
        layers = []
        for i in range(len(num_channels)):
            dilation = 2 ** i
            in_ch = input_size if i == 0 else num_channels[i - 1]
            layers.append(_TemporalBlock(in_ch, num_channels[i], kernel_size, dilation, dropout))
        self.network = nn.Sequential(*layers)
        self.output_layer = nn.Sequential(
            nn.Linear(num_channels[-1], 64), nn.ReLU(), nn.Dropout(dropout), nn.Linear(64, 1),
        )

    def forward(self, x):
        x = x.transpose(1, 2)          # (batch, features, window_size)
        out = self.network(x)          # (batch, channels, window_size)
        last_step = out[:, :, -1]      # most recent timestep, like an LSTM's final hidden state
        return self.output_layer(last_step).squeeze(-1)


class TCNModel:
    """
    Same conventions as models/lstm.py's LSTMModel: X/y scaling fit
    train-only, Huber loss, grad clipping, chronological val split, early
    stopping. Forces deterministic cuDNN (fixed conv algorithm, no autotune)
    since cuDNN's default algorithm-selection is not reproducible run-to-run
    on GPU even with a fixed seed -- this was confirmed in the source
    project (FCF) to flip Optuna hyperparameter-search conclusions between
    identical runs. `seed` is overridable so a caller can train the same
    config under several seeds and average away that remaining run-to-run
    noise.
    """

    def __init__(
            self, num_channels=(32, 32, 32, 32), kernel_size=3, dropout=0.1, learning_rate=5e-4,
            epochs=150, batch_size=128, val_ratio=0.1, patience=10, loss_delta=1.0,
            weight_decay=1e-5, adam_eps=1e-4, device=None, seed=None,
    ):
        self.num_channels = list(num_channels)
        self.kernel_size = kernel_size
        self.dropout = dropout
        self.learning_rate = learning_rate
        self.epochs = epochs
        self.batch_size = batch_size
        self.val_ratio = val_ratio
        self.patience = patience
        self.loss_delta = loss_delta
        self.weight_decay = weight_decay
        self.adam_eps = adam_eps

        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.seed = seed if seed is not None else RANDOM_STATE
        random.seed(self.seed)
        np.random.seed(self.seed)
        torch.manual_seed(self.seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed(self.seed)
            torch.cuda.manual_seed_all(self.seed)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
        torch.use_deterministic_algorithms(True, warn_only=True)

        self.model = None
        self.scaler = StandardScaler()
        self.y_scaler = StandardScaler()

    def _scale_fit(self, X):
        n, w, f = X.shape
        self.scaler.fit(X.reshape(-1, f))
        return self.scaler.transform(X.reshape(-1, f)).reshape(n, w, f)

    def _scale_transform(self, X):
        n, w, f = X.shape
        return self.scaler.transform(X.reshape(-1, f)).reshape(n, w, f)

    def _y_scale_fit(self, y):
        y2d = np.asarray(y).reshape(-1, 1)
        self.y_scaler.fit(y2d)
        return self.y_scaler.transform(y2d).reshape(-1)

    def _y_scale_transform(self, y):
        y2d = np.asarray(y).reshape(-1, 1)
        return self.y_scaler.transform(y2d).reshape(-1)

    def _y_inverse_transform(self, y_scaled):
        y2d = np.asarray(y_scaled).reshape(-1, 1)
        return self.y_scaler.inverse_transform(y2d).reshape(-1)

    def _build_model(self, input_size):
        self.model = _TCNNet(input_size, self.num_channels, self.kernel_size, self.dropout).to(self.device)

    def train(self, X_train, y_train, verbose=True, val_ratio=None, patience=None):
        val_ratio = self.val_ratio if val_ratio is None else val_ratio
        patience = self.patience if patience is None else patience

        if self.model is None:
            self._build_model(input_size=X_train.shape[2])

        n_val = int(len(X_train) * val_ratio)
        X_tr, X_val = X_train[:-n_val], X_train[-n_val:]
        y_tr, y_val = y_train[:-n_val], y_train[-n_val:]

        X_tr_scaled = self._scale_fit(X_tr)
        X_val_scaled = self._scale_transform(X_val)
        y_tr_scaled = self._y_scale_fit(y_tr)
        y_val_scaled = self._y_scale_transform(y_val)

        X_tensor = torch.tensor(X_tr_scaled, dtype=torch.float32)
        y_tensor = torch.tensor(y_tr_scaled, dtype=torch.float32)
        X_val_tensor = torch.tensor(X_val_scaled, dtype=torch.float32).to(self.device)
        y_val_tensor = torch.tensor(y_val_scaled, dtype=torch.float32).to(self.device)

        loader = DataLoader(TensorDataset(X_tensor, y_tensor), batch_size=self.batch_size, shuffle=True)

        criterion = nn.HuberLoss(delta=self.loss_delta)
        optimizer = torch.optim.Adam(
            self.model.parameters(), lr=self.learning_rate, weight_decay=self.weight_decay, eps=self.adam_eps,
        )
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", factor=0.5, patience=3)

        best_val_loss = float("inf")
        best_state = None
        epochs_no_improve = 0

        for epoch in range(self.epochs):
            self.model.train()
            total_loss, n_seen, n_skipped = 0.0, 0, 0
            for X_batch, y_batch in loader:
                X_batch, y_batch = X_batch.to(self.device), y_batch.to(self.device)
                optimizer.zero_grad()
                loss = criterion(self.model(X_batch), y_batch)
                loss.backward()
                grad_norm = torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                if not torch.isfinite(grad_norm):
                    optimizer.zero_grad()
                    n_skipped += 1
                    continue
                optimizer.step()
                total_loss += loss.item() * X_batch.size(0)
                n_seen += X_batch.size(0)

            train_loss = total_loss / n_seen if n_seen else float("nan")
            if verbose and n_skipped:
                print(f"  ({n_skipped} batch(es) skipped this epoch: non-finite gradient)")

            self.model.eval()
            with torch.no_grad():
                val_loss = criterion(self.model(X_val_tensor), y_val_tensor).item()
            scheduler.step(val_loss)

            if verbose:
                print(f"Epoch {epoch + 1}/{self.epochs} - train_loss: {train_loss:.6f}  val_loss: {val_loss:.6f}")

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_state = {k: v.clone() for k, v in self.model.state_dict().items()}
                epochs_no_improve = 0
            else:
                epochs_no_improve += 1
                if epochs_no_improve >= patience:
                    if verbose:
                        print(f"Early stopping at epoch {epoch + 1} (no val improvement for {patience} epochs)")
                    break

        if best_state is not None:
            self.model.load_state_dict(best_state)

    def predict(self, X_test):
        self.model.eval()
        X_tensor = torch.tensor(self._scale_transform(X_test), dtype=torch.float32).to(self.device)
        with torch.no_grad():
            y_pred_scaled = self.model(X_tensor).cpu().numpy()
        return self._y_inverse_transform(y_pred_scaled)

    def save(self, path):
        torch.save({
            "state_dict": self.model.state_dict(), "num_channels": self.num_channels,
            "kernel_size": self.kernel_size, "dropout": self.dropout, "input_size": self.model.input_size,
            "scaler": self.scaler, "y_scaler": self.y_scaler,
        }, path)

    def load(self, path):
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)
        self.num_channels = checkpoint["num_channels"]
        self.kernel_size = checkpoint["kernel_size"]
        self.dropout = checkpoint["dropout"]
        self.scaler = checkpoint["scaler"]
        self.y_scaler = checkpoint["y_scaler"]
        self._build_model(input_size=checkpoint["input_size"])
        self.model.load_state_dict(checkpoint["state_dict"])
