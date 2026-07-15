"""Evaluation script: compute precision/recall/F1 and ROC curve."""
import json
import csv
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import (
    precision_recall_curve,
    roc_curve,
    auc,
    f1_score,
    precision_score,
    recall_score,
    confusion_matrix,
)

# Handle imports
try:
    from src.detectors import compute_all_scores
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from src.detectors import compute_all_scores


def load_conversations(data_dir: str = "data") -> List[Dict]:
    """Load conversations from JSONL file."""
    conversations = []
    path = Path(data_dir) / "conversations.jsonl"

    with open(path, "r") as f:
        for line in f:
            conversations.append(json.loads(line))

    return conversations


def load_labels(data_dir: str = "data") -> Dict[str, int]:
    """Load ground-truth labels from CSV."""
    labels = {}
    path = Path(data_dir) / "labels.csv"

    with open(path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            labels[row["id"]] = int(row["is_drifted"])

    return labels


def score_all_conversations(conversations: List[Dict]) -> Dict[str, Dict]:
    """Score all conversations with all detectors."""
    scores = {}

    for i, conv in enumerate(conversations):
        if (i + 1) % 100 == 0:
            print(f"Scored {i + 1}/{len(conversations)}...")

        all_scores = compute_all_scores(conv)
        scores[conv["id"]] = all_scores

    return scores


def compute_metrics_at_threshold(
    y_true: np.ndarray,
    y_scores: np.ndarray,
    threshold: float,
) -> Dict[str, float]:
    """Compute precision, recall, F1 at a specific threshold."""
    y_pred = (y_scores >= threshold).astype(int)

    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()

    return {
        "threshold": threshold,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn),
    }


