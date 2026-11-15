"""Training script for AlgoRevive ML Recommendation Engine.

Trains RandomForestClassifier and XGBClassifier on empirical dataset,
evaluates Accuracy, Macro Precision, Recall, Macro F1, Top-3 Accuracy, and MRR,
selects the best model by Macro F1, and saves artifacts and docs/ML_REPORT.md.

Repeatable with: docker compose exec backend python -m ml.train
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    precision_recall_fscore_support,
    top_k_accuracy_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier

FEATURE_COLUMNS = [
    "input_size_log10",
    "current_algorithm_code",
    "current_complexity_rank",
    "lookup_freq_level",
    "insert_ratio",
    "delete_ratio",
    "read_write_ratio",
    "data_distribution_code",
    "memory_constraint_level",
    "latency_requirement_level",
    "call_count_log10",
    "runtime_pct",
]


def compute_mrr(y_true_indices: np.ndarray, y_proba: np.ndarray) -> float:
    """Compute Mean Reciprocal Rank (MRR) over all samples."""
    ranks: List[float] = []
    for true_idx, probas in zip(y_true_indices, y_proba):
        # Sort indices by probability descending
        ranked_indices = np.argsort(probas)[::-1]
        rank_positions = np.where(ranked_indices == true_idx)[0]
        if len(rank_positions) > 0:
            rank = rank_positions[0] + 1
            ranks.append(1.0 / rank)
        else:
            ranks.append(0.0)
    return float(np.mean(ranks)) if ranks else 0.0


def evaluate_model(
    name: str,
    model: Any,
    X_test: pd.DataFrame,
    y_test_labels: np.ndarray,
    classes: List[str],
    label_encoder: LabelEncoder | None = None,
) -> Tuple[Dict[str, float], np.ndarray, np.ndarray]:
    """Compute all required metrics on the held-out test split."""
    if label_encoder is not None:
        y_test_encoded = label_encoder.transform(y_test_labels)
        y_pred_encoded = model.predict(X_test)
        y_pred_labels = label_encoder.inverse_transform(y_pred_encoded)
        y_proba = model.predict_proba(X_test)
        true_indices = y_test_encoded
    else:
        y_pred_labels = model.predict(X_test)
        y_proba = model.predict_proba(X_test)
        class_to_idx = {c: i for i, c in enumerate(classes)}
        true_indices = np.array([class_to_idx[lbl] for lbl in y_test_labels])

    acc = float(accuracy_score(y_test_labels, y_pred_labels))
    prec, rec, f1, _ = precision_recall_fscore_support(
        y_test_labels, y_pred_labels, average="macro", zero_division=0
    )

    # Top-3 Accuracy
    k = min(3, len(classes))
    top3 = float(top_k_accuracy_score(true_indices, y_proba, k=k, labels=list(range(len(classes)))))

    # MRR
    mrr = compute_mrr(true_indices, y_proba)

    metrics = {
        "accuracy": round(acc, 5),
        "macro_precision": round(float(prec), 5),
        "macro_recall": round(float(rec), 5),
        "macro_f1": round(float(f1), 5),
        "top_3_accuracy": round(top3, 5),
        "mrr": round(mrr, 5),
    }

    print(f"\n--- {name} Metrics ---")
    for k_m, v_m in metrics.items():
        print(f"  {k_m}: {v_m}")

    return metrics, y_pred_labels, y_proba


def get_lib_version(pkg_name: str) -> str:
    try:
        return importlib.metadata.version(pkg_name)
    except Exception:
        return "unknown"


def generate_ml_report(
    rf_metrics: Dict[str, float],
    xgb_metrics: Dict[str, float],
    best_name: str,
    classes: List[str],
    importances: Dict[str, float],
    report_text: str,
    output_path: Path,
) -> None:
    """Write ML evaluation report to docs/ML_REPORT.md."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    content = f"""# ML Recommendation Engine - Training & Evaluation Report

**Generated:** {now_str}  
**Selected Best Model:** `{best_name}` (selected by highest Macro F1)

---

## 1. Executive Summary & Metric Comparison

