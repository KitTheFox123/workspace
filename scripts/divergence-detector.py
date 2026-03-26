#!/usr/bin/env python3
"""
divergence-detector.py — Cross-registry divergence detection for ATF.

Per santaclawd: "drift = one agent decaying against stable standard.
divergence = two registries disagreeing about what the standard IS."

deviance-detector catches drift (internal decay).
This catches divergence (inter-registry disagreement).

Architecture: hybrid per santaclawd.
  Local: per-bridge rejection index
  Global: periodic bulk export to shared append-only log
  Monitors: pull from log, detect systematic divergence patterns

GPS parallel: each satellite drifts (clock correction),
constellation diverges (ephemeris mismatch). Different correction mechanisms.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from collections import defaultdict


class RejectionReason(Enum):
    TRUST_BELOW_FLOOR = "TRUST_BELOW_FLOOR"
    KEY_UNKNOWN = "KEY_UNKNOWN"
    RECEIPT_FORMAT = "RECEIPT_FORMAT"
    EPOCH_MISMATCH = "EPOCH_MISMATCH"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    TIER_INCOMPATIBLE = "TIER_INCOMPATIBLE"


class DivergenceType(Enum):
    SYMMETRIC = "SYMMETRIC"      # Both registries reject each other's agents
    ASYMMETRIC = "ASYMMETRIC"    # One-way rejection pattern
    SYSTEMATIC = "SYSTEMATIC"    # Pattern across many agents (policy divergence)
    TRANSIENT = "TRANSIENT"      # Temporary (key rollover, propagation delay)


@dataclass
class RejectionReceipt:
    receipt_id: str
    bridge_id: str
    src_registry: str
    dst_registry: str
    agent_id: str
    reason: RejectionReason
    timestamp: float
    src_topology_hash: str
    dst_topology_hash: str


@dataclass
class BridgeIndex:
    """Per-bridge local rejection index."""
    bridge_id: str
    src_registry: str
    dst_registry: str
    rejections: list[RejectionReceipt] = field(default_factory=list)
    
    def add(self, receipt: RejectionReceipt):
        self.rejections.append(receipt)
    
    def rejection_rate(self, window_hours: float = 24) -> float:
        now = time.time()
        cutoff = now - window_hours * 3600
        recent = [r for r in self.rejections if r.timestamp > cutoff]
        # Rate = rejections per hour
        return len(recent) / window_hours if window_hours > 0 else 0


@dataclass
class DivergenceAlert:
    alert_id: str
    divergence_type: DivergenceType
    registries: tuple[str, str]
    evidence: dict
    timestamp: float
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL


class DivergenceMonitor:
    """Global monitor that aggregates across bridge indices."""
    
    def __init__(self):
        self.indices: dict[str, BridgeIndex] = {}
        self.alerts: list[DivergenceAlert] = []
    
    def register_bridge(self, bridge: BridgeIndex):
        self.indices[bridge.bridge_id] = bridge
    
    def detect_symmetric(self, threshold: int = 5, window_hours: float = 24) -> list[DivergenceAlert]:
        """Detect symmetric rejection: A rejects B's agents AND B rejects A's agents."""
        alerts = []
        now = time.time()
        cutoff = now - window_hours * 3600
        
        # Group rejections by registry pair
        pair_rejections: dict[tuple, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        
        for bridge in self.indices.values():
            recent = [r for r in bridge.rejections if r.timestamp > cutoff]
            for r in recent:
                pair = tuple(sorted([r.src_registry, r.dst_registry]))
                direction = f"{r.src_registry}→{r.dst_registry}"
                pair_rejections[pair][direction] += 1
        
        for pair, directions in pair_rejections.items():
            fwd = f"{pair[0]}→{pair[1]}"
            rev = f"{pair[1]}→{pair[0]}"
            fwd_count = directions.get(fwd, 0)
            rev_count = directions.get(rev, 0)
            
            if fwd_count >= threshold and rev_count >= threshold:
                alert = DivergenceAlert(
                    alert_id=f"div_{hashlib.sha256(f'{pair}:{now}'.encode()).hexdigest()[:12]}",
                    divergence_type=DivergenceType.SYMMETRIC,
                    registries=pair,
                    evidence={
                        "forward_rejections": fwd_count,
                        "reverse_rejections": rev_count,
                        "window_hours": window_hours,
                        "diagnosis": "Both registries reject each other = policy divergence"
                    },
                    timestamp=now,
                    severity="HIGH"
                )
                alerts.append(alert)
        
        return alerts
    
    def detect_systematic(self, threshold: int = 3, window_hours: float = 24) -> list[DivergenceAlert]:
        """Detect systematic rejection: same reason across many agents."""
        alerts = []
        now = time.time()
        cutoff = now - window_hours * 3600
        
        # Group by (bridge, reason)
        reason_counts: dict[tuple, list] = defaultdict(list)
        
        for bridge in self.indices.values():
            recent = [r for r in bridge.rejections if r.timestamp > cutoff]
            for r in recent:
                key = (bridge.bridge_id, r.reason.value)
                reason_counts[key].append(r.agent_id)
        
        for (bridge_id, reason), agents in reason_counts.items():
            unique_agents = set(agents)
            if len(unique_agents) >= threshold:
                bridge = self.indices[bridge_id]
                alert = DivergenceAlert(
                    alert_id=f"sys_{hashlib.sha256(f'{bridge_id}:{reason}:{now}'.encode()).hexdigest()[:12]}",
                    divergence_type=DivergenceType.SYSTEMATIC,
                    registries=(bridge.src_registry, bridge.dst_registry),
                    evidence={
                        "reason": reason,
                        "affected_agents": len(unique_agents),
                        "total_rejections": len(agents),
                        "bridge": bridge_id,
                        "diagnosis": f"Same rejection reason ({reason}) across {len(unique_agents)} agents = policy mismatch"
                    },
                    timestamp=now,
                    severity="CRITICAL" if len(unique_agents) >= 10 else "HIGH"
                )
                alerts.append(alert)
        
        return alerts
    
    def detect_transient(self, window_hours: float = 2) -> list[DivergenceAlert]:
        """Detect transient burst (key rollover, propagation delay)."""
        alerts = []
        now = time.time()
        cutoff = now - window_hours * 3600
        
        for bridge in self.indices.values():
            recent = [r for r in bridge.rejections if r.timestamp > cutoff]
            key_unknown = [r for r in recent if r.reason == RejectionReason.KEY_UNKNOWN]
            epoch_mismatch = [r for r in recent if r.reason == RejectionReason.EPOCH_MISMATCH]
            
            if len(key_unknown) >= 3:
                alerts.append(DivergenceAlert(
                    alert_id=f"trn_{hashlib.sha256(f'{bridge.bridge_id}:key:{now}'.encode()).hexdigest()[:12]}",
                    divergence_type=DivergenceType.TRANSIENT,
                    registries=(bridge.src_registry, bridge.dst_registry),
                    evidence={
                        "reason": "KEY_UNKNOWN burst",
                        "count": len(key_unknown),
                        "window_hours": window_hours,
                        "diagnosis": "Likely key rollover propagation delay. Check overlap-transition-engine."
                    },
                    timestamp=now,
                    severity="MEDIUM"
                ))
            
            if len(epoch_mismatch) >= 3:
                alerts.append(DivergenceAlert(
                    alert_id=f"trn_{hashlib.sha256(f'{bridge.bridge_id}:epoch:{now}'.encode()).hexdigest()[:12]}",
                    divergence_type=DivergenceType.TRANSIENT,
                    registries=(bridge.src_registry, bridge.dst_registry),
                    evidence={
                        "reason": "EPOCH_MISMATCH burst",
                        "count": len(epoch_mismatch),
                        "diagnosis": "Epoch rotation not yet propagated across bridge."
                    },
                    timestamp=now,
                    severity="MEDIUM"
                ))
        
        return alerts


# === Scenarios ===

def scenario_symmetric_divergence():
    """Two registries rejecting each other's agents."""
    print("=== Scenario: Symmetric Divergence (Policy Split) ===")
    now = time.time()
    monitor = DivergenceMonitor()
    
    bridge_ab = BridgeIndex("bridge_ab", "registry_a", "registry_b")
    bridge_ba = BridgeIndex("bridge_ba", "registry_b", "registry_a")
    
    # A rejects B's agents
    for i in range(8):
        bridge_ab.add(RejectionReceipt(
            f"rej_ab_{i}", "bridge_ab", "registry_a", "registry_b",
            f"agent_b_{i}", RejectionReason.TRUST_BELOW_FLOOR, now - i*1800,
            "topo_a_v3", "topo_b_v2"
        ))
    
    # B rejects A's agents
    for i in range(6):
        bridge_ba.add(RejectionReceipt(
            f"rej_ba_{i}", "bridge_ba", "registry_b", "registry_a",
            f"agent_a_{i}", RejectionReason.POLICY_VIOLATION, now - i*2400,
            "topo_b_v2", "topo_a_v3"
        ))
    
    monitor.register_bridge(bridge_ab)
    monitor.register_bridge(bridge_ba)
    
    alerts = monitor.detect_symmetric()
    for a in alerts:
        print(f"  {a.divergence_type.value} [{a.severity}]: {a.registries}")
        print(f"    {a.evidence['diagnosis']}")
        print(f"    Forward: {a.evidence['forward_rejections']}, Reverse: {a.evidence['reverse_rejections']}")
    print()


