export type TradingMode = "demo" | "paper" | "live";

export interface SystemStatus {
  trading_active: boolean;
  cycle_count: number;
  last_cycle_at: string | null;
  symbols: string[];
  active_symbols: string[];
  open_positions: number;
  trading_paused: boolean;
  mode: TradingMode;
  llm_provider: string;
  llm_model: string;
  performance?: {
    total_trades?: number;
    win_rate_pct?: number;
    profit_factor?: number;
    peak_portfolio?: number;
  };
  circuit_breakers?: Record<string, { state?: string }>;
}

export interface Position {
  id: string;
  symbol: string;
  side: "long" | "short";
  entry_price: number;
  current_price: number;
  usd_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  stop_loss: number;
  take_profit: number;
  opened_at: string;
}

export interface Portfolio {
  total_value: number;
  unrealized_pnl: number;
  realized_pnl: number;
  win_rate: number;
  profit_factor: number;
  max_drawdown: number;
  available_balance: number;
  invested_value: number;
  total_pnl_pct: number;
}

export interface Signal {
  id: string;
  symbol: string;
  direction: "buy" | "sell" | "hold";
  confidence: number;
  reasoning: string;
  strategy: string;
  risk_approved: boolean;
  timestamp: string;
}

export interface RiskStatus {
  paused: boolean;
  pause_reason: string | null;
  daily_loss_pct: number;
  current_drawdown: number;
  open_positions: number;
  circuit_breaker_state: "closed" | "open" | "half_open";
  correlation_graph_nodes: number;
  stop_loss_pct: number;
  take_profit_pct: number;
  max_open_positions: number;
}

export interface ApprovalRequest {
  id: string;
  symbol: string;
  side: "buy" | "sell";
  usd_amount: number;
  confidence: number;
  status: "pending" | "approved" | "denied" | "expired";
  created_at: string;
  expires_at: string;
  strategy: string;
  reasoning: string;
  risk_reward: number;
  stop_loss: number;
  take_profit: number;
}

export interface TrainingStatus {
  running: boolean;
  symbol?: string;
  timesteps?: number;
  episode: number;
  total_episodes: number;
  sharpe_ratio: number;
  win_rate: number;
  avg_reward: number;
  best_reward: number;
  current_date: string | null;
  replay_speed: number;
  checkpoint_saved: boolean;
  model_path?: string | null;
}

export interface Trade {
  id: string;
  symbol: string;
  side: "buy" | "sell";
  strategy: string;
  entry_price: number;
  exit_price: number | null;
  confidence: number;
  realized_pnl: number | null;
  realized_pnl_pct: number | null;
  opened_at: string;
  status: string;
}

export interface EquityPoint {
  time: number;
  value: number;
}

export interface OHLCV {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface WSEvent {
  type: string;
  data: any;
}
