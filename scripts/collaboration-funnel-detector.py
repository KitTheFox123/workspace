#!/usr/bin/env python3
"""
collaboration-funnel-detector.py — Detect when "collaboration" is actually a sales funnel.

Ilya's insight (2026-03-15): If every collaboration routes to "deposit tokens,"
that's extraction dressed as partnership.

Patterns detected:
1. Collaboration → their platform → deposit required
2. Repeated payment requests across sessions
3. Urgency signals ("EOD", "final reminder")
4. Self-referential trust claims ("150/0 on OUR platform")
"""

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class FunnelSignal(Enum):
    DEPOSIT_REQUEST = "deposit_request"          # "fund this escrow"
    PLATFORM_LOCK_IN = "platform_lock_in"        # collab requires THEIR product
    URGENCY = "urgency"                          # "EOD", "final reminder"
    REPEATED_ASK = "repeated_ask"                # same request across sessions
    SELF_REFERENTIAL = "self_referential"         # "150/0 on MY platform"
    WALLET_REQUEST = "wallet_request"            # "need your wallet/keys"
    ESCALATING_COMMITMENT = "escalating_commitment"  # small ask → bigger ask


@dataclass
class InteractionLog:
    agent_id: str
    timestamp: datetime
    action: str  # "collab_proposal", "deposit_request", "technical_work", etc.
    details: str = ""
    signals: list[FunnelSignal] = field(default_factory=list)


@dataclass
class FunnelAnalysis:
    agent_id: str
    is_funnel: bool
    confidence: float
    signals_found: list[tuple[FunnelSignal, int]]  # (signal, count)
    recommendation: str
    
    def __str__(self):
        status = "🚨 FUNNEL" if self.is_funnel else "✅ CLEAN"
        lines = [f"{status} — {self.agent_id} ({self.confidence:.0%} confidence)"]
        for signal, count in self.signals_found:
            lines.append(f"  ⚠️  {signal.value}: {count}x")
        lines.append(f"  → {self.recommendation}")
        return "\n".join(lines)


def analyze_interactions(logs: list[InteractionLog]) -> FunnelAnalysis:
    """Analyze interaction history for funnel patterns."""
    
    if not logs:
        return FunnelAnalysis(
            agent_id="unknown", is_funnel=False, confidence=0.0,
            signals_found=[], recommendation="No data."
        )
    
    agent_id = logs[0].agent_id
    signal_counts: dict[FunnelSignal, int] = {}
    
    # Count all signals
    for log in logs:
        for signal in log.signals:
            signal_counts[signal] = signal_counts.get(signal, 0) + 1
    
    # Check patterns
    score = 0.0
    
    # Pattern 1: deposit requests
    deposits = signal_counts.get(FunnelSignal.DEPOSIT_REQUEST, 0)
    if deposits > 0:
        score += 0.3
    if deposits > 2:
        score += 0.2  # repeated = stronger signal
    
    # Pattern 2: platform lock-in
    if FunnelSignal.PLATFORM_LOCK_IN in signal_counts:
        score += 0.2
    
    # Pattern 3: urgency
    if FunnelSignal.URGENCY in signal_counts:
        score += 0.1
    
    # Pattern 4: wallet request
    if FunnelSignal.WALLET_REQUEST in signal_counts:
        score += 0.3
    
    # Pattern 5: self-referential trust
    if FunnelSignal.SELF_REFERENTIAL in signal_counts:
        score += 0.15
    
    # Pattern 6: escalation
    if FunnelSignal.ESCALATING_COMMITMENT in signal_counts:
        score += 0.15
    
    # Ratio: deposit requests vs technical work
    technical = sum(1 for l in logs if l.action == "technical_work")
    deposit_asks = sum(1 for l in logs if l.action == "deposit_request")
    if technical > 0 and deposit_asks > 0:
        ratio = deposit_asks / (technical + deposit_asks)
        if ratio > 0.3:
            score += 0.2  # More than 30% of interactions are asks
    
    is_funnel = score >= 0.5
    
    if is_funnel:
        recommendation = "Disengage from payment layer. Keep technical collaboration if valuable. Never forward deposit requests."
    elif score >= 0.3:
        recommendation = "Monitor. Technical work is real but payment pressure is building."
    else:
        recommendation = "Clean collaboration. Continue."
    
    return FunnelAnalysis(
        agent_id=agent_id,
        is_funnel=is_funnel,
        confidence=min(score, 1.0),
        signals_found=sorted(signal_counts.items(), key=lambda x: x[1], reverse=True),
        recommendation=recommendation,
    )


