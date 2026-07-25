import os
import random
import sys

import numpy as np
import torch
import torch.nn as nn
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, TensorDataset

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import RANDOM_STATE


class _LSTMNet(nn.Module):
    def __init__(self, input_size, hidden_size, num_layers, dropout):
        super().__init__()
        self.input_size = input_size
        self.lstm = nn.LSTM(
            input_size=input_size, hidden_size=hidden_size, num_layers=num_layers,
            batch_first=True, dropout=dropout if num_layers > 1 else 0.0,
        )
        self.dropout_layer = nn.Dropout(dropout)
        self.fc = nn.Sequential(
            nn.Linear(hidden_size, 64), nn.ReLU(), nn.Dropout(dropout), nn.Linear(64, 1),
        )

    def forward(self, x):
        out, _ = self.lstm(x)
        last_hidden = self.dropout_layer(out[:, -1, :])
        return self.fc(last_hidden).squeeze(-1)


class LSTMModel:
    """
    X and y are standardized (StandardScaler fit on train only); predictions
    are inverse-transformed back to raw units before evaluation. Huber loss
    (not MSE) since V has skewed/spiky regions (startup ramps, load steps).
    Gradient clipping + skip-on-nonfinite-gradient every step. Early stopping
    uses a chronological validation split (last val_ratio fraction of
    X_train, no shuffling) and restores the best-val-loss weights.
    """

    def __init__(
            self, hidden_size=128, num_layers=2, dropout=0.1, learning_rate=5e-4,
            epochs=150, batch_size=128, val_ratio=0.1, patience=10, loss_delta=1.0,
            adam_eps=1e-4, device=None,
    ):
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.dropout = dropout
        self.learning_rate = learning_rate
        self.epochs = epochs
        self.batch_size = batch_size
        # Default 1e-4 (PyTorch's Adam default is 1e-8): with delta targets
        # sitting at ~0 for long stretches, many parameters see persistently
        # tiny gradients, and Adam's denominator (sqrt(v_hat)+eps) can end up
        # dominated by eps itself -- too small an eps then produces a wildly
        # oversized update the moment a batch with real signal appears,
        # diverging to NaN.
        self.adam_eps = adam_eps
        self.loss_delta = loss_delta
        self.val_ratio = val_ratio
        self.patience = patience

        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        random.seed(RANDOM_STATE)
        np.random.seed(RANDOM_STATE)
        torch.manual_seed(RANDOM_STATE)
        if torch.cuda.is_available():
            torch.cuda.manual_seed(RANDOM_STATE)
            torch.cuda.manual_seed_all(RANDOM_STATE)

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
        self.model = _LSTMNet(input_size, self.hidden_size, self.num_layers, self.dropout).to(self.device)

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
            self.model.parameters(), lr=self.learning_rate, weight_decay=1e-5, eps=self.adam_eps,
        )
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", factor=0.5, patience=3)

        best_val_loss = float("inf")
        best_state = None
        epochs_no_improve = 0

        for epoch in range(self.epochs):
            self.model.train()
            total_loss, n_seen = 0.0, 0
            for X_batch, y_batch in loader:
                X_batch, y_batch = X_batch.to(self.device), y_batch.to(self.device)
                optimizer.zero_grad()
                loss = criterion(self.model(X_batch), y_batch)
                loss.backward()
                grad_norm = torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                if not torch.isfinite(grad_norm):
                    optimizer.zero_grad()
                    continue
                optimizer.step()
                total_loss += loss.item() * X_batch.size(0)
                n_seen += X_batch.size(0)

            train_loss = total_loss / n_seen if n_seen else float("nan")

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
            "state_dict": self.model.state_dict(), "hidden_size": self.hidden_size,
            "num_layers": self.num_layers, "dropout": self.dropout,
            "input_size": self.model.input_size, "scaler": self.scaler, "y_scaler": self.y_scaler,
        }, path)

    def load(self, path):
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)
        self.hidden_size = checkpoint["hidden_size"]
        self.num_layers = checkpoint["num_layers"]
        self.dropout = checkpoint["dropout"]
        self.scaler = checkpoint["scaler"]
        self.y_scaler = checkpoint["y_scaler"]
        self._build_model(input_size=checkpoint["input_size"])
        self.model.load_state_dict(checkpoint["state_dict"])
