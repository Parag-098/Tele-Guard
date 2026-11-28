"""Persistent state for continuous simulation and monitoring."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import now


class SimulatorRun(Base):
    __tablename__ = "simulator_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_by: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), index=True)
    configuration: Mapped[dict] = mapped_column(JSON)
    cursor: Mapped[int] = mapped_column(Integer, default=0)
    quarantined: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    next_tick_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SyntheticOutcomeRecord(Base):
    __tablename__ = "synthetic_outcome_records"
    event_id: Mapped[str] = mapped_column(ForeignKey("events.event_id"), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulator_runs.id"), index=True)
    actual: Mapped[int] = mapped_column(Integer)
    scenario: Mapped[str] = mapped_column(String(80))
    episode_id: Mapped[str | None] = mapped_column(String(100))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ServedSnapshot(Base):
    __tablename__ = "served_snapshots"
    __table_args__ = (Index("ix_served_snapshot_cohort_time", "cohort", "observed_at"),)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), primary_key=True)
    cohort: Mapped[str] = mapped_column(String(60))
    event_type: Mapped[str] = mapped_column(String(30))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    release: Mapped[str | None] = mapped_column(String(100), index=True)
    assigned_role: Mapped[str] = mapped_column(String(20))
    actual_role: Mapped[str] = mapped_column(String(20))
    classifier_threshold: Mapped[float]
    values: Mapped[dict] = mapped_column(JSON)


class MonitorWindow(Base):
    __tablename__ = "monitor_windows"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    cohort: Mapped[str] = mapped_column(String(60), index=True)
    model_version: Mapped[str] = mapped_column(String(80))
    feature_version: Mapped[str] = mapped_column(String(40))
    policy_version: Mapped[str] = mapped_column(String(40))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sample_count: Mapped[int] = mapped_column(Integer)
    result: Mapped[dict] = mapped_column(JSON)


class QuarantinedEvent(Base):
    __tablename__ = "quarantined_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(60), index=True)
    external_id: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
