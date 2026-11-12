"""Persist simulated response actions and reversal history."""

from alembic import op
from app import models

revision = "0002_response_actions"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    models.ResponseAction.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade():
    models.ResponseAction.__table__.drop(bind=op.get_bind())
