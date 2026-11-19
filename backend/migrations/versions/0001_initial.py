"""Initial persistent application schema (the original event-v1 schema).

Keep this definition frozen. Importing current ORM metadata here causes a clean
install to create tables and columns owned by later migrations prematurely.
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

metadata = sa.MetaData()
users = sa.Table(
    "users", metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("username", sa.String(80), nullable=False, unique=True),
    sa.Column("password_hash", sa.String(255), nullable=False),
    sa.Column("role", sa.String(30), nullable=False),
    sa.Column("active", sa.Boolean(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
events = sa.Table(
    "events", metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("event_id", sa.String(64), nullable=False, unique=True),
    sa.Column("event_type", sa.String(30), nullable=False),
    sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
    sa.Column("subscriber_id", sa.String(64), nullable=False),
    sa.Column("source_token", sa.String(64)),
    sa.Column("destination_token", sa.String(64)),
    sa.Column("sim_id", sa.String(64)),
    sa.Column("device_id", sa.String(64)),
    sa.Column("network_token", sa.String(64)),
    sa.Column("location_token", sa.String(64)),
    sa.Column("duration_seconds", sa.Integer()),
    sa.Column("scenario_label", sa.String(80)),
    sa.Column("fraud_label", sa.Integer()),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
predictions = sa.Table(
    "predictions", metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("event_id", sa.String(64), sa.ForeignKey("events.event_id"), nullable=False, unique=True),
    sa.Column("model_version", sa.String(80), nullable=False),
    sa.Column("feature_version", sa.String(40), nullable=False),
    sa.Column("policy_version", sa.String(40), nullable=False),
    sa.Column("probability", sa.Float(), nullable=False),
    sa.Column("anomaly_score", sa.Float(), nullable=False),
    sa.Column("graph_score", sa.Float(), nullable=False),
    sa.Column("rule_score", sa.Float(), nullable=False),
    sa.Column("risk_score", sa.Float(), nullable=False),
    sa.Column("risk_band", sa.String(20), nullable=False),
    sa.Column("evidence", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
incidents = sa.Table(
    "incidents", metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("prediction_id", sa.Integer(), sa.ForeignKey("predictions.id"), nullable=False),
    sa.Column("subscriber_id", sa.String(64), nullable=False),
    sa.Column("title", sa.String(180), nullable=False),
    sa.Column("status", sa.String(30), nullable=False),
    sa.Column("severity", sa.String(20), nullable=False),
    sa.Column("assigned_to", sa.String(80)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
audit_logs = sa.Table(
    "audit_logs", metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("actor", sa.String(80), nullable=False),
    sa.Column("action", sa.String(80), nullable=False),
    sa.Column("target", sa.String(100), nullable=False),
    sa.Column("reason", sa.Text()),
    sa.Column("details", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
notes = sa.Table(
    "incident_notes", metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("incident_id", sa.Integer(), sa.ForeignKey("incidents.id"), nullable=False),
    sa.Column("author", sa.String(80), nullable=False),
    sa.Column("body", sa.Text(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
model_runs = sa.Table(
    "model_runs", metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("version", sa.String(80), nullable=False, unique=True),
    sa.Column("algorithm", sa.String(80), nullable=False),
    sa.Column("dataset_version", sa.String(80), nullable=False),
    sa.Column("metrics", sa.JSON(), nullable=False),
    sa.Column("artifact_path", sa.String(255), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

for table, column in (
    (users, "username"),
    (events, "event_id"), (events, "event_time"), (events, "subscriber_id"),
    (events, "device_id"), (events, "network_token"),
    (predictions, "event_id"), (incidents, "prediction_id"),
):
    sa.Index(f"ix_{table.name}_{column}", table.c[column], unique=column in {"username", "event_id"})
sa.Index("ix_users_active", users.c.active)
sa.Index("ix_incidents_subscriber_id", incidents.c.subscriber_id)
sa.Index("ix_audit_logs_actor", audit_logs.c.actor)
sa.Index("ix_audit_logs_action", audit_logs.c.action)
sa.Index("ix_audit_logs_target", audit_logs.c.target)
sa.Index("ix_incident_notes_incident_id", notes.c.incident_id)


def upgrade():
    metadata.create_all(bind=op.get_bind())


def downgrade():
    metadata.drop_all(bind=op.get_bind())
