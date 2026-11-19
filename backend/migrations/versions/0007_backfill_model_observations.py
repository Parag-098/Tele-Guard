"""Seed monitoring observations for predictions created before label monitoring."""

import sqlalchemy as sa
from alembic import op

revision = "0007_backfill_model_observations"
down_revision = "0006_context_serving_labels"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        sa.text(
            """
            INSERT INTO model_observations (
                prediction_id, model_version, serving_role, probability,
                predicted_label, outcome_label, evaluated_at, created_at
            )
            SELECT p.id, p.model_version, 'champion', p.probability,
                   CASE WHEN p.probability >= 0.5 THEN 1 ELSE 0 END,
                   p.ground_truth_label, p.label_received_at, p.created_at
            FROM predictions AS p
            WHERE NOT EXISTS (
                SELECT 1 FROM model_observations AS o WHERE o.prediction_id = p.id
            )
            """
        )
    )


def downgrade():
    # Keep monitoring evidence if the application is rolled back.
    pass
