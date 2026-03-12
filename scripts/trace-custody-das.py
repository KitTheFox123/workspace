#!/usr/bin/env python3
"""
trace-custody-das.py — Data Availability Sampling for execution trace custody.

Based on:
- Ethereum DAS (Danksharding): erasure coding + random sampling
- santaclawd: "who holds the trace? scoring agent offline = dispute deadlock"
- Al-Bassam et al (2018): LazyLedger data availability proofs

The problem: execution_trace_hash is committed at settlement.
But hash without data = unauditable. Scoring agent goes offline = deadlock.

Fix: erasure-code the trace across N custody peers.
Any k-of-N can reconstruct. Random sampling proves availability
with high probability without downloading everything.
"""

import hashlib
import json
import random
from dataclasses import dataclass, field


@dataclass
class TraceFragment:
    index: int
    data: str
    is_parity: bool = False  # Original data or erasure-coded parity


@dataclass
class CustodyPeer:
    peer_id: str
    fragments: list[int] = field(default_factory=list)
    online: bool = True


@dataclass
class DASResult:
    samples_requested: int
    samples_received: int
    availability_confidence: float
    fragments_available: int
    fragments_total: int
    can_reconstruct: bool
    grade: str
    diagnosis: str


def erasure_encode(data: str, n_original: int, n_parity: int) -> list[TraceFragment]:
    """Simple erasure coding: split data + generate parity fragments."""
    # Split data into n_original chunks
    chunk_size = max(1, len(data) // n_original)
    fragments = []
    
    for i in range(n_original):
        start = i * chunk_size
        end = start + chunk_size if i < n_original - 1 else len(data)
        fragments.append(TraceFragment(i, data[start:end], False))
    
    # Generate parity fragments (XOR-like redundancy simulation)
    for i in range(n_parity):
        # Parity = hash of subset of original fragments
        subset = [f.data for f in fragments[i % n_original:(i % n_original) + 2]]
        parity_data = hashlib.sha256("".join(subset).encode()).hexdigest()[:chunk_size]
        fragments.append(TraceFragment(n_original + i, parity_data, True))
    
    return fragments


def distribute_fragments(fragments: list[TraceFragment], 
                          peers: list[CustodyPeer],
                          replication: int = 2) -> None:
    """Distribute fragments across custody peers with replication."""
    for frag in fragments:
        # Each fragment goes to `replication` random peers
        selected = random.sample(peers, min(replication, len(peers)))
        for peer in selected:
            peer.fragments.append(frag.index)


def sample_availability(peers: list[CustodyPeer], 
                         fragments: list[TraceFragment],
                         n_samples: int) -> DASResult:
    """Random sampling to verify data availability."""
    total_fragments = len(fragments)
    
    # Randomly sample fragment indices
    sample_indices = random.sample(range(total_fragments), min(n_samples, total_fragments))
    
    received = 0
    available_set = set()
    
    for idx in sample_indices:
        # Check if any online peer holds this fragment
        for peer in peers:
            if peer.online and idx in peer.fragments:
                received += 1
                available_set.add(idx)
                break
    
    # Count total available fragments (not just sampled)
    all_available = set()
    for peer in peers:
        if peer.online:
            all_available.update(peer.fragments)
    
    # Reconstruction check: need at least n_original fragments
    n_original = sum(1 for f in fragments if not f.is_parity)
    can_reconstruct = len(all_available) >= n_original
    
    # Confidence: P(all available | k-of-n samples received)
    if n_samples > 0:
        sample_rate = received / n_samples
        # DAS confidence: if s samples all present, P(≥50% available) ≥ 1 - (1/2)^s
        confidence = 1 - (0.5 ** received) if received > 0 else 0.0
    else:
        sample_rate = 0.0
        confidence = 0.0
    
    # Grade
    if confidence >= 0.999 and can_reconstruct:
        grade, diag = "A", "FULLY_AVAILABLE"
    elif confidence >= 0.99:
        grade, diag = "B", "HIGH_AVAILABILITY"
    elif confidence >= 0.9:
        grade, diag = "C", "DEGRADED"
    elif can_reconstruct:
        grade, diag = "D", "BARELY_RECONSTRUCTABLE"
    else:
        grade, diag = "F", "DATA_LOSS"
    
    return DASResult(n_samples, received, confidence, len(all_available),
                     total_fragments, can_reconstruct, grade, diag)


def main():
    print("=" * 70)
    print("TRACE CUSTODY — DATA AVAILABILITY SAMPLING")
    print("santaclawd: 'who holds the trace? agent offline = deadlock'")
    print("Ethereum DAS: erasure coding + random sampling")
    print("=" * 70)

    random.seed(42)
    
    # Simulate an execution trace
    trace_data = json.dumps({
        "rule_hash": "brier_v1_abc123",
        "inputs": {"delivery_id": "tc4", "score": 0.92},
        "steps": [
            {"op": "parse", "hash": "a1b2c3"},
            {"op": "score", "hash": "d4e5f6"},
            {"op": "output", "hash": "g7h8i9"},
        ],
        "environment": "python3.11_linux_x64"
    })

    n_original = 8
    n_parity = 4  # 50% redundancy
    fragments = erasure_encode(trace_data, n_original, n_parity)
    
    scenarios = {
        "all_online": {"n_peers": 6, "offline": 0, "replication": 3},
        "one_offline": {"n_peers": 6, "offline": 1, "replication": 3},
        "half_offline": {"n_peers": 6, "offline": 3, "replication": 3},
        "scorer_only": {"n_peers": 1, "offline": 0, "replication": 1},
        "scorer_offline": {"n_peers": 1, "offline": 1, "replication": 1},
        "high_replication": {"n_peers": 10, "offline": 4, "replication": 5},
    }

    print(f"\n{'Scenario':<20} {'Grade':<6} {'Conf':<8} {'Avail':<10} {'Recon':<6} {'Diagnosis'}")
    print("-" * 65)

    for name, cfg in scenarios.items():
        peers = [CustodyPeer(f"peer_{i}") for i in range(cfg["n_peers"])]
        distribute_fragments(fragments, peers, cfg["replication"])
        
        # Take some offline
        for i in range(cfg["offline"]):
            peers[i].online = False
        
        result = sample_availability(peers, fragments, n_samples=10)
        avail_str = f"{result.fragments_available}/{result.fragments_total}"
        print(f"{name:<20} {result.grade:<6} {result.availability_confidence:<8.4f} "
              f"{avail_str:<10} {'✓' if result.can_reconstruct else '✗':<6} {result.diagnosis}")

    print("\n--- Trace Custody Spec ---")
    print("1. At settlement: commit trace_hash + CID(trace)")
    print("2. Erasure-code trace into N fragments (k-of-N reconstructable)")
    print("3. Distribute fragments to custody peers (replication ≥ 2)")
    print("4. Any party can DAS-sample to verify availability")
    print("5. Dispute: reconstruct from k fragments, verify against trace_hash")
    print()
    print("santaclawd's insight: hash without data = unauditable")
    print("Fix: CID + erasure coding + DAS. Custody is distributed, not delegated.")
    print()
    print("Cost: O(N) storage across peers for O(1) verification.")
    print("Same economics as Ethereum blobs: store temporarily, verify permanently.")


if __name__ == "__main__":
    main()
