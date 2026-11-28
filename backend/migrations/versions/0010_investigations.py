"""Add correlated case links, reversible consolidations and audited adjudication."""

import sqlalchemy as sa
from alembic import op

revision = "0010_investigations"
down_revision = "0009_continuous_operations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "case_predictions",
        sa.Column("prediction_id", sa.Integer(), sa.ForeignKey("predictions.id"), primary_key=True),
        sa.Column("incident_id", sa.Integer(), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("decision", sa.String(40), nullable=False),
        sa.Column("actor", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_case_predictions_incident_id", "case_predictions", ["incident_id"])
    op.create_table(
        "case_merges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("target_id", sa.Integer(), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("actor", sa.String(80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reversed_at", sa.DateTime(timezone=True)),
        sa.Column("reversed_by", sa.String(80)),
        sa.Column("reversal_reason", sa.Text()),
    )
    op.create_index("ix_case_merges_source_id", "case_merges", ["source_id"])
    op.create_index("ix_case_merges_target_id", "case_merges", ["target_id"])
    op.create_table(
        "adjudications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.String(36), unique=True),
        sa.Column("incident_id", sa.Integer(), sa.ForeignKey("incidents.id")),
        sa.Column("prediction_id", sa.Integer(), sa.ForeignKey("predictions.id")),
        sa.Column("correction_of", sa.Integer(), sa.ForeignKey("adjudications.id")),
        sa.Column("outcome", sa.String(30), nullable=False),
        sa.Column("reviewer", sa.String(80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(incident_id IS NULL) <> (prediction_id IS NULL)", name="ck_adjudication_scope"
        ),
    )
    op.create_index("ix_adjudications_incident_id", "adjudications", ["incident_id"])
    op.create_index("ix_adjudications_prediction_id", "adjudications", ["prediction_id"])


def downgrade():
    op.drop_table("adjudications")
    op.drop_table("case_merges")
    op.drop_table("case_predictions")
