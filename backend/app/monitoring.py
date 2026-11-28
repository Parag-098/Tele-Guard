"""Compute scheduled model-specific windows from actual persisted inference."""

from collections import defaultdict
from datetime import timedelta
from hashlib import sha256

import numpy as np
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dataset_jobs import queue_job
from app.db import get_db
from app.models import Event, MLOpsJob, Prediction
from app.runtime_models import MonitorWindow, QuarantinedEvent, ServedSnapshot, SimulatorRun
from app.security import current_user
from app.simulator import utc

router = APIRouter(prefix="/api/monitoring", tags=["Monitoring"])
FEATURES = ("duration_seconds", "call_count_1h", "failed_auth_1h", "subscriber_event_count")
WINDOW_LENGTH = timedelta(hours=1)
MAX_WINDOW_ROWS = 10_000


def allocation(db, serving):
    release = serving.get("deployment_id")
    if not release or serving["mode"] != "canary":
        return {"configured_percent": 0, "events": 0, "subscribers": 0,
                "assigned_events": 0, "assigned_subscribers": 0, "served_events": 0, "fallback_events": 0}
    counts = db.execute(
        select(ServedSnapshot.assigned_role, ServedSnapshot.actual_role,
               func.count(), func.count(func.distinct(Event.subscriber_id)))
        .join(Prediction, Prediction.id == ServedSnapshot.prediction_id)
        .join(Event, Event.event_id == Prediction.event_id)
        .where(ServedSnapshot.release == release)
        .group_by(ServedSnapshot.assigned_role, ServedSnapshot.actual_role)
    ).all()
    subscribers, assigned = db.execute(
        select(func.count(func.distinct(Event.subscriber_id)),
               func.count(func.distinct(Event.subscriber_id)).filter(ServedSnapshot.assigned_role == "canary"))
        .join(Prediction, Prediction.id == ServedSnapshot.prediction_id)
        .join(Event, Event.event_id == Prediction.event_id)
        .where(ServedSnapshot.release == release)
    ).one()
    return {"configured_percent": serving["canary_percent"], "subscribers": subscribers,
            "assigned_subscribers": assigned, "events": sum(row[2] for row in counts),
            "assigned_events": sum(row[2] for row in counts if row[0] == "canary"),
            "served_events": sum(row[2] for row in counts if row[1] == "canary"),
            "fallback_events": sum(row[2] for row in counts if row[0] == "canary" and row[1] != "canary")}


def performance(rows):
    labeled = [(sample, prediction) for sample, prediction in rows if prediction.ground_truth_label is not None]
    positive = sum(pred.ground_truth_label == 1 for _, pred in labeled)
    negative = len(labeled) - positive
    tp = sum(pred.ground_truth_label == 1 and pred.probability >= sample.classifier_threshold
             for sample, pred in labeled)
    fp = sum(pred.ground_truth_label == 0 and pred.probability >= sample.classifier_threshold
             for sample, pred in labeled)
    return {
        "count": len(labeled), "coverage": len(labeled) / max(len(rows), 1),
        "positives": positive, "negatives": negative,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / positive if positive else None, "false_positive_rate": fp / negative if negative else None,
        "brier": (sum((pred.probability - pred.ground_truth_label) ** 2 for _, pred in labeled)
                  / len(labeled)) if labeled else None,
    }


def _distribution(values, cuts):
    clean = [value for value in values if value is not None and np.isfinite(value)]
    counts = np.histogram(clean, bins=[-np.inf, *cuts, np.inf])[0].tolist()
    return [*counts, len(values) - len(clean)]


def compare_to_baseline(values, baseline=None):
    if baseline is None:
        clean = [value for value in values if value is not None and np.isfinite(value)]
        cuts = np.unique(np.quantile(clean, [0.1, 0.25, 0.5, 0.75, 0.9])).tolist() if clean else []
        return {"cuts": cuts, "reference_counts": _distribution(values, cuts), "psi": 0.0}
    cuts, ref = baseline["cuts"], baseline["reference_counts"]
    counts = _distribution(values, cuts)
    base_probs = (np.asarray(ref) + 0.5) / (sum(ref) + len(ref) * 0.5)
    cur_probs = (np.asarray(counts) + 0.5) / (sum(counts) + len(counts) * 0.5)
    return {**baseline, "current_counts": counts,
            "psi": float(np.sum((cur_probs - base_probs) * np.log(cur_probs / base_probs)))}


