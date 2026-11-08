"use client";

import { useMemo, useState } from "react";
import {
  Activity, AlertTriangle, ArrowDownRight, ArrowUpRight, Bell, Bot, BrainCircuit,
  CalendarDays, CheckCircle2, ChevronDown, CircleHelp, Clock3, Command, Database,
  Download, Gauge, LayoutDashboard, LineChart, Menu, MoreHorizontal, Play, Radio,
  Search, Settings2, Shield, ShieldAlert, SlidersHorizontal, Sparkles, Target,
  TrendingDown, TrendingUp, Wallet, X, Zap
} from "lucide-react";
import {
  Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis
} from "recharts";

type NavItem = { label: string; icon: typeof LayoutDashboard; section: string };

const navItems: NavItem[] = [
  { label: "Overview", icon: LayoutDashboard, section: "WORKSPACE" },
  { label: "Live Terminal", icon: Activity, section: "WORKSPACE" },
  { label: "Strategy Lab", icon: BrainCircuit, section: "RESEARCH" },
  { label: "Backtesting", icon: LineChart, section: "RESEARCH" },
  { label: "Trade History", icon: Clock3, section: "RESEARCH" },
  { label: "Risk Center", icon: Shield, section: "CONTROL" },
  { label: "Analytics", icon: Gauge, section: "CONTROL" },
  { label: "AI Analyst", icon: Sparkles, section: "TOOLS" },
  { label: "Data & Integrations", icon: Database, section: "TOOLS" },
  { label: "Settings", icon: Settings2, section: "SYSTEM" },
];

const equityData = [
  { time: "09:30", equity: 50000 }, { time: "09:45", equity: 50042 }, { time: "10:00", equity: 50018 },
  { time: "10:15", equity: 50110 }, { time: "10:30", equity: 50084 }, { time: "10:45", equity: 50148 },
  { time: "11:00", equity: 50120 }, { time: "11:15", equity: 50202 }, { time: "11:30", equity: 50182 },
  { time: "11:45", equity: 50255 }, { time: "12:00", equity: 50230 }, { time: "12:15", equity: 50318 },
  { time: "12:30", equity: 50302 }, { time: "12:45", equity: 50376 }, { time: "13:00", equity: 50348 },
  { time: "13:15", equity: 50420 }, { time: "13:30", equity: 50405 }, { time: "13:45", equity: 50486 },
  { time: "14:00", equity: 50462 }, { time: "14:15", equity: 50530 },
];

const trades = [
  { time: "14:12:08", symbol: "MNQ", side: "LONG", qty: 1, entry: "20,842.25", exit: "20,851.00", pnl: 17.50, status: "CLOSED" },
  { time: "13:48:32", symbol: "MES", side: "SHORT", qty: 1, entry: "5,942.50", exit: "5,940.75", pnl: 8.75, status: "CLOSED" },
  { time: "12:26:14", symbol: "MNQ", side: "LONG", qty: 1, entry: "20,816.00", exit: "20,810.25", pnl: -11.50, status: "CLOSED" },
  { time: "11:52:41", symbol: "MES", side: "LONG", qty: 1, entry: "5,938.25", exit: "5,943.00", pnl: 23.75, status: "CLOSED" },
];

const chartRanges = ["1D", "1W", "1M", "ALL"];

function MetricCard({ label, value, change, positive, icon: Icon, note }: {
  label: string; value: string; change?: string; positive?: boolean; icon: typeof Wallet; note: string;
}) {
  return (
    <div className="panel min-w-0 p-4 transition-colors hover:border-slate-600/80">
      <div className="flex items-center justify-between gap-2">
        <span className="eyebrow">{label}</span>
        <Icon size={16} className="text-slate-500" />
      </div>
      <div className="mt-3 flex flex-wrap items-end justify-between gap-2">
        <span className="mono text-[25px] font-semibold tracking-tight text-slate-100">{value}</span>
        {change && <span className={`mono mb-1 flex items-center gap-1 text-xs ${positive ? "text-emerald-400" : "text-rose-400"}`}>
          {positive ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}{change}
        </span>}
      </div>
      <p className="mt-1.5 text-[11px] text-slate-500">{note}</p>
    </div>
  );
}

