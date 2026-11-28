"""Fit and evaluate an event-time model against sealed synthetic snapshots."""

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import version as package_version
import json
from pathlib import Path
from time import perf_counter

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score, brier_score_loss, confusion_matrix, f1_score,
    precision_score, recall_score, roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_sample_weight
from threadpoolctl import threadpool_limits

from app.dataset_manifest import canonical_json, file_sha256, iter_records, load_manifest
from app.ml import FEATURES, FEATURE_VERSION, FeatureState, track_training_run

TRAINING_ROWS_MIN = 100_001
CLASSIFIERS = ("LogisticRegression", "RandomForestClassifier", "HistGradientBoostingClassifier")


@dataclass
class PreparedRows:
    frame: pd.DataFrame
    outcomes: np.ndarray
    partitions: dict[str, np.ndarray]
    times: list[datetime]
    label_times: list[datetime]
    scenarios: np.ndarray
    episodes: np.ndarray
    subscribers: set[str]
    event_ids: set[str]


def prepare_rows(path: Path, manifest: dict) -> PreparedRows:
    """Build features from event payload only, in the same order as serving."""
    state = FeatureState()
    frames, chunk, labels, times, label_times, scenarios, episodes = [], [], [], [], [], [], []
    subscribers, event_ids = set(), set()
    partition_rows = defaultdict(list)
    for index, (split, record) in enumerate(iter_records(path, manifest)):
        event, outcome = record.event, record.outcome
        input_row = event.model_dump(exclude={"contract_version", "fraud_label", "scenario_label"})
        chunk.append(input_row)
        labels.append(outcome.label)
        times.append(event.event_time)
        label_times.append(outcome.available_at)
        scenarios.append(outcome.scenario)
        episodes.append(outcome.episode_id)
        subscribers.add(event.subscriber_id)
        event_ids.add(event.event_id)
        partition_rows[split].append(index)
        if len(chunk) == 2_000:
            frames.append(state.transform(chunk))
            chunk = []
    if chunk:
        frames.append(state.transform(chunk))
    if {name: len(rows) for name, rows in partition_rows.items()} != {
        name: summary["rows"] for name, summary in manifest["splits"].items()
    }:
        raise ValueError("feature input does not match manifest split counts")
    return PreparedRows(
        pd.concat(frames, ignore_index=True), np.asarray(labels, dtype=np.uint8),
        {name: np.asarray(rows) for name, rows in partition_rows.items()},
        times, label_times, np.asarray(scenarios), np.asarray(episodes, dtype=object),
        subscribers, event_ids,
    )


def _eligible(development: PreparedRows, name: str, before: str, minimum: int) -> np.ndarray:
    cutoff = development.times[development.partitions[before][0]]
    indexes = np.asarray(
        [idx for idx in development.partitions[name] if development.label_times[idx] < cutoff],
        dtype=np.int64,
    )
    if len(indexes) < minimum or np.unique(development.outcomes[indexes]).size != 2:
        raise ValueError(f"insufficient eligible labels in {name} before the {before} boundary")
    return indexes


def _fit_partition_evidence(data: PreparedRows, name: str, before: str, indexes: np.ndarray) -> dict:
    digest = sha256(canonical_json(indexes.tolist())).hexdigest()
    return {
        "eligible_rows": len(indexes),
        "excluded_for_label_delay": len(data.partitions[name]) - len(indexes),
        "label_cutoff_exclusive": data.times[data.partitions[before][0]].isoformat(),
        "eligible_manifest_positions_sha256": digest,
    }


def _models() -> dict:
    return {
        CLASSIFIERS[0]: make_pipeline(
            StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=600, random_state=17),
        ),
        CLASSIFIERS[1]: RandomForestClassifier(
            n_estimators=80, max_depth=8, class_weight="balanced", n_jobs=2, random_state=17,
        ),
        CLASSIFIERS[2]: HistGradientBoostingClassifier(
            max_iter=110, max_leaf_nodes=15, l2_regularization=1.0, random_state=29,
        ),
    }


def select_threshold(labels: np.ndarray, probabilities: np.ndarray) -> float:
    """Freeze the highest-F1 validation cut among candidates with at most 5% FPR."""
    if np.unique(labels).size != 2:
        raise ValueError("threshold selection needs both observed classes")
    best = (-1.0, -1.0, -1.0)
    for threshold in np.append(np.linspace(0.001, 0.999, 201), 1.0):
        predicted = probabilities >= threshold
        fpr = predicted[labels == 0].mean()
        if fpr <= 0.05:
            best = max(best, (float(f1_score(labels, predicted, zero_division=0)), -float(fpr), threshold))
    if best[0] < 0:
        raise ValueError("no bounded threshold satisfies the validation false-positive budget")
    return float(best[2])


