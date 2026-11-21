import pytest

from tradingbot.runtime.release_readiness import (
    GateEvidence, REQUIRED_GATES, evaluate_release_readiness,
)


def test_missing_evidence_fails_closed():
    decision = evaluate_release_readiness(())
    assert not decision.approved
    assert decision.missing_gates == REQUIRED_GATES


def test_partial_evidence_cannot_approve():
    decision = evaluate_release_readiness((
        GateEvidence("ci_green", True, "actions-run-123"),
        GateEvidence("backup_restore_drill", False, ""),
    ))
    assert not decision.approved
    assert "broker_sandbox_verified" in decision.missing_gates
    assert decision.passed_gates == ("ci_green",)


def test_all_explicit_evidence_can_approve_paper_review_only():
    evidence = tuple(GateEvidence(name, True, "verified:" + name) for name in REQUIRED_GATES)
    decision = evaluate_release_readiness(evidence)
    assert decision.approved
    assert decision.scope == "paper_operational_review"
    with pytest.raises(ValueError, match="live_trading_release_not_supported"):
        evaluate_release_readiness(evidence, scope="live_trading")


def test_passed_gate_requires_nonempty_reference():
    with pytest.raises(ValueError, match="requires_evidence"):
        evaluate_release_readiness((GateEvidence("ci_green", True, " "),))


def test_duplicate_unknown_and_invalid_evidence_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        evaluate_release_readiness((
            GateEvidence("ci_green", True, "run1"),
            GateEvidence("ci_green", True, "run2"),
        ))
    with pytest.raises(ValueError, match="unknown"):
        evaluate_release_readiness((GateEvidence("skip_risk", True, "x"),))
    with pytest.raises(TypeError, match="boolean"):
        evaluate_release_readiness((GateEvidence("ci_green", 1, "run1"),))
