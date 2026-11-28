"""Persisted synthetic telecom network, driven by the application worker."""

from datetime import timedelta, timezone
from types import SimpleNamespace
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.decision_policy import lock_model_release
from app.longitudinal import TelecomConfig, TelecomGenerator
from app.models import AuditLog, ModelObservation, ModelRun, Prediction, now
from app.runtime_models import QuarantinedEvent, SimulatorRun, SyntheticOutcomeRecord
from app.schemas import EventIn
from app.security import allow, current_user

router = APIRouter(prefix="/api/simulator", tags=["Simulator"])
manage = allow("Administrator", "ML Engineer")


class RunConfiguration(BaseModel):
    seed: int = Field(default=20261128, ge=0, le=4_294_967_295)
    population: int = Field(default=500, ge=24, le=20_000)
    rate: int = Field(default=5, ge=1, le=20, description="Events per worker tick")
    logical_interval_seconds: int = Field(default=5, ge=1, le=3600)
    prevalence: float = Field(default=0.02, ge=0, le=0.2)
    event_limit: int = Field(default=1500, ge=20, le=100_000)
    drift_at: int | None = Field(default=None, ge=1)
    recover_at: int | None = Field(default=None, ge=1)
    invalidate_every: int | None = Field(default=None, ge=3)
    monitor_minimum: int = Field(default=500, ge=10, le=5000)

    @model_validator(mode="after")
    def check_schedule(self):
        if self.drift_at is not None and self.drift_at >= self.event_limit:
            raise ValueError("Drift must start before the event limit")
        if self.recover_at is not None and (
            self.drift_at is None or not self.drift_at < self.recover_at < self.event_limit
        ):
            raise ValueError("Recovery must follow drift and precede the event limit")
        return self


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def run_view(run):
    return {"id": run.id, "status": run.status, "configuration": run.configuration,
            "cursor": run.cursor, "quarantined": run.quarantined,
            "scored": run.cursor - run.quarantined, "created_at": utc(run.created_at).isoformat()}


@router.get("/runs")
def list_runs(db: Session = Depends(get_db), user=Depends(current_user)):
    return [run_view(run) for run in db.scalars(
        select(SimulatorRun).order_by(SimulatorRun.created_at.desc()).limit(25)
    )]


@router.post("/runs", status_code=202)
def start_run(configuration: RunConfiguration, db: Session = Depends(get_db), user=Depends(manage)):
    lock_model_release(db)
    if db.scalar(select(SimulatorRun.id).where(SimulatorRun.status.in_(["running", "paused"])).limit(1)):
        raise HTTPException(409, "Stop or finish the current simulator run first")
    run = SimulatorRun(id=str(uuid4()), status="running", created_by=user.username,
                       configuration=configuration.model_dump(), cursor=0, quarantined=0)
    db.add(run)
    db.add(AuditLog(actor=user.username, action="simulator.started", target=run.id,
                    details={"configuration": run.configuration}))
    db.commit()
    return run_view(run)


@router.post("/runs/{run_id}/{action}")
def change_run(run_id: str, action: Literal["pause", "resume", "stop"],
               db: Session = Depends(get_db), user=Depends(manage)):
    run = db.scalar(select(SimulatorRun).where(SimulatorRun.id == run_id).with_for_update())
    if not run:
        raise HTTPException(404, "Simulator run not found")
    transitions = {"pause": {"running": "paused"}, "resume": {"paused": "running"},
                   "stop": {"running": "stopped", "paused": "stopped"}}
    target = transitions[action].get(run.status)
    if not target:
        raise HTTPException(409, f"Cannot {action} a {run.status} run")
    run.status = target
    run.next_tick_at = now()
    db.add(AuditLog(actor=user.username, action=f"simulator.{action}", target=run.id))
    db.commit()
    return run_view(run)


