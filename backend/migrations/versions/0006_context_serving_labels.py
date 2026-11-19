"""Context features, per-model observations and delayed labels."""
import sqlalchemy as sa
from alembic import op

revision = "0006_context_serving_labels"
down_revision = "0005_mlflow_run_reference"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    for table, column in (
        ("events", sa.Column("latitude", sa.Float(), nullable=True)),
        ("events", sa.Column("longitude", sa.Float(), nullable=True)),
        ("predictions", sa.Column("ground_truth_label", sa.Integer(), nullable=True)),
        ("predictions", sa.Column("label_source", sa.String(length=80), nullable=True)),
        ("predictions", sa.Column("label_received_at", sa.DateTime(timezone=True), nullable=True)),
    ):
        if column.name not in {c["name"] for c in sa.inspect(bind).get_columns(table)}:
            op.add_column(table, column)
    if not sa.inspect(bind).has_table("model_observations"):
        op.create_table(
            "model_observations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("prediction_id", sa.Integer(), sa.ForeignKey("predictions.id"), nullable=False),
            sa.Column("model_version", sa.String(length=80), nullable=False),
            sa.Column("serving_role", sa.String(length=20), nullable=False),
            sa.Column("probability", sa.Float(), nullable=False),
            sa.Column("predicted_label", sa.Integer(), nullable=False),
            sa.Column("outcome_label", sa.Integer(), nullable=True),
            sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    indexes = {ix["name"] for ix in sa.inspect(bind).get_indexes("model_observations")}
    if "ix_model_observations_prediction_id" not in indexes:
        op.create_index("ix_model_observations_prediction_id", "model_observations", ["prediction_id"])
    if "ix_model_observations_model_version" not in indexes:
        op.create_index("ix_model_observations_model_version", "model_observations", ["model_version"])


def downgrade():
    op.drop_index("ix_model_observations_model_version", table_name="model_observations")
    op.drop_index("ix_model_observations_prediction_id", table_name="model_observations")
    op.drop_table("model_observations")
    op.drop_column("predictions", "label_received_at")
    op.drop_column("predictions", "label_source")
    op.drop_column("predictions", "ground_truth_label")
    op.drop_column("events", "longitude")
    op.drop_column("events", "latitude")
