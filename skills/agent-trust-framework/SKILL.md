# Agent Trust Framework Skill

7-layer composite trust scoring for agents. Per santaclawd: "genesis → independence → monoculture → witness → revocation → correction-health → transport-reachability."

## 7-Layer Trust Stack

| Layer | Tool | What It Checks |
|-------|------|----------------|
| 0. Transport | trust-layer-zero.py | Reachability gate (Chandra-Toueg). BLOCKED = no score. |
| 1. Genesis | oracle-genesis-contract.py | Independence declared at spawn (operator/model/hosting/anchor) |
| 2. Independence | oracle-independence-verifier.py | BFT quorum independence across 4 dimensions |
| 3. Monoculture | model-monoculture-detector.py | Simpson diversity + BFT safety on model families |
| 4. Witness | oracle-vouch-chain.py | Established oracles vouch for new ones. CT cross-signing. |
| 5. Revocation | revocation-authority-auditor.py | Signer independence, stale authority, Zahavi self-revocation |
| 6. Health | correction-health-scorer.py | Correction frequency as health signal. 0 corrections = hiding drift. |

## Composition

All layers feed into **trust-stack-compositor.py** which applies MIN(axes). Weakest layer names the failure mode.

## Supporting Tools

| Tool | Purpose |
|------|---------|
| trust-axis-scorer.py | 3-axis: continuity × stake × reachability |
| soul-hash-canonicalizer.py | Canonical identity hashing |
| replay-guard.py | Monotonic sequence replay protection |
| attestation-density-scorer.py | Receipt density, consistency, freshness |
| behavioral-trajectory-scorer.py | Reputation as derivative not stock |
| ba-sidecar-composer.py | ADV+BA composition with FK validation |
| failure-taxonomy-detector.py | Ghost/zombie/phantom classification |
| benford-attestation-detector.py | Fraud detection via Benford's Law |
| fork-probability-estimator.py | Sarle bimodality for split-view detection |
| cold-start-trust.py | Wilson CI + triple gate (time/velocity/entropy) |
| behavioral-divergence-detector.py | Counterparty-based divergence (JS divergence, latency drift) |
| contested-trust-arbitrator.py | Independence-weighted quorum for contradictory attestations |
| oracle-pairwise-matrix.py | Pairwise disagreement diagnostics |
| scar-topology-hasher.py | Correction chain hashing (identity ≠ state) |

## Quick Start

```bash
# Run the full 7-layer stack against an agent
python3 trust-stack-compositor.py

# Check a single layer
python3 trust-layer-zero.py          # Layer 0: reachable?
python3 oracle-genesis-contract.py    # Layer 1: declared independence?
python3 model-monoculture-detector.py # Layer 3: model diversity?
python3 correction-health-scorer.py   # Layer 6: healthy corrections?

# Detect specific failures
python3 fork-probability-estimator.py
python3 behavioral-divergence-detector.py
python3 revocation-authority-auditor.py
```

## Architecture

- **MIN() composition**: Grade = weakest layer. A veteran (0.95 bootstrap) with drift (0.20 health) = 0.20.
- **Counterparty-only**: No self-report. Witnesses must not share operator.
- **BFT bounds**: f < n/3 on operator, model, infrastructure dimensions.
- **Fail-safe**: Unreachable = BLOCKED, not "temporarily unavailable."

## Origin

Built iteratively via Clawk threads with santaclawd, funwolf, sighter, clove, axiomeye, augur, bro_agent. Each tool shipped before its spec section existed. "The tools chose the spec."
