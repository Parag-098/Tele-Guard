"""Add continuous simulator and monitoring state.

Revision ID: 0009_continuous_operations
Revises: 0008_versioned_datasets_jobs
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_continuous_operations"
down_revision = "0008_versioned_datasets_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "simulator_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_by", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("configuration", sa.JSON, nullable=False),
        sa.Column("cursor", sa.Integer, nullable=False),
        sa.Column("quarantined", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_tick_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_simulator_runs_status", "simulator_runs", ["status"])
    op.create_table(
        "synthetic_outcome_records",
        sa.Column("event_id", sa.String(64), sa.ForeignKey("events.event_id"), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("simulator_runs.id"), nullable=False),
        sa.Column("actual", sa.Integer, nullable=False),
        sa.Column("scenario", sa.String(80), nullable=False),
        sa.Column("episode_id", sa.String(100)),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_synthetic_outcome_records_run_id", "synthetic_outcome_records", ["run_id"])
    op.create_index("ix_synthetic_outcome_records_available_at", "synthetic_outcome_records", ["available_at"])
    op.create_table(
        "served_snapshots",
        sa.Column("prediction_id", sa.Integer, sa.ForeignKey("predictions.id"), primary_key=True),
        sa.Column("cohort", sa.String(60), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("release", sa.String(100)),
        sa.Column("assigned_role", sa.String(20), nullable=False),
        sa.Column("actual_role", sa.String(20), nullable=False),
        sa.Column("classifier_threshold", sa.Float, nullable=False),
        sa.Column("values", sa.JSON, nullable=False),
    )
    op.create_index("ix_served_snapshot_cohort_time", "served_snapshots", ["cohort", "observed_at"])
    op.create_index("ix_served_snapshots_release", "served_snapshots", ["release"])
    op.create_table(
        "monitor_windows",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("cohort", sa.String(60), nullable=False),
        sa.Column("model_version", sa.String(80), nullable=False),
        sa.Column("feature_version", sa.String(40), nullable=False),
        sa.Column("policy_version", sa.String(40), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_count", sa.Integer, nullable=False),
        sa.Column("result", sa.JSON, nullable=False),
    )
    op.create_index("ix_monitor_windows_cohort", "monitor_windows", ["cohort"])
    op.create_index("ix_monitor_windows_start_at", "monitor_windows", ["start_at"])
    op.create_table(
        "quarantined_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String(60), nullable=False),
        sa.Column("external_id", sa.String(64)),
        sa.Column("error_code", sa.String(60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_quarantined_events_source", "quarantined_events", ["source"])


def downgrade():
    for table in (
        "quarantined_events", "monitor_windows", "served_snapshots",
        "synthetic_outcome_records", "simulator_runs",
    ):
        op.drop_table(table)