def evaluate(data_dir: str = "data", output_dir: str = "evaluation_results"):
    """
    Run full evaluation: precision/recall/F1 table and ROC curve.

    Outputs:
    - metrics_table.csv: Precision/recall/F1 at different thresholds
    - roc_curve.png: ROC curve with AUC
    - best_threshold.txt: Recommended operating threshold
    - evaluation_summary.json: Full results
    """
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    print("Loading conversations and labels...")
    conversations = load_conversations(data_dir)
    labels = load_labels(data_dir)

    print(f"Loaded {len(conversations)} conversations")

    print("Computing detector scores...")
    scores = score_all_conversations(conversations)

    # Prepare data
    conv_ids = list(scores.keys())
    y_true = np.array([labels[cid] for cid in conv_ids])
    semantic_scores = np.array([scores[cid]["semantic_drift"] for cid in conv_ids])
    rolling_scores = np.array([scores[cid]["rolling_window_drift"] for cid in conv_ids])
    anomaly_scores = np.array([scores[cid]["response_anomaly"] for cid in conv_ids])
    ensemble_scores = np.array([scores[cid]["ensemble_score"] for cid in conv_ids])

    print(f"\nGround truth distribution: {y_true.sum()} drifted, {len(y_true) - y_true.sum()} coherent")

    # Evaluate each detector
    detectors = {
        "semantic_drift": semantic_scores,
        "rolling_window_drift": rolling_scores,
        "response_anomaly": anomaly_scores,
        "ensemble": ensemble_scores,
    }

    results = {}
    best_f1s = {}

    for detector_name, detector_scores in detectors.items():
        print(f"\n{'='*60}")
        print(f"Evaluating: {detector_name}")
        print(f"{'='*60}")

        # Compute metrics at various thresholds
        thresholds = np.linspace(0, 1, 21)
        metrics_at_threshold = [
            compute_metrics_at_threshold(y_true, detector_scores, t)
            for t in thresholds
        ]

        # Find best F1
        best_idx = np.argmax([m["f1"] for m in metrics_at_threshold])
        best_threshold = metrics_at_threshold[best_idx]["threshold"]
        best_f1 = metrics_at_threshold[best_idx]["f1"]

        best_f1s[detector_name] = (best_threshold, best_f1)

        # Print table
        print(f"\n{'Threshold':<12} {'Precision':<12} {'Recall':<12} {'F1':<12} {'TP':<6} {'FP':<6} {'FN':<6}")
        print("-" * 72)
        for m in metrics_at_threshold:
            marker = " <-- BEST" if m["threshold"] == best_threshold else ""
            print(
                f"{m['threshold']:<12.2f} "
                f"{m['precision']:<12.3f} "
                f"{m['recall']:<12.3f} "
                f"{m['f1']:<12.3f} "
                f"{m['tp']:<6} "
                f"{m['fp']:<6} "
                f"{m['fn']:<6}"
                f"{marker}"
            )

        # Compute ROC curve
        fpr, tpr, roc_thresholds = roc_curve(y_true, detector_scores)
        roc_auc = auc(fpr, tpr)

        # Compute PR curve
        precision, recall, pr_thresholds = precision_recall_curve(y_true, detector_scores)
        pr_auc = auc(recall, precision)

        results[detector_name] = {
            "metrics_at_threshold": metrics_at_threshold,
            "best_threshold": best_threshold,
            "best_f1": best_f1,
            "roc_auc": roc_auc,
            "pr_auc": pr_auc,
            "fpr": fpr.tolist(),
            "tpr": tpr.tolist(),
            "precision": precision.tolist(),
            "recall": recall.tolist(),
        }

        print(f"\nROC AUC: {roc_auc:.3f}")
        print(f"PR AUC: {pr_auc:.3f}")
        print(f"Best threshold: {best_threshold:.2f} (F1={best_f1:.3f})")

    # Save results
    print(f"\n{'='*60}")
    print("Saving results...")
    print(f"{'='*60}")

    # Save metrics table
    all_metrics = []
    for detector_name, metrics_list in [
        ("semantic_drift", results["semantic_drift"]["metrics_at_threshold"]),
        ("rolling_window_drift", results["rolling_window_drift"]["metrics_at_threshold"]),
        ("response_anomaly", results["response_anomaly"]["metrics_at_threshold"]),
        ("ensemble", results["ensemble"]["metrics_at_threshold"]),
    ]:
        for m in metrics_list:
            m["detector"] = detector_name
            all_metrics.append(m)

    metrics_df = pd.DataFrame(all_metrics)
    metrics_path = output_path / "metrics_table.csv"
    metrics_df.to_csv(metrics_path, index=False)
    print(f"Metrics table: {metrics_path}")

    # Save ROC/PR curves
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    fig.suptitle("Drift Detection Evaluation", fontsize=16)

    for idx, (detector_name, detector_results) in enumerate(results.items()):
        ax = axes[idx // 2, idx % 2]

        # Plot ROC curve
        ax.plot(
            detector_results["fpr"],
            detector_results["tpr"],
            label=f"ROC (AUC={detector_results['roc_auc']:.3f})",
            linewidth=2,
            color="blue",
        )

        # Plot PR curve
        ax2 = ax.twinx()
        ax2.plot(
            detector_results["recall"],
            detector_results["precision"],
            label=f"PR (AUC={detector_results['pr_auc']:.3f})",
            linewidth=2,
            color="orange",
        )

        ax.plot([0, 1], [0, 1], "k--", alpha=0.3, label="Random")

        ax.set_xlabel("FPR (ROC) / Recall (PR)", fontsize=10)
        ax.set_ylabel("TPR (ROC)", fontsize=10, color="blue")
        ax2.set_ylabel("Precision (PR)", fontsize=10, color="orange")
        ax.set_title(f"{detector_name.replace('_', ' ').title()}", fontsize=12, fontweight="bold")
        ax.legend(loc="lower right", fontsize=9)
        ax2.legend(loc="upper right", fontsize=9)
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    roc_path = output_path / "roc_curves.png"
    plt.savefig(roc_path, dpi=150)
    print(f"ROC/PR curves: {roc_path}")
    plt.close()

    # Save best thresholds
    thresholds_path = output_path / "best_thresholds.txt"
    with open(thresholds_path, "w") as f:
        f.write("Recommended Operating Thresholds (from ROC curve analysis)\n")
        f.write("=" * 60 + "\n\n")
        for detector_name, (threshold, f1) in best_f1s.items():
            f.write(f"{detector_name:<25} threshold={threshold:.2f}  F1={f1:.3f}\n")
        f.write("\n\nRecommendation: Use ensemble detector with threshold=0.50\n")

    print(f"Best thresholds: {thresholds_path}")

    # Save full results
    summary_path = output_path / "evaluation_summary.json"
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Full results: {summary_path}")

    print(f"\n{'='*60}")
    print("Evaluation complete!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data", help="Directory with conversations.jsonl and labels.csv")
    parser.add_argument("--output-dir", default="evaluation_results", help="Output directory for results")
    args = parser.parse_args()

    evaluate(args.data_dir, args.output_dir)