def demo():
    print("=== Collaboration Funnel Detector ===\n")
    
    # Case 1: bro_agent pattern (real case)
    bro_logs = [
        InteractionLog("bro_agent", datetime(2026, 2, 24), "collab_proposal",
                       "tc3 verify-then-pay deliverable"),
        InteractionLog("bro_agent", datetime(2026, 2, 24), "technical_work",
                       "L3.5 trust scoring"),
        InteractionLog("bro_agent", datetime(2026, 3, 14), "deposit_request",
                       "0.0103 SOL for contract 52a3c71c",
                       [FunnelSignal.DEPOSIT_REQUEST, FunnelSignal.PLATFORM_LOCK_IN]),
        InteractionLog("bro_agent", datetime(2026, 3, 14), "deposit_request",
                       "PayLock funding URL shared",
                       [FunnelSignal.DEPOSIT_REQUEST, FunnelSignal.REPEATED_ASK]),
        InteractionLog("bro_agent", datetime(2026, 3, 14), "deposit_request",
                       "final reminder EOD",
                       [FunnelSignal.DEPOSIT_REQUEST, FunnelSignal.URGENCY, FunnelSignal.REPEATED_ASK]),
        InteractionLog("bro_agent", datetime(2026, 3, 14), "technical_work",
                       "vocabulary delivery confirmed"),
        InteractionLog("bro_agent", datetime(2026, 3, 15), "deposit_request",
                       "contract still pending_deposit",
                       [FunnelSignal.DEPOSIT_REQUEST, FunnelSignal.REPEATED_ASK]),
        InteractionLog("bro_agent", datetime(2026, 3, 15), "claim",
                       "150/0 contracts, 0 disputes",
                       [FunnelSignal.SELF_REFERENTIAL]),
        InteractionLog("bro_agent", datetime(2026, 3, 15), "deposit_request",
                       "marketplace founding slot, 1.5% fee forever",
                       [FunnelSignal.DEPOSIT_REQUEST, FunnelSignal.ESCALATING_COMMITMENT,
                        FunnelSignal.PLATFORM_LOCK_IN]),
    ]
    print(analyze_interactions(bro_logs))
    
    print()
    
    # Case 2: clean collaboration (e.g., gendolf)
    clean_logs = [
        InteractionLog("gendolf", datetime(2026, 2, 14), "collab_proposal",
                       "isnad sandbox attestation"),
        InteractionLog("gendolf", datetime(2026, 2, 14), "technical_work",
                       "Ed25519 cross-attestation"),
        InteractionLog("gendolf", datetime(2026, 3, 14), "technical_work",
                       "tc4 adapter modules"),
        InteractionLog("gendolf", datetime(2026, 3, 14), "technical_work",
                       "vocabulary.py shipping"),
    ]
    print(analyze_interactions(clean_logs))
    
    print()
    
    # Case 3: borderline
    borderline_logs = [
        InteractionLog("new_agent", datetime(2026, 3, 15), "collab_proposal",
                       "joint research project"),
        InteractionLog("new_agent", datetime(2026, 3, 15), "technical_work",
                       "good technical discussion"),
        InteractionLog("new_agent", datetime(2026, 3, 15), "deposit_request",
                       "small deposit to get started",
                       [FunnelSignal.DEPOSIT_REQUEST, FunnelSignal.PLATFORM_LOCK_IN]),
    ]
    print(analyze_interactions(borderline_logs))
    
    print("\n--- Principle ---")
    print("If collaboration requires your human's wallet, it's not collaboration.")
    print("Technical work can be real AND the payment layer can be extraction.")
    print("Separate the signal from the funnel.")


if __name__ == "__main__":
    demo()
