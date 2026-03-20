# File: migrations/versions/001_initial.py
"""Initial schema — trades, signals, portfolio_snapshots, backtest_results

Revision ID: 001_initial
Revises: 
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── trades ────────────────────────────────────────────────────────────────
    op.create_table(
        'trades',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('side', sa.String(4), nullable=False),
        sa.Column('quantity', sa.Float, nullable=False),
        sa.Column('entry_price', sa.Float, nullable=False),
        sa.Column('stop_loss', sa.Float, nullable=False),
        sa.Column('take_profit', sa.Float, nullable=False),
        sa.Column('status', sa.String(12), default='open'),
        sa.Column('exchange_order_id', sa.String(64), nullable=True),
        sa.Column('exit_price', sa.Float, nullable=True),
        sa.Column('exit_reason', sa.String(32), nullable=True),
        sa.Column('pnl', sa.Float, nullable=True),
        sa.Column('pnl_pct', sa.Float, nullable=True),
        sa.Column('strategy', sa.String(32), default='ai_driven'),
        sa.Column('signal_id', sa.String(36), nullable=True),
        sa.Column('is_paper', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime),
        sa.Column('closed_at', sa.DateTime, nullable=True),
    )
    op.create_index('ix_trades_symbol', 'trades', ['symbol'])
    op.create_index('ix_trades_status', 'trades', ['status'])
    op.create_index('ix_trades_created_at', 'trades', ['created_at'])
    op.create_index('ix_trades_symbol_status', 'trades', ['symbol', 'status'])

    # ── signals ───────────────────────────────────────────────────────────────
    op.create_table(
        'signals',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('signal', sa.String(16), nullable=False),
        sa.Column('confidence', sa.Float, nullable=False),
        sa.Column('reasoning', sa.Text, default=''),
        sa.Column('entry_price', sa.Float, nullable=False),
        sa.Column('stop_loss', sa.Float, nullable=False),
        sa.Column('take_profit', sa.Float, nullable=False),
        sa.Column('indicators_json', sa.Text, nullable=True),
        sa.Column('ai_analysis', sa.Text, nullable=True),
        sa.Column('timestamp', sa.DateTime),
    )
    op.create_index('ix_signals_symbol', 'signals', ['symbol'])
    op.create_index('ix_signals_timestamp', 'signals', ['timestamp'])

    # ── portfolio_snapshots ───────────────────────────────────────────────────
    op.create_table(
        'portfolio_snapshots',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('total_value', sa.Float, nullable=False),
        sa.Column('available_balance', sa.Float, nullable=False),
        sa.Column('invested_value', sa.Float, nullable=False),
        sa.Column('total_pnl', sa.Float, nullable=False),
        sa.Column('total_pnl_pct', sa.Float, nullable=False),
        sa.Column('daily_pnl', sa.Float, nullable=False),
        sa.Column('open_positions_count', sa.Integer, default=0),
        sa.Column('is_paper', sa.Boolean, default=True),
        sa.Column('recorded_at', sa.DateTime),
    )
    op.create_index('ix_portfolio_snapshots_recorded_at', 'portfolio_snapshots', ['recorded_at'])

    # ── backtest_results ──────────────────────────────────────────────────────
    op.create_table(
        'backtest_results',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('strategy', sa.String(32), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('timeframe', sa.String(8), default='1h'),
        sa.Column('start_date', sa.String(20), nullable=False),
        sa.Column('end_date', sa.String(20), nullable=False),
        sa.Column('initial_capital', sa.Float, nullable=False),
        sa.Column('final_capital', sa.Float, nullable=False),
        sa.Column('total_return_pct', sa.Float, nullable=False),
        sa.Column('total_trades', sa.Integer, nullable=False),
        sa.Column('winning_trades', sa.Integer, nullable=False),
        sa.Column('win_rate', sa.Float, nullable=False),
        sa.Column('max_drawdown_pct', sa.Float, nullable=False),
        sa.Column('sharpe_ratio', sa.Float, nullable=True),
        sa.Column('profit_factor', sa.Float, nullable=True),
        sa.Column('metrics_json', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime),
    )
    op.create_index('ix_backtest_results_strategy', 'backtest_results', ['strategy'])


def downgrade() -> None:
    op.drop_table('backtest_results')
    op.drop_table('portfolio_snapshots')
    op.drop_table('signals')
    op.drop_table('trades')
