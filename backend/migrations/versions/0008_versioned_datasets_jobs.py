"""Add normalized dataset versions and durable MLOps jobs.

Existing event, dataset snapshot, prediction, and model data is retained.  The
nullable event reference keeps all pre-existing rows compatible.
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_versioned_datasets_jobs"
down_revision = "0007_backfill_model_observations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dataset_versions",
        sa.Column("version", sa.String(120), primary_key=True),
        sa.Column("kind", sa.String(30), nullable=False, server_default="operational"),
        sa.Column("generator_version", sa.String(40), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("target_rows", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="building"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_by", sa.String(80), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_dataset_versions_status", "dataset_versions", ["status"])
    op.create_table(
        "mlops_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("requested_by", sa.String(80), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("progress_current", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_mlops_jobs_kind", "mlops_jobs", ["kind"])
    op.create_index("ix_mlops_jobs_status", "mlops_jobs", ["status"])
    op.create_table(
        "service_heartbeats",
        sa.Column("service", sa.String(40), primary_key=True),
        sa.Column("instance_id", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="healthy"),
        sa.Column("current_job_id", sa.String(36), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    with op.batch_alter_table("events") as batch:
        batch.add_column(sa.Column("dataset_version", sa.String(120), nullable=True))
        batch.add_column(sa.Column("call_direction", sa.String(12), nullable=True))
        batch.add_column(sa.Column("call_status", sa.String(12), nullable=True))
        batch.add_column(sa.Column("is_international", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("is_roaming", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("message_count", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("auth_outcome", sa.String(12), nullable=True))
        batch.create_foreign_key(
            "fk_events_dataset_version", "dataset_versions", ["dataset_version"], ["version"]
        )
        batch.create_index("ix_events_dataset_version", ["dataset_version"])


def downgrade():
    # Dataset provenance and job history are durable evidence; downgrade leaves
    # the additive tables intact instead of deleting rows during a rollback.
    pass
