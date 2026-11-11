"""Explicit, source-backed raw futures contract-roll event auditing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from tradingbot.data.raw_futures import RawFuturesBar


@dataclass(frozen=True, slots=True)
class ContractRollEvent:
    root_symbol: str
    event_time: datetime
    old_contract_symbol: str
    old_instrument_id: str
    new_contract_symbol: str
    new_instrument_id: str
    source_url: str

    def __post_init__(self) -> None:
        if self.event_time.tzinfo is None or self.event_time.utcoffset() is None:
            raise ValueError("Contract-roll event_time must be timezone-aware")
        if not all((
            self.root_symbol.strip(),
            self.old_contract_symbol.strip(),
            self.old_instrument_id.strip(),
            self.new_contract_symbol.strip(),
            self.new_instrument_id.strip(),
            self.source_url.strip(),
        )):
            raise ValueError("Contract-roll event identity and source_url are required")
        if (
            self.old_contract_symbol.strip().upper() == self.new_contract_symbol.strip().upper()
            or self.old_instrument_id.strip() == self.new_instrument_id.strip()
        ):
            raise ValueError("A contract-roll event must change both symbol and instrument ID")


def audit_contract_rolls(
    bars: Iterable[RawFuturesBar],
    events: Iterable[ContractRollEvent],
    *,
    expected_root_symbol: str | None = None,
) -> dict[str, Any]:
    """Check event chronology, mapping chain and existence of post-event new bars.

    Raw contracts can trade concurrently around rolls. Old-contract bars after
    the mapping event are therefore not automatically treated as defects.
    This audit verifies supplied mapping events against observed identities; it
    cannot discover or certify a provider's continuous-contract mapping alone.
    """
    rows = list(bars)
    roll_events = list(events)
    if not rows:
        raise ValueError("Cannot audit contract rolls without raw futures bars")

    root = (expected_root_symbol or rows[0].root_symbol).strip().upper()
    identities: dict[str, str] = {}
    contracts: dict[str, str] = {}
    for bar in rows:
        if bar.root_symbol.strip().upper() != root:
            raise ValueError("Contract-roll audit cannot mix futures roots")
        instrument_id = bar.instrument_id.strip()
        contract = bar.contract_symbol.strip().upper()
        if instrument_id in identities and identities[instrument_id] != contract:
            raise ValueError(f"Instrument ID {instrument_id} maps to multiple contracts")
        if contract in contracts and contracts[contract] != instrument_id:
            raise ValueError(f"Contract {contract} maps to multiple instrument IDs")
        identities[instrument_id] = contract
        contracts[contract] = instrument_id

    ordered = sorted(roll_events, key=lambda item: item.event_time.astimezone(timezone.utc).timestamp())
    if ordered != roll_events:
        raise ValueError("Contract-roll events must be supplied in chronological order")

    transitions: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    prior_event: ContractRollEvent | None = None
    for event in roll_events:
        if event.root_symbol.strip().upper() != root:
            raise ValueError("Contract-roll event root does not match raw bars")
        if prior_event is not None:
            if event.event_time.astimezone(timezone.utc) <= prior_event.event_time.astimezone(timezone.utc):
                issues.append({"type": "non_increasing_event_time", "at": event.event_time.isoformat()})
            if (
                event.old_contract_symbol.strip().upper()
                != prior_event.new_contract_symbol.strip().upper()
                or event.old_instrument_id.strip() != prior_event.new_instrument_id.strip()
            ):
                issues.append({"type": "broken_mapping_chain", "at": event.event_time.isoformat()})

        old_symbol = event.old_contract_symbol.strip().upper()
        new_symbol = event.new_contract_symbol.strip().upper()
        old_id = event.old_instrument_id.strip()
        new_id = event.new_instrument_id.strip()
        if identities.get(old_id) != old_symbol:
            issues.append({"type": "old_contract_identity_not_observed", "at": event.event_time.isoformat()})
        if identities.get(new_id) != new_symbol:
            issues.append({"type": "new_contract_identity_not_observed", "at": event.event_time.isoformat()})

        new_after_event = [
            bar for bar in rows
            if bar.instrument_id.strip() == new_id
            and bar.timestamp.astimezone(timezone.utc) >= event.event_time.astimezone()
        ]
        first_new = min(new_after_event, key=lambda bar: bar.timestamp) if new_after_event else None
        if first_new is None:
            issues.append({"type": "no_new_contract_bar_at_or_after_event", "at": event.event_time.isoformat()})
        transitions.append({
            "event_time": event.event_time.isoformat(),
            "old_contract_symbol": old_symbol,
            "old_instrument_id": old_id,
            "new_contract_symbol": new_symbol,
            "new_instrument_id": new_id,
            "source_url": event.source_url,
            "first_new_contract_bar_utc": (
                first_new.timestamp.astimezone().isoformat() if first_new else None
            ),
            "seconds_until_first_new_bar": (
                (first_new.timestamp - event.event_time).total_seconds()
                if first_new else None
            ),
        })
        prior_event = event

    event_contracts = {
        (event.new_contract_symbol.strip().upper(), event.new_instrument_id.strip())
        for event in roll_events
    }
    first_contract = (
        (roll_events[0].old_contract_symbol.strip().upper(), roll_events[0].old_instrument_id.strip())
        if roll_events else None
    )
    explained = event_contracts | ({first_contract} if first_contract else set())
    observed = {(contract, instrument_id) for contract, instrument_id in contracts.items()}
    unannounced = sorted(observed - explained)

    if unannounced:
        issues.append({
            "type": "contracts_without_supplied_roll_event",
            "at": ",".join(f"{symbol}:{instrument_id}" for symbol, instrument_id in unannounced),
        })

    return {
        "status": "verified_against_supplied_events" if not issues else "needs_review",
        "root_symbol": root,
        "observed_contract_count": len(observed),
        "event_count": len(roll_events),
        "transitions": transitions,
        "unannounced_contracts": [
            {"contract_symbol": symbol, "instrument_id": instrument_id}
            for symbol, instrument_id in unannounced
        ],
        "issues": issues,
        "important_note": (
            "This checks raw bars against supplied source-backed roll events. "
            "It does not independently establish the provider's continuous mapping rule."
        ),
    }
