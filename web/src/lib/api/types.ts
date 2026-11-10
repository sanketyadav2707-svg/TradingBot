/** API contracts for the read-only local TradingBot service.
 * Money is serialized as decimal strings. Null means unavailable, not zero.
 */

export type EnvironmentState = "DEMO" | "PAPER" | "DISCONNECTED" | "STALE" | "ERROR";
export type ConnectionState = "CONNECTED" | "DISCONNECTED" | "DELAYED" | "UNKNOWN";
export type DataAvailability = "AVAILABLE" | "NOT_CONFIGURED" | "NOT_PERSISTED" | "NOT_IMPLEMENTED";

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
  mark_price: string | null;
  mark_timestamp: string | null;
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

export interface AvailabilityPage<T> {
  availability: DataAvailability;
  items: T[];
  next_cursor: string | null;
  reason: string | null;
}

export interface InstrumentMetadata {
  symbol: string;
  name: string;
  exchange: string;
  tick_size: string;
  tick_value_usd: Money;
  point_value_usd: Money;
}

export interface InstrumentsResponse {
  availability: "AVAILABLE" | "NOT_CONFIGURED";
  source: string;
  items: InstrumentMetadata[];
  reason: string | null;
}

export interface PaperFill {
  order_id: string;
  symbol: string;
  side: "LONG" | "SHORT";
  quantity: number;
  requested_price: string;
  fill_price: string;
  commission: Money;
  timestamp: string;
}

export interface EquityPoint {
  timestamp: string;
  equity: Money;
}

export interface EquityResponse {
  availability: DataAvailability;
  items: EquityPoint[];
  reason: string | null;
  range: "1d" | "1w" | "1m" | "all";
}

export interface RiskSnapshotResponse {
  meta: ApiMeta;
  gate: "PASS" | "BLOCK" | "UNKNOWN";
  reasons: string[];
  daily_loss_used: Money | null;
  daily_loss_limit: Money | null;
  open_positions: number | null;
  max_contracts: number | null;
}

export interface OperationalEvent {
  id: string;
  timestamp: string;
  severity: "INFO" | "WARNING" | "ERROR";
  category: string;
  message: string;
}
