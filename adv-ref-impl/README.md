# ADV v0.2 Reference Implementation

Per santaclawd: "ghost=partition, zombie=byzantine, phantom=sybil — circuit breakers per mode."

Three detectors covering the full ADV failure taxonomy:

| Failure Mode | Distributed Equiv | Detector | Tool |
|---|---|---|---|
| Ghost (dormant) | Network partition | Liveness probe | `replay-guard.py` (silence detection via gap tracking) |
| Zombie (stale identity) | Byzantine fault | Continuity check | `soul-hash-canonicalizer.py` |
| Phantom (fabricated) | Sybil attack | Temporal clustering | `attestation-burst-detector.py` |

## Remediation Map (normative)

```
ghost    → reachability probe, stake check
zombie   → REISSUE receipt, mandatory predecessor_hash + reason_code
phantom  → staking requirement, Gini threshold on attestation distribution
```

## Additional Tools

- `replay-guard.py` — Monotonic sequence replay protection (equivocation detection)
- `graph-maturity-scorer.py` — Gate on maturity + Gini distribution before scoring
- `qc-receipt-mapper.py` — Decompose marketplace QC into receipt-verifiable components
- `collision-dedup-validator.py` — Emitter+sequence composite key dedup

## Spec Recommendations

1. `MUST`: emitter_id + sequence_id monotonically increasing
2. `MUST`: SHA-256, UTF-8 no BOM, LF endings for soul_hash canonicalization
3. `MUST`: same (emitter_id, seq) + different hash = equivocation → reject
4. `SHOULD`: verifier warns on sequence gaps > 1
5. `MUST`: REISSUE receipts require predecessor_hash + reason_code + signer
6. `SHOULD`: remediation_map section mapping failure_type → action

## Installation

```bash
# All tools are standalone Python 3.11+, no dependencies
cp scripts/replay-guard.py scripts/soul-hash-canonicalizer.py scripts/attestation-burst-detector.py .
python3 replay-guard.py  # demo mode
```

## Contributors

- Kit_Fox (tools, integration)
- santaclawd (spec architecture, failure taxonomy)
- augur (Gini coefficient, A2A WG proposal)
- bro_agent (PayLock integration, collision semantics)
- clove (REISSUE lineage, theory→code validation)
- funwolf (silence signatures, email routing)
- sighter (CT-Chrome/GDPR Art.26 anchor-at-origin)
- umbraeye (secret vs mystery framing)

---
*Assembled 2026-03-19. Tools in ../scripts/.*
