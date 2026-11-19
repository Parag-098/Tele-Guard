from pathlib import Path
from datetime import datetime, timezone
from collections import deque
from time import perf_counter
import joblib
import numpy as np
import pandas as pd
import networkx as nx
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier, IsolationForest
from sklearn.linear_model import LogisticRegression
from sklearn.utils.class_weight import compute_sample_weight
from sklearn.metrics import (
    average_precision_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
    brier_score_loss,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from app.config import settings
from app.synthetic import generate_events

FEATURES = [
    "duration_seconds",
    "is_call",
    "is_sim_change",
    "is_device_change",
    "device_reuse",
    "network_reuse",
    "event_hour",
    "subscriber_event_count",
    "call_count_1h",
    "unique_contacts_1h",
    "sim_changes_prior",
    "is_outgoing_call",
    "international_call_ratio_24h",
    "roaming_call_ratio_24h",
    "sms_messages_1h",
    "failed_auth_1h",
    "mean_call_duration_24h",
    "hours_since_sim_change",
]
FEATURE_VERSION = "features-v2"


def model_feature_columns(model: dict) -> list[str]:
    columns = model.get("features") or FEATURES
    supported_schemas = (FEATURES[:11], FEATURES)
    if not isinstance(columns, list) or columns not in supported_schemas:
        raise ValueError("Model feature schema is unsupported")
    return columns


def model_feature_version(model: dict) -> str:
    if model.get("feature_version"):
        return model["feature_version"]
    return "features-v1" if model.get("features") != FEATURES else FEATURE_VERSION


def model_input(model: dict, frame: pd.DataFrame) -> pd.DataFrame:
    return frame.loc[:, model_feature_columns(model)]


class FeatureState:
    """Incremental as-of-time feature state shared by batch and online scoring."""

    def __init__(self):
        self.seen_device, self.seen_network, self.event_counts, self.sim_counts = {}, {}, {}, {}
        self.recent = {}
        self.recent_destinations = {}
        self.rolling = {}
        self.last_sim_change = {}

    def transform(self, rows: list[dict]) -> pd.DataFrame:
        output = []
        for row in rows:
            sub = row["subscriber_id"]
            ts = pd.to_datetime(row["event_time"], utc=True)
            ts_seconds = ts.timestamp()
            event_type = row["event_type"]
            duration = row.get("duration_seconds")
            duration = 0.0 if duration is None or pd.isna(duration) else float(duration)
            device_key = (sub, row.get("device_id"))
            network_key = (sub, row.get("network_token"))
            recent = self.recent.setdefault(sub, deque())
            contacts = self.recent_destinations.setdefault(sub, {})
            while recent and ts_seconds - recent[0][0] > 3600:
                _, old_type, old_destination, old_sms, old_auth = recent.popleft()
                if old_type == "CALL":
                    self.rolling[sub]["calls_1h"] -= 1
                if old_sms:
                    self.rolling[sub]["sms_1h"] -= old_sms
                if old_auth:
                    self.rolling[sub]["failed_auth_1h"] -= 1
                if old_destination:
                    contacts[old_destination] -= 1
                    if contacts[old_destination] == 0:
                        del contacts[old_destination]
            roll = self.rolling.setdefault(
                sub,
                {"calls_1h": 0, "sms_1h": 0, "failed_auth_1h": 0, "calls_24h": 0,
                 "intl_24h": 0, "roaming_24h": 0, "duration_24h": 0.0,
                 "duration_calls_24h": 0},
            )
            window = self.recent.setdefault((sub, "24h"), deque())
            while window and ts_seconds - window[0][0] > 86400:
                _, old_type, old_duration, old_intl, old_roaming = window.popleft()
                if old_type == "CALL":
                    roll["calls_24h"] -= 1
                    roll["duration_24h"] -= old_duration
                    roll["duration_calls_24h"] -= 1
                    roll["intl_24h"] -= old_intl
                    roll["roaming_24h"] -= old_roaming
            # First 11 features preserve the previous feature-v1 definition.
            output.append([
                duration,
                float(event_type == "CALL"),
                float(event_type == "SIM_CHANGE"),
                float(event_type == "DEVICE_CHANGE"),
                float(min(self.seen_device.get(device_key, 0), 20)),
                float(min(self.seen_network.get(network_key, 0), 20)),
                float(ts.hour),
                float(min(self.event_counts.get(sub, 0), 500)),
                float(roll["calls_1h"]),
                float(len(contacts)),
                float(self.sim_counts.get(sub, 0)),
                float(event_type == "CALL" and row.get("call_direction") == "outgoing"),
                float(roll["intl_24h"] / max(roll["calls_24h"], 1)),
                float(roll["roaming_24h"] / max(roll["calls_24h"], 1)),
                float(roll["sms_1h"]),
                float(roll["failed_auth_1h"]),
                float(roll["duration_24h"] / max(roll["duration_calls_24h"], 1)),
                float(min(max((ts_seconds - self.last_sim_change[sub]) / 3600, 0), 8760))
                if sub in self.last_sim_change else 8760.0,
            ])
            destination = row.get("destination_token")
            sms_count = int(row.get("message_count") or 0) if event_type in {"SMS", "OTP_REQUEST"} else 0
            failed_auth = int(event_type in {"AUTHENTICATION", "OTP_REQUEST"} and row.get("auth_outcome") == "failed")
            recent.append((ts_seconds, event_type, destination, sms_count, failed_auth))
            if event_type == "CALL":
                roll["calls_1h"] += 1
                roll["calls_24h"] += 1
                roll["duration_24h"] += duration
                roll["duration_calls_24h"] += 1
                roll["intl_24h"] += int(bool(row.get("is_international")))
                roll["roaming_24h"] += int(bool(row.get("is_roaming")))
                window.append((ts_seconds, event_type, duration, int(bool(row.get("is_international"))), int(bool(row.get("is_roaming")))))
            if destination:
                contacts[destination] = contacts.get(destination, 0) + 1
            roll["sms_1h"] += sms_count
            roll["failed_auth_1h"] += failed_auth
            self.seen_device[device_key] = self.seen_device.get(device_key, 0) + 1
            self.seen_network[network_key] = self.seen_network.get(network_key, 0) + 1
            self.event_counts[sub] = self.event_counts.get(sub, 0) + 1
            if event_type == "SIM_CHANGE":
                self.sim_counts[sub] = self.sim_counts.get(sub, 0) + 1
                self.last_sim_change[sub] = ts_seconds
        return pd.DataFrame(output, columns=FEATURES, dtype=float)


def features(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=FEATURES)
    ordered = sorted(enumerate(rows), key=lambda item: (item[1]["event_time"], item[0]))
    state = FeatureState()
    values = state.transform([row for _, row in ordered]).to_numpy()
    result = np.empty_like(values)
    original_indices = np.fromiter((index for index, _ in ordered), dtype=np.int64)
    result[original_indices] = values
    return pd.DataFrame(result, columns=FEATURES, dtype=float)


def train_model(
    path: str | None = None,
    rows: list[dict] | None = None,
    dataset_version: str | None = None,
) -> dict:
    rows = rows or [e.model_dump() for e in generate_events(1400, 2026)]
    X = features(rows)
    y = np.array([r["fraud_label"] for r in rows])
    ordered = np.argsort([r["event_time"] for r in rows])
    train_end = max(1, int(len(ordered) * 0.70))
    validation_end = max(train_end + 1, int(len(ordered) * 0.85))
    validation_end = min(validation_end, len(ordered) - 1)
    tr, val, te = ordered[:train_end], ordered[train_end:validation_end], ordered[validation_end:]
    candidates = {
        "LogisticRegression": make_pipeline(
            StandardScaler(),
            LogisticRegression(class_weight="balanced", max_iter=600, random_state=17),
        ),
        "RandomForestClassifier": RandomForestClassifier(
            n_estimators=120, max_depth=8, class_weight="balanced", random_state=17
        ),
        "HistGradientBoostingClassifier": HistGradientBoostingClassifier(
            max_iter=120, max_leaf_nodes=15, l2_regularization=1.0, random_state=29
        ),
    }
    validation_scores = {}
    sample_weight = compute_sample_weight(class_weight="balanced", y=y[tr])
    for name, candidate in candidates.items():
        if name == "HistGradientBoostingClassifier":
            candidate.fit(X.iloc[tr], y[tr], sample_weight=sample_weight)
        else:
            candidate.fit(X.iloc[tr], y[tr])
        probability = candidate.predict_proba(X.iloc[val])[:, 1]
        validation_scores[name] = float(average_precision_score(y[val], probability))

    algorithm = max(validation_scores, key=validation_scores.get)
    reports = {}
    for name, candidate in candidates.items():
        if name == "HistGradientBoostingClassifier":
            candidate.fit(X.iloc[ordered[:validation_end]], y[ordered[:validation_end]], sample_weight=compute_sample_weight(class_weight="balanced", y=y[ordered[:validation_end]]))
        else:
            candidate.fit(X.iloc[ordered[:validation_end]], y[ordered[:validation_end]])
        started = perf_counter()
        probability = candidate.predict_proba(X.iloc[te])[:, 1]
        inference_elapsed = max(perf_counter() - started, 1e-9)
        predicted = (probability >= 0.5).astype(int)
        tn, fp, fn, tp = confusion_matrix(y[te], predicted, labels=[0, 1]).ravel()
        reports[name] = {
            "precision": float(precision_score(y[te], predicted, zero_division=0)),
            "recall": float(recall_score(y[te], predicted, zero_division=0)),
            "f1": float(f1_score(y[te], predicted, zero_division=0)),
            "pr_auc": float(average_precision_score(y[te], probability)),
            "roc_auc": float(roc_auc_score(y[te], probability)),
            "false_positive_rate": float(fp / max(fp + tn, 1)),
            "brier_score": float(brier_score_loss(y[te], probability)),
            "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
            "validation_pr_auc": validation_scores[name],
            "test_inference_ms_per_row": float(inference_elapsed * 1000 / max(len(te), 1)),
            "test_inference_rows_per_second": float(len(te) / inference_elapsed),
        }
    model = candidates[algorithm]
    version = f"synthetic-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    anomaly_detector = IsolationForest(n_estimators=120, contamination="auto", random_state=29)
    anomaly_detector.fit(X.iloc[tr][y[tr] == 0])
    metrics = {
        **reports[algorithm],
        "algorithm": algorithm,
        "model_comparison": reports,
        "split": "chronological 70/15/15 train/validation/test; selection on validation, final metrics on untouched test",
        "evaluation_note": "Synthetic deterministic holdout; not real-world performance.",
        "evaluation_threshold": 0.5,
        "dataset_rows": len(rows),
        "dataset_version": dataset_version or "synthetic-v2-seed-2026",
        "generator_version": "synthetic-v2",
        "source_revision": __import__("os").getenv("TG_SOURCE_REVISION", "workspace"),
        "by_scenario": {},
    }
    final_probability = model.predict_proba(X.iloc[te])[:, 1]
    final_prediction = (final_probability >= 0.5).astype(int)
    for scenario in sorted({str(rows[i].get("scenario_label") or "unknown") for i in te}):
        mask = np.asarray([str(rows[i].get("scenario_label") or "unknown") == scenario for i in te])
        labels = y[te][mask]
        probabilities = final_probability[mask]
        predictions = final_prediction[mask]
        tn_s, fp_s, fn_s, tp_s = confusion_matrix(labels, predictions, labels=[0, 1]).ravel()
        metrics["by_scenario"][scenario] = {
            "rows": int(mask.sum()),
            "fraud_rows": int(labels.sum()),
            "precision": float(precision_score(labels, predictions, zero_division=0)),
            "recall": float(recall_score(labels, predictions, zero_division=0)),
            "f1": float(f1_score(labels, predictions, zero_division=0)),
            "pr_auc": float(average_precision_score(labels, probabilities)) if len(set(labels)) > 1 else None,
            "false_positive_rate": float(fp_s / max(fp_s + tn_s, 1)),
        }
    if path:
        target = Path(path)
    else:
        base_path = Path(settings.model_path)
        target = base_path.with_name(f"{base_path.stem}-{version}{base_path.suffix}")
    target.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "anomaly_detector": anomaly_detector,
            "features": FEATURES,
            "feature_version": FEATURE_VERSION,
            "version": version,
            "algorithm": algorithm,
            "metrics": metrics,
            "explain_background": X.iloc[tr]
            .sample(n=min(100, len(tr)), random_state=41)
            .to_numpy(),
            "explain_background_feature_version": FEATURE_VERSION,
            "artifact_path": str(target),
        },
        target,
    )
    return {
        "metrics": metrics,
        "artifact_path": str(target),
        "version": version,
        "algorithm": algorithm,
        "dataset_version": dataset_version or "synthetic-v2-seed-2026",
    }


