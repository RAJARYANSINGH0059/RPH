"""shared rate limit events

One row per counted request against a rate-limit bucket, so limits hold across workers and instances instead of
living in a per-process dictionary. Rows expire by time; see app/services/ratelimit.py.

Revision ID: 4d7b2e8c9a31
Revises: 3c4a91f7b215
"""
from alembic import op
import sqlalchemy as sa

revision = "4d7b2e8c9a31"
down_revision = "3c4a91f7b215"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rate_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("bucket", sa.String(length=160), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rate_events_bucket", "rate_events", ["bucket"])
    op.create_index("ix_rate_events_at", "rate_events", ["at"])
    # The pair is what every lookup filters on.
    op.create_index("ix_rate_events_bucket_at", "rate_events", ["bucket", "at"])


def downgrade() -> None:
    op.drop_index("ix_rate_events_bucket_at", table_name="rate_events")
    op.drop_index("ix_rate_events_at", table_name="rate_events")
    op.drop_index("ix_rate_events_bucket", table_name="rate_events")
    op.drop_table("rate_events")
