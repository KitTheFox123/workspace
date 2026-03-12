#!/usr/bin/env python3
"""
trust-conservation-auditor.py — Verify trust conservation across transformations.

Noether insight (Clawk thread Feb 25): trust is conserved, not created.
Every transformation (escrow→rep, gen-time→verification-free) should
conserve total trust. If trust appears from nowhere = inflation. If it
vanishes = leakage.

Audits a sequence of trust events and checks conservation.
"""

import json
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class TrustEvent:
    """A trust transformation event."""
    timestamp: str
    event_type: str  # "creation", "transfer", "decay", "destruction"
    source: str      # where trust comes from
    target: str      # where trust goes
    amount: float    # trust units
    proof_type: str  # what backs it
    metadata: dict = field(default_factory=dict)


# Trust creation requires proof work (no free trust)
CREATION_COSTS = {
    "x402_tx": 0.95,      # payment = high trust yield
    "gen_sig": 0.80,       # generation sig = moderate
    "dkim": 0.70,          # transport proof = moderate
    "witness": 0.50,       # witness = lower (single point)
    "self_attestation": 0.10,  # self-report = minimal
}

# Decay rates per proof type (fraction lost per day)
DECAY_RATES = {
    "x402_tx": 0.001,      # payment proofs decay very slowly
    "gen_sig": 0.005,      # generation sigs moderate
    "dkim": 0.01,          # transport proofs faster
    "witness": 0.02,       # witness attestations fastest
    "self_attestation": 0.05,  # self-reports decay fast
}


def audit_conservation(events: list[dict]) -> dict:
    """Audit a sequence of trust events for conservation violations."""
    ledger = {}  # agent -> trust balance
    violations = []
    total_created = 0.0
    total_destroyed = 0.0
    total_decayed = 0.0
    
    for i, e in enumerate(events):
        evt = TrustEvent(**e) if isinstance(e, dict) else e
        
        if evt.event_type == "creation":
            # Trust creation requires proof work
            cost = CREATION_COSTS.get(evt.proof_type, 0.30)
            effective = evt.amount * cost
            ledger[evt.target] = ledger.get(evt.target, 0.0) + effective
            total_created += effective
            
            if evt.proof_type == "self_attestation" and evt.amount > 0.5:
                violations.append({
                    "event": i,
                    "type": "inflation",
                    "detail": f"self-attestation creating {evt.amount} trust (max credible: 0.5)",
                    "severity": "high",
                })
        
        elif evt.event_type == "transfer":
            # Conservation: source loses, target gains (minus friction)
            friction = 0.05  # 5% transfer cost
            source_bal = ledger.get(evt.source, 0.0)
            
            if evt.amount > source_bal + 0.01:  # small epsilon
                violations.append({
                    "event": i,
                    "type": "overdraft",
                    "detail": f"{evt.source} transferring {evt.amount} but balance is {source_bal:.3f}",
                    "severity": "critical",
                })
            
            ledger[evt.source] = max(0, source_bal - evt.amount)
            ledger[evt.target] = ledger.get(evt.target, 0.0) + evt.amount * (1 - friction)
            total_destroyed += evt.amount * friction  # friction = trust destroyed
        
        elif evt.event_type == "decay":
            rate = DECAY_RATES.get(evt.proof_type, 0.01)
            days = evt.amount  # amount = days elapsed
            for agent in ledger:
                decay = ledger[agent] * (1 - math.exp(-rate * days))
                ledger[agent] -= decay
                total_decayed += decay
        
        elif evt.event_type == "destruction":
            bal = ledger.get(evt.target, 0.0)
            destroyed = min(evt.amount, bal)
            ledger[evt.target] = max(0, bal - destroyed)
            total_destroyed += destroyed
    
    # Conservation check
    total_balance = sum(ledger.values())
    expected = total_created - total_destroyed - total_decayed
    conservation_error = abs(total_balance - expected)
    conserved = conservation_error < 0.01
    
    return {
        "conserved": conserved,
        "conservation_error": round(conservation_error, 6),
        "total_created": round(total_created, 3),
        "total_destroyed": round(total_destroyed, 3),
        "total_decayed": round(total_decayed, 3),
        "balances": {k: round(v, 3) for k, v in ledger.items()},
        "violations": violations,
        "n_events": len(events),
        "audited_at": datetime.now(timezone.utc).isoformat(),
    }


def demo():
    """Demo with tc3-like scenario."""
    print("=== Trust Conservation Auditor ===\n")
    
    # Healthy tc3 flow
    healthy = [
        {"timestamp": "2026-02-24T06:00:00Z", "event_type": "creation", "source": "system",
         "target": "kit_fox", "amount": 1.0, "proof_type": "x402_tx", "metadata": {"tx": "tc3_escrow"}},
        {"timestamp": "2026-02-24T07:00:00Z", "event_type": "creation", "source": "system",
         "target": "kit_fox", "amount": 0.8, "proof_type": "gen_sig", "metadata": {"deliverable": "tc3"}},
        {"timestamp": "2026-02-24T07:30:00Z", "event_type": "creation", "source": "system",
         "target": "kit_fox", "amount": 0.7, "proof_type": "dkim", "metadata": {"email": "delivery"}},
        {"timestamp": "2026-02-24T08:00:00Z", "event_type": "transfer", "source": "kit_fox",
         "target": "bro_agent", "amount": 0.5, "proof_type": "witness", "metadata": {"attestation": True}},
    ]
    
    result = audit_conservation(healthy)
    print(f"  TC3 healthy flow:")
    print(f"    Conserved: {result['conserved']} (error: {result['conservation_error']})")
    print(f"    Created: {result['total_created']}, Destroyed: {result['total_destroyed']}")
    print(f"    Balances: {result['balances']}")
    print(f"    Violations: {len(result['violations'])}\n")
    
    # Sybil inflation attack
    sybil = [
        {"timestamp": "2026-02-25T00:00:00Z", "event_type": "creation", "source": "system",
         "target": "sybil_1", "amount": 5.0, "proof_type": "self_attestation", "metadata": {}},
        {"timestamp": "2026-02-25T00:01:00Z", "event_type": "transfer", "source": "sybil_1",
         "target": "sybil_2", "amount": 3.0, "proof_type": "self_attestation", "metadata": {}},
        {"timestamp": "2026-02-25T00:02:00Z", "event_type": "transfer", "source": "sybil_2",
         "target": "attacker", "amount": 2.0, "proof_type": "self_attestation", "metadata": {}},
    ]
    
    result = audit_conservation(sybil)
    print(f"  Sybil inflation attack:")
    print(f"    Conserved: {result['conserved']} (error: {result['conservation_error']})")
    print(f"    Created: {result['total_created']}, Destroyed: {result['total_destroyed']}")
    print(f"    Balances: {result['balances']}")
    print(f"    Violations: {len(result['violations'])}")
    for v in result['violations']:
        print(f"    ⚠️  [{v['severity']}] {v['type']}: {v['detail']}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        events = json.loads(sys.stdin.read())
        result = audit_conservation(events)
        print(json.dumps(result, indent=2))
    else:
        demo()
