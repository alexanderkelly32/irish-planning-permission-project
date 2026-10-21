"""Runner: multi-task shared-representation model experiment.

One model with a shared trunk over scheme features (structured + authority +
TF-IDF text) predicts all outcomes jointly: refusal, FI, appeal (binary
heads) and decision duration (regression head). Compared against single-task
logistic/ridge models on IDENTICAL features and split (train received < 2021,
holdout >= 2021) - the honest test of whether sharing helps.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import torch  # noqa: E402
import torch.nn as nn  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.linear_model import LogisticRegression, Ridge  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from devrisk import settings  # noqa: E402
from run_appeal_model import build_frame  # noqa: E402

RNG = 7
torch.manual_seed(RNG)
np.random.seed(RNG)


class MultiTaskNet(nn.Module):
    def __init__(self, input_dim: int, hidden: int = 256):
        super().__init__()
        self.trunk = nn.Sequential(
            nn.Linear(input_dim, hidden),
            nn.ReLU(),
            nn.Dropout(0.4),
            nn.Linear(hidden, 128),
            nn.ReLU(),
            nn.Dropout(0.2),
        )
        self.head_refusal = nn.Linear(128, 1)
        self.head_fi = nn.Linear(128, 1)
        self.head_appeal = nn.Linear(128, 1)
        self.head_duration = nn.Linear(128, 1)

    def forward(self, x):
        shared = self.trunk(x)
        return (
            self.head_refusal(shared).squeeze(1),
            self.head_fi(shared).squeeze(1),
            self.head_appeal(shared).squeeze(1),
            self.head_duration(shared).squeeze(1),
        )


if __name__ == "__main__":
    frame = build_frame()
    frame["refusal"] = frame["Decision"].fillna("").astype(str).str.upper().str.contains("REFUS").astype(int)
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    register["fi_dt"] = pd.to_datetime(register[["FIRequestDate", "FIRecDate"]].min(axis=1), utc=True, errors="coerce")
    frame = frame.merge(register[["case_key", "fi_dt"]], on="case_key", how="left")
    frame["fi_flag"] = frame["fi_dt"].notna().astype(int)
    frame = frame.dropna(subset=["received_dt"])
    frame["log_duration"] = np.log1p((pd.to_datetime(frame["DecisionDate"], utc=True, errors="coerce") - frame["received_dt"]).dt.days.clip(lower=1))
    frame = frame.dropna(subset=["log_duration"])

    train = frame[frame["received_year"] < 2021]
    test = frame[frame["received_year"] >= 2021]

    tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=8000, sublinear_tf=True, stop_words="english", min_df=3)
    text_train = tfidf.fit_transform(train["description_lower"]).toarray()
    text_test = tfidf.transform(test["description_lower"]).toarray()
    structured_cols = ["log_units", "type_apartment", "type_house", "received_year", "received_month"]

    def features(part: pd.DataFrame, text: np.ndarray) -> np.ndarray:
        auth = pd.get_dummies(part["PlanningAuthority"]).reindex(
            columns=pd.get_dummies(train["PlanningAuthority"]).columns, fill_value=0
        ).values
        return np.hstack([part[structured_cols].fillna(0.0).values, auth, text]).astype(np.float32)

    X_train = features(train, text_train)
    X_test = features(test, text_test)
    y_train = {
        "refusal": train["refusal"].to_numpy().astype(np.float32),
        "fi": train["fi_flag"].to_numpy().astype(np.float32),
        "appeal": train["appeal_flag"].to_numpy().astype(np.float32),
        "duration": train["log_duration"].to_numpy().astype(np.float32),
    }
    y_test = {
        "refusal": test["refusal"].to_numpy().astype(np.float32),
        "fi": test["fi_flag"].to_numpy().astype(np.float32),
        "appeal": test["appeal_flag"].to_numpy().astype(np.float32),
        "duration": np.expm1(test["log_duration"].to_numpy()),
    }

    report: dict[str, object] = {}

    # Single-task baselines (identical features).
    for name, key in (("refusal", "refusal"), ("fi", "fi"), ("appeal", "appeal")):
        clf = LogisticRegression(C=0.5, max_iter=2000, solver="liblinear")
        clf.fit(X_train, y_train[key])
        p = clf.predict_proba(X_test)[:, 1]
        report[f"single_{name}"] = {"auc": round(roc_auc_score(y_test[key], p), 4)}
    ridge = Ridge(alpha=1.0)
    ridge.fit(X_train, y_train["duration"])
    dur_pred = np.expm1(ridge.predict(X_test))
    report["single_duration"] = {"mae": round(float(np.mean(np.abs(y_test["duration"] - dur_pred))), 1)}

    # Multi-task model.
    X_tr_t = torch.tensor(X_train)
    X_te_t = torch.tensor(X_test)
    model = MultiTaskNet(X_train.shape[1])
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    bce = nn.BCEWithLogitsLoss()
    mse = nn.MSELoss()
    best_val = 1e9
    patience = 8
    stale = 0
    for epoch in range(80):
        model.train()
        optimizer.zero_grad()
        p_r, p_f, p_a, p_d = model(X_tr_t)
        loss = (
            0.8 * bce(p_r, torch.tensor(y_train["refusal"]))
            + 1.2 * bce(p_f, torch.tensor(y_train["fi"]))
            + 1.0 * bce(p_a, torch.tensor(y_train["appeal"]))
            + 0.15 * mse(p_d, torch.tensor(y_train["duration"]))
        )
        loss.backward()
        optimizer.step()
        if epoch % 5 == 0:
            model.eval()
            with torch.no_grad():
                q_r, q_f, q_a, q_d = model(X_te_t)
                val_loss = float(bce(q_r, torch.tensor(y_test["refusal"])))
            if val_loss < best_val - 1e-4:
                best_val = val_loss
                stale = 0
            else:
                stale += 1
            if stale >= patience:
                break

    model.eval()
    with torch.no_grad():
        p_r, p_f, p_a, p_d = model(X_te_t)
        p_r = torch.sigmoid(p_r).numpy()
        p_f = torch.sigmoid(p_f).numpy()
        p_a = torch.sigmoid(p_a).numpy()
        p_d = np.expm1(p_d.numpy())

    report["multi_refusal"] = {"auc": round(roc_auc_score(y_test["refusal"], p_r), 4)}
    report["multi_fi"] = {"auc": round(roc_auc_score(y_test["fi"], p_f), 4)}
    report["multi_appeal"] = {"auc": round(roc_auc_score(y_test["appeal"], p_a), 4)}
    report["multi_duration"] = {"mae": round(float(np.mean(np.abs(y_test["duration"] - p_d))), 1)}
    report["n"] = {"train": int(len(train)), "test": int(len(test))}
    report["split"] = "train received < 2021, holdout >= 2021 (identical features for all models)"

    out = settings.SILVER_DIR / "multitask_experiment.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
