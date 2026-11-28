from collections import Counter
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import gzip
import json

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits

from app.dataset_manifest import build_snapshot, iter_records, load_manifest
from app.db import SessionLocal
from app.experiment import CLASSIFIERS, prepare_rows, run_experiment, select_threshold
from app.longitudinal import HOLDOUT_SCENARIOS, TRAIN_SCENARIOS, TelecomConfig, TelecomGenerator
from app.ml import FEATURES, FEATURE_VERSION, explain_prediction
from app.models import Event, Prediction
from app.runtime_models import SimulatorRun, SyntheticOutcomeRecord


def test_synthetic_record_is_seekable_and_truth_is_delayed():
    config = TelecomConfig(20261128, "live-testing", population=80, prevalence=0.12)
    generator = TelecomGenerator(config)
    rows = [generator.record(index) for index in range(2_500)]
    assert rows[947] == TelecomGenerator(config).record(947)
    assert rows[947] == generator.record(947)
    assert rows[947].event.event_id == generator.record(947, "shift").event.event_id
    assert len({row.event.event_id for row in rows}) == len(rows)
    assert all(a.event.event_time < b.event.event_time for a, b in zip(rows, rows[1:]))
    assert set(Counter(row.event.event_type for row in rows)) >= {"CALL", "SMS", "SIM_CHANGE", "LOCATION"}
    assert len(Counter(row.event.subscriber_id for row in rows)) == config.population
    assert all(row.event.fraud_label is None and row.event.scenario_label is None for row in rows)
    assert all(row.outcome.available_at - row.event.event_time >= timedelta(minutes=30) for row in rows)
    reference_scenarios = {row.outcome.scenario for row in rows if row.outcome.label}
    assert 4 <= len(reference_scenarios) and reference_scenarios <= set(TRAIN_SCENARIOS)
    shifted = [generator.record(index, "shift") for index in range(2_500)]
    assert {row.outcome.scenario for row in shifted if row.outcome.label} <= set(HOLDOUT_SCENARIOS)
    assert sum(row.outcome.label for row in shifted) > sum(row.outcome.label for row in rows)


def test_manifest_is_path_independent_and_rejects_corrupted_part(tmp_path):
    config = TelecomConfig(99, "deterministic-snap", role="development")
    path = build_snapshot(tmp_path / "first", config, 4_000, "test", 750)
    repeated = build_snapshot(tmp_path / "second", config, 4_000, "test", 750)
    assert path.read_bytes() == repeated.read_bytes()
    manifest = load_manifest(path, verify_parts=True)
    assert manifest["unique_events"] == manifest["count"] == 4_000
    assert load_manifest(path, verify_parts=True)["manifest_sha256"] == manifest["manifest_sha256"]
    assert {name: summary["rows"] for name, summary in manifest["splits"].items()} == {
        "training": 2_800, "calibration": 300, "selection": 300, "test": 600
    }
    assert sum(1 for _ in iter_records(path, manifest)) == 4_000
    assert len({summary["assignment_sha256"] for summary in manifest["splits"].values()}) == 4
    assert build_snapshot(tmp_path / "first", config, 4_000, "test", 750) == path

    first_event_part = path.parent / manifest["parts"][0]["events"]
    with gzip.open(first_event_part, "rb") as file:
        assert "fraud_label" not in json.loads(file.readline())
    with first_event_part.open("ab") as file:
        file.write(b"corruption")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_manifest(path, verify_parts=True)


def test_manifest_features_do_not_consume_outcome_metadata(tmp_path):
    config = TelecomConfig(99, "feature-snap", role="development")
    path = build_snapshot(tmp_path, config, 2_000, "test", 450)
    manifest = load_manifest(path, verify_parts=True)
    result = prepare_rows(path, manifest)
    assert list(result.frame.columns) == FEATURES
    assert result.frame.shape == (2_000, len(FEATURES))
    assert "scenario_label" not in result.frame
    assert np.isfinite(result.frame.to_numpy()).all()
    assert set(result.outcomes) == {0, 1}


