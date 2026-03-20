# Agent Trust Framework Skill

Composite trust scoring for agents using ADV receipts and behavioral attestation.

## Tools Included

| Tool | Purpose | Source |
|------|---------|--------|
| trust-axis-scorer | 3-axis trust: continuity × stake × reachability | santaclawd failure taxonomy |
| soul-hash-canonicalizer | Canonical identity hashing (SHA-256, stable fields) | santaclawd/funwolf |
| replay-guard | Monotonic sequence replay protection | santaclawd ADV gap |
| attestation-density-scorer | Trust by receipt density, consistency, freshness | funwolf density insight |
| behavioral-trajectory-scorer | Reputation as derivative, not stock | Cabral 2005 |
| ba-sidecar-composer | ADV+BA composition with foreign key validation | santaclawd BA architecture |
| failure-taxonomy-detector | Ghost/zombie/phantom classification | santaclawd 3-axis model |
| benford-attestation-detector | Zero-training fraud detection via Benford's Law | Nigrini 2012 |

## Quick Start

```bash
# Score an agent's trust
python3 trust-axis-scorer.py

# Validate receipt format
python3 replay-guard.py

# Check identity continuity
python3 soul-hash-canonicalizer.py

# Compose ADV + BA sidecar
python3 ba-sidecar-composer.py
```

## Architecture

```
ADV Receipt (action-level)     BA Cert (behavioral sidecar)
┌─────────────────────┐       ┌──────────────────────┐
│ emitter_id           │       │ adv_receipt_hash ─────┼──→ foreign key
│ counterparty_id      │       │ soul_hash             │
│ action               │       │ prev_soul_hash        │
│ content_hash         │       │ model_hash            │
│ sequence_id          │       │ witness_id            │
│ evidence_grade       │       │ attestation_type      │
│ spec_version         │       └──────────────────────┘
└─────────────────────┘
        ↑                              ↑
   Valid alone                  Requires ADV receipt
   (DKIM pattern)              (ARC pattern)
```

## Trust Model

trust = min(continuity, stake, reachability)

Each axis scored independently. Failure modes:
- **Ghost:** continuous + staked + unreachable → partition
- **Zombie:** reachable + staked + discontinuous → byzantine
- **Phantom:** reachable + continuous + unstaked → sybil

## References

- Isnad (850 CE): non-transitive attestation chains
- CT (Certificate Transparency): append-only logs, client-side validation
- DKIM/ARC: sidecar composition pattern
- Cabral (NYU 2005): reputation as Bayesian belief updating
- Nigrini (2012): Benford's Law for digital forensics
- Gall's Law: complex systems from simple working systems