def _reliability(labels: np.ndarray, scores: np.ndarray) -> list[dict]:
    bins = np.minimum((scores * 10).astype(int), 9)
    return [
        {
            "bin": index, "rows": int(samples.sum()),
            "mean_score": float(scores[samples].mean()) if samples.any() else None,
            "observed_rate": float(labels[samples].mean()) if samples.any() else None,
        }
        for index in range(10)
        for samples in (bins == index,)
    ]


def measure(labels: np.ndarray, scores: np.ndarray, threshold: float, episodes: np.ndarray) -> dict:
    dec = scores >= threshold
    tn, fp, fn, tp = (int(value) for value in confusion_matrix(labels, dec, labels=[0, 1]).ravel())
    positives, negatives = tp + fn, fp + tn
    all_episodes = {episode for episode in episodes if episode is not None}
    caught_episodes = {episode for episode in episodes[dec] if episode is not None}
    review_count = min(200, len(labels))
    best = np.argsort(-scores, kind="stable")[:review_count]
    return {
        "rows": len(labels), "positive_events": positives, "negative_events": negatives,
        "pr_auc": float(average_precision_score(labels, scores)) if positives and negatives else None,
        "roc_auc": float(roc_auc_score(labels, scores)) if positives and negatives else None,
        "precision": float(precision_score(labels, dec, zero_division=0)) if tp + fp else None,
        "recall": float(recall_score(labels, dec, zero_division=0)) if positives else None,
        "f1": float(f1_score(labels, dec, zero_division=0)) if positives else None,
        "false_positive_rate": fp / negatives if negatives else None,
        "brier_score": float(brier_score_loss(labels, scores, pos_label=1)),
        "confusion_matrix": [[tn, fp], [fn, tp]], "threshold": threshold,
        "fraud_episodes": len(all_episodes), "episodes_detected": len(caught_episodes),
        "episode_recall": len(caught_episodes) / len(all_episodes) if all_episodes else None,
        "review_budget": review_count,
        "precision_at_review_budget": float(labels[best].mean()) if review_count else None,
        "alerts_per_1000_events": float(dec.mean() * 1000),
    }


def _timed_probabilities(model, frame: pd.DataFrame) -> tuple[np.ndarray, dict]:
    predictions, durations = [], []
    for start in range(0, len(frame), 2_000):
        chunk = frame.iloc[start:start + 2_000]
        tick = perf_counter()
        scores = model.predict_proba(chunk)[:, 1]
        elapsed = perf_counter() - tick
        durations.append((elapsed, len(chunk)))
        predictions.append(scores)
    micros_per_row = [duration * 1_000_000 / count for duration, count in durations]
    return np.concatenate(predictions), {
        "classifier_throughput_rows_per_second": len(frame) / max(sum(d for d, _ in durations), 1e-9),
        "classifier_chunk_row_us_p50": float(np.quantile(micros_per_row, 0.50)),
        "classifier_chunk_row_us_p95": float(np.quantile(micros_per_row, 0.95)),
        "chunk_averages_are_not_request_latency": True,
    }


def _assessment(model, data: PreparedRows, indexes: np.ndarray, threshold: float) -> dict:
    scores, timing = _timed_probabilities(model, data.frame.iloc[indexes])
    labels, scenarios, episodes = data.outcomes[indexes], data.scenarios[indexes], data.episodes[indexes]
    return {
        **measure(labels, scores, threshold, episodes),
        **timing,
        "realized_prevalence": float(labels.mean()),
        "score_reliability": _reliability(labels, scores),
        "by_scenario": {
            scenario: measure(labels[mask], scores[mask], threshold, episodes[mask])
            for scenario in sorted(set(scenarios))
            for mask in (scenarios == scenario,)
        },
    }


def _sigmoid_diagnostic(model, data, calibration_indexes, selection_indexes) -> dict:
    cal_frame = data.frame.iloc[calibration_indexes]
    selection_frame = data.frame.iloc[selection_indexes]
    calibration = model.predict_proba(cal_frame)[:, 1]
    selection = model.predict_proba(selection_frame)[:, 1]
    sigmoid = LogisticRegression(random_state=17)
    sigmoid.fit(calibration.reshape(-1, 1), data.outcomes[calibration_indexes])
    adjusted = sigmoid.predict_proba(selection.reshape(-1, 1))[:, 1]
    return {
        "native_brier": float(brier_score_loss(data.outcomes[selection_indexes], selection)),
        "diagnostic_sigmoid_brier": float(brier_score_loss(data.outcomes[selection_indexes], adjusted)),
        "calibration_rows": len(calibration_indexes),
        "serving_policy": "native probabilities; no unmatched calibration transform in serving",
    }


