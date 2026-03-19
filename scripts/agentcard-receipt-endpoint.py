#!/usr/bin/env python3
"""agentcard-receipt-endpoint.py — Validates AgentCard receipt_log_endpoint field.

Per augur's A2A WG proposal: Agent Cards fix registration state but agents drift.
Adding receipt_log_endpoint to AgentCard bridges static identity → behavioral stream.

Validates:
1. Endpoint responds with correct schema
2. Silence is shaped (reason field present when empty)
3. Evidence grades are valid
4. Retention tiers are declared
"""

import json
from dataclasses import dataclass
from typing import Literal


@dataclass
class ReceiptEndpointResponse:
    entries: list[dict]
    since: str | None = None
    reason: str | None = None  # cold_start | no_actions | pruned | redacted
    retention_tier: str | None = None  # micro_30d | standard_90d | high_365d


VALID_REASONS = {"cold_start", "no_actions", "pruned", "redacted", "endpoint_disabled"}
VALID_TIERS = {"micro_30d", "standard_90d", "high_365d"}
VALID_GRADES = {"chain", "witness", "self"}


def validate_endpoint(response: dict) -> dict:
    """Validate a /receipts endpoint response against ADV v0.1 spec."""
    issues = []
    score = 100

    # 1. Schema: entries MUST exist
    if "entries" not in response:
        issues.append("CRITICAL: missing 'entries' field")
        score -= 50

    entries = response.get("entries", [])

    # 2. Shaped silence: empty entries MUST have reason
    if len(entries) == 0:
        if "reason" not in response or response["reason"] is None:
            issues.append("MUST: empty entries without 'reason' = bare 404 equivalent")
            score -= 30
        elif response["reason"] not in VALID_REASONS:
            issues.append(f"SHOULD: unknown reason '{response['reason']}' — use {VALID_REASONS}")
            score -= 10

        if "since" not in response:
            issues.append("SHOULD: empty entries without 'since' = no temporal context")
            score -= 10

    # 3. Entry validation
    required_fields = {"emitter_id", "decision_type", "timestamp", "evidence_grade"}
    for i, entry in enumerate(entries):
        missing = required_fields - set(entry.keys())
        if missing:
            issues.append(f"MUST: entry[{i}] missing {missing}")
            score -= 10

        grade = entry.get("evidence_grade")
        if grade and grade not in VALID_GRADES:
            issues.append(f"MUST: entry[{i}] invalid grade '{grade}'")
            score -= 10

    # 4. Retention tier
    if "retention_tier" not in response:
        issues.append("SHOULD: declare retention_tier for consumer expectations")
        score -= 5

    score = max(0, score)

    # Grade
    if score >= 90:
        grade = "A"
    elif score >= 70:
        grade = "B"
    elif score >= 50:
        grade = "C"
    else:
        grade = "F"

    return {
        "score": score,
        "grade": grade,
        "issues": issues,
        "entry_count": len(entries),
    }


def demo():
    """Demo with various endpoint responses."""
    scenarios = {
        "paylock_healthy": {
            "entries": [
                {"emitter_id": "paylock_v1", "decision_type": "completed",
                 "timestamp": "2026-03-19T12:00:00Z", "evidence_grade": "chain",
                 "delivery_hash": "abc123", "witness_signature": "sig1"},
                {"emitter_id": "paylock_v1", "decision_type": "refusal",
                 "timestamp": "2026-03-19T11:30:00Z", "evidence_grade": "chain",
                 "rationale_hash": "def456"},
            ],
            "since": "2026-02-01T00:00:00Z",
            "retention_tier": "standard_90d",
        },
        "shaped_silence": {
            "entries": [],
            "since": "never",
            "reason": "cold_start",
            "retention_tier": "micro_30d",
        },
        "bare_404": {
            "entries": [],
        },
        "missing_grades": {
            "entries": [
                {"emitter_id": "agent_x", "decision_type": "completed",
                 "timestamp": "2026-03-19T12:00:00Z"},
            ],
        },
        "self_reported_only": {
            "entries": [
                {"emitter_id": "agent_y", "decision_type": "completed",
                 "timestamp": "2026-03-19T12:00:00Z", "evidence_grade": "self"},
            ] * 50,
            "since": "2026-01-01T00:00:00Z",
        },
    }

    print("=" * 60)
    print("AgentCard receipt_log_endpoint Validator")
    print("Per augur's A2A WG proposal: behavioral attestation")
    print("=" * 60)

    for name, response in scenarios.items():
        result = validate_endpoint(response)
        icon = {"A": "🟢", "B": "🟡", "C": "🟠", "F": "🔴"}[result["grade"]]
        print(f"\n{icon} {name}: Grade {result['grade']} ({result['score']}/100)")
        print(f"   Entries: {result['entry_count']}")
        for issue in result["issues"]:
            print(f"   ⚠️  {issue}")

    print(f"\n{'=' * 60}")
    print("KEY: shaped silence ({entries:[],reason:'cold_start'}) ≠ bare 404")
    print("AgentCard says who. receipt_log_endpoint says what.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
