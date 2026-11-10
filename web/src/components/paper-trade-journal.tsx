"use client";

import { useEffect, useState } from "react";
import { Clock3, Database, RefreshCw } from "lucide-react";
import { tradingBotApi } from "@/lib/api/client";
import type { Position, Trade } from "@/lib/api/types";

function amount(value: string | null | undefined): string {
  if (value === null || value === undefined) return "Awaiting mark";
  const number = Number(value);
  return Number.isFinite(number)
    ? new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(number)
    : "Unavailable";
}

function pnl(value: { amount: string; currency: "USD" } | null): string {
  if (!value) return "Awaiting mark";
  const n = Number(value.amount);
  if (!Number.isFinite(n)) return "Unavailable";
  const formatted = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Math.abs(n));
  return `${n > 0 ? "+" : n < 0 ? "−" : ""}${formatted}`;
}

export function PaperTradeJournal() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    let busy = false;
    let controller: AbortController | null = null;
    const refresh = async () => {
      if (busy) return;
      busy = true;
      controller = new AbortController();
      try {
        const [positionPage, tradePage] = await Promise.all([
          tradingBotApi.positions(controller.signal),
          tradingBotApi.trades(25, undefined, controller.signal),
        ]);
        if (!disposed) {
          if (positionPage.availability === "AVAILABLE") setPositions(positionPage.items);
          if (tradePage.availability === "AVAILABLE") setTrades(tradePage.items);
          setError(null);
        }
      } catch (reason) {
        if (!disposed && !(reason instanceof Error && reason.name === "AbortError")) {
          setError(reason instanceof Error ? reason.message : "Paper ledger unavailable.");
        }
      } finally {
        busy = false;
        if (!disposed) setLoading(false);
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 15_000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
      controller?.abort();
    };
  }, []);

  return (
    <div className="space-y-3">
      <section className="rounded-xl border border-[#263241] bg-[#0e151e]">
        <div className="flex items-center justify-between border-b border-[#202b38] px-3.5 py-3">
          <div>
            <h2 className="text-[11px] font-semibold">Open paper positions</h2>
            <p className="mt-0.5 text-[8px] text-slate-500">PERSISTED FIFO LOT BOOK · NO BROKER CONNECTION</p>
          </div>
          <span className="font-mono text-[10px] text-slate-300">{positions.length} symbols</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[620px] text-left">
            <thead><tr className="text-[8px] tracking-wider text-slate-600"><th className="px-3 py-2">SYMBOL</th><th className="px-3 py-2">SIDE</th><th className="px-3 py-2 text-right">QTY</th><th className="px-3 py-2 text-right">AVG ENTRY</th><th className="px-3 py-2 text-right">UNREALIZED P&L</th><th className="px-3 py-2">OPENED</th></tr></thead>
            <tbody>
              {positions.map((position) => (
                <tr key={position.id} className="border-t border-[#202b38]/70 text-[9px]">
                  <td className="px-3 py-3 font-mono font-bold">{position.symbol}</td>
                  <td className={`px-3 py-3 font-bold ${position.side === "LONG" ? "text-emerald-300" : "text-rose-300"}`}>{position.side}</td>
                  <td className="px-3 py-3 text-right font-mono">{position.quantity}</td>
                  <td className="px-3 py-3 text-right font-mono">{amount(position.average_price)}</td>
                  <td className="px-3 py-3 text-right font-mono">{pnl(position.unrealized_pnl)}</td>
                  <td className="px-3 py-3 text-slate-500">{new Date(position.opened_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!positions.length && <div className="px-3 py-8 text-center text-[10px] text-slate-500">{loading ? "Loading account positions…" : "No open paper positions."}</div>}
        </div>
      </section>

      <section className="rounded-xl border border-[#263241] bg-[#0e151e]">
        <div className="flex items-center justify-between border-b border-[#202b38] px-3.5 py-3">
          <div>
            <h2 className="text-[11px] font-semibold">Closed paper trades</h2>
            <p className="mt-0.5 text-[8px] text-slate-500">FIFO MATCHED LOTS · COMMISSIONS INCLUDED IN NET P&L</p>
          </div>
          <span className="font-mono text-[10px] text-slate-300">{trades.length} loaded</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px] text-left">
            <thead><tr className="text-[8px] tracking-wider text-slate-600"><th className="px-3 py-2">EXIT TIME</th><th className="px-3 py-2">SYMBOL</th><th className="px-3 py-2">SIDE</th><th className="px-3 py-2 text-right">QTY</th><th className="px-3 py-2 text-right">ENTRY</th><th className="px-3 py-2 text-right">EXIT</th><th className="px-3 py-2 text-right">NET P&L</th></tr></thead>
            <tbody>
              {trades.map((trade) => {
                const n = Number(trade.net_pnl.amount);
                return <tr key={trade.id} className="border-t border-[#202b38]/70 text-[9px]">
                  <td className="px-3 py-3 text-slate-500">{new Date(trade.exit_time).toLocaleString()}</td>
                  <td className="px-3 py-3 font-mono font-bold">{trade.symbol}</td>
                  <td className={`px-3 py-3 font-bold ${trade.side === "LONG" ? "text-emerald-300" : "text-rose-300"}`}>{trade.side}</td>
                  <td className="px-3 py-3 text-right font-mono">{trade.quantity}</td>
                  <td className="px-3 py-3 text-right font-mono">{amount(trade.entry_price)}</td>
                  <td className="px-3 py-3 text-right font-mono">{amount(trade.exit_price)}</td>
                  <td className={`px-3 py-3 text-right font-mono font-bold ${n >= 0 ? "text-emerald-300" : "text-rose-300"}`}>{pnl(trade.net_pnl)}</td>
                </tr>;
              })}
            </tbody>
          </table>
          {!trades.length && <div className="px-3 py-8 text-center text-[10px] text-slate-500">No completed paper trades yet. Closed trades appear here after an opposing paper fill.</div>}
        </div>
      </section>

      <div className="flex flex-wrap items-center justify-between gap-2 text-[8px] text-slate-500">
        <span className="flex items-center gap-1.5"><Database size={10}/> Persistent local SQLite ledger</span>
        <span className="flex items-center gap-1.5"><Clock3 size={10}/> Refreshes every 15 seconds</span>
        {error && <span className="text-rose-300">{error}</span>}
        <span className="flex items-center gap-1"><RefreshCw size={9}/> Read-only view</span>
      </div>
    </div>
  );
}
