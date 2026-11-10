"use client";

import { useEffect, useState } from "react";
import { ArrowDownRight, ArrowUpRight, CircleHelp, Wallet } from "lucide-react";
import { tradingBotApi } from "@/lib/api/client";
import type { DashboardSummaryResponse, Money } from "@/lib/api/types";

function usd(value: Money | null): string {
  if (!value) return "Unavailable";
  const amount = Number(value.amount);
  if (!Number.isFinite(amount)) return "Invalid value";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: value.currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

function Card({
  label,
  value,
  detail,
  tone = "neutral",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: "neutral" | "positive" | "negative" | "unknown";
}) {
  const toneClass = {
    neutral: "text-slate-100",
    positive: "text-emerald-300",
    negative: "text-rose-300",
    unknown: "text-amber-300",
  }[tone];
  return (
    <section className="min-w-0 rounded-xl border border-[#263241] bg-[#0e151e] p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[8px] font-bold tracking-[.14em] text-slate-500">{label}</span>
        {tone === "unknown" ? <CircleHelp size={13} className="text-amber-300" /> : <Wallet size={13} className="text-slate-500" />}
      </div>
      <div className={`mt-2 truncate font-mono text-[19px] font-semibold ${toneClass}`}>{value}</div>
      <div className="mt-1 truncate text-[9px] text-slate-500">{detail}</div>
    </section>
  );
}

export function PaperAccountSummary() {
  const [summary, setSummary] = useState<DashboardSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    let controller: AbortController | null = null;
    let busy = false;
    const refresh = async () => {
      if (busy) return;
      busy = true;
      controller = new AbortController();
      try {
        const result = await tradingBotApi.summary(controller.signal);
        if (!disposed) {
          setSummary(result);
          setError(null);
        }
      } catch (reason) {
        if (!disposed && !(reason instanceof Error && reason.name === "AbortError")) {
          setError(reason instanceof Error ? reason.message : "Account summary unavailable.");
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

  const account = summary?.account;
  const net = account?.net_pnl ?? null;
  const netAmount = net ? Number(net.amount) : null;
  const netTone = netAmount === null ? "unknown" : netAmount > 0 ? "positive" : netAmount < 0 ? "negative" : "neutral";
  const mode = summary?.meta.environment ?? "UNKNOWN";

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2 px-1">
        <div className="text-[8px] font-bold tracking-[.15em] text-slate-500">PERSISTED PAPER ACCOUNT · {mode}</div>
        <div className="text-[8px] text-slate-500">
          {summary ? `Source: ${summary.meta.source}` : loading ? "Reading local account…" : "No account connection"}
        </div>
      </div>
      {error && <div className="rounded-lg border border-amber-400/15 bg-amber-400/[.04] px-3 py-2 text-[9px] text-amber-200">{error}</div>}
      <div className="grid grid-cols-2 gap-2 xl:grid-cols-4">
        <Card label="CASH BALANCE" value={account ? usd(account.balance) : loading ? "Loading…" : "Unavailable"} detail="Starting capital plus realized cash flows" />
        <Card label="ACCOUNT EQUITY" value={account ? usd(account.equity) : loading ? "Loading…" : "Unavailable"} detail="Cash balance plus marked open P&L" />
        <Card label="REALIZED NET P&L" value={account ? usd(account.realized_pnl) : loading ? "Loading…" : "Unavailable"} detail="Closed FIFO lots · fees included" tone={account?.realized_pnl && Number(account.realized_pnl.amount) > 0 ? "positive" : account?.realized_pnl && Number(account.realized_pnl.amount) < 0 ? "negative" : "neutral"} />
        <Card label="TOTAL NET P&L" value={net ? usd(net) : loading ? "Loading…" : "Unavailable"} detail="Equity minus virtual starting balance" tone={netTone} />
      </div>
    </div>
  );
}