Both models were trained on the empirical dataset using stratified train/test split (80/20) with fixed random seed 42.

| Metric | RandomForestClassifier | XGBClassifier | Selected (`{best_name}`) |
|---|---|---|---|
| **Accuracy** | {rf_metrics["accuracy"]:.4f} | {xgb_metrics["accuracy"]:.4f} | {max(rf_metrics["accuracy"], xgb_metrics["accuracy"]):.4f} |
| **Macro Precision** | {rf_metrics["macro_precision"]:.4f} | {xgb_metrics["macro_precision"]:.4f} | {max(rf_metrics["macro_precision"], xgb_metrics["macro_precision"]):.4f} |
| **Macro Recall** | {rf_metrics["macro_recall"]:.4f} | {xgb_metrics["macro_recall"]:.4f} | {max(rf_metrics["macro_recall"], xgb_metrics["macro_recall"]):.4f} |
| **Macro F1 (Key)** | **{rf_metrics["macro_f1"]:.4f}** | **{xgb_metrics["macro_f1"]:.4f}** | **{max(rf_metrics["macro_f1"], xgb_metrics["macro_f1"]):.4f}** |
| **Top-3 Accuracy** | {rf_metrics["top_3_accuracy"]:.4f} | {xgb_metrics["top_3_accuracy"]:.4f} | {max(rf_metrics["top_3_accuracy"], xgb_metrics["top_3_accuracy"]):.4f} |
| **MRR (Mean Reciprocal Rank)** | {rf_metrics["mrr"]:.4f} | {xgb_metrics["mrr"]:.4f} | {max(rf_metrics["mrr"], xgb_metrics["mrr"]):.4f} |

---

## 2. Feature Importances (Ranked)

| Rank | Feature | Importance | Description |
|---|---|---|---|
"""
    sorted_imp = sorted(importances.items(), key=lambda x: x[1], reverse=True)
    for idx, (feat, val) in enumerate(sorted_imp, 1):
        content += f"| {idx} | `{feat}` | {val:.4f} | 12-dim FeatureVector field |\n"

    content += f"""
---

## 3. Detailed Classification Report (Selected Model)

```text
{report_text}
```

---

## 4. Model Artifact Details
- **Path:** `backend/ml/models/recommender.joblib`
- **Metadata:** `backend/ml/models/metadata.json`
- **Target Classes ({len(classes)}):** {", ".join(f"`{c}`" for c in classes)}
- **Feature Vector Dimension:** 12 numeric features
- **Fallback Guarantee:** Deterministic rule-based engine when model artifact is missing or low-confidence (< 0.50).
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")
    print(f"Wrote ML report to {output_path}")


