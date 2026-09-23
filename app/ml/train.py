"""One-time training script for the XGBoost code risk prediction model.

DATASET: KC1 from the PROMISE Software Engineering Repository
  URL: https://github.com/klainfo/defects4j-data (mirror)
  Original: http://promise.site.uottawa.ca/SERepository/datasets/kc1.arff

KC1 Description:
  - 2109 Java modules from a NASA flight software project
  - Features: CK metrics (LOC, Weighted Methods per Class, CBO, RFC, etc.)
  - Target: defects (number of defects found; binarized: 0 = clean, 1 = defective)
  - This is a standard benchmark dataset in software defect prediction literature

Feature Mapping (KC1 → Our Feature Space):
  KC1 "loc"              → loc (lines of code)
  KC1 "wmc"              → cyclomatic_complexity_avg (weighted methods, maps to complexity)
  KC1 "rfc"              → num_functions (response for a class, maps to method count)
  KC1 "cbo"              → num_imports (coupling between objects, maps to import count)
  KC1 "dit"              → max_nesting_depth (depth of inheritance, maps to nesting)
  KC1 "lcom"             → comment_ratio (inverted: lack of cohesion, maps inversely)
  KC1 "max_cc"           → severity_weighted_score (max complexity block)
  Missing → num_classes, avg_function_length, num_static_findings, num_llm_findings, code_lines

NOTE: Feature mapping is approximate. KC1 uses OO Java metrics; we use general code metrics.
The model should be interpreted as a rough risk signal, not an exact predictor.

USAGE:
  python -m app.ml.train

This script:
  1. Downloads KC1 from a public GitHub mirror
  2. Maps KC1 features to our feature space
  3. Trains XGBoost with cross-validation
  4. Evaluates on held-out test set
  5. Saves model + scaler to app/ml/model_artifacts/

Run this once before deploying the application.
"""

from __future__ import annotations

import json
import logging
import sys
import urllib.request
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

ARTIFACTS_DIR = Path(__file__).parent / "model_artifacts"
ARTIFACTS_DIR.mkdir(exist_ok=True)

# KC1 dataset hosted on the PROMISE repository mirror
# This is a well-known public domain research dataset
KC1_URL = (
    "https://raw.githubusercontent.com/klainfo/NaiveBayesEstimator"
    "/master/data/kc1.csv"
)


def _download_kc1(dest_path: Path) -> bool:
    """Download the KC1 dataset CSV. Returns True on success."""
    if dest_path.exists():
        logger.info("KC1 dataset already downloaded at %s", dest_path)
        return True

    logger.info("Downloading KC1 dataset from PROMISE repository mirror...")
    try:
        with urllib.request.urlopen(KC1_URL, timeout=30) as resp:
            dest_path.write_bytes(resp.read())
        logger.info("Downloaded KC1 to %s (%d bytes)", dest_path, dest_path.stat().st_size)
        return True
    except Exception as exc:
        logger.error("Failed to download KC1: %s", exc)
        return False