def test_same_manifest_reference_stream_matches_scheduled_worker_replay(tmp_path, client):
    """The worker simulator must replay the sealed event and delayed-outcome stream exactly."""
    from app.simulator import advance_simulator
    from app.main import _event_payload_matches

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    run_id = "manifest-parity-worker-2026"
    config = TelecomConfig(
        7831, run_id, population=64, start=start, interval_seconds=60,
        prevalence=0.10, role="drift",
    )
    path = build_snapshot(tmp_path, config, 80, "manifest-worker-parity")
    manifest = load_manifest(path, verify_parts=True)
    expected = [record for split, record in iter_records(path, manifest) if split == "reference"]
    assert len(expected) == 20

    with SessionLocal() as db:
        db.add(SimulatorRun(
            id=run_id, created_by="acceptance", status="running",
            configuration={
                "seed": config.seed, "population": config.population, "rate": 20,
                "logical_interval_seconds": config.interval_seconds,
                "prevalence": config.prevalence, "event_limit": 20,
                "drift_at": None, "recover_at": None, "invalidate_every": None,
                "monitor_minimum": 10,
            },
            cursor=0, quarantined=0, created_at=start, next_tick_at=start,
        ))
        db.commit()
        advance_simulator(db, start + timedelta(seconds=1))
        db.commit()
        run = db.get(SimulatorRun, run_id)
        assert run.status == "completed" and run.cursor == 20 and run.quarantined == 0
        actual_events = {
            item.event_id: item for item in db.query(Event).filter(Event.event_id.in_(
                [record.event.event_id for record in expected]
            )).all()
        }
        actual_outcomes = {
            row.event_id: row for row in db.query(SyntheticOutcomeRecord).filter_by(run_id=run_id)
        }
        actual_predictions = {
            row.event_id: row for row in db.query(Prediction).filter(Prediction.event_id.in_(
                [record.event.event_id for record in expected]
            )).all()
        }

    assert set(actual_events) == {record.event.event_id for record in expected}
    assert set(actual_outcomes) == set(actual_events)
    assert set(actual_predictions) == set(actual_events)
    for record in expected:
        event_id = record.event.event_id
        stored = actual_events[event_id]
        generated = record.event
        assert stored.event_type == generated.event_type
        assert stored.event_time == generated.event_time.replace(tzinfo=None)
        assert stored.subscriber_id == generated.subscriber_id
        assert _event_payload_matches(stored, generated)
        outcome = actual_outcomes[event_id]
        assert outcome.actual == record.outcome.label
        assert outcome.scenario == record.outcome.scenario
        assert outcome.episode_id == record.outcome.episode_id
        assert outcome.available_at == record.outcome.available_at.replace(tzinfo=None)
        assert outcome.released_at is None
        assert actual_predictions[event_id].ground_truth_label is None


def test_experiment_checks_training_volume_and_does_not_refit_on_holdouts(tmp_path):
    config = TelecomConfig(1551, "fit-sealed", population=80, prevalence=0.12, role="development")
    development = build_snapshot(tmp_path, config, 7_500, "test")
    independent = build_snapshot(
        tmp_path, replace(config, namespace="independent-sealed", role="independent"), 2_500, "test"
    )
    with pytest.raises(ValueError, match="100,001"):
        run_experiment(development, {"independent": independent}, tmp_path / "failed")
    result = run_experiment(
        development, {"independent": independent}, tmp_path / "trained", min_training_rows=1_000
    )
    assert not result["published"]
    assert set(result["metrics"]["model_comparison"]) == set(CLASSIFIERS)
    assert 1_000 <= result["metrics"]["fit_rows"] < 7_500 * 0.70
    report = json.loads((tmp_path / "trained" / f"{result['version']}-evaluation.json").read_bytes())
    assert report["research_only"] and not report["meets_training_volume"]
    assert report["data"]["test_rows"] == 1_125
    assert report["sealed_assessment"]["independent"]["partitions"]["independent"]["rows"] == 2_500
    assert (
        joblib.load(result["artifact_path"])["classification_threshold"]
        == result["classification_threshold"]
    )


def test_threshold_respects_validation_false_positive_budget():
    outcomes = np.array([0] * 10 + [1] * 2)
    scores = np.array([0.10] * 9 + [0.92, 0.85, 0.95])
    threshold = select_threshold(outcomes, scores)
    assert 0.92 < threshold <= 0.95
    assert not (scores[outcomes == 0] >= threshold).any()


def test_histogram_model_explains_the_recorded_feature_vector():
    rng = np.random.default_rng(17)
    frame = pd.DataFrame(rng.normal(size=(200, len(FEATURES))), columns=FEATURES)
    outcomes = (frame["duration_seconds"] + frame["call_count_1h"] > 0.25).astype(int)
    model = HistGradientBoostingClassifier(max_iter=20, min_samples_leaf=6, random_state=17)
    with threadpool_limits(limits=2):
        model.fit(frame, outcomes)
        artifact = {
            "version": "tested-candidate", "model": model,
            "algorithm": "HistGradientBoostingClassifier", "features": FEATURES,
            "feature_version": FEATURE_VERSION,
        }
        features = frame.iloc[42].to_dict()
        explanation = explain_prediction(artifact, {}, [], frame.iloc[:30], scored_features=features)
        predicted = model.decision_function(frame.iloc[[42]])[0]
    assert explanation["model_version"] == "tested-candidate"
    assert explanation["output_scale"] == "fraud_log_odds"
    assert explanation["predicted_value"] == pytest.approx(predicted, abs=1e-7)
    assert explanation["additivity_residual"] == pytest.approx(0, abs=1e-5)
    assert {factor["feature"]: factor["feature_value"] for factor in explanation["contributions"]} == features