def advance_simulator(db, wall_time):
    from app.main import _active_release, ingest_event, load_model_run

    run = db.scalar(
        select(SimulatorRun).where(SimulatorRun.status == "running",
                                  SimulatorRun.next_tick_at <= wall_time)
        .order_by(SimulatorRun.created_at).with_for_update(skip_locked=True).limit(1)
    )
    if not run:
        return
    try:
        configuration = RunConfiguration.model_validate(run.configuration)
    except ValidationError:
        run.status = "failed"
        run.quarantined += 1
        db.add(QuarantinedEvent(
            source=run.id, external_id=None, error_code="invalid_run_configuration",
            created_at=wall_time,
        ))
        db.add(AuditLog(
            actor="system", action="simulator.input_quarantined", target=run.id,
            details={"error_code": "invalid_run_configuration"},
        ))
        return
    active = _active_release(db)
    if active is None:
        return
    model_run = db.scalar(select(ModelRun).where(ModelRun.version == active.version))
    if model_run is None:
        return
    model = load_model_run(model_run)
    start = utc(run.created_at).replace(second=0, microsecond=0)
    generator = TelecomGenerator(TelecomConfig(
        seed=configuration.seed, namespace=run.id, population=configuration.population,
        start=start, interval_seconds=configuration.logical_interval_seconds,
        prevalence=configuration.prevalence, role="live",
    ))
    actor = SimpleNamespace(username="system")
    end = min(run.cursor + configuration.rate, configuration.event_limit)
    for index in range(run.cursor, end):
        phase = "reference"
        if configuration.recover_at is not None and index >= configuration.recover_at:
            phase = "recovery"
        elif configuration.drift_at is not None and index >= configuration.drift_at:
            phase = "shift"
        generated = generator.record(index, phase=phase)
        event = generated.event
        if (phase == "shift" and configuration.invalidate_every
                and (index + 1) % configuration.invalidate_every == 0):
            try:
                EventIn.model_validate({**event.model_dump(), "subscriber_id": ""})
            except ValidationError:
                db.add(QuarantinedEvent(source=run.id, external_id=event.event_id,
                                       error_code="invalid_subscriber", created_at=event.event_time))
                run.quarantined += 1
                continue
        try:
            _, _, duplicate = ingest_event(db, event, actor, model, cohort=run.id,
                                            observed_at=event.event_time)
        except HTTPException as exc:
            if exc.status_code != 409:
                raise
            db.add(QuarantinedEvent(source=run.id, external_id=event.event_id,
                                    error_code="event_id_conflict", created_at=event.event_time))
            run.quarantined += 1
            continue
        if not duplicate:
            outcome = generated.outcome
            db.add(SyntheticOutcomeRecord(
                event_id=event.event_id, run_id=run.id, actual=outcome.label,
                scenario=outcome.scenario, episode_id=outcome.episode_id,
                available_at=outcome.available_at,
            ))
    run.cursor = end
    run.next_tick_at = wall_time + timedelta(seconds=1)
    if end == configuration.event_limit:
        run.status = "completed"
    db.flush()
    logical_time = start + timedelta(seconds=end * configuration.logical_interval_seconds)
    release_outcomes(db, run.id, logical_time, wall_time)


def settle_finished_runs(db, wall_time):
    pending_runs = db.scalars(
        select(SimulatorRun).where(
            SimulatorRun.status.in_(["completed", "stopped"]),
            SimulatorRun.id.in_(select(SyntheticOutcomeRecord.run_id).where(
                SyntheticOutcomeRecord.released_at.is_(None)
            )),
        ).order_by(SimulatorRun.created_at).limit(5)
    )
    for run in pending_runs:
        config = RunConfiguration.model_validate(run.configuration)
        start = utc(run.created_at).replace(second=0, microsecond=0)
        elapsed = max((wall_time - utc(run.next_tick_at)).total_seconds(), 0)
        steps = run.cursor + elapsed * config.rate
        release_outcomes(db, run.id, start + timedelta(seconds=steps * config.logical_interval_seconds), wall_time)


def release_outcomes(db, run_id, logical_time, wall_time):
    rows = db.execute(
        select(SyntheticOutcomeRecord, Prediction)
        .join(Prediction, Prediction.event_id == SyntheticOutcomeRecord.event_id)
        .where(SyntheticOutcomeRecord.run_id == run_id,
               SyntheticOutcomeRecord.released_at.is_(None),
               SyntheticOutcomeRecord.available_at <= logical_time)
        .order_by(SyntheticOutcomeRecord.available_at).limit(500)
    ).all()
    for outcome, prediction in rows:
        outcome.released_at = wall_time
        if prediction.ground_truth_label is not None:
            continue
        prediction.ground_truth_label = outcome.actual
        prediction.label_source = "synthetic-outcome"
        prediction.label_received_at = wall_time
        for obs in db.scalars(select(ModelObservation).where(
            ModelObservation.prediction_id == prediction.id,
        )):
            obs.outcome_label = outcome.actual
            obs.evaluated_at = wall_time