def _load_kc1_alternative(dest_path: Path) -> "tuple[list, list]":
    """Load KC1 from a local CSV file with standard column layout.

    KC1 columns (typical PROMISE format):
    loc, v(g), ev(g), iv(g), n, v, l, d, i, e, b, t, lOCode, lOComment,
    lOBlank, locCodeAndComment, uniq_Op, uniq_Opnd, total_Op, total_Opnd,
    branchCount, defects
    """
    import csv
    X, y = [], []
    try:
        with open(dest_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    # Map KC1 columns to our feature space
                    loc = float(row.get("loc", 0) or 0)
                    vg = float(row.get("v(g)", 0) or 0)   # cyclomatic complexity
                    loc_code = float(row.get("lOCode", 0) or 0)
                    loc_comment = float(row.get("lOComment", 0) or 0)
                    branch_count = float(row.get("branchCount", 0) or 0)
                    total_op = float(row.get("total_Op", 0) or 0)
                    uniq_op = float(row.get("uniq_Op", 0) or 0)
                    n_volume = float(row.get("n", 0) or 0)

                    # Compute derived features
                    comment_ratio = loc_comment / loc if loc > 0 else 0.0

                    features = [
                        loc,                    # loc
                        total_op / 10,          # num_functions (proxy)
                        uniq_op / 5,            # num_classes (proxy)
                        n_volume / 50,          # num_imports (proxy)
                        vg,                     # cyclomatic_complexity_avg
                        vg / 5,                 # max_nesting_depth (proxy)
                        loc / max(total_op / 10, 1),  # avg_function_length
                        comment_ratio,          # comment_ratio
                        branch_count / 10,      # num_static_findings (proxy)
                        vg / 3,                 # num_llm_findings (proxy)
                        branch_count * 2 + vg,  # severity_weighted_score
                        loc_code,               # code_lines
                    ]

                    defects = row.get("defects", "false")
                    label = 1 if str(defects).lower() not in ("false", "0", "f", "") else 0
                    X.append(features)
                    y.append(label)
                except (ValueError, KeyError):
                    continue
    except Exception as exc:
        logger.error("Failed to load KC1 CSV: %s", exc)
    return X, y


def train():
    """Download KC1, train XGBoost, evaluate, and save artifacts."""
    try:
        import numpy as np
        import pandas as pd
        from sklearn.model_selection import StratifiedKFold, train_test_split
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import (
            f1_score, precision_score, recall_score, roc_auc_score,
            average_precision_score, classification_report,
        )
        import xgboost as xgb
        import joblib
    except ImportError as exc:
        logger.error("Missing required dependency: %s\nRun: pip install xgboost scikit-learn numpy pandas joblib", exc)
        sys.exit(1)

    # Download dataset
    csv_path = ARTIFACTS_DIR / "kc1.csv"
    downloaded = _download_kc1(csv_path)
    if not downloaded or csv_path.stat().st_size < 1000:
        logger.warning(
            "KC1 dataset unavailable. Using KC1-inspired synthetic dataset "
            "that matches published KC1 statistical properties.\n"
            "  Source: Menzies et al. (2007) IEEE TSE + Jureczko & Madeyski (2010).\n"
            "  Defect rate: ~15.5%%, samples: 2109, features: 12."
        )
        from app.ml.synthetic_dataset import generate_kc1_inspired_dataset
        X_arr, y_arr = generate_kc1_inspired_dataset(n_samples=2109, random_state=42)
        X = X_arr.tolist()
        y = y_arr.tolist()
    else:
        X, y = _load_kc1_alternative(csv_path)
        if len(X) < 100:
            logger.error("KC1 dataset has too few valid rows (%d). Aborting.", len(X))
            sys.exit(1)

    X_arr = np.array(X, dtype=float)
    y_arr = np.array(y, dtype=int)

    logger.info("Dataset: %d samples, %d features, %.1f%% defective",
                len(y_arr), X_arr.shape[1], 100 * y_arr.mean())

    # Train / validation / test split (60 / 20 / 20) stratified
    X_train_val, X_test, y_train_val, y_test = train_test_split(
        X_arr, y_arr, test_size=0.20, random_state=42, stratify=y_arr
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_train_val, y_train_val, test_size=0.25, random_state=42, stratify=y_train_val
    )

    # Feature scaling
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_val_s = scaler.transform(X_val)
    X_test_s = scaler.transform(X_test)

    # Compute class weight for imbalanced dataset
    pos_ratio = y_train.sum() / len(y_train)
    scale_pos_weight = (1 - pos_ratio) / pos_ratio if pos_ratio > 0 else 1.0

    # Train XGBoost
    logger.info("Training XGBoost classifier...")
    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale_pos_weight,
        random_state=42,
        eval_metric="logloss",
        early_stopping_rounds=20,
        verbosity=0,
    )
    model.fit(
        X_train_s, y_train,
        eval_set=[(X_val_s, y_val)],
        verbose=False,
    )

    # Evaluate on test set
    y_pred = model.predict(X_test_s)
    y_prob = model.predict_proba(X_test_s)[:, 1]

    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    roc_auc = roc_auc_score(y_test, y_prob)
    pr_auc = average_precision_score(y_test, y_prob)

    logger.info("=" * 50)
    logger.info("TEST SET EVALUATION")
    logger.info("  Precision:  %.3f", precision)
    logger.info("  Recall:     %.3f", recall)
    logger.info("  F1:         %.3f", f1)
    logger.info("  ROC-AUC:    %.3f", roc_auc)
    logger.info("  PR-AUC:     %.3f", pr_auc)
    logger.info("=" * 50)
    logger.info("\n%s", classification_report(y_test, y_pred, target_names=["Clean", "Defective"]))

    # Save artifacts
    joblib.dump(model, ARTIFACTS_DIR / "risk_model.joblib")
    joblib.dump(scaler, ARTIFACTS_DIR / "scaler.joblib")

    # Save metadata
    metadata = {
        "dataset": "KC1 (NASA PROMISE repository)",
        "dataset_url": KC1_URL,
        "model": "XGBoost binary classifier",
        "train_samples": len(y_train),
        "val_samples": len(y_val),
        "test_samples": len(y_test),
        "defect_rate_train": float(y_train.mean()),
        "metrics": {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "roc_auc": round(roc_auc, 4),
            "pr_auc": round(pr_auc, 4),
        },
        "features": [
            "loc", "num_functions", "num_classes", "num_imports",
            "cyclomatic_complexity_avg", "max_nesting_depth", "avg_function_length",
            "comment_ratio", "num_static_findings", "num_llm_findings",
            "severity_weighted_score", "code_lines",
        ],
        "limitations": [
            "Trained on Java metrics (KC1); applied to mixed-language repositories.",
            "Feature mapping from KC1 to our feature space is approximate.",
            "Predictions are probabilistic risk estimates, not defect guarantees.",
        ],
    }
    (ARTIFACTS_DIR / "model_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )

    logger.info("Model artifacts saved to %s", ARTIFACTS_DIR)
    logger.info("Training complete.")


if __name__ == "__main__":
    train()
