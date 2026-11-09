/** Stable, read-only API contract shared by the dashboard and Python service.
 * Monetary values are decimal strings to avoid binary floating-point ambiguity.
 * All timestamps are ISO-8601 UTC strings.
 */

export type EnvironmentState = "DEMO" | "PAPER" | "DISCONNECTED" | "STALE" | "ERROR";
export type ConnectionState = "CONNECTED" | "DISCONNECTED" | "DELAYED" | "UNKNOWN";

export interface ApiMeta {
  as_of: string;
  environment: EnvironmentState;
  source: string;
}

export interface HealthResponse {
  status: "ok" | "degraded" | "error";
  version: string;
  timestamp: string;
}

export interface Money {
  amount: string;
  currency: "USD";
}

export interface DashboardSummaryResponse {
  meta: ApiMeta;
  account: {
    balance: Money | null;
    equity: Money | null;
    realized_pnl: Money | null;
    unrealized_pnl: Money | null;
    net_pnl: Money | null;
    max_drawdown: Money | null;
  };
  strategy: {
    name: string | null;
    state: "IDLE" | "RUNNING" | "HALTED" | "ERROR" | "UNKNOWN";
  };
  market_data: {
    connection: ConnectionState;
    last_update: string | null;
    symbols: string[];
  };
}

export interface Position {
  id: string;
  symbol: string;
  side: "LONG" | "SHORT";
  quantity: number;
  average_price: string;
  unrealized_pnl: Money | null;
  opened_at: string;
}

export interface Trade {
  id: string;
  symbol: string;
  side: "LONG" | "SHORT";
  quantity: number;
  entry_time: string;
  exit_time: string;
  entry_price: string;
  exit_price: string;
  net_pnl: Money;
  exit_reason: string;
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface EquityPoint {
  timestamp: string;
  equity: Money;
}

export interface RiskSnapshotResponse {
  meta: ApiMeta;
  gate: "PASS" | "BLOCK" | "UNKNOWN";
  reasons: string[];
  daily_loss_used: Money | null;
  daily_loss_limit: Money | null;
  open_positions: number;
  max_positions: number | null;
}

export interface OperationalEvent {
  id: string;
  timestamp: string;
  severity: "INFO" | "WARNING" | "ERROR";
  category: string;
  message: string;
}
