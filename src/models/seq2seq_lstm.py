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


class _Seq2SeqNet(nn.Module):
    """
    Encoder reads WINDOW_SIZE past steps -> final (hidden, cell). Decoder is
    an autoregressive LSTM that unrolls n_horizons steps, consuming its own
    previous prediction (starting from a learned "start" value) at each
    step, optionally concatenated with the step's normalized horizon so the
    decoder can tell "1 step ahead" from "20 steps ahead" apart.
    """

    def __init__(self, input_size, hidden_size, num_layers, dropout, n_horizons, horizons=None, horizon_aware=False):
        super().__init__()
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.n_horizons = n_horizons
        self.horizon_aware = horizon_aware

        self.encoder = nn.LSTM(
            input_size=input_size, hidden_size=hidden_size, num_layers=num_layers,
            batch_first=True, dropout=dropout if num_layers > 1 else 0.0,
        )
        decoder_input_size = 2 if horizon_aware else 1
        self.decoder = nn.LSTM(
            input_size=decoder_input_size, hidden_size=hidden_size, num_layers=num_layers,
            batch_first=True, dropout=dropout if num_layers > 1 else 0.0,
        )
        self.dropout_layer = nn.Dropout(dropout)
        self.output_layer = nn.Sequential(
            nn.Linear(hidden_size, 64), nn.ReLU(), nn.Dropout(dropout), nn.Linear(64, 1),
        )
        self.start_token = nn.Parameter(torch.zeros(1, 1, 1))

        if horizon_aware:
            if horizons is None:
                raise ValueError("horizons must be provided when horizon_aware=True")
            norm = [h / max(horizons) for h in horizons]
            self.register_buffer("horizon_features", torch.tensor(norm, dtype=torch.float32).view(1, n_horizons, 1))

    def forward(self, x, y_true=None, teacher_forcing_ratio=0.0):
        batch_size = x.size(0)
        _, (h, c) = self.encoder(x)
        prev_pred = self.start_token.expand(batch_size, 1, 1)
        hidden = (h, c)

        outputs = []
        for step in range(self.n_horizons):
            if self.horizon_aware:
                h_feat = self.horizon_features[:, step, :].expand(batch_size, 1, 1)
                decoder_input = torch.cat([prev_pred, h_feat], dim=-1)
            else:
                decoder_input = prev_pred

            out, hidden = self.decoder(decoder_input, hidden)
            out = self.dropout_layer(out.squeeze(1))
            pred = self.output_layer(out)
            outputs.append(pred)

            use_tf = (
                self.training and y_true is not None and teacher_forcing_ratio > 0.0
                and torch.rand(1).item() < teacher_forcing_ratio
            )
            prev_pred = y_true[:, step].reshape(batch_size, 1, 1) if use_tf else pred.unsqueeze(1)

        return torch.cat(outputs, dim=1)


class Seq2SeqLSTMModel:
    def __init__(
            self, horizons, hidden_size=128, num_layers=2, dropout=0.1, learning_rate=5e-4,
            epochs=150, batch_size=128, val_ratio=0.1, patience=10, loss_delta=1.0,
            weight_decay=1e-5, horizon_aware_decoder=False, teacher_forcing_start=0.0,
            teacher_forcing_decay_epochs=None, adam_eps=1e-4, device=None, seed=None,
    ):
        self.horizons = list(horizons)
        self.n_horizons = len(self.horizons)
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.dropout = dropout
        self.learning_rate = learning_rate
        self.epochs = epochs
        self.batch_size = batch_size
        self.val_ratio = val_ratio
        self.patience = patience
        self.loss_delta = loss_delta
        self.weight_decay = weight_decay
        self.horizon_aware_decoder = horizon_aware_decoder
        self.teacher_forcing_start = teacher_forcing_start
        self.teacher_forcing_decay_epochs = teacher_forcing_decay_epochs or epochs
        self.adam_eps = adam_eps

        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.seed = seed if seed is not None else RANDOM_STATE
        random.seed(self.seed)
        np.random.seed(self.seed)
        torch.manual_seed(self.seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed(self.seed)
            torch.cuda.manual_seed_all(self.seed)

        self.model = None
        self.scaler = StandardScaler()
        # One scaler for the target, fit jointly across all horizon columns
        # (not one scaler per horizon) so the decoder learns a single
        # consistent output scale across the whole sequence.
        self.y_scaler = StandardScaler()

    def _scale_fit(self, X):
        n, w, f = X.shape
        self.scaler.fit(X.reshape(-1, f))
        return self.scaler.transform(X.reshape(-1, f)).reshape(n, w, f)

    def _scale_transform(self, X):
        n, w, f = X.shape
        return self.scaler.transform(X.reshape(-1, f)).reshape(n, w, f)

    def _y_scale_fit(self, y):
        flat = y.reshape(-1, 1)
        self.y_scaler.fit(flat)
        return self.y_scaler.transform(flat).reshape(y.shape)

    def _y_scale_transform(self, y):
        flat = y.reshape(-1, 1)
        return self.y_scaler.transform(flat).reshape(y.shape)

    def _y_inverse_transform(self, y_scaled):
        shape = y_scaled.shape
        return self.y_scaler.inverse_transform(y_scaled.reshape(-1, 1)).reshape(shape)

    def _build_model(self, input_size):
        self.model = _Seq2SeqNet(
            input_size=input_size, hidden_size=self.hidden_size, num_layers=self.num_layers,
            dropout=self.dropout, n_horizons=self.n_horizons, horizons=self.horizons,
            horizon_aware=self.horizon_aware_decoder,
        ).to(self.device)

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
            tf_ratio = max(0.0, self.teacher_forcing_start * (1 - epoch / self.teacher_forcing_decay_epochs))

            self.model.train()
            total_loss, n_seen = 0.0, 0
            for X_batch, y_batch in loader:
                X_batch, y_batch = X_batch.to(self.device), y_batch.to(self.device)
                optimizer.zero_grad()
                y_pred = self.model(X_batch, y_true=y_batch, teacher_forcing_ratio=tf_ratio)
                loss = criterion(y_pred, y_batch)
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
        """Returns (samples, n_horizons), columns in the order of self.horizons."""
        self.model.eval()
        X_tensor = torch.tensor(self._scale_transform(X_test), dtype=torch.float32).to(self.device)
        with torch.no_grad():
            y_pred_scaled = self.model(X_tensor).cpu().numpy()
        return self._y_inverse_transform(y_pred_scaled)

    def save(self, path):
        torch.save({
            "state_dict": self.model.state_dict(), "hidden_size": self.hidden_size,
            "num_layers": self.num_layers, "dropout": self.dropout, "input_size": self.model.input_size,
            "horizons": self.horizons, "scaler": self.scaler, "y_scaler": self.y_scaler,
            "horizon_aware_decoder": self.horizon_aware_decoder,
        }, path)

    def load(self, path):
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)
        self.horizons = checkpoint["horizons"]
        self.n_horizons = len(self.horizons)
        self.hidden_size = checkpoint["hidden_size"]
        self.num_layers = checkpoint["num_layers"]
        self.dropout = checkpoint["dropout"]
        self.scaler = checkpoint["scaler"]
        self.y_scaler = checkpoint["y_scaler"]
        self.horizon_aware_decoder = checkpoint.get("horizon_aware_decoder", False)
        self._build_model(input_size=checkpoint["input_size"])
        self.model.load_state_dict(checkpoint["state_dict"])
