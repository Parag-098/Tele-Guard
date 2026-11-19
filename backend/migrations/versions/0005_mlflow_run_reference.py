"""Store MLflow run IDs so model artifacts can be restored from remote storage."""

import sqlalchemy as sa
from alembic import op

revision = "0005_mlflow_run_reference"
down_revision = "0004_shap_resolution"
branch_labels = None
depends_on = None


def upgrade():
    if "mlflow_run_id" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("model_runs")}:
        op.add_column("model_runs", sa.Column("mlflow_run_id", sa.String(64), nullable=True))


def downgrade():
    op.drop_column("model_runs", "mlflow_run_id")
