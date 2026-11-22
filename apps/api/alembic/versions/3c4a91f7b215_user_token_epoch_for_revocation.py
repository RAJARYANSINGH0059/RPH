"""user token epoch for stateless revocation

Adds users.token_epoch. Every token carries the epoch it was minted under; raising the value invalidates every token
already issued to that principal, which is what signing out and an administrator revocation do. Additive and
backward-compatible: existing rows default to 0, which is the epoch tokens without the claim are treated as.

Revision ID: 3c4a91f7b215
Revises: 2222d8017e5e
"""
from alembic import op
import sqlalchemy as sa

revision = "3c4a91f7b215"
down_revision = "2222d8017e5e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("token_epoch", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("users", "token_epoch")