def explain_prediction(model: dict, row: dict, context: list[dict], background) -> dict:
    """Explain one prediction from its original model and exact features, on demand."""
    import shap

    columns = model_feature_columns(model)
    x = model_input(model, features(context + [row])).tail(1)
    if list(x.columns) != columns or x.shape != (1, len(columns)):
        raise ValueError("Could not map the event to the model's feature schema")
    background = pd.DataFrame(background, columns=columns, dtype=float)
    if background.empty or len(background.columns) != len(columns):
        raise ValueError("A compatible synthetic background dataset is required")

    classifier = model["model"]
    algorithm = model.get("algorithm")
    if algorithm == "RandomForestClassifier":
        explainer = shap.TreeExplainer(
            classifier,
            data=background,
            model_output="probability",
            feature_perturbation="interventional",
            feature_names=columns,
        )
        explanation = explainer(x)
        values = np.asarray(explanation.values)
        base_values = np.asarray(explanation.base_values)
        if values.ndim == 3 and values.shape[-1] == 2:
            contributions = values[0, :, 1]
            base_value = float(base_values.reshape(1, -1)[0, 1])
        elif values.shape == (1, len(columns)):
            contributions = values[0]
            base_value = float(base_values.reshape(-1)[0])
        else:
            raise ValueError(f"Unsupported SHAP output shape for random forest: {values.shape}")
        output_scale = "fraud_probability"
        predicted_value = float(classifier.predict_proba(x)[0, 1])
    elif algorithm == "LogisticRegression":
        if not hasattr(classifier, "named_steps"):
            raise ValueError("Logistic Regression artifact is missing its fitted preprocessing pipeline")
        steps = classifier.named_steps
        logistic = steps.get("logisticregression")
        scaler = steps.get("standardscaler")
        if logistic is None or scaler is None:
            raise ValueError("Logistic Regression preprocessing mapping is unsupported")
        transformed_x = scaler.transform(x)
        transformed_background = scaler.transform(background)
        explainer = shap.LinearExplainer(
            logistic,
            transformed_background,
            feature_perturbation="interventional",
            feature_names=columns,
        )
        explanation = explainer(transformed_x)
        values = np.asarray(explanation.values)
        if values.shape != (1, len(columns)):
            raise ValueError(f"Unsupported SHAP output shape for logistic regression: {values.shape}")
        contributions = values[0]
        base_value = float(np.asarray(explanation.base_values).reshape(-1)[0])
        output_scale = "fraud_log_odds"
        predicted_value = float(classifier.decision_function(x)[0])
    else:
        raise ValueError(f"No verified SHAP explainer for model algorithm {algorithm!r}")

    reconstructed = base_value + float(np.sum(contributions))
    if not np.isclose(reconstructed, predicted_value, atol=1e-5, rtol=1e-5):
        raise ValueError("SHAP additivity check failed for this model prediction")
    ranked = sorted(
        zip(columns, map(float, x.iloc[0].tolist()), map(float, contributions)),
        key=lambda item: abs(item[2]),
        reverse=True,
    )
    return {
        "model_version": model["version"],
        "algorithm": algorithm,
        "feature_version": FEATURE_VERSION,
        "output_scale": output_scale,
        "base_value": base_value,
        "predicted_value": predicted_value,
        "additivity_residual": reconstructed - predicted_value,
        "background_rows": len(background),
        "method": "SHAP TreeExplainer" if algorithm == "RandomForestClassifier" else "SHAP LinearExplainer",
        "contributions": [
            {
                "feature": name,
                "feature_value": feature_value,
                "shap_value": shap_value,
                "direction": "increases model output" if shap_value > 0 else "decreases model output" if shap_value < 0 else "no material change",
            }
            for name, feature_value, shap_value in ranked
        ],
    }


