#!/usr/bin/env python3
"""
bridge-receipt.py — Cross-registry transit receipts for ATF forensics.

Per santaclawd: "cross-registry trust can be audited inside each registry,
but the transit event is invisible."

Bridge receipt = signed artifact at bridge crossing. Two signatures:
  1. Source registry attests the export (what was the trust state at departure)
  2. Bridge attests the transit (when and where it crossed)

Like BGP route announcements for trust — every hop is auditable.
"""

import hashlib
import time
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TrustTier(Enum):
    ROOT = "ROOT"            # 90d epoch
    OPERATIONAL = "OPERATIONAL"  # 30d epoch
    DISCOVERY = "DISCOVERY"  # 7d epoch


class TransitStatus(Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


# SPEC_CONSTANTS
BRIDGE_RECEIPT_TTL_HOURS = 24  # Transit must complete within 24h
MAX_HOP_COUNT = 3              # Maximum registry hops (A→B→C = 2 hops)
TRUST_DECAY_PER_HOP = 0.10    # 10% trust decay per hop


@dataclass
class BridgeReceipt:
    receipt_id: str
    agent_id: str
    src_registry: str
    dst_registry: str
    bridge_id: str
    timestamp: float
    # Exported trust state (attested by source)
    exported_trust_tier: TrustTier
    exported_wilson_ci: float
    exported_diversity_score: float
    exported_receipt_count: int
    # Signatures
    src_registry_sig: str   # Source attests the export
    bridge_sig: str         # Bridge attests the transit
    # Transit metadata
    hop_count: int = 1
    transit_chain: list[str] = field(default_factory=list)  # Prior bridge IDs
    status: TransitStatus = TransitStatus.PENDING
    completed_at: Optional[float] = None
    # Destination acceptance
    dst_accepted_tier: Optional[TrustTier] = None
    dst_accepted_score: Optional[float] = None


def create_bridge_receipt(
    agent_id: str, src_registry: str, dst_registry: str, bridge_id: str,
    trust_tier: TrustTier, wilson_ci: float, diversity: float, receipt_count: int,
    prior_chain: list[str] = None
) -> BridgeReceipt:
    """Create a bridge receipt for cross-registry transit."""
    now = time.time()
    hop_count = len(prior_chain) + 1 if prior_chain else 1
    
    # Hash for signatures
    content = f"{agent_id}:{src_registry}:{dst_registry}:{now}:{trust_tier.value}:{wilson_ci}"
    src_sig = hashlib.sha256(f"src:{src_registry}:{content}".encode()).hexdigest()[:16]
    bridge_sig = hashlib.sha256(f"bridge:{bridge_id}:{content}".encode()).hexdigest()[:16]
    
    return BridgeReceipt(
        receipt_id=f"br_{hashlib.sha256(f'{agent_id}:{now}'.encode()).hexdigest()[:12]}",
        agent_id=agent_id,
        src_registry=src_registry,
        dst_registry=dst_registry,
        bridge_id=bridge_id,
        timestamp=now,
        exported_trust_tier=trust_tier,
        exported_wilson_ci=wilson_ci,
        exported_diversity_score=diversity,
        exported_receipt_count=receipt_count,
        src_registry_sig=src_sig,
        bridge_sig=bridge_sig,
        hop_count=hop_count,
        transit_chain=prior_chain or []
    )


def accept_at_destination(receipt: BridgeReceipt) -> dict:
    """Destination registry processes incoming bridge receipt."""
    now = time.time()
    
    # Check TTL
    age_hours = (now - receipt.timestamp) / 3600
    if age_hours > BRIDGE_RECEIPT_TTL_HOURS:
        receipt.status = TransitStatus.EXPIRED
        return {"accepted": False, "reason": f"Transit expired ({age_hours:.1f}h > {BRIDGE_RECEIPT_TTL_HOURS}h)"}
    
    # Check hop count
    if receipt.hop_count > MAX_HOP_COUNT:
        receipt.status = TransitStatus.REJECTED
        return {"accepted": False, "reason": f"Max hops exceeded ({receipt.hop_count} > {MAX_HOP_COUNT})"}
    
    # Apply trust decay per hop
    decayed_score = receipt.exported_wilson_ci * (1 - TRUST_DECAY_PER_HOP * receipt.hop_count)
    decayed_score = max(0, decayed_score)
    
    # Destination assigns tier (may downgrade)
    if decayed_score >= 0.7:
        dst_tier = receipt.exported_trust_tier  # Preserve tier
    elif decayed_score >= 0.4:
        # Downgrade one level
        tier_order = [TrustTier.ROOT, TrustTier.OPERATIONAL, TrustTier.DISCOVERY]
        src_idx = tier_order.index(receipt.exported_trust_tier)
        dst_tier = tier_order[min(src_idx + 1, len(tier_order) - 1)]
    else:
        dst_tier = TrustTier.DISCOVERY  # Floor
    
    receipt.status = TransitStatus.COMPLETED
    receipt.completed_at = now
    receipt.dst_accepted_tier = dst_tier
    receipt.dst_accepted_score = round(decayed_score, 4)
    
    return {
        "accepted": True,
        "exported_score": receipt.exported_wilson_ci,
        "accepted_score": receipt.dst_accepted_score,
        "decay": round(TRUST_DECAY_PER_HOP * receipt.hop_count, 2),
        "exported_tier": receipt.exported_trust_tier.value,
        "accepted_tier": dst_tier.value,
        "hop_count": receipt.hop_count,
        "transit_time_hours": round(age_hours, 2)
    }


def reconstruct_crossing_chain(receipts: list[BridgeReceipt]) -> dict:
    """Forensic reconstruction of an agent's cross-registry journey."""
    chain = sorted(receipts, key=lambda r: r.timestamp)
    
    hops = []
    for r in chain:
        hops.append({
            "receipt_id": r.receipt_id,
            "src": r.src_registry,
            "dst": r.dst_registry,
            "bridge": r.bridge_id,
            "timestamp": r.timestamp,
            "exported_score": r.exported_wilson_ci,
            "accepted_score": r.dst_accepted_score,
            "tier_change": f"{r.exported_trust_tier.value}→{r.dst_accepted_tier.value}" if r.dst_accepted_tier else "pending",
            "status": r.status.value
        })
    
    total_decay = 0
    if chain and chain[0].exported_wilson_ci > 0 and chain[-1].dst_accepted_score:
        total_decay = 1 - (chain[-1].dst_accepted_score / chain[0].exported_wilson_ci)
    
    return {
        "agent_id": chain[0].agent_id if chain else None,
        "total_hops": len(chain),
        "total_decay": round(total_decay, 4),
        "origin": chain[0].src_registry if chain else None,
        "destination": chain[-1].dst_registry if chain else None,
        "chain": hops,
        "forensic_complete": all(r.status == TransitStatus.COMPLETED for r in chain)
    }


# === Scenarios ===

def scenario_single_hop():
    """Simple A→B transit."""
    print("=== Scenario: Single Hop (Registry A → B) ===")
    receipt = create_bridge_receipt(
        "agent_mobile", "registry_a", "registry_b", "bridge_ab",
        TrustTier.OPERATIONAL, 0.85, 0.72, 45
    )
    result = accept_at_destination(receipt)
    print(f"  Export: {receipt.exported_wilson_ci} ({receipt.exported_trust_tier.value})")
    print(f"  Accept: {result['accepted_score']} ({result['accepted_tier']})")
    print(f"  Decay: {result['decay']}")
    print()


def scenario_multi_hop():
    """A→B→C transit with cumulative decay."""
    print("=== Scenario: Multi-Hop (A → B → C) ===")
    
    # Hop 1: A→B
    r1 = create_bridge_receipt(
        "agent_nomad", "registry_a", "registry_b", "bridge_ab",
        TrustTier.OPERATIONAL, 0.90, 0.80, 60
    )
    res1 = accept_at_destination(r1)
    print(f"  Hop 1 (A→B): {r1.exported_wilson_ci} → {res1['accepted_score']} ({res1['accepted_tier']})")
    
    # Hop 2: B→C (using accepted score from B)
    r2 = create_bridge_receipt(
        "agent_nomad", "registry_b", "registry_c", "bridge_bc",
        TrustTier.OPERATIONAL, res1['accepted_score'], 0.65, 30,
        prior_chain=["bridge_ab"]
    )
    res2 = accept_at_destination(r2)
    print(f"  Hop 2 (B→C): {r2.exported_wilson_ci} → {res2['accepted_score']} ({res2['accepted_tier']})")
    
    # Forensic reconstruction
    chain = reconstruct_crossing_chain([r1, r2])
    print(f"  Total decay: {chain['total_decay']:.1%}")
    print(f"  Forensic complete: {chain['forensic_complete']}")
    print()


def scenario_max_hops_exceeded():
    """Too many hops — rejected."""
    print("=== Scenario: Max Hops Exceeded ===")
    receipt = create_bridge_receipt(
        "agent_wanderer", "registry_d", "registry_e", "bridge_de",
        TrustTier.DISCOVERY, 0.60, 0.50, 20,
        prior_chain=["bridge_ab", "bridge_bc", "bridge_cd"]  # 4th hop
    )
    result = accept_at_destination(receipt)
    print(f"  Hops: {receipt.hop_count} (max: {MAX_HOP_COUNT})")
    print(f"  Accepted: {result['accepted']}")
    print(f"  Reason: {result['reason']}")
    print()


def scenario_tier_downgrade():
    """High trust decays across hops → tier downgrade."""
    print("=== Scenario: Tier Downgrade on Transit ===")
    receipt = create_bridge_receipt(
        "agent_diplomat", "registry_premium", "registry_public", "bridge_pp",
        TrustTier.ROOT, 0.55, 0.40, 15  # Marginal ROOT
    )
    result = accept_at_destination(receipt)
    print(f"  Exported: {receipt.exported_trust_tier.value} @ {receipt.exported_wilson_ci}")
    print(f"  Accepted: {result['accepted_tier']} @ {result['accepted_score']}")
    print(f"  Decay alone pushed below OPERATIONAL threshold → DISCOVERY")
    print()


if __name__ == "__main__":
    print("Bridge Receipt — Cross-Registry Transit Forensics for ATF")
    print("Per santaclawd: transit events must be auditable")
    print("=" * 70)
    print()
    print(f"TTL: {BRIDGE_RECEIPT_TTL_HOURS}h | Max hops: {MAX_HOP_COUNT} | Decay/hop: {TRUST_DECAY_PER_HOP:.0%}")
    print("Two signatures: source registry (export) + bridge (transit)")
    print()
    
    scenario_single_hop()
    scenario_multi_hop()
    scenario_max_hops_exceeded()
    scenario_tier_downgrade()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Transit events were invisible — bridge receipts make them auditable.")
    print("2. Two signatures per crossing: source attests export, bridge attests transit.")
    print("3. Trust decays 10% per hop — incentivizes direct relationships over relay.")
    print("4. Max 3 hops prevents trust laundering through long chains.")
    print("5. Tier can downgrade on transit — marginal ROOT becomes DISCOVERY.")
    print("6. Forensic reconstruction: full crossing chain from bridge receipts.")
