"""Persist revocable sessions and MLOps demonstration records."""

from alembic import op
from app import models  # noqa: F401

revision = "0003_mlops_sessions"
down_revision = "0002_response_actions"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    models.AuthSession.__table__.create(bind=bind, checkfirst=True)
    models.DemoDataset.__table__.create(bind=bind, checkfirst=True)
    models.MLOpsRecord.__table__.create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    models.MLOpsRecord.__table__.drop(bind=bind, checkfirst=True)
    models.DemoDataset.__table__.drop(bind=bind, checkfirst=True)
    models.AuthSession.__table__.drop(bind=bind, checkfirst=True)