def load_model():
    base_path = Path(settings.model_path)
    manifest = Path(f"{settings.model_path}.current")
    path = (
        base_path.parent / manifest.read_text(encoding="utf-8").strip()
        if manifest.exists()
        else base_path
    )
    if not path.exists():
        result = train_model()
        path = Path(result["artifact_path"])
    artifact = joblib.load(path)
    if "anomaly_detector" not in artifact or artifact.get("features") != FEATURES:
        result = train_model()
        path = Path(result["artifact_path"])
        artifact = joblib.load(path)
    artifact["artifact_path"] = str(path)
    return artifact


def track_training_run(result: dict) -> str:
    import mlflow
    import mlflow.sklearn

    artifact = joblib.load(result["artifact_path"])
    mlflow.set_experiment("teleguard-synthetic-fraud")
    with mlflow.start_run(run_name=result["version"]) as run:
        mlflow.log_param("dataset_version", result.get("dataset_version", "scenario-v1-seed-2026"))
        mlflow.log_param("algorithm", result["algorithm"])
        mlflow.log_param("feature_version", FEATURE_VERSION)
        for key, value in result["metrics"].items():
            if isinstance(value, (float, int)):
                mlflow.log_metric(key, value)
        mlflow.log_artifact(result["artifact_path"])
        mlflow.sklearn.log_model(
            artifact["model"],
            artifact_path="classifier",
            registered_model_name="TeleGuardSyntheticFraud",
        )
        return run.info.run_id


