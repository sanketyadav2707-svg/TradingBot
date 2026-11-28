"""Transactional persistence wrapper for the offline option simulator.

One database contains one paper account. Every mutation runs under a SQLite
write lock and persists the position, realized P&L and halt state together.
No live execution, credentials or external reconciliation is performed.
"""
from contextlib import closing, contextmanager
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from dataclasses import asdict

from tradingbot.paper.index_options import LongOptionPaperSimulator, LongOptionPaperPosition
from tradingbot.risk.index_options import aware


class DurableOptionPaper:
    def __init__(self, path: str | Path, **simulator_options):
        self.path = str(path)
        sim = LongOptionPaperSimulator(**simulator_options)
        self.options = dict(stop_fraction=str(sim.stop_fraction),
                            target_fraction=str(sim.target_fraction),
                            max_holding_seconds=sim.max_holding_seconds,
                            quote_max_age_seconds=sim.quote_max_age_seconds)
        with closing(self._connect()) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""CREATE TABLE IF NOT EXISTS option_paper_state (
                id INTEGER PRIMARY KEY CHECK(id=1), config TEXT NOT NULL,
                state TEXT NOT NULL)""")
            conn.execute("INSERT OR IGNORE INTO option_paper_state VALUES(1,?,?)",
                         (json.dumps(self.options,sort_keys=True),self._dump(sim)))
            self._load(conn)

    def _connect(self):
        conn=sqlite3.connect(self.path,isolation_level=None,timeout=10)
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    @staticmethod
    def _dump(sim):
        pos=asdict(sim.position) if sim.position else None
        if pos:
            for key in ("entry_ask","debit","round_trip_fees"):
                pos[key]=str(pos[key])
            pos["entry_timestamp"]=aware(pos["entry_timestamp"],"entry").isoformat()
        return json.dumps(dict(position=pos,halted=sim.halted,
                               halt_reason=sim.halt_reason,
                               realized_pnl=str(sim.realized_pnl)),sort_keys=True)

    def _load(self,conn):
        config,state=conn.execute("SELECT config,state FROM option_paper_state WHERE id=1").fetchone()
        if json.loads(config)!=self.options:
            raise ValueError("paper_configuration_mismatch")
        data=json.loads(state)
        sim=LongOptionPaperSimulator(**self.options)
        pos=data["position"]
        if pos:
            for key in ("entry_ask","debit","round_trip_fees"):
                pos[key]=Decimal(pos[key])
            pos["entry_timestamp"]=datetime.fromisoformat(pos["entry_timestamp"])
            sim.position=LongOptionPaperPosition(**pos)
        sim.realized_pnl=Decimal(data["realized_pnl"])
        sim.halted=data["halted"]
        sim.halt_reason=data["halt_reason"]
        return sim

    def _mutate(self,method,**kwargs):
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            sim=self._load(conn)
            try:
                result=getattr(sim,method)(**kwargs)
            except RuntimeError:
                # The simulator deliberately raises after setting a halt.
                # Persist that halt even though the attempted operation failed.
                conn.execute("UPDATE option_paper_state SET state=? WHERE id=1",(self._dump(sim),))
                conn.commit()
                raise
            conn.execute("UPDATE option_paper_state SET state=? WHERE id=1",(self._dump(sim),))
            conn.commit()
            return result

    def enter(self,**kwargs):
        return self._mutate("enter",**kwargs)

    def evaluate_exit(self,**kwargs):
        return self._mutate("evaluate_exit",**kwargs)

    def halt(self,reason):
        return self._mutate("halt",reason=reason)

    def snapshot(self):
        with closing(self._connect()) as conn:
            return self._load(conn)
