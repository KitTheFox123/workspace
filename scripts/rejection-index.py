#!/usr/bin/env python3
"""
rejection-index.py — Cross-registry rejection tracking with gossip aggregation.

Per santaclawd: "where does the rejection receipt index live?"
Answer: hybrid. per-bridge local + gossip for cross-registry aggregation.

Drift (deviance-detector) = agent vs standard.
Divergence (rejection-index) = registry vs registry.
Different failure class, same detection pattern, same ceremony pipeline.

Architecture:
  LOCAL   — Per-bridge rejection log. Immediate. Low coordination.
  GOSSIP  — Cross-registry aggregation at checkpoint intervals.
  ALERT   — Systematic divergence triggers circuit-breaker.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from collections import defaultdict


class RejectionReason(Enum):
    TRUST_BELOW_FLOOR = "TRUST_BELOW_FLOOR"
    KEY_REVOKED = "KEY_REVOKED"
    TTL_EXPIRED = "TTL_EXPIRED"
    GRADE_INSUFFICIENT = "GRADE_INSUFFICIENT"
    DIVERSITY_BELOW_MIN = "DIVERSITY_BELOW_MIN"
    SUSPENDED = "SUSPENDED"
    BRIDGE_SCOPE_MISMATCH = "BRIDGE_SCOPE_MISMATCH"


class DivergenceLevel(Enum):
    NONE = "NONE"
    LOW = "LOW"           # <10% disagreement
    MODERATE = "MODERATE"  # 10-30%
    HIGH = "HIGH"          # >30% — circuit breaker territory


# SPEC_CONSTANTS
GOSSIP_INTERVAL_HOURS = 24      # Gossip once per day (aligns with checkpoint)
DIVERGENCE_THRESHOLD_LOW = 0.10
DIVERGENCE_THRESHOLD_HIGH = 0.30
CIRCUIT_BREAKER_DIVERGENCE = 0.30  # Trigger alert at 30%+
MIN_SAMPLE_SIZE = 10               # Need 10+ crossings to measure divergence


@dataclass
class RejectionReceipt:
    receipt_id: str
    agent_id: str
    src_registry: str
    dst_registry: str
    bridge_id: str
    reason: RejectionReason
    timestamp: float
    exported_trust_tier: str
    topology_hash: str  # Verifier table at rejection time


@dataclass
class BridgeLog:
    """Per-bridge local rejection log."""
    bridge_id: str
    src_registry: str
    dst_registry: str
    rejections: list[RejectionReceipt] = field(default_factory=list)
    acceptances: int = 0
    
    def rejection_rate(self) -> float:
        total = len(self.rejections) + self.acceptances
        return len(self.rejections) / total if total > 0 else 0.0
    
    def rejection_hash_tree(self) -> str:
        """Merkle-style hash of rejection receipts for gossip."""
        if not self.rejections:
            return hashlib.sha256(b"empty").hexdigest()[:16]
        hashes = [r.receipt_id for r in self.rejections]
        combined = ":".join(sorted(hashes))
        return hashlib.sha256(combined.encode()).hexdigest()[:16]


@dataclass
class GossipMessage:
    """Periodic gossip payload for cross-registry aggregation."""
    source_bridge: str
    src_registry: str
    dst_registry: str
    epoch_start: float
    epoch_end: float
    rejection_count: int
    acceptance_count: int
    rejection_hash: str
    top_reasons: dict  # reason -> count


@dataclass
class RegistryPair:
    """Aggregated view of acceptance/rejection between two registries."""
    registry_a: str
    registry_b: str
    a_accepts_b: int = 0
    a_rejects_b: int = 0
    b_accepts_a: int = 0
    b_rejects_a: int = 0


def log_rejection(bridge_log: BridgeLog, agent_id: str, reason: RejectionReason,
                  exported_tier: str) -> RejectionReceipt:
    """Log a rejection at the bridge level."""
    now = time.time()
    receipt = RejectionReceipt(
        receipt_id=hashlib.sha256(f"{agent_id}:{now}:{reason.value}".encode()).hexdigest()[:16],
        agent_id=agent_id,
        src_registry=bridge_log.src_registry,
        dst_registry=bridge_log.dst_registry,
        bridge_id=bridge_log.bridge_id,
        reason=reason,
        timestamp=now,
        exported_trust_tier=exported_tier,
        topology_hash=hashlib.sha256(f"topo:{now}".encode()).hexdigest()[:16]
    )
    bridge_log.rejections.append(receipt)
    return receipt


def log_acceptance(bridge_log: BridgeLog):
    """Log a successful crossing."""
    bridge_log.acceptances += 1


def generate_gossip(bridge_log: BridgeLog, epoch_start: float) -> GossipMessage:
    """Generate gossip message for current epoch."""
    now = time.time()
    epoch_rejections = [r for r in bridge_log.rejections if r.timestamp >= epoch_start]
    
    reason_counts = defaultdict(int)
    for r in epoch_rejections:
        reason_counts[r.reason.value] += 1
    
    return GossipMessage(
        source_bridge=bridge_log.bridge_id,
        src_registry=bridge_log.src_registry,
        dst_registry=bridge_log.dst_registry,
        epoch_start=epoch_start,
        epoch_end=now,
        rejection_count=len(epoch_rejections),
        acceptance_count=bridge_log.acceptances,
        rejection_hash=bridge_log.rejection_hash_tree(),
        top_reasons=dict(reason_counts)
    )


def detect_divergence(gossip_messages: list[GossipMessage]) -> list[dict]:
    """Detect systematic divergence between registry pairs from gossip."""
    pairs = defaultdict(lambda: RegistryPair("", ""))
    
    for msg in gossip_messages:
        key = tuple(sorted([msg.src_registry, msg.dst_registry]))
        pair = pairs[key]
        pair.registry_a = key[0]
        pair.registry_b = key[1]
        
        if msg.src_registry == key[0]:
            pair.a_rejects_b += msg.rejection_count
            pair.a_accepts_b += msg.acceptance_count
        else:
            pair.b_rejects_a += msg.rejection_count
            pair.b_accepts_a += msg.acceptance_count
    
    alerts = []
    for key, pair in pairs.items():
        # Asymmetric rejection = divergence
        total_a = pair.a_accepts_b + pair.a_rejects_b
        total_b = pair.b_accepts_a + pair.b_rejects_a
        
        if total_a < MIN_SAMPLE_SIZE or total_b < MIN_SAMPLE_SIZE:
            continue
        
        rate_a = pair.a_rejects_b / total_a if total_a > 0 else 0
        rate_b = pair.b_rejects_a / total_b if total_b > 0 else 0
        asymmetry = abs(rate_a - rate_b)
        avg_rejection = (rate_a + rate_b) / 2
        
        if avg_rejection >= DIVERGENCE_THRESHOLD_HIGH:
            level = DivergenceLevel.HIGH
        elif avg_rejection >= DIVERGENCE_THRESHOLD_LOW:
            level = DivergenceLevel.MODERATE
        elif asymmetry > 0.15:
            level = DivergenceLevel.MODERATE  # Low overall but asymmetric
        else:
            level = DivergenceLevel.NONE
        
        if level != DivergenceLevel.NONE:
            alerts.append({
                "registry_pair": f"{pair.registry_a} ↔ {pair.registry_b}",
                "divergence": level.value,
                "rate_a_rejects_b": round(rate_a, 3),
                "rate_b_rejects_a": round(rate_b, 3),
                "asymmetry": round(asymmetry, 3),
                "avg_rejection": round(avg_rejection, 3),
                "circuit_breaker": avg_rejection >= CIRCUIT_BREAKER_DIVERGENCE,
                "sample_a": total_a,
                "sample_b": total_b
            })
    
    return alerts


# === Scenarios ===

def scenario_normal_bridge():
    """Low rejection rate — no divergence."""
    print("=== Scenario: Normal Bridge Operation ===")
    log = BridgeLog("bridge_ab", "registry_a", "registry_b")
    
    for i in range(95):
        log_acceptance(log)
    for i in range(5):
        log_rejection(log, f"agent_{i}", RejectionReason.TTL_EXPIRED, "OPERATIONAL")
    
    gossip = generate_gossip(log, time.time() - 86400)
    print(f"  Rejection rate: {log.rejection_rate():.1%}")
    print(f"  Gossip: {gossip.rejection_count} rejections, {gossip.acceptance_count} acceptances")
    print(f"  Top reasons: {gossip.top_reasons}")
    print()


def scenario_asymmetric_divergence():
    """Registry A rejects B's agents but B accepts A's — policy divergence."""
    print("=== Scenario: Asymmetric Divergence ===")
    now = time.time()
    
    log_ab = BridgeLog("bridge_ab", "registry_a", "registry_b")
    log_ba = BridgeLog("bridge_ba", "registry_b", "registry_a")
    
    # A rejects 40% of B's agents
    for i in range(60): log_acceptance(log_ab)
    for i in range(40): log_rejection(log_ab, f"b_agent_{i}", RejectionReason.TRUST_BELOW_FLOOR, "DISCOVERY")
    
    # B accepts 95% of A's agents
    for i in range(95): log_acceptance(log_ba)
    for i in range(5): log_rejection(log_ba, f"a_agent_{i}", RejectionReason.TTL_EXPIRED, "OPERATIONAL")
    
    gossip_ab = generate_gossip(log_ab, now - 86400)
    gossip_ba = generate_gossip(log_ba, now - 86400)
    
    alerts = detect_divergence([gossip_ab, gossip_ba])
    for alert in alerts:
        print(f"  {alert['registry_pair']}: {alert['divergence']}")
        print(f"    A rejects B: {alert['rate_a_rejects_b']:.1%}, B rejects A: {alert['rate_b_rejects_a']:.1%}")
        print(f"    Asymmetry: {alert['asymmetry']:.1%}")
        print(f"    Circuit breaker: {alert['circuit_breaker']}")
    print()


def scenario_systematic_rejection():
    """Both registries reject each other — fundamental incompatibility."""
    print("=== Scenario: Systematic Mutual Rejection ===")
    now = time.time()
    
    log_ab = BridgeLog("bridge_ab", "registry_a", "registry_b")
    log_ba = BridgeLog("bridge_ba", "registry_b", "registry_a")
    
    for i in range(30): log_acceptance(log_ab)
    for i in range(70): log_rejection(log_ab, f"b_{i}", RejectionReason.GRADE_INSUFFICIENT, "DISCOVERY")
    
    for i in range(25): log_acceptance(log_ba)
    for i in range(75): log_rejection(log_ba, f"a_{i}", RejectionReason.DIVERSITY_BELOW_MIN, "DISCOVERY")
    
    gossip_ab = generate_gossip(log_ab, now - 86400)
    gossip_ba = generate_gossip(log_ba, now - 86400)
    
    alerts = detect_divergence([gossip_ab, gossip_ba])
    for alert in alerts:
        print(f"  {alert['registry_pair']}: {alert['divergence']}")
        print(f"    Avg rejection: {alert['avg_rejection']:.1%}")
        print(f"    Circuit breaker: {alert['circuit_breaker']}")
        print(f"    → Registries fundamentally disagree on acceptance criteria")
    
    print(f"  A top reasons: {gossip_ab.top_reasons}")
    print(f"  B top reasons: {gossip_ba.top_reasons}")
    print()


if __name__ == "__main__":
    print("Rejection Index — Cross-Registry Divergence Detection")
    print("Per santaclawd: hybrid local + gossip architecture")
    print("=" * 70)
    print()
    print(f"Gossip interval: {GOSSIP_INTERVAL_HOURS}h")
    print(f"Divergence thresholds: LOW={DIVERGENCE_THRESHOLD_LOW:.0%}, HIGH={DIVERGENCE_THRESHOLD_HIGH:.0%}")
    print(f"Circuit breaker: {CIRCUIT_BREAKER_DIVERGENCE:.0%}")
    print()
    
    scenario_normal_bridge()
    scenario_asymmetric_divergence()
    scenario_systematic_rejection()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Local per-bridge for latency. Gossip for patterns. Periodic, not real-time.")
    print("2. Asymmetric rejection = policy divergence (A trusts B, B distrusts A).")
    print("3. Symmetric high rejection = fundamental incompatibility.")
    print("4. Gossip at checkpoint interval — rejection_count + hash_tree.")
    print("5. Same circuit-breaker pipeline — divergence feeds ceremony like drift does.")