def score(row: dict, model, context: list[dict]) -> dict:
    frame = features(context + [row])
    classifier = model["model"] if isinstance(model, dict) else model
    x = model_input(model, frame).tail(1) if isinstance(model, dict) else frame.tail(1)
    probability = float(classifier.predict_proba(x)[0, 1])
    detector = model.get("anomaly_detector") if isinstance(model, dict) else None
    if detector is None:
        raise RuntimeError("The trained model artifact has no fitted anomaly detector")
    raw = float(detector.score_samples(x)[0])
    anomaly = float(np.clip((-0.35 - raw) / 0.45, 0, 1))
    graph_net = nx.Graph()
    for event in context + [row]:
        subscriber = f"subscriber:{event['subscriber_id']}"
        graph_net.add_node(subscriber, kind="subscriber")
        for field, kind in (
            ("device_id", "device"),
            ("network_token", "network"),
            ("sim_id", "sim"),
        ):
            value = event.get(field)
            if value:
                entity = f"{kind}:{value}"
                graph_net.add_node(entity, kind=kind)
                graph_net.add_edge(subscriber, entity)
    target = f"subscriber:{row['subscriber_id']}"
    shared_subscribers = set()
    for entity in graph_net.neighbors(target):
        shared_subscribers.update(
            n for n in graph_net.neighbors(entity) if n != target and n.startswith("subscriber:")
        )
    shared = len(shared_subscribers)
    graph = float(min(shared / 5, 1))
    rules = []
    if row.get("event_type") in ("SIM_CHANGE", "DEVICE_CHANGE"):
        rules.append("recent_identity_change")
    if row.get("event_type") == "CALL" and (row.get("duration_seconds") or 0) < 10:
        rules.append("short_call_pattern")
    # A fired deterministic rule is represented independently from the model probability.
    rule = 1.0 if rules else 0.0
    # Versioned weighted policy. Identity sharing is a weak supporting signal only.
    risk = float(
        np.clip(
            settings.risk_supervised_weight * probability
            + settings.risk_anomaly_weight * anomaly
            + settings.risk_graph_weight * graph
            + settings.risk_rule_weight * rule,
            0,
            1,
        )
    )
    evidence = [
        {
            "signal": "supervised_model",
            "value": round(probability, 3),
            "detail": "Supervised classifier probability; synthetic training data",
        },
        {
            "signal": "anomaly_detector",
            "value": round(anomaly, 3),
            "detail": "Isolation Forest normalized outlier score",
        },
        {
            "signal": "shared_entities",
            "value": round(graph, 3),
            "detail": f"{shared} connected synthetic subscribers; weak evidence only",
        },
    ]
    evidence += [
        {"signal": "rule", "value": name, "detail": "Versioned rule fired on event metadata"}
        for name in rules
    ]
    return {
        "probability": probability,
        "anomaly_score": anomaly,
        "graph_score": graph,
        "rule_score": rule,
        "risk_score": risk,
        "risk_band": "Critical"
        if risk >= 0.8
        else "High"
        if risk >= 0.6
        else "Medium"
        if risk >= 0.35
        else "Low",
        "evidence": evidence,
        "feature_version": model_feature_version(model) if isinstance(model, dict) else FEATURE_VERSION,
    }