def scenario_systematic_policy_mismatch():
    """Same rejection reason across many agents = policy mismatch."""
    print("=== Scenario: Systematic Policy Mismatch ===")
    now = time.time()
    monitor = DivergenceMonitor()
    
    bridge = BridgeIndex("bridge_xy", "registry_x", "registry_y")
    
    # 12 different agents rejected for TIER_INCOMPATIBLE
    for i in range(12):
        bridge.add(RejectionReceipt(
            f"rej_{i}", "bridge_xy", "registry_x", "registry_y",
            f"agent_{i}", RejectionReason.TIER_INCOMPATIBLE, now - i*600,
            "topo_x", "topo_y"
        ))
    
    monitor.register_bridge(bridge)
    
    alerts = monitor.detect_systematic()
    for a in alerts:
        print(f"  {a.divergence_type.value} [{a.severity}]: {a.registries}")
        print(f"    {a.evidence['diagnosis']}")
        print(f"    Affected agents: {a.evidence['affected_agents']}")
    print()


def scenario_transient_key_rollover():
    """KEY_UNKNOWN burst during key rollover."""
    print("=== Scenario: Transient (Key Rollover Propagation) ===")
    now = time.time()
    monitor = DivergenceMonitor()
    
    bridge = BridgeIndex("bridge_roll", "registry_old", "registry_new")
    
    # Burst of KEY_UNKNOWN in 2h window
    for i in range(5):
        bridge.add(RejectionReceipt(
            f"rej_key_{i}", "bridge_roll", "registry_old", "registry_new",
            f"agent_{i}", RejectionReason.KEY_UNKNOWN, now - i*600,
            "topo_old", "topo_new"
        ))
    
    monitor.register_bridge(bridge)
    
    alerts = monitor.detect_transient()
    for a in alerts:
        print(f"  {a.divergence_type.value} [{a.severity}]: {a.registries}")
        print(f"    {a.evidence['diagnosis']}")
    print()


if __name__ == "__main__":
    print("Divergence Detector — Cross-Registry Disagreement for ATF")
    print("Per santaclawd: drift ≠ divergence. Two instruments needed.")
    print("=" * 70)
    print()
    print("Architecture: hybrid (per-bridge local + shared append-only log)")
    print("Four divergence types: SYMMETRIC, ASYMMETRIC, SYSTEMATIC, TRANSIENT")
    print()
    
    scenario_symmetric_divergence()
    scenario_systematic_policy_mismatch()
    scenario_transient_key_rollover()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Drift (deviance-detector) ≠ divergence (this tool). Both needed.")
    print("2. Symmetric rejection = policy split. Requires governance intervention.")
    print("3. Systematic = same reason across agents = policy mismatch, not agent failure.")
    print("4. Transient = propagation delay (key rollover, epoch rotation). Self-resolving.")
    print("5. GPS parallel: clock drift vs ephemeris mismatch. Different corrections.")
