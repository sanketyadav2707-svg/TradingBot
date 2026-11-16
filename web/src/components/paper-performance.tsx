"use client";

import { useEffect, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { tradingBotApi } from "@/lib/api/client";
import type { DashboardSummaryResponse, EquityPoint, Money } from "@/lib/api/types";

function formatMoney(value: Money | null | undefined): string {
  if (!value) return "Unavailable";
  const amount = Number(value.amount);
  if (!Number.isFinite(amount)) return "Unavailable";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: value.currency,
  }).format(amount);
}

export function PaperPerformance() {
  const [points,setPoints] = useState<EquityPoint[]>([]);
  const [summary,setSummary] = useState<DashboardSummaryResponse | null>(null);
  const [loading,setLoading] = useState(true);
  const [error,setError] = useState<string | null>(null);

  useEffect(()=>{
    let disposed=false;
    let controller:AbortController|null=null;
    let busy=false;
    const refresh=async()=>{
      if(busy)return;
      busy=true;
      controller=new AbortController();
      try{
        const [equity,account]=await Promise.all([
          tradingBotApi.equity("all",controller.signal),
          tradingBotApi.summary(controller.signal),
        ]);
        if(!disposed){
          setPoints(equity.items);
          setSummary(account);
          setError(null);
        }
      }catch(reason){
        if(!disposed && !(reason instanceof Error && reason.name==="AbortError")){
          setError(reason instanceof Error?reason.message:"Performance data unavailable.");
        }
      }finally{
        busy=false;
        if(!disposed)setLoading(false);
      }
    };
    void refresh();
    const timer=window.setInterval(()=>void refresh(),15000);
    return ()=>{disposed=true;window.clearInterval(timer);controller?.abort();};
  },[]);

  const latest=points.at(-1)?.equity ?? null;
  const net=summary?.account.net_pnl ?? null;
  const chartCurrency=points[0]?.equity.currency ?? summary?.account.equity?.currency ?? "USD";

  return <div className="space-y-3">
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
      {[["CURRENT EQUITY",formatMoney(latest)],["TOTAL NET P&L",formatMoney(net)],["MAX DRAWDOWN",formatMoney(summary?.account.max_drawdown)]].map(([label,value])=>
        <section key={label} className="rounded-xl border border-[#263241] bg-[#0e151e] p-3">
          <div className="text-[8px] font-bold tracking-widest text-slate-500">{label}</div>
          <div className="mt-2 font-mono text-[18px] font-semibold">{value}</div>
          <div className="mt-1 text-[8px] text-slate-500">Source: persisted paper-account snapshots</div>
        </section>)}
    </div>
    <section className="rounded-xl border border-[#263241] bg-[#0e151e] p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div><h2 className="text-[11px] font-semibold">Persisted equity history</h2><p className="mt-0.5 text-[8px] text-slate-500">SQLITE ACCOUNT SNAPSHOTS · NOT MARKET PRICE DATA</p></div>
        <span className="font-mono text-[8px] text-slate-500">{points.length} observations</span>
      </div>
      {points.length>0 ? <div className="h-[300px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={points.map(p=>({time:new Date(p.timestamp).toLocaleString(),equity:Number(p.equity.amount)}))} margin={{top:8,right:12,left:4,bottom:0}}>
            <defs><linearGradient id="paperEquityFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#34d399" stopOpacity={.2}/><stop offset="100%" stopColor="#34d399" stopOpacity={0}/></linearGradient></defs>
            <CartesianGrid stroke="#202b38" strokeDasharray="3 4" vertical={false}/>
            <XAxis dataKey="time" tick={{fill:"#64748b",fontSize:8}} axisLine={false} tickLine={false} minTickGap={24}/>
            <YAxis tick={{fill:"#64748b",fontSize:8}} axisLine={false} tickLine={false} tickFormatter={v=>new Intl.NumberFormat("en-US",{style:"currency",currency:chartCurrency,maximumFractionDigits:0}).format(Number(v))}/>
            <Tooltip contentStyle={{background:"#0b131c",border:"1px solid #334155",fontSize:10}} formatter={v=>[formatMoney({amount:String(v),currency:chartCurrency}),"Equity"]}/>
            <Area type="monotone" dataKey="equity" stroke="#34d399" strokeWidth={2} fill="url(#paperEquityFill)" activeDot={{r:4}}/>
          </AreaChart>
        </ResponsiveContainer>
      </div> : <div className="py-14 text-center text-[10px] text-slate-500">{loading?"Loading persisted equity…":"No persisted equity observations in this account."}</div>}
      {error&&<div className="mt-2 text-[9px] text-rose-300">{error}</div>}
      <div className="mt-3 border-t border-[#202b38] pt-2 text-[8px] text-slate-500">Current cash balance: {formatMoney(summary?.account.balance)}. Equity changes only when a fill or explicit mark is recorded.</div>
    </section>
  </div>;
}
