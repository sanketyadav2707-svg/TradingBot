"""Generate an auditable, fail-closed inventory of Phase 2–6 evidence.

This tool checks local artifacts and SHA-256 digests. It never treats the
presence of a file as proof of a profitable strategy, broker authorization,
regulatory permission, or sustained paper trading.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from tradingbot.runtime.release_readiness import REQUIRED_GATES


@dataclass(frozen=True)
class ArtifactCheck:
    gate: str
    path: str | None
    exists: bool
    sha256: str | None
    size_bytes: int | None
    verified: bool
    reason: str


@dataclass(frozen=True)
class EvidenceInventory:
    generated_at: str
    checks: tuple[ArtifactCheck, ...]
    verified_count: int
    outstanding_count: int


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def inventory_evidence(
    *,
    root: str | Path,
    artifacts: Mapping[str, str],
    expected_sha256: Mapping[str, str],
    generated_at: datetime,
) -> EvidenceInventory:
    """Audit immutable local artifacts; never grant release approval.

    A valid matching digest establishes file identity only. All high-stakes
    release gates still need independent human/source verification.
    """
    if not isinstance(generated_at, datetime) or generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("generated_at_must_be_timezone_aware")
    if not isinstance(artifacts, Mapping) or not isinstance(expected_sha256, Mapping):
        raise TypeError("artifact_maps_required")
    if set(artifacts) - set(REQUIRED_GATES) or set(expected_sha256) - set(REQUIRED_GATES):
        raise ValueError("unknown_evidence_gate")
    base = Path(root).resolve()
    checks = []
    for gate in REQUIRED_GATES:
        raw = artifacts.get(gate)
        expected = expected_sha256.get(gate)
        if raw is None:
            checks.append(ArtifactCheck(gate, None, False, None, None, False, "no_artifact_registered"))
            continue
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("invalid_artifact_path:" + gate)
        candidate = (base / raw).resolve()
        if not candidate.is_relative_to(base):
            checks.append(ArtifactCheck(gate, raw, False, None, None, False, "path_outside_root"))
            continue
        if not candidate.is_file():
            checks.append(ArtifactCheck(gate, raw, False, None, None, False, "artifact_missing"))
            continue
        digest = _digest(candidate)
        size = candidate.stat().st_size
        if not isinstance(expected, str) or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            reason = "pinned_sha256_missing_or_invalid"
        elif digest != expected:
            reason = "sha256_mismatch"
        else:
            reason = "sha256_matched_identity_only"
        checks.append(ArtifactCheck(
            gate, raw, True, digest, size, reason == "sha256_matched_identity_only", reason
        ))
    count = sum(item.verified for item in checks)
    return EvidenceInventory(
        generated_at=generated_at.astimezone(timezone.utc).isoformat(),
        checks=tuple(checks),
        verified_count=count,
        outstanding_count=len(REQUIRED_GATES) - count,
    )


def inventory_to_json(inventory: EvidenceInventory) -> str:
    return json.dumps(asdict(inventory), sort_keys=True, indent=2)
