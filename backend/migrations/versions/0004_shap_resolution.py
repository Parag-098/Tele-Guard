"""Persist per-prediction SHAP values and incident resolution provenance."""

import sqlalchemy as sa
from alembic import op

revision = "0004_shap_resolution"
down_revision = "0003_mlops_sessions"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    for table, column in (
        ("predictions", sa.Column("explanation", sa.JSON(), nullable=True)),
        ("incidents", sa.Column("resolution_outcome", sa.String(30), nullable=True)),
        ("incidents", sa.Column("resolution_reason", sa.Text(), nullable=True)),
        ("incidents", sa.Column("resolved_by", sa.String(80), nullable=True)),
        ("incidents", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True)),
    ):
        if column.name not in {c["name"] for c in sa.inspect(bind).get_columns(table)}:
            op.add_column(table, column)


def downgrade():
    op.drop_column("incidents", "resolved_at")
    op.drop_column("incidents", "resolved_by")
    op.drop_column("incidents", "resolution_reason")
    op.drop_column("incidents", "resolution_outcome")
    op.drop_column("predictions", "explanation")