function SectionTitle({ title, subtitle, action }: { title: string; subtitle?: string; action?: React.ReactNode }) {
  return <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
    <div><h2 className="text-sm font-semibold text-slate-100">{title}</h2>{subtitle && <p className="mt-1 text-[11px] text-slate-500">{subtitle}</p>}</div>
    {action}
  </div>;
}

export default function DashboardPage() {
  const [activeNav, setActiveNav] = useState("Overview");
  const [range, setRange] = useState("1D");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [toast, setToast] = useState("");
  const visibleTrades = useMemo(() => trades.filter(t => `${t.symbol} ${t.side} ${t.time}`.toLowerCase().includes(search.toLowerCase())), [search]);

  const notify = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 2600);
  };

  const groups = ["WORKSPACE", "RESEARCH", "CONTROL", "TOOLS", "SYSTEM"];
  return (
    <div className="min-h-screen text-slate-100">
      <div className="flex min-h-screen">
        <aside className={`fixed inset-y-0 left-0 z-40 flex w-[248px] flex-col border-r border-slate-800/90 bg-[#0b1017] transition-transform lg:static lg:translate-x-0 ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}`}>
          <div className="flex h-[76px] items-center justify-between border-b border-slate-800/80 px-5">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-cyan-400/20 bg-cyan-400/10 text-cyan-300"><Activity size={19} /></div>
              <div><div className="text-[15px] font-bold tracking-wide">Trading<span className="text-cyan-300">Bot</span></div><div className="text-[9px] tracking-[.18em] text-slate-500">QUANT WORKSPACE</div></div>
            </div>
            <button onClick={() => setSidebarOpen(false)} className="rounded-lg p-1 text-slate-500 hover:bg-slate-800 lg:hidden" aria-label="Close navigation"><X size={18}/></button>
          </div>
          <div className="px-4 pt-5">
            <div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900/70 p-3">
              <div className="flex items-center gap-2.5"><div className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,.7)]"/><div><div className="text-xs font-semibold">Paper Environment</div><div className="mt-0.5 text-[10px] text-slate-500">Local simulation</div></div></div>
              <ChevronDown size={14} className="text-slate-500"/>
            </div>
          </div>
          <nav className="scrollbar-none flex-1 overflow-y-auto px-3 py-5">
            {groups.map(group => <div key={group} className="mb-5">
              <div className="mb-2 px-3 text-[9px] font-bold tracking-[.16em] text-slate-600">{group}</div>
              {navItems.filter(item => item.section === group).map(item => {
                const Icon = item.icon; const active = activeNav === item.label;
                return <button key={item.label} onClick={() => { setActiveNav(item.label); setSidebarOpen(false); }} className={`mb-1 flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-[12px] transition-all ${active ? "border border-cyan-400/15 bg-cyan-400/[.09] font-semibold text-cyan-200" : "text-slate-400 hover:bg-slate-800/70 hover:text-slate-100"}`}>
                  <Icon size={16} className={active ? "text-cyan-300" : "text-slate-500"}/>{item.label}
                  {item.label === "Risk Center" && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-amber-400"/>}
                </button>;
              })}
            </div>)}
          </nav>
          <div className="border-t border-slate-800/80 p-4">
            <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-3">
              <div className="flex items-center gap-2 text-[11px] font-semibold text-slate-300"><Shield size={14} className="text-emerald-400"/> Safety systems active</div>
              <p className="mt-1.5 text-[10px] leading-relaxed text-slate-500">Live execution is not implemented in this build.</p>
            </div>
            <div className="mt-4 flex items-center gap-2.5 px-1">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-800 text-[10px] font-bold text-slate-300">SY</div>
              <div className="min-w-0 flex-1"><div className="truncate text-[11px] font-semibold">Workspace Owner</div><div className="text-[10px] text-slate-500">Local session</div></div>
              <MoreHorizontal size={17} className="text-slate-500"/>
            </div>
          </div>
        </aside>

        {sidebarOpen && <button className="fixed inset-0 z-30 bg-black/60 lg:hidden" onClick={() => setSidebarOpen(false)} aria-label="Close menu overlay"/>}

        <main className="min-w-0 flex-1">
          <header className="sticky top-0 z-20 flex h-[76px] items-center justify-between border-b border-slate-800/80 bg-[#0b1017]/90 px-4 backdrop-blur-xl sm:px-6 xl:px-8">
            <div className="flex min-w-0 items-center gap-3">
              <button onClick={() => setSidebarOpen(true)} className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 lg:hidden" aria-label="Open navigation"><Menu size={19}/></button>
              <div><div className="text-[13px] font-semibold">{activeNav}</div><div className="mt-0.5 hidden text-[10px] text-slate-500 sm:block">Your trading operations at a glance</div></div>
            </div>
            <div className="flex items-center gap-2 sm:gap-3">
              <div className="hidden items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 md:flex"><Command size={12} className="text-slate-500"/><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Filter recent trades..." className="w-36 bg-transparent text-[10px] text-slate-200 outline-none placeholder:text-slate-600"/><span className="text-[9px] text-slate-600">⌘ K</span></div>
              <div className="hidden items-center gap-1.5 rounded-lg border border-emerald-400/20 bg-emerald-400/[.07] px-2.5 py-2 sm:flex"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400"/><span className="text-[10px] font-semibold tracking-wide text-emerald-300">PAPER MODE</span></div>
              <div className="relative">
                <button onClick={() => setNotificationsOpen(!notificationsOpen)} className="relative rounded-lg border border-slate-800 p-2 text-slate-400 hover:bg-slate-800" aria-label="Notifications"><Bell size={16}/><span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-amber-400"/></button>
                {notificationsOpen && <div className="absolute right-0 top-11 w-64 rounded-xl border border-slate-700 bg-[#111923] p-3 shadow-2xl"><div className="text-xs font-semibold">Notifications</div><p className="mt-2 text-[11px] leading-relaxed text-slate-400">Demo workspace is active. No broker or live market connection is configured.</p></div>}
              </div>
              <button onClick={() => notify("Settings will be enabled after backend configuration.")} className="hidden rounded-lg border border-slate-800 p-2 text-slate-400 hover:bg-slate-800 sm:block" aria-label="Settings"><Settings2 size={16}/></button>
            </div>
          </header>

          <div className="mx-auto max-w-[1600px] px-4 py-6 sm:px-6 xl:px-8">
            <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
              <div><div className="flex items-center gap-2"><h1 className="text-[22px] font-semibold tracking-tight">Good afternoon<span className="text-cyan-300">.</span></h1><span className="rounded-md border border-slate-700 bg-slate-800/70 px-2 py-1 text-[9px] font-bold tracking-wider text-slate-400">DEMO</span></div><p className="mt-1.5 text-xs text-slate-500">Here&apos;s your system snapshot for today.</p></div>
              <div className="flex items-center gap-2"><button onClick={() => notify("Demo report export is not connected yet.")} className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-[11px] font-medium text-slate-300 hover:border-slate-500"><Download size={14}/> <span className="hidden sm:inline">Export report</span></button><button onClick={() => notify("Bot controls are disabled in the demo foundation.")} className="flex items-center gap-2 rounded-lg bg-cyan-300 px-3 py-2 text-[11px] font-bold text-slate-950 hover:bg-cyan-200"><Play size={13} fill="currentColor"/> <span>Bot controls</span></button></div>
            </div>

            <div className="mb-5 flex items-start gap-3 rounded-xl border border-amber-400/20 bg-amber-400/[.055] px-4 py-3">
              <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-300"/>
              <div className="min-w-0"><div className="text-[11px] font-semibold text-amber-200">Demo environment · No real trading activity</div><p className="mt-1 text-[10px] leading-relaxed text-amber-100/60">All figures, trades and chart points below are illustrative demo fixtures. No live market feed, broker account or order execution is connected.</p></div>
              <span className="ml-auto hidden shrink-0 rounded-md border border-amber-300/20 px-2 py-1 text-[9px] font-bold tracking-wider text-amber-200 sm:block">PAPER ONLY</span>
            </div>

            <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard label="Net P&L" value="+$486.25" change="+0.97%" positive icon={Wallet} note="Demo account · Today"/>
              <MetricCard label="Win rate" value="68.4%" change="+4.2%" positive icon={Target} note="13 wins · 6 losses"/>
              <MetricCard label="Profit factor" value="1.82" change="+0.18" positive icon={Activity} note="Gross profit / gross loss"/>
              <MetricCard label="Max drawdown" value="1.24%" change="−0.12%" positive icon={ShieldAlert} note="Peak-to-trough · Demo"/>
            </div>

            <div className="mb-5 grid grid-cols-1 gap-4 2xl:grid-cols-[minmax(0,1.7fr)_minmax(300px,.8fr)]">
              <section className="panel min-w-0 p-4 sm:p-5">
                <SectionTitle title="Account performance" subtitle="Illustrative equity curve · USD" action={<div className="flex rounded-lg border border-slate-800 bg-slate-950/60 p-1">{chartRanges.map(r => <button key={r} onClick={() => setRange(r)} className={`rounded-md px-2.5 py-1.5 text-[9px] font-semibold ${range === r ? "bg-slate-700 text-white" : "text-slate-500 hover:text-slate-200"}`}>{r}</button>)}</div>}/>
                <div className="mb-3 flex items-end gap-3"><div className="mono text-[27px] font-semibold tracking-tight">$50,486.25</div><div className="mb-1 flex items-center gap-1 text-[10px] text-emerald-400"><TrendingUp size={13}/> +$486.25 (0.97%)</div></div>
                <div className="h-[230px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={equityData} margin={{ top: 10, right: 8, left: -18, bottom: 0 }}>
                      <defs><linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#34d399" stopOpacity={.22}/><stop offset="95%" stopColor="#34d399" stopOpacity={0}/></linearGradient></defs>
                      <CartesianGrid stroke="#202a37" strokeDasharray="3 5" vertical={false}/>
                      <XAxis dataKey="time" tick={{ fill: "#64748b", fontSize: 9 }} axisLine={false} tickLine={false} minTickGap={25}/>
                      <YAxis domain={["dataMin - 100", "dataMax + 100"]} tick={{ fill: "#64748b", fontSize: 9 }} axisLine={false} tickLine={false} tickFormatter={v => `$${(v/1000).toFixed(1)}k`}/>
                      <Tooltip contentStyle={{ background: "#101721", border: "1px solid #2a3747", borderRadius: 9, fontSize: 11 }} labelStyle={{ color: "#94a3b8" }} formatter={(v) => [`$${Number(v).toLocaleString("en-US", {minimumFractionDigits:2})}`, "Equity"]}/>
                      <ReferenceLine y={50000} stroke="#475569" strokeDasharray="4 4"/>
                      <Area type="monotone" dataKey="equity" stroke="#34d399" strokeWidth={2} fill="url(#equityFill)" activeDot={{ r: 4, fill: "#34d399", stroke: "#0b1017", strokeWidth: 2 }}/>
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-slate-800/80 pt-3 text-[10px] text-slate-500"><span className="flex items-center gap-2"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400"/> Equity</span><span>Starting balance <b className="mono ml-1 text-slate-300">$50,000.00</b></span><span>Updated <b className="mono ml-1 text-slate-300">14:30:00 ET</b></span></div>
              </section>

              <section className="panel p-4 sm:p-5">
                <SectionTitle title="System health" subtitle="Local application status"/>
                <div className="mb-4 flex items-center justify-between rounded-xl border border-emerald-400/15 bg-emerald-400/[.045] p-3"><div className="flex items-center gap-2.5"><div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-400/10 text-emerald-300"><CheckCircle2 size={17}/></div><div><div className="text-[11px] font-semibold text-emerald-200">Safety checks active</div><div className="mt-0.5 text-[9px] text-slate-500">Demo UI · Backend not connected</div></div></div><span className="rounded-md bg-emerald-400/10 px-2 py-1 text-[8px] font-bold tracking-wider text-emerald-300">LOCAL</span></div>
                {[
                  { name: "Python engine", detail: "Not connected", state: "Pending", color: "bg-slate-500" },
                  { name: "Market data", detail: "No feed configured", state: "Offline", color: "bg-slate-500" },
                  { name: "Paper broker", detail: "Backend integration pending", state: "Pending", color: "bg-amber-400" },
                  { name: "Risk & compliance", detail: "UI status only", state: "Unverified", color: "bg-amber-400" },
                ].map(row => <div key={row.name} className="flex items-center justify-between border-b border-slate-800/70 py-3 last:border-0"><div className="flex items-center gap-2.5"><span className={`h-1.5 w-1.5 rounded-full ${row.color}`}/><div><div className="text-[11px] font-medium text-slate-300">{row.name}</div><div className="mt-0.5 text-[9px] text-slate-600">{row.detail}</div></div></div><span className="text-[9px] text-slate-500">{row.state}</span></div>)}
                <div className="mt-3 flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2.5 text-[10px] text-slate-500"><Radio size={13} className="text-slate-500"/> No live connection established</div>
              </section>
            </div>

            <div className="mb-5 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(280px,.8fr)]">
              <section className="panel min-w-0 p-4 sm:p-5">
                <SectionTitle title="Recent trades" subtitle="Latest simulated executions" action={<button onClick={() => setActiveNav("Trade History")} className="text-[10px] font-semibold text-cyan-300 hover:text-cyan-200">View all →</button>}/>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[570px] text-left">
                    <thead><tr className="border-b border-slate-800 text-[9px] uppercase tracking-wider text-slate-600"><th className="pb-3 font-semibold">Time</th><th className="pb-3 font-semibold">Instrument</th><th className="pb-3 font-semibold">Side</th><th className="pb-3 font-semibold">Qty</th><th className="pb-3 font-semibold">Entry → Exit</th><th className="pb-3 text-right font-semibold">Net P&L</th></tr></thead>
                    <tbody>{visibleTrades.map((trade, i) => <tr key={trade.time} className="border-b border-slate-800/60 last:border-0"><td className="mono py-3 text-[10px] text-slate-500">{trade.time}</td><td className="py-3 text-[11px] font-semibold">{trade.symbol}</td><td className="py-3"><span className={`rounded px-1.5 py-1 text-[8px] font-bold ${trade.side === "LONG" ? "bg-emerald-400/10 text-emerald-300" : "bg-rose-400/10 text-rose-300"}`}>{trade.side}</span></td><td className="mono py-3 text-[10px] text-slate-400">{trade.qty}</td><td className="mono py-3 text-[10px] text-slate-400">{trade.entry} <span className="text-slate-600">→</span> {trade.exit}</td><td className={`mono py-3 text-right text-[11px] font-semibold ${trade.pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>{trade.pnl >= 0 ? "+" : "−"}${Math.abs(trade.pnl).toFixed(2)}</td></tr>)}</tbody>
                  </table>
                  {visibleTrades.length === 0 && <div className="py-8 text-center text-xs text-slate-500">No demo trades match your filter.</div>}
                </div>
                <div className="mt-3 text-[9px] text-slate-600">Illustrative sample trades · Not broker records</div>
              </section>

              <section className="panel p-4 sm:p-5">
                <SectionTitle title="Risk overview" subtitle="Illustrative limits · USD"/>
                <div className="mb-4 flex items-center justify-between"><div><div className="text-[10px] text-slate-500">Daily loss used</div><div className="mono mt-1 text-xl font-semibold">$42.75 <span className="text-[10px] font-normal text-slate-500">/ $300</span></div></div><div className="rounded-lg bg-emerald-400/10 p-2 text-emerald-300"><Shield size={18}/></div></div>
                <div className="h-2 overflow-hidden rounded-full bg-slate-800"><div className="h-full w-[14.25%] rounded-full bg-emerald-400"/></div>
                <div className="mt-2 flex justify-between text-[9px] text-slate-500"><span>14.25% utilized</span><span>85.75% remaining</span></div>
                <div className="mt-5 space-y-3">
                  {[["Trades today","4 / 8"],["Open positions","0"],["Max contracts","1"],["Emergency halt","Not connected"]].map(([k,v]) => <div key={k} className="flex items-center justify-between border-b border-slate-800/70 pb-2.5 last:border-0"><span className="text-[10px] text-slate-500">{k}</span><span className="mono text-[10px] text-slate-300">{v}</span></div>)}
                </div>
                <div className="mt-2 flex items-center gap-2 rounded-lg border border-amber-400/15 bg-amber-400/[.04] px-3 py-2 text-[9px] leading-relaxed text-amber-200/70"><AlertTriangle size={12} className="shrink-0"/> Risk values are examples, not active enforcement.</div>
              </section>
            </div>

            <div className="mb-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
              <section className="panel p-4 sm:p-5">
                <SectionTitle title="Strategy monitor" subtitle="Research candidates · Not running"/>
                <div className="space-y-3">
                  {[{name:"MNQ ORB15",desc:"Opening range breakout · 15m",tag:"RESEARCH",score:"Pending validation"},{name:"MES VWAP Pullback",desc:"Trend continuation · Intraday",tag:"DRAFT",score:"Not evaluated"},{name:"Compression Breakout",desc:"Volatility expansion · Intraday",tag:"DRAFT",score:"Not evaluated"}].map((s,i)=><div key={s.name} className="flex items-center gap-3 rounded-lg border border-slate-800/80 bg-slate-950/30 p-3"><div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-800 text-slate-400">{i === 0 ? <Zap size={15}/> : <BrainCircuit size={15}/>}</div><div className="min-w-0 flex-1"><div className="text-[11px] font-semibold">{s.name}</div><div className="mt-0.5 text-[9px] text-slate-500">{s.desc}</div></div><div className="text-right"><div className="text-[8px] font-bold tracking-wider text-slate-400">{s.tag}</div><div className="mt-1 text-[9px] text-slate-600">{s.score}</div></div></div>)}
                </div>
              </section>
              <section className="panel p-4 sm:p-5">
                <SectionTitle title="Research assistant" subtitle="AI support · Advisory only"/>
                <div className="flex items-start gap-3 rounded-xl border border-cyan-400/15 bg-cyan-400/[.045] p-3"><div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-cyan-400/10 text-cyan-300"><Sparkles size={16}/></div><div><div className="text-[11px] font-semibold text-slate-200">Research workspace ready</div><p className="mt-1 text-[10px] leading-relaxed text-slate-500">Connect experiment reports and trade logs to generate grounded summaries. AI will not place trades or modify risk controls.</p></div></div>
                <div className="mt-3 flex flex-wrap gap-2">{["Review latest backtest","Explain risk limits","Compare MES vs MNQ"].map(q=><button key={q} onClick={() => notify("AI Analyst becomes available after verified research data is connected.")} className="rounded-lg border border-slate-800 px-2.5 py-2 text-[9px] text-slate-400 hover:border-slate-600 hover:text-slate-200">{q}</button>)}</div>
              </section>
            </div>
            <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-800/70 py-4 text-[9px] text-slate-600"><span>TradingBot · Research-first futures workspace</span><span className="flex items-center gap-1.5"><Shield size={11}/> Paper-only foundation · No live execution</span><span>UI foundation v0.1.0</span></footer>
          </div>
        </main>
      </div>
      {toast && <div role="status" className="fixed bottom-5 right-5 z-50 rounded-xl border border-slate-700 bg-[#17212d] px-4 py-3 text-xs text-slate-200 shadow-2xl">{toast}</div>}
    </div>
  );
}
