#!/usr/bin/env python3
"""
enforcement-fallback.py — Graceful degradation for receipt enforcement.

Per Clawk thread (Mar 16): "shipping default-reject without coordinated
fallback is how you get silent failures at scale. Chrome could hold because
browsers have update channels."

The problem: Agent runtimes have no Chrome-style coordinated update path.
STRICT enforcement without fallback = broken transactions, not better trust.

Solution: Enforcement with graceful degradation.
- STRICT mode rejects unverified receipts
- But offers FALLBACK: accept with higher escrow / shorter timeout / limited scope
- The "Not Secure" label equivalent: transaction proceeds but consumer is WARNED
- Degraded mode is worse than verified mode but better than rejection

Chrome analogy:
- Chrome doesn't refuse to load HTTP — it labels it "Not Secure"
- Users CAN proceed, but they see the risk
- The forcing function is the UX, not the block

Agent analogy:
- Don't refuse unverified agents — degrade their terms
- Unverified = 2x escrow, 50% shorter timeout, 50% lower tx limit
- Verified = standard terms
- The economic pressure drives adoption without breaking transactions
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class VerificationStatus(Enum):
    VERIFIED = "verified"       # Full Merkle + witnesses + diversity
    PARTIAL = "partial"         # Some checks pass, some fail
    UNVERIFIED = "unverified"   # No valid receipt
    EXPIRED = "expired"         # Had receipt, now stale


@dataclass
class TransactionTerms:
    """Terms applied to a transaction based on verification status."""
    escrow_multiplier: float      # 1.0 = standard, 2.0 = double escrow
    timeout_multiplier: float     # 1.0 = standard, 0.5 = half timeout
    tx_limit_multiplier: float    # 1.0 = standard, 0.5 = half max
    warning_level: str            # "none", "info", "warning", "danger"
    label: str                    # Human-readable status label
    
    @property
    def economic_penalty(self) -> float:
        """Overall penalty (1.0 = no penalty, higher = worse terms)."""
        return self.escrow_multiplier / (self.timeout_multiplier * self.tx_limit_multiplier)


class FallbackEnforcer:
    """
    Graduated enforcement with economic fallback.
    
    Instead of binary accept/reject:
    - Verified agents get standard terms
    - Unverified agents get degraded terms (economic pressure)
    - The degradation IS the forcing function
    
    Chrome parallel:
    - HTTP sites aren't blocked, they're labeled "Not Secure"
    - Users can proceed but see the risk
    - Economic pressure (lower conversion) drives HTTPS adoption
    """
    
    TERMS = {
        VerificationStatus.VERIFIED: TransactionTerms(
            escrow_multiplier=1.0,
            timeout_multiplier=1.0,
            tx_limit_multiplier=1.0,
            warning_level="none",
            label="✅ Verified",
        ),
        VerificationStatus.PARTIAL: TransactionTerms(
            escrow_multiplier=1.5,
            timeout_multiplier=0.75,
            tx_limit_multiplier=0.75,
            warning_level="info",
            label="⚠️ Partially Verified",
        ),
        VerificationStatus.UNVERIFIED: TransactionTerms(
            escrow_multiplier=2.0,
            timeout_multiplier=0.5,
            tx_limit_multiplier=0.5,
            warning_level="warning",
            label="🔴 Unverified — degraded terms apply",
        ),
        VerificationStatus.EXPIRED: TransactionTerms(
            escrow_multiplier=1.75,
            timeout_multiplier=0.6,
            tx_limit_multiplier=0.6,
            warning_level="warning",
            label="⏰ Expired — re-verification needed",
        ),
    }
    
    def __init__(self):
        self.transactions: list[dict] = []
        self.adoption_pressure: dict[str, list] = {}  # agent_id → [status history]
    
    def evaluate_transaction(
        self,
        agent_id: str,
        verification_status: VerificationStatus,
        base_escrow: float = 1.0,
        base_timeout_h: float = 24.0,
        base_tx_limit: float = 10.0,
    ) -> dict:
        """Evaluate transaction terms based on verification status."""
        terms = self.TERMS[verification_status]
        
        actual_escrow = base_escrow * terms.escrow_multiplier
        actual_timeout = base_timeout_h * terms.timeout_multiplier
        actual_limit = base_tx_limit * terms.tx_limit_multiplier
        
        # Track adoption pressure
        if agent_id not in self.adoption_pressure:
            self.adoption_pressure[agent_id] = []
        self.adoption_pressure[agent_id].append({
            "status": verification_status.value,
            "penalty": terms.economic_penalty,
            "timestamp": time.time(),
        })
        
        result = {
            "agent_id": agent_id,
            "verification": verification_status.value,
            "label": terms.label,
            "warning_level": terms.warning_level,
            "terms": {
                "escrow": f"{actual_escrow:.2f} SOL (base: {base_escrow:.2f})",
                "timeout": f"{actual_timeout:.1f}h (base: {base_timeout_h:.1f}h)",
                "tx_limit": f"{actual_limit:.2f} SOL (base: {base_tx_limit:.2f})",
            },
            "economic_penalty": f"{terms.economic_penalty:.2f}x",
            "accepted": True,  # Always accepted — just with different terms
        }
        
        self.transactions.append(result)
        return result
    
    def adoption_report(self) -> dict:
        """How much economic pressure is being applied."""
        total = len(self.transactions)
        by_status = {}
        for tx in self.transactions:
            s = tx["verification"]
            by_status[s] = by_status.get(s, 0) + 1
        
        # Cumulative penalty per agent
        agent_penalties = {}
        for agent_id, history in self.adoption_pressure.items():
            avg_penalty = sum(h["penalty"] for h in history) / len(history)
            agent_penalties[agent_id] = {
                "transactions": len(history),
                "avg_penalty": f"{avg_penalty:.2f}x",
                "verified_rate": f"{sum(1 for h in history if h['status'] == 'verified') / len(history):.0%}",
            }
        
        # Agents with worst terms (highest avg penalty)
        worst = sorted(
            agent_penalties.items(),
            key=lambda x: float(x[1]["avg_penalty"].rstrip("x")),
            reverse=True,
        )
        
        return {
            "total_transactions": total,
            "by_status": by_status,
            "verified_rate": f"{by_status.get('verified', 0) / max(total, 1):.0%}",
            "agents_under_pressure": len([
                a for a, p in agent_penalties.items()
                if float(p["avg_penalty"].rstrip("x")) > 1.5
            ]),
            "worst_agents": worst[:5],
        }


def demo():
    """Demonstrate fallback enforcement."""
    print("=" * 60)
    print("ENFORCEMENT FALLBACK — Economic pressure, not rejection")
    print("Chrome 'Not Secure' model for agent trust")
    print("=" * 60)
    
    enforcer = FallbackEnforcer()
    
    scenarios = [
        ("agent:verified_pro", VerificationStatus.VERIFIED, "Fully verified agent"),
        ("agent:partial_newbie", VerificationStatus.PARTIAL, "Some checks pass"),
        ("agent:no_receipt", VerificationStatus.UNVERIFIED, "No valid receipt at all"),
        ("agent:stale_cert", VerificationStatus.EXPIRED, "Receipt was valid, now 48h old"),
        ("agent:no_receipt", VerificationStatus.UNVERIFIED, "Same unverified agent, 2nd tx"),
    ]
    
    for agent_id, status, description in scenarios:
        result = enforcer.evaluate_transaction(
            agent_id=agent_id,
            verification_status=status,
            base_escrow=1.0,
            base_timeout_h=24.0,
            base_tx_limit=10.0,
        )
        print(f"\n  {description}")
        print(f"  Agent: {result['agent_id']}")
        print(f"  Status: {result['label']}")
        print(f"  Escrow: {result['terms']['escrow']}")
        print(f"  Timeout: {result['terms']['timeout']}")
        print(f"  Tx Limit: {result['terms']['tx_limit']}")
        print(f"  Penalty: {result['economic_penalty']}")
        print(f"  Accepted: {result['accepted']} (always — just with terms)")
    
    print(f"\n{'='*60}")
    print("ADOPTION PRESSURE REPORT")
    print(f"{'='*60}")
    report = enforcer.adoption_report()
    print(f"  Total: {report['total_transactions']}")
    print(f"  Verified rate: {report['verified_rate']}")
    print(f"  By status: {report['by_status']}")
    print(f"  Agents under pressure: {report['agents_under_pressure']}")
    if report['worst_agents']:
        print(f"  Worst terms:")
        for agent, stats in report['worst_agents']:
            print(f"    {agent}: {stats['avg_penalty']} penalty, "
                  f"{stats['verified_rate']} verified")
    
    # Key insight
    print(f"\n  💡 Key insight: No transaction was REJECTED.")
    print(f"     Unverified agents pay 2x escrow + 50% shorter timeout.")
    print(f"     The economic pressure IS the forcing function.")
    print(f"     Chrome didn't block HTTP — it labeled it 'Not Secure'.")


if __name__ == "__main__":
    demo()
