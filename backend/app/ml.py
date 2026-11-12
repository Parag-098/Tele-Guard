from pathlib import Path
from datetime import datetime, timezone
import joblib
import numpy as np
import pandas as pd
import networkx as nx
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.linear_model import LogisticRegression
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
]
FEATURE_VERSION = "features-v1"


def features(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=FEATURES)
    # Only count identifiers on this subscriber's history up to the current row.
    order = df.assign(_position=range(len(df))).sort_values("event_time", kind="stable")
    seen_device, seen_network, history_by_sub, result = {}, {}, {}, {}
    for row in order.to_dict("records"):
        sub = row["subscriber_id"]
        key = (sub, row.get("device_id"))
        nkey = (sub, row.get("network_token"))
        ts = pd.to_datetime(row["event_time"], utc=True)
        pos = row["_position"]
        history = history_by_sub.setdefault(sub, [])
        recent = [old for old in history if 0 <= (ts - old["ts"]).total_seconds() <= 3600]
        duration = row.get("duration_seconds")
        if pd.isna(duration):
            duration = 0
        result[pos] = [
            float(duration),
            float(row["event_type"] == "CALL"),
            float(row["event_type"] == "SIM_CHANGE"),
            float(row["event_type"] == "DEVICE_CHANGE"),
            float(min(seen_device.get(key, 0), 20)),
            float(min(seen_network.get(nkey, 0), 20)),
            float(ts.hour),
            float(min(len(history), 500)),
            float(sum(old["event_type"] == "CALL" for old in recent)),
            float(
                len(
                    {old.get("destination_token") for old in recent if old.get("destination_token")}
                )
            ),
            float(sum(old["event_type"] == "SIM_CHANGE" for old in history)),
        ]
        seen_device[key] = seen_device.get(key, 0) + 1
        seen_network[nkey] = seen_network.get(nkey, 0) + 1
        history.append(
            {
                "ts": ts,
                "event_type": row["event_type"],
                "destination_token": row.get("destination_token"),
            }
        )
    return (
        pd.DataFrame.from_dict(result, orient="index")
        .sort_index()
        .set_axis(FEATURES, axis=1)
        .astype(float)
    )


def train_model(path: str | None = None) -> dict:
    rows = [e.model_dump() for e in generate_events(1400, 2026)]
    X = features(rows)
    y = np.array([r["fraud_label"] for r in rows])
    ordered = np.argsort([r["event_time"] for r in rows])
    split = int(len(ordered) * 0.8)
    tr, te = ordered[:split], ordered[split:]
    candidates = {
        "LogisticRegression": make_pipeline(
            StandardScaler(),
            LogisticRegression(class_weight="balanced", max_iter=600, random_state=17),
        ),
        "RandomForestClassifier": RandomForestClassifier(
            n_estimators=120, max_depth=8, class_weight="balanced", random_state=17
        ),
    }
    reports = {}
    for name, candidate in candidates.items():
        candidate.fit(X.iloc[tr], y[tr])
        probability = candidate.predict_proba(X.iloc[te])[:, 1]
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
        }
    algorithm = max(reports, key=lambda n: reports[n]["pr_auc"])
    model = candidates[algorithm]
    version = f"synthetic-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    anomaly_detector = IsolationForest(n_estimators=120, contamination="auto", random_state=29)
    anomaly_detector.fit(X.iloc[tr][y[tr] == 0])
    metrics = {
        **reports[algorithm],
        "algorithm": algorithm,
        "model_comparison": reports,
        "split": "chronological 80/20; preprocessing fit on train partition only",
        "evaluation_note": "Synthetic deterministic holdout; not real-world performance.",
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
            "version": version,
            "algorithm": algorithm,
            "metrics": metrics,
            "artifact_path": str(target),
        },
        target,
    )
    if path is None:
        Path(f"{settings.model_path}.current").write_text(target.name, encoding="utf-8")
    return {
        "metrics": metrics,
        "artifact_path": str(target),
        "version": version,
        "algorithm": algorithm,
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


def track_training_run(result: dict) -> None:
    import mlflow
    import mlflow.sklearn

    artifact = joblib.load(result["artifact_path"])
    mlflow.set_experiment("teleguard-synthetic-fraud")
    with mlflow.start_run(run_name=result["version"]):
        mlflow.log_param("dataset_version", "scenario-v1-seed-2026")
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


def score(row: dict, model, context: list[dict]) -> dict:
    frame = features(context + [row])
    x = frame.tail(1)
    classifier = model["model"] if isinstance(model, dict) else model
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
    }