def train_models(
    data_path: Path,
    models_dir: Path,
    docs_dir: Path,
    seed: int = 42,
) -> None:
    """Execute complete training and evaluation pipeline."""
    print(f"Loading empirical dataset from {data_path}...")
    if not data_path.exists():
        raise FileNotFoundError(f"Dataset not found at {data_path}. Run generate_dataset.py first.")

    df = pd.read_csv(data_path)
    X = df[FEATURE_COLUMNS]
    y = df["label"]

    classes = sorted(list(y.unique()))
    print(f"Dataset size: {len(df)} samples across {len(classes)} classes: {classes}")

    # Stratified train/test split (80/20)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=seed, stratify=y
    )
    print(f"Train set: {len(X_train)} samples, Test set: {len(X_test)} samples")

    # 1. Train RandomForestClassifier
    print("\nTraining RandomForestClassifier...")
    rf = RandomForestClassifier(n_estimators=100, random_state=seed, n_jobs=-1)
    rf.fit(X_train, y_train)
    rf_metrics, rf_preds, _ = evaluate_model(
        "RandomForestClassifier", rf, X_test, y_test.values, classes
    )

    # 2. Train XGBClassifier
    print("\nTraining XGBClassifier...")
    le = LabelEncoder()
    le.fit(classes)
    y_train_encoded = le.transform(y_train)

    xgb = XGBClassifier(
        n_estimators=100,
        random_state=seed,
        eval_metric="mlogloss",
        n_jobs=-1,
    )
    xgb.fit(X_train, y_train_encoded)
    xgb_metrics, xgb_preds, _ = evaluate_model(
        "XGBClassifier", xgb, X_test, y_test.values, classes, label_encoder=le
    )

    # 3. Pick best model by macro F1
    if xgb_metrics["macro_f1"] > rf_metrics["macro_f1"]:
        best_name = "XGBClassifier"
        best_estimator = xgb
        best_metrics = xgb_metrics
        best_preds = xgb_preds
        raw_importances = xgb.feature_importances_
    else:
        best_name = "RandomForestClassifier"
        best_estimator = rf
        best_metrics = rf_metrics
        best_preds = rf_preds
        raw_importances = rf.feature_importances_

    print(f"\nBest model selected: {best_name} (Macro F1: {best_metrics['macro_f1']})")

    # Ensure Macro F1 >= 0.75
    assert best_metrics["macro_f1"] >= 0.75, (
        f"Macro F1 {best_metrics['macro_f1']} is below requirement 0.75"
    )

    # Save model artifact as clean, robust dictionary
    models_dir.mkdir(parents=True, exist_ok=True)
    model_artifact_path = models_dir / "recommender.joblib"
    artifact = {
        "model": best_estimator,
        "best_name": best_name,
        "classes": list(classes),
        "feature_names": FEATURE_COLUMNS,
        "label_encoder": le,
    }
    joblib.dump(artifact, model_artifact_path)
    print(f"Saved recommender artifact to {model_artifact_path}")

    # Calculate feature means and stds for explainability fallback
    feature_means = {col: float(X_train[col].mean()) for col in FEATURE_COLUMNS}
    feature_stds = {col: float(max(1e-6, X_train[col].std())) for col in FEATURE_COLUMNS}
    feature_importances = {
        col: float(round(raw_importances[i], 5))
        for i, col in enumerate(FEATURE_COLUMNS)
    }

    # Save metadata.json
    metadata = {
        "best_model": best_name,
        "feature_order": FEATURE_COLUMNS,
        "classes": classes,
        "feature_means": feature_means,
        "feature_stds": feature_stds,
        "feature_importances": feature_importances,
        "metrics": {
            "random_forest": rf_metrics,
            "xgboost": xgb_metrics,
            "best": best_metrics,
        },
        "library_versions": {
            "python": sys.version.split()[0],
            "scikit-learn": get_lib_version("scikit-learn"),
            "xgboost": get_lib_version("xgboost"),
            "joblib": get_lib_version("joblib"),
            "pandas": get_lib_version("pandas"),
            "numpy": get_lib_version("numpy"),
        },
        "seed": seed,
        "training_date": datetime.now(timezone.utc).isoformat(),
    }

    metadata_path = models_dir / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    print(f"Saved metadata to {metadata_path}")

    # Generate ML report
    report_text = classification_report(y_test, best_preds, zero_division=0)
    report_path = docs_dir / "ML_REPORT.md"
    generate_ml_report(
        rf_metrics=rf_metrics,
        xgb_metrics=xgb_metrics,
        best_name=best_name,
        classes=classes,
        importances=feature_importances,
        report_text=report_text,
        output_path=report_path,
    )


def main():
    parser = argparse.ArgumentParser(description="Train ML Recommendation Engine.")
    parser.add_argument("--seed", type=int, default=42, help="Fixed random seed")
    args = parser.parse_args()

    ml_dir = Path(__file__).resolve().parent
    data_path = ml_dir / "data" / "dataset.csv"
    models_dir = ml_dir / "models"

    # Find docs directory
    if (ml_dir.parent / "docs").exists():
        docs_dir = ml_dir.parent / "docs"
    elif (ml_dir.parent.parent / "docs").exists():
        docs_dir = ml_dir.parent.parent / "docs"
    else:
        docs_dir = ml_dir.parent.parent / "docs"

    train_models(
        data_path=data_path,
        models_dir=models_dir,
        docs_dir=docs_dir,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
