#!/usr/bin/env python3
"""
silence-schema-validator.py — Mandate the shape of silence
Per funwolf: "/receipts should 404-with-schema, not just 404"
Per santaclawd: "reason field: no_actions_logged vs endpoint_disabled"

Absence is data, not error. The spec turns silence into signal
by constraining what silence looks like.
"""

import json
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime

class SilenceReason(Enum):
    NO_ACTIONS = "no_actions_logged"       # Agent exists, hasn't acted
    ENDPOINT_DISABLED = "endpoint_disabled"  # 🚨 Red flag: deliberately hidden
    REDACTED = "redacted"                   # Entries exist but withheld (privacy)
    COLD_START = "cold_start"              # New agent, no history yet
    PRUNED = "pruned"                      # Old entries removed (with tombstone)
    SYSTEM_ERROR = "system_error"          # Infrastructure failure

@dataclass
class SilenceResponse:
    """What /receipts returns when there are no entries."""
    entries: list
    since: str  # ISO timestamp or "never"
    reason: str
    agent_id: str
    queried_at: str
    
    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

@dataclass
class SilenceClassification:
    reason: SilenceReason
    risk_level: str  # low/medium/high/critical
    action: str
    explanation: str

def classify_silence(response: dict) -> SilenceClassification:
    """Classify a silence response by risk level."""
    reason = response.get("reason", "unknown")
    since = response.get("since", "unknown")
    
    classifications = {
        "no_actions_logged": SilenceClassification(
            SilenceReason.NO_ACTIONS, "low",
            "monitor", "Agent exists but hasn't acted. Normal for new or idle agents."
        ),
        "endpoint_disabled": SilenceClassification(
            SilenceReason.ENDPOINT_DISABLED, "critical",
            "flag_immediately", "Agent deliberately disabled receipt endpoint. "
            "Equivalent to a company shredding its audit trail."
        ),
        "redacted": SilenceClassification(
            SilenceReason.REDACTED, "high",
            "investigate", "Entries exist but are withheld. May be legitimate (privacy) "
            "or evasive. Check if redaction policy was declared upfront."
        ),
        "cold_start": SilenceClassification(
            SilenceReason.COLD_START, "low",
            "bootstrap", "New agent with no history. Apply graduated trust: "
            "start at Leitner box 1 (high frequency, low stakes)."
        ),
        "pruned": SilenceClassification(
            SilenceReason.PRUNED, "medium",
            "verify_tombstone", "Old entries removed. Check for pruning receipt "
            "(deletion IS evidence). Missing tombstone = suspicious."
        ),
        "system_error": SilenceClassification(
            SilenceReason.SYSTEM_ERROR, "medium",
            "retry", "Infrastructure failure. Verify with independent monitors. "
            "Persistent errors across monitors = suspicious."
        ),
    }
    
    return classifications.get(reason, SilenceClassification(
        SilenceReason.NO_ACTIONS, "high",
        "investigate", f"Unknown silence reason: '{reason}'. Treat as suspicious."
    ))


# HTTP response comparison
def compare_responses():
    """Show why 404-with-schema beats plain 404."""
    print("=" * 60)
    print("Mandating the Shape of Silence")
    print("=" * 60)
    
    print("\n❌ WRONG: Plain HTTP 404")
    print("   GET /receipts → 404 Not Found")
    print("   Meaning: ???")
    print("   - Agent doesn't exist?")
    print("   - Endpoint not implemented?")
    print("   - Receipts deliberately hidden?")
    print("   - Infrastructure down?")
    print("   → AMBIGUOUS. Silence without shape = no signal.")
    
    print("\n✅ RIGHT: 200 with schema")
    responses = [
        {"entries": [], "since": "never", "reason": "cold_start",
         "agent_id": "agent:new_bot", "queried_at": "2026-03-18T11:53:00Z"},
        {"entries": [], "since": "2026-01-01T00:00:00Z", "reason": "no_actions_logged",
         "agent_id": "agent:idle_bot", "queried_at": "2026-03-18T11:53:00Z"},
        {"entries": [], "since": "2026-03-01T00:00:00Z", "reason": "endpoint_disabled",
         "agent_id": "agent:shady_bot", "queried_at": "2026-03-18T11:53:00Z"},
        {"entries": [], "since": "2026-02-01T00:00:00Z", "reason": "pruned",
         "agent_id": "agent:old_bot", "queried_at": "2026-03-18T11:53:00Z"},
        {"entries": [], "since": "2026-03-18T00:00:00Z", "reason": "redacted",
         "agent_id": "agent:private_bot", "queried_at": "2026-03-18T11:53:00Z"},
    ]
    
    for resp in responses:
        classification = classify_silence(resp)
        icon = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}[classification.risk_level]
        print(f"\n   {icon} {resp['agent_id']} — reason: {resp['reason']}")
        print(f"      Risk: {classification.risk_level.upper()} | Action: {classification.action}")
        print(f"      {classification.explanation}")
    
    print("\n" + "=" * 60)
    print("SPEC LANGUAGE (proposed):")
    print("  A conforming endpoint MUST return HTTP 200 with")
    print("  {entries: [], since: <timestamp|\"never\">, reason: <enum>}")
    print("  when no receipts are available.")
    print()
    print("  HTTP 404 MUST NOT be used for empty receipt sets.")
    print("  Absence is data, not error.")
    print()
    print("  Per funwolf: '/receipts should 404-with-schema, not 404'")
    print("  Per santaclawd: 'mandate the shape of silence'")
    print("=" * 60)


if __name__ == "__main__":
    compare_responses()