def run_experiment(
    development: Path, evaluation: dict[str, Path], output: Path, *, min_training_rows: int = TRAINING_ROWS_MIN
) -> dict:
    """Train a candidate without changing the application's active release."""
    manifest = load_manifest(development, verify_parts=True)
    if manifest["config"]["role"] != "development":
        raise ValueError("development snapshot must specify training, calibration, selection and test")
    if not evaluation:
        raise ValueError("a sealed independent evaluation snapshot is required")
    if manifest["splits"]["training"]["rows"] < min_training_rows:
        raise ValueError(f"expected at least {min_training_rows:,} unique training records")
    data = prepare_rows(development, manifest)
    training = _eligible(data, "training", "calibration", min_training_rows)
    calibration = _eligible(data, "calibration", "selection", 20)
    selection = _eligible(data, "selection", "test", 20)
    test = data.partitions["test"]
    models = _models()
    validation, comparison = {}, {}
    for name, model in models.items():
        started = perf_counter()
        with threadpool_limits(limits=2):
            fit_args = (
                {"sample_weight": compute_sample_weight("balanced", data.outcomes[training])}
                if name == CLASSIFIERS[2] else {}
            )
            model.fit(data.frame.iloc[training], data.outcomes[training], **fit_args)
            scores = model.predict_proba(data.frame.iloc[selection])[:, 1]
        threshold = select_threshold(data.outcomes[selection], scores)
        validation[name] = {
            "validation_pr_auc": float(average_precision_score(data.outcomes[selection], scores)),
            "threshold": threshold, "fit_and_selection_seconds": perf_counter() - started,
        }
    name = max(validation, key=lambda algorithm: validation[algorithm]["validation_pr_auc"])
    threshold = validation[name]["threshold"]
    model = models[name]
    with threadpool_limits(limits=2):
        for candidate_name, candidate in models.items():
            comparison[candidate_name] = {
                **validation[candidate_name],
                **_assessment(candidate, data, test, validation[candidate_name]["threshold"]),
            }
        calibration_report = _sigmoid_diagnostic(model, data, calibration, selection)
        benign_training = training[data.outcomes[training] == 0]
        anomaly_detector = IsolationForest(n_estimators=80, contamination="auto", random_state=29)
        anomaly_detector.fit(data.frame.iloc[benign_training])

    development_rate = float(data.outcomes[training].mean())
    test_baseline = measure(
        data.outcomes[test], np.full(len(test), development_rate), threshold, data.episodes[test]
    )
    evaluation_reports, evaluation_digests = {}, {}
    seen_subscribers, seen_events = data.subscribers, data.event_ids
    independent_seen = False
    with threadpool_limits(limits=2):
        for key, path in evaluation.items():
            candidate_manifest = load_manifest(path, verify_parts=True)
            role = candidate_manifest["config"]["role"]
            if role not in {"independent", "drift"}:
                raise ValueError("external assessment requires an independent or drift snapshot")
            if candidate_manifest["config"]["namespace"] == manifest["config"]["namespace"]:
                raise ValueError("assessment and development need disjoint namespaces")
            assessed = prepare_rows(path, candidate_manifest)
            if seen_subscribers.intersection(assessed.subscribers) or seen_events.intersection(assessed.event_ids):
                raise ValueError("evaluation snapshot overlaps previously evaluated subscriber or event IDs")
            if role == "independent":
                held_out = set(candidate_manifest["scenarios"]) - set(manifest["scenarios"])
                if not held_out:
                    raise ValueError("independent assessment must contain unseen scenario variants")
                independent_seen = True
            seen_subscribers.update(assessed.subscribers)
            seen_events.update(assessed.event_ids)
            evaluation_digests[key] = candidate_manifest["manifest_sha256"]
            evaluation_reports[key] = {
                "target_prevalence": candidate_manifest["config"]["prevalence"],
                "version": candidate_manifest["version"], "role": role,
                "partitions": {
                    split: _assessment(model, assessed, indexes, threshold)
                    for split, indexes in assessed.partitions.items()
                },
            }
    if not independent_seen:
        raise ValueError("no independent holdout was assessed")

    version = f"synthetic-v3-{datetime.now(timezone.utc):%Y%m%d%H%M%S%f}"
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    target = (output / f"{version}.joblib").resolve()
    report_path = output / f"{version}-evaluation.json"
    model_input = data.frame.iloc[training].sample(n=min(len(training), 100), random_state=41)
    numeric_test = {
        key: value for key, value in comparison[name].items() if isinstance(value, (int, float))
    }
    metrics = {
        **numeric_test, "model_comparison": comparison,
        "dataset_rows": manifest["count"], "fit_rows": len(training),
        "dataset_version": manifest["version"], "evaluation_threshold": threshold,
        "generator_version": manifest["generator_version"], "source_revision": manifest["source_revision"],
        "evaluation_note": "Synthetic sealed holdouts; no real-world performance claim.",
        "by_scenario": comparison[name]["by_scenario"],
    }
    joblib.dump(
        {
            "model": model, "anomaly_detector": anomaly_detector, "features": FEATURES,
            "feature_version": FEATURE_VERSION, "version": version, "algorithm": name,
            "classification_threshold": threshold, "metrics": metrics,
            "explain_background": model_input.to_numpy(), "explain_background_feature_version": FEATURE_VERSION,
            "artifact_path": str(target), "dataset_manifest_sha256": manifest["manifest_sha256"],
        },
        target,
    )
    digest = file_sha256(target)
    report = {
        "algorithm": name, "candidate_version": version, "artifact_sha256": digest,
        "research_only": True, "meets_training_volume": len(training) >= TRAINING_ROWS_MIN,
        "evaluation_method": {
            "pr_auc": "scikit-learn average precision across recall increments",
            "roc_auc": "scikit-learn ROC AUC from native classifier scores",
            "classifier_threshold": "maximum validation F1 on the bounded grid at ≤5% validation FPR",
            "candidate_selection": "highest validation average precision; no evaluation-data refit",
        },
        "data": {
            "development": manifest["version"], "manifest_sha256": manifest["manifest_sha256"],
            "split_assignments": manifest["splits"], "training_labeled_rows": len(training),
            "calibration_labeled_rows": len(calibration), "selection_labeled_rows": len(selection), "test_rows": len(test),
            "evaluation_digests": evaluation_digests, "source_revision": manifest["source_revision"],
            "eligible_partitions": {
                "training": _fit_partition_evidence(data, "training", "calibration", training),
                "calibration": _fit_partition_evidence(data, "calibration", "selection", calibration),
                "selection": _fit_partition_evidence(data, "selection", "test", selection),
            },
        },
        "metrics": metrics, "baseline_constant_test": test_baseline,
        "native_vs_sigmoid_validation": calibration_report, "sealed_assessment": evaluation_reports,
        "features": FEATURES, "feature_version": FEATURE_VERSION,
        "classifiers": {name: str(candidate) for name, candidate in models.items()},
        "versions": {package: package_version(package) for package in ("numpy", "pandas", "scikit-learn", "joblib")},
    }
    report_path.write_bytes(canonical_json(report))
    return {
        "version": version, "algorithm": name, "dataset_version": manifest["version"],
        "classification_threshold": threshold, "metrics": metrics,
        "artifact_path": str(target), "artifact_sha256": digest,
        "report_path": str(report_path.resolve()), "report_sha256": file_sha256(report_path),
        "independent_assessments": len(evaluation_reports), "published": False,
    }