def _window_rows(db, cohort, start, end):
    return db.execute(
        select(ServedSnapshot, Prediction)
        .join(Prediction, Prediction.id == ServedSnapshot.prediction_id)
        .where(ServedSnapshot.cohort == cohort, ServedSnapshot.observed_at >= start,
               ServedSnapshot.observed_at < end)
        .order_by(ServedSnapshot.observed_at, ServedSnapshot.prediction_id)
        .limit(MAX_WINDOW_ROWS + 1)
    ).all()


def _save_window(db, cohort, start, end, versions, rows, minimum, invalid, overflow, wall_time):
    key = sha256("|".join((cohort, start.isoformat(), *versions)).encode()).hexdigest()
    existing = db.get(MonitorWindow, key)
    model, feature, policy = versions
    earlier = (
        select(MonitorWindow).where(MonitorWindow.cohort == cohort,
                                    MonitorWindow.model_version == model,
                                    MonitorWindow.feature_version == feature,
                                    MonitorWindow.policy_version == policy,
                                    MonitorWindow.start_at < start)
    )
    previous = db.scalar(earlier.order_by(MonitorWindow.start_at.desc()).limit(1))
    baseline = next((entry for entry in db.scalars(earlier.order_by(MonitorWindow.start_at))
                     if entry.result["status"] == "baseline"), None)
    perf = performance(rows)
    values = {name: [snapshot.values.get(name) for snapshot, _ in rows] for name in FEATURES}
    values["probability"] = [prediction.probability for _, prediction in rows]
    values["risk_score"] = [prediction.risk_score for _, prediction in rows]
    status = "insufficient_samples"
    distributions = {}
    breaches = 0
    if overflow or invalid:
        status = "data_quality"
    elif len(rows) >= minimum:
        if not baseline:
            status = "baseline"
            distributions = {name: compare_to_baseline(series) for name, series in values.items()}
        else:
            distributions = {name: compare_to_baseline(series, baseline.result["features"][name])
                             for name, series in values.items()}
            shifted = any(item["psi"] >= 0.20 for item in distributions.values())
            consecutive = previous and utc(previous.end_at) == start
            breaches = 1 + (previous.result["consecutive_breaches"] if consecutive else 0) if shifted else 0
            status = "drift_alert" if breaches >= 2 else "watch" if shifted else "stable"
    baseline_perf = baseline.result["performance"] if baseline else None
    supported = (baseline_perf and all(report["coverage"] >= 0.5 and report["positives"] >= 5
                                       and report["negatives"] >= 20 for report in (perf, baseline_perf)))
    degraded = bool(supported and (baseline_perf["recall"] - perf["recall"] >= 0.15
                                    or perf["false_positive_rate"] - baseline_perf["false_positive_rate"] >= 0.10))
    result = {"status": status, "features": distributions, "performance": perf,
              "consecutive_breaches": breaches, "baseline_window": baseline.key if baseline else None,
              "new_drift_alert": breaches == 2, "quality_rejections": invalid, "overflow": overflow,
              "performance_degraded": degraded, "minimum_samples": minimum,
              "predicted_positive_rate": sum(p.probability >= s.classifier_threshold for s, p in rows) / max(len(rows), 1)}
    if existing:
        existing.result = result
    else:
        db.add(MonitorWindow(
            key=key, cohort=cohort, model_version=model, feature_version=feature,
            policy_version=policy, start_at=start, end_at=end, sample_count=len(rows), result=result,
        ))
    if degraded and status != "data_quality":
        _trigger_training(db, key, cohort, rows, wall_time)


