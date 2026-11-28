from datetime import datetime, timezone
import hashlib
import json

import pytest

from tradingbot.runtime.evidence_inventory import inventory_evidence, inventory_to_json
from tradingbot.runtime.release_readiness import REQUIRED_GATES

NOW = datetime(2026, 11, 19, 15, 0, tzinfo=timezone.utc)


def scan(tmp_path, artifacts=None, expected=None):
    return inventory_evidence(
        root=tmp_path, artifacts=artifacts or {}, expected_sha256=expected or {},
        generated_at=NOW,
    )


def test_missing_evidence_remains_outstanding(tmp_path):
    result = scan(tmp_path)
    assert result.outstanding_count == len(REQUIRED_GATES)
    assert all(not x.verified for x in result.checks)
    assert json.loads(inventory_to_json(result))["verified_count"] == 0


def test_pinned_artifact_identity_only(tmp_path):
    path = tmp_path / "ci.txt"
    path.write_text("workflow succeeded")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    result = scan(tmp_path, {"ci_green": "ci.txt"}, {"ci_green": sha})
    check = result.checks[0]
    assert check.exists and check.verified
    assert check.reason == "sha256_matched_identity_only"
    assert result.outstanding_count == len(REQUIRED_GATES) - 1


def test_unpinned_or_tampered_artifact_never_verifies(tmp_path):
    path = tmp_path / "ci.txt"
    path.write_text("original")
    old = hashlib.sha256(path.read_bytes()).hexdigest()
    assert not scan(tmp_path, {"ci_green": "ci.txt"}).checks[0].verified
    path.write_text("modified")
    result = scan(tmp_path, {"ci_green": "ci.txt"}, {"ci_green": old})
    assert result.checks[0].reason == "sha256_mismatch"


def test_path_escape_and_symlink_escape_rejected(tmp_path):
    outside = tmp_path.parent / "outside-evidence.txt"
    outside.write_text("not in evidence root")
    try:
        result = scan(tmp_path, {"ci_green": "../outside-evidence.txt"})
        assert result.checks[0].reason == "path_outside_root"
        (tmp_path / "link.txt").symlink_to(outside)
        result = scan(tmp_path, {"ci_green": "link.txt"})
        assert result.checks[0].reason == "path_outside_root"
    finally:
        outside.unlink(missing_ok=True)


def test_unknown_gate_and_naive_time_rejected(tmp_path):
    with pytest.raises(ValueError, match="unknown"):
        scan(tmp_path, {"skip_all": "fake"})
    with pytest.raises(ValueError, match="timezone"):
        inventory_evidence(
            root=tmp_path, artifacts={}, expected_sha256={},
            generated_at=NOW.replace(tzinfo=None),
        )