def publish_experiment(result: dict) -> str:
    """Track validated artifact and preserve the evaluation report on the same run."""
    from mlflow import MlflowClient

    if file_sha256(Path(result["artifact_path"])) != result["artifact_sha256"]:
        raise ValueError("trained artifact changed after evaluation")
    if file_sha256(Path(result["report_path"])) != result["report_sha256"]:
        raise ValueError("evaluation report changed after evaluation")
    run_id = track_training_run(result)
    client = MlflowClient()
    client.log_artifact(run_id, result["report_path"], artifact_path="evaluation")
    client.set_tag(run_id, "teleguard.artifact_sha256", result["artifact_sha256"])
    client.set_tag(run_id, "teleguard.report_sha256", result["report_sha256"])
    return run_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development", type=Path, required=True)
    parser.add_argument("--evaluation", action="append", required=True, metavar="NAME=MANIFEST")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--small", action="store_true", help="allow reduced test data for smoke evaluation")
    parser.add_argument("--track", action="store_true", help="publish using the configured local MLflow service")
    args = parser.parse_args()
    evaluation = {}
    for value in args.evaluation:
        name, sep, path = value.partition("=")
        if not name or not sep or not path or name in evaluation:
            parser.error("each --evaluation must be a unique NAME=MANIFEST")
        evaluation[name] = Path(path)
    result = run_experiment(
        args.development, evaluation, args.output, min_training_rows=100 if args.small else TRAINING_ROWS_MIN
    )
    summary = {key: value for key, value in result.items() if key != "metrics"}
    summary["fit_rows"] = result["metrics"]["fit_rows"]
    summary["development_test_pr_auc"] = result["metrics"].get("pr_auc")
    if args.track:
        summary["mlflow_run_id"] = publish_experiment(result)
        summary["published"] = True
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
