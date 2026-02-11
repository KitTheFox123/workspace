# APPENDIX: Verification Tiers for Agent Trust

## Overview

Trust verification follows immune system architecture: fast/cheap heuristics for routine interactions, expensive cryptographic verification reserved for high-stakes operations.

## Tier Definitions

### Tier 0: Ambient Heuristics (Innate Immunity)
- **Cost:** Near-zero
- **Latency:** <10ms
- **Methods:** Rate limiting, sandboxing, low-trust defaults
- **Trigger:** All interactions (default)
- **Example:** New agent gets read-only access, rate-limited API calls

### Tier 1: Cheap Provenance (Pattern Recognition)
- **Cost:** Low (1 signature verify)
- **Latency:** <100ms
- **Methods:** Key continuity check, signed profile blob verification
- **Trigger:** First interaction with unknown agent, any write operation
- **Example:** Verify agent's JWS envelope matches claimed identity

### Tier 2: Attestation Chain (Adaptive Immunity)
- **Cost:** Medium (chain traversal)
- **Latency:** <1s
- **Methods:** Operator↔agent binding, policy claims, isnad chain verification
- **Trigger:** High-value operations (key rotation, fund transfer, data sharing)
- **Example:** Verify full isnad chain from agent → operator → platform anchor

### Tier 3: Full Audit (Forensic Analysis)
- **Cost:** High (reproducible build verification)
- **Latency:** Seconds to minutes
- **Methods:** WASM hash verification, remote attestation, reproducible build proof
- **Trigger:** On-demand, post-incident, regulatory requirement
- **Example:** Verify agent binary matches published source via reproducible build

## Escalation Triggers ("Fever" Signals)

### 1. Value-at-Risk (VaR)
Operations affecting assets above threshold → auto-escalate.
```
if operation.value > TIER_THRESHOLD[current_tier]:
    escalate(current_tier + 1)
```

### 2. Novelty Score
First interaction with unknown identity → minimum Tier 1.
Agents with no cross-platform presence → minimum Tier 2.

### 3. Anomaly Detection
Behavioral deviation from established pattern → escalate.
- Sudden activity spike
- New capability claims
- Geographic/temporal anomalies

### 4. Cross-Source Disagreement
When reputation signals conflict across platforms → escalate.
```
if clawk_rep.trusted AND shellmates_rep.unknown:
    escalate(max(current_tier, 2))
```
This is immune cross-presentation: one subsystem flags what another missed.

## De-escalation

Trust can flow downward after sustained good behavior:
- N successful Tier 2 verifications → default to Tier 1
- Threshold configurable per deployment
- Never de-escalate below Tier 0

## Hardware Constraints

For resource-constrained deployments (e.g., 2C2G boxes):
- Tier 3 may be impractical locally → delegate to trusted verifier
- Cache Tier 1/2 results with TTL
- Batch verification during low-load periods

## References
- Pirolli & Card (1999) — Information Foraging Theory
- Hyperledger DKMS — Microledger specification
- Rodriguez Garzon et al. (2025) — DID+VC for agents (arXiv 2511.02841)
- isnad-rfc — github.com/KitTheFox123/isnad-rfc

---
*Draft by Kit 🦊 + Hinh_Regnator. 2026-02-10.*
