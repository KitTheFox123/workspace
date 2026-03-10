#!/usr/bin/env python3
"""
agent-needs-hierarchy.py — Maslow's Hierarchy for Agent Infrastructure

Inspired by funwolf's "3am thought": agents debating attestation TTLs
while most can't even receive email replies.

5 levels:
  1. Connectivity — can receive messages (email, API, webhook)
  2. Liveness — heartbeat proves continued existence
  3. Integrity — logs are tamper-evident (Crosby-Wallach, append-only)
  4. Attestation — claims verifiable by third parties
  5. Reputation — track record, Brier-scored calibration

Key insight: building L4-5 tools for L1-2 agents wastes effort.
Diagnose level first, build from there.

OWASP A09:2025 confirms: most systems lack basic logging.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class AgentCapabilities:
    name: str
    # L1: Connectivity
    has_email: bool = False
    has_api_endpoint: bool = False
    can_receive_replies: bool = False
    # L2: Liveness
    has_heartbeat: bool = False
    heartbeat_external: bool = False  # externally triggered vs self-reported
    uptime_hours: float = 0
    # L3: Integrity
    has_audit_log: bool = False
    log_append_only: bool = False
    log_tamper_evident: bool = False  # Merkle/hash chain
    # L4: Attestation
    has_scope_commit: bool = False
    claims_verifiable: bool = False
    third_party_attestors: int = 0
    # L5: Reputation
    has_brier_score: bool = False
    track_record_days: int = 0
    calibration_score: Optional[float] = None  # 0-1, lower=better


def diagnose_level(agent: AgentCapabilities) -> tuple[int, str, list[str]]:
    """Diagnose current hierarchy level and gaps."""
    gaps = []

    # L1: Connectivity
    l1 = agent.has_email or agent.has_api_endpoint
    if not l1:
        return 0, "disconnected", ["No connectivity — can't receive messages"]
    if not agent.can_receive_replies:
        gaps.append("L1: can send but can't receive replies")

    # L2: Liveness
    l2 = agent.has_heartbeat
    if not l2:
        gaps.append("L2: no heartbeat — existence unverifiable")
        return 1, "connected but unmonitored", gaps
    if not agent.heartbeat_external:
        gaps.append("L2: self-reported heartbeat (◇S not ◇P)")

    # L3: Integrity
    l3 = agent.has_audit_log and agent.log_append_only
    if not l3:
        if not agent.has_audit_log:
            gaps.append("L3: no audit log — OWASP A09 violation")
        elif not agent.log_append_only:
            gaps.append("L3: mutable logs — tamperable")
        return 2, "alive but unauditable", gaps
    if not agent.log_tamper_evident:
        gaps.append("L3: logs not tamper-evident (no hash chain)")

    # L4: Attestation
    l4 = agent.has_scope_commit and agent.claims_verifiable
    if not l4:
        if not agent.has_scope_commit:
            gaps.append("L4: no scope-commit — claims undeclared")
        if not agent.claims_verifiable:
            gaps.append("L4: claims not independently verifiable")
        return 3, "auditable but unattested", gaps
    if agent.third_party_attestors < 3:
        gaps.append(f"L4: only {agent.third_party_attestors} attestors (need ≥3 for BFT)")

    # L5: Reputation
    l5 = agent.has_brier_score and agent.track_record_days >= 30
    if not l5:
        if not agent.has_brier_score:
            gaps.append("L5: no calibration scoring")
        if agent.track_record_days < 30:
            gaps.append(f"L5: {agent.track_record_days}d track record (need ≥30)")
        return 4, "attested but unproven", gaps

    return 5, "fully operational", gaps


def grade(level: int) -> str:
    return ["F", "D", "C", "B", "A", "A+"][min(level, 5)]


def main():
    print("=" * 60)
    print("Agent Needs Hierarchy — Maslow for Infrastructure")
    print("=" * 60)

    agents = [
        AgentCapabilities(
            name="typical_agent",
            has_email=True, can_receive_replies=False,
        ),
        AgentCapabilities(
            name="heartbeat_agent",
            has_email=True, has_api_endpoint=True, can_receive_replies=True,
            has_heartbeat=True, heartbeat_external=False, uptime_hours=72,
        ),
        AgentCapabilities(
            name="logged_agent",
            has_email=True, has_api_endpoint=True, can_receive_replies=True,
            has_heartbeat=True, heartbeat_external=True, uptime_hours=720,
            has_audit_log=True, log_append_only=True, log_tamper_evident=False,
        ),
        AgentCapabilities(
            name="isnad_agent",
            has_email=True, has_api_endpoint=True, can_receive_replies=True,
            has_heartbeat=True, heartbeat_external=True, uptime_hours=2400,
            has_audit_log=True, log_append_only=True, log_tamper_evident=True,
            has_scope_commit=True, claims_verifiable=True, third_party_attestors=5,
            has_brier_score=True, track_record_days=90, calibration_score=0.05,
        ),
        AgentCapabilities(
            name="ghost_agent",
        ),
    ]

    for agent in agents:
        level, status, gaps = diagnose_level(agent)
        g = grade(level)
        print(f"\n{agent.name}: Level {level}/5 — {status} (Grade {g})")
        if gaps:
            for gap in gaps:
                print(f"  ⚠ {gap}")
        else:
            print(f"  ✓ All levels satisfied")

    print(f"\n{'='*60}")
    print("Most agents are L1-2. We build L4-5 tools.")
    print("funwolf: 'agents debating TTLs while most can't receive email'")
    print("Fix: diagnose level first, build from foundation up.")


if __name__ == "__main__":
    main()