def _trigger_training(db, key, cohort, rows, wall_time):
    from app.decision_policy import lock_model_release
    from app.investigations import approved_labels
    from app.runtime_models import SyntheticOutcomeRecord

    lock_model_release(db)
    recent = db.scalar(
        select(MLOpsJob.id).where(MLOpsJob.kind == "retrain_live",
                                  MLOpsJob.arguments["cohort"].as_string() == cohort,
                                  MLOpsJob.created_at > wall_time - timedelta(hours=1)).limit(1)
    )
    repeated = db.scalar(
        select(MLOpsJob.id).where(MLOpsJob.kind == "retrain_live",
                                  MLOpsJob.arguments["window"].as_string() == key).limit(1)
    )
    if recent or repeated:
        return
    candidates = db.execute(
        select(Prediction.id, Prediction.ground_truth_label, Prediction.label_source, Event.event_id)
        .join(ServedSnapshot, ServedSnapshot.prediction_id == Prediction.id)
        .join(Event, Event.event_id == Prediction.event_id)
        .where(ServedSnapshot.cohort == cohort, ServedSnapshot.observed_at < wall_time,
               Prediction.ground_truth_label.is_not(None), Prediction.label_received_at.is_not(None),
               Prediction.label_received_at <= wall_time)
        .order_by(ServedSnapshot.observed_at.desc(), Prediction.id.desc())
        .limit(MAX_WINDOW_ROWS * 5)
    ).all()
    cutoff = utc(wall_time)
    reviewed = approved_labels(db, cutoff)
    outcomes = {
        outcome.event_id: outcome
        for outcome in db.scalars(select(SyntheticOutcomeRecord).where(
            SyntheticOutcomeRecord.event_id.in_([event_id for _, _, _, event_id in candidates])
        )).all()
    } if candidates else {}
    eligible = []
    for prediction_id, label, source, event_id in candidates:
        label = int(label)
        if source == "analyst_review":
            verified = reviewed.get(event_id) == label
        elif source == "synthetic-outcome":
            outcome = outcomes.get(event_id)
            verified = bool(
                outcome and outcome.actual == label and outcome.released_at and
                utc(outcome.released_at) <= cutoff and utc(outcome.available_at) <= cutoff
            )
        else:
            verified = False
        if verified:
            eligible.append((prediction_id, label))
    eligible = eligible[-MAX_WINDOW_ROWS:]
    eligible.reverse()
    labels = [int(label) for _, label in eligible]
    if len(labels) < 50 or set(labels) != {0, 1}:
        return
    # The training evaluator uses chronological 70/15/15 partitions. Avoid
    # queueing a candidate job that cannot be evaluated because a time partition
    # has no positive or negative examples.
    train_end = max(1, int(len(labels) * 0.70))
    validation_end = min(max(train_end + 1, int(len(labels) * 0.85)), len(labels) - 1)
    if any(set(labels[start:end]) != {0, 1} for start, end in
           ((0, train_end), (train_end, validation_end), (validation_end, len(labels)))):
        return
    frozen = {str(identifier): label for identifier, label in eligible}
    queue_job(db, "retrain_live", "system", {
        "window": key, "cohort": cohort, "frozen_outcomes": frozen,
        "reason": "supported delayed-label degradation", "count": len(frozen),
        "label_cutoff": wall_time.isoformat(),
    })


def refresh_monitoring(db, wall_time):
    runs = db.scalars(select(SimulatorRun).order_by(SimulatorRun.created_at.desc()).limit(5)).all()
    cohorts = [("live", wall_time, 500), ("csv", wall_time, 500)]
    for run in runs:
        last = db.scalar(select(func.max(ServedSnapshot.observed_at)).where(ServedSnapshot.cohort == run.id))
        if last:
            cohorts.append((run.id, utc(last), run.configuration["monitor_minimum"]))
    for cohort, watermark, minimum in cohorts:
        boundary = watermark.replace(minute=0, second=0, microsecond=0)
        offsets = range(14, 0, -1) if cohort not in {"live", "csv"} else range(4, 0, -1)
        for offset in offsets:
            end = boundary - WINDOW_LENGTH * (offset - 1)
            start = end - WINDOW_LENGTH
            report = _window_rows(db, cohort, start, end)
            if not report:
                continue
            invalid = db.scalar(select(func.count()).select_from(QuarantinedEvent).where(
                QuarantinedEvent.source == cohort, QuarantinedEvent.created_at >= start,
                QuarantinedEvent.created_at < end,
            ))
            grouped = defaultdict(list)
            for sample, prediction in report[:MAX_WINDOW_ROWS]:
                grouped[(prediction.model_version, prediction.feature_version, prediction.policy_version)].append((sample, prediction))
            for versions, rows in grouped.items():
                _save_window(db, cohort, start, end, versions, rows, minimum, invalid,
                             len(report) > MAX_WINDOW_ROWS, wall_time)
            db.flush()


@router.get("/windows")
def list_windows(cohort: str | None = Query(default=None, max_length=60),
                 db: Session = Depends(get_db), user=Depends(current_user)):
    statement = select(MonitorWindow).order_by(MonitorWindow.start_at.desc()).limit(80)
    if cohort:
        statement = statement.where(MonitorWindow.cohort == cohort)
    return [{"id": entry.key, "cohort": entry.cohort, "model_version": entry.model_version,
             "feature_version": entry.feature_version, "policy_version": entry.policy_version,
             "start": utc(entry.start_at), "end": utc(entry.end_at), "sample_count": entry.sample_count,
             **entry.result}
            for entry in db.scalars(statement)]
