"""Phase 3 approvals table.

Revision ID: 004_phase3_approvals
Revises: 003_phase2_market_data
"""

from alembic import op
import sqlalchemy as sa

revision = "004_phase3_approvals"
down_revision = "003_phase2_market_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("position_usd", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("trade_payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decided_by", sa.String(100), nullable=True),
    )
    op.create_index("ix_approval_requests_symbol", "approval_requests", ["symbol"])
    op.create_index("ix_approval_requests_status", "approval_requests", ["status"])
    op.create_index("ix_approval_requests_created_at", "approval_requests", ["created_at"])


def downgrade() -> None:
    op.drop_table("approval_requests")
