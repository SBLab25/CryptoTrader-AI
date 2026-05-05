"""Phase 2 market data and signal persistence tables.

Revision ID: 003_phase2_market_data
Revises: 002_phase1_security
"""

from alembic import op
import sqlalchemy as sa

revision = "003_phase2_market_data"
down_revision = "002_phase1_security"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ohlcv",
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default="rest"),
        sa.PrimaryKeyConstraint("timestamp", "symbol"),
    )

    op.create_table(
        "signal_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("strategy", sa.String(50), nullable=False, server_default="ai_llm_ta"),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("take_profit", sa.Float(), nullable=True),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("rsi", sa.Float(), nullable=True),
        sa.Column("macd_histogram", sa.Float(), nullable=True),
        sa.Column("bb_percent_b", sa.Float(), nullable=True),
        sa.Column("ema_trend", sa.String(20), nullable=True),
        sa.Column("atr", sa.Float(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("llm_provider", sa.String(50), nullable=True),
        sa.Column("llm_model", sa.String(100), nullable=True),
        sa.Column("llm_latency_ms", sa.Integer(), nullable=True),
        sa.Column("risk_passed", sa.Boolean(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("trade_id", sa.String(36), nullable=True),
        sa.Column("qdrant_stored", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("mode", sa.String(20), nullable=False, server_default="paper"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_signal_log_symbol", "signal_log", ["symbol"])
    op.create_index("ix_signal_log_created_at", "signal_log", ["created_at"])

    op.create_table(
        "exchange_credentials",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("exchange", sa.String(50), nullable=False),
        sa.Column("label", sa.String(100), nullable=True),
        sa.Column("api_key_enc", sa.LargeBinary(), nullable=False),
        sa.Column("api_secret_enc", sa.LargeBinary(), nullable=False),
        sa.Column("permissions_json", sa.Text(), nullable=False, server_default='["trade","read"]'),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_exchange_credentials_exchange", "exchange_credentials", ["exchange"])


def downgrade() -> None:
    op.drop_table("exchange_credentials")
    op.drop_table("signal_log")
    op.drop_table("ohlcv")
