import type {
  DashboardSummaryResponse,
  EquityPoint,
  HealthResponse,
  OperationalEvent,
  Page,
  Position,
  RiskSnapshotResponse,
  Trade,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string = "API_ERROR",
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const API_BASE = process.env.NEXT_PUBLIC_TRADINGBOT_API_URL ?? "";

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal,
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new ApiError("TradingBot API is unreachable.", 0, "NETWORK_ERROR");
  }

  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail =
      typeof body === "object" && body !== null && "detail" in body &&
      typeof body.detail === "string"
        ? body.detail
        : `TradingBot API returned HTTP ${response.status}.`;
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

/** Read-only endpoints. No order, settings or risk mutation method is exposed. */
export const tradingBotApi = {
  health: (signal?: AbortSignal) => request<HealthResponse>("/health", signal),
  summary: (signal?: AbortSignal) =>
    request<DashboardSummaryResponse>("/api/v1/dashboard/summary", signal),
  positions: (signal?: AbortSignal) =>
    request<Page<Position>>("/api/v1/positions", signal),
  trades: (limit = 50, cursor?: string, signal?: AbortSignal) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cursor) params.set("cursor", cursor);
    return request<Page<Trade>>(`/api/v1/trades?${params.toString()}`, signal);
  },
  equity: (range = "1d", signal?: AbortSignal) =>
    request<{ items: EquityPoint[] }>(
      `/api/v1/performance/equity?range=${encodeURIComponent(range)}`,
      signal,
    ),
  risk: (signal?: AbortSignal) =>
    request<RiskSnapshotResponse>("/api/v1/risk/snapshot", signal),
  events: (limit = 50, cursor?: string, signal?: AbortSignal) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cursor) params.set("cursor", cursor);
    return request<Page<OperationalEvent>>(
      `/api/v1/events?${params.toString()}`,
      signal,
    );
  },
};
