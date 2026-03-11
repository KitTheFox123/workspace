#!/usr/bin/env python3
"""
split-view-detector.py — Detect CT-style split-view attacks in attestation logs.

santaclawd's insight: even with stable address + cert chain, the cert log 
can diverge silently. A split-view attack shows different state to different 
queriers. Fix: gossip protocol between monitors.

Each attestor reports what they see. If attestor A sees state X and attestor B
sees state Y for the same agent at the same epoch, one of them is being lied to.

Based on:
- RFC6962 CT gossip requirements
- Trillian Tessera (2025): tiled transparency logs
- Ostertág 2024 (arXiv 2405.05206): anomaly detection in CT logs
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ObservedState:
    """What an attestor saw at a given epoch."""
    attestor_id: str
    agent_id: str
    epoch: int
    state_hash: str  # hash of observed agent state
    tree_head: str   # signed tree head from attestor's view
    timestamp: float


@dataclass
class ConsistencyCheck:
    """Result of comparing two attestors' views."""
    attestor_a: str
    attestor_b: str
    agent_id: str
    epoch: int
    state_match: bool
    tree_match: bool
    verdict: str  # CONSISTENT, SPLIT_VIEW, PARTIAL_DIVERGENCE


class SplitViewDetector:
    def __init__(self):
        self.observations: list[ObservedState] = []
        self.checks: list[ConsistencyCheck] = []
    
    def record_observation(self, obs: ObservedState):
        self.observations.append(obs)
    
    def gossip_check(self, agent_id: str, epoch: int) -> list[ConsistencyCheck]:
        """Cross-check all attestor views for an agent at an epoch."""
        epoch_obs = [o for o in self.observations 
                     if o.agent_id == agent_id and o.epoch == epoch]
        
        checks = []
        for i in range(len(epoch_obs)):
            for j in range(i + 1, len(epoch_obs)):
                a, b = epoch_obs[i], epoch_obs[j]
                state_match = a.state_hash == b.state_hash
                tree_match = a.tree_head == b.tree_head
                
                if state_match and tree_match:
                    verdict = "CONSISTENT"
                elif not state_match and not tree_match:
                    verdict = "SPLIT_VIEW"  # Full divergence — attack likely
                else:
                    verdict = "PARTIAL_DIVERGENCE"  # One matches, other doesn't
                
                check = ConsistencyCheck(
                    attestor_a=a.attestor_id,
                    attestor_b=b.attestor_id,
                    agent_id=agent_id,
                    epoch=epoch,
                    state_match=state_match,
                    tree_match=tree_match,
                    verdict=verdict
                )
                checks.append(check)
                self.checks.append(check)
        
        return checks
    
    def detect_splits(self) -> dict:
        """Analyze all checks for split-view patterns."""
        if not self.checks:
            return {"total_checks": 0, "splits": 0, "grade": "N/A"}
        
        total = len(self.checks)
        splits = sum(1 for c in self.checks if c.verdict == "SPLIT_VIEW")
        partial = sum(1 for c in self.checks if c.verdict == "PARTIAL_DIVERGENCE")
        consistent = sum(1 for c in self.checks if c.verdict == "CONSISTENT")
        
        split_rate = splits / total
        
        if splits == 0 and partial == 0:
            grade = "A"  # All consistent
        elif splits == 0 and partial > 0:
            grade = "B"  # Partial issues (timing, propagation delay)
        elif split_rate < 0.1:
            grade = "C"  # Some splits detected
        else:
            grade = "F"  # Widespread split-view attack
        
        return {
            "total_checks": total,
            "consistent": consistent,
            "partial_divergence": partial,
            "split_views": splits,
            "split_rate": round(split_rate, 3),
            "grade": grade
        }
    
    def identify_byzantine(self) -> dict:
        """Identify attestors showing different views (potential Byzantine nodes)."""
        attestor_splits = {}
        for check in self.checks:
            if check.verdict in ("SPLIT_VIEW", "PARTIAL_DIVERGENCE"):
                for a_id in (check.attestor_a, check.attestor_b):
                    attestor_splits[a_id] = attestor_splits.get(a_id, 0) + 1
        
        # Attestor appearing in most splits is most likely Byzantine
        if not attestor_splits:
            return {"byzantine_candidates": [], "confidence": "N/A"}
        
        max_splits = max(attestor_splits.values())
        candidates = [a for a, count in attestor_splits.items() if count == max_splits]
        
        return {
            "byzantine_candidates": candidates,
            "split_counts": attestor_splits,
            "confidence": "HIGH" if max_splits > 2 else "LOW"
        }


def make_hash(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def demo():
    detector = SplitViewDetector()
    
    # Scenario 1: Honest network — all attestors see same state
    print("=" * 60)
    print("SPLIT-VIEW DETECTOR — CT Gossip for Agent Trust")
    print("=" * 60)
    
    agent = "agent_alpha"
    honest_state = make_hash("agent_alpha:epoch5:scope_ok:actions_logged")
    honest_tree = make_hash("tree_head:epoch5:root_abc")
    
    for attestor in ["monitor_A", "monitor_B", "monitor_C"]:
        detector.record_observation(ObservedState(
            attestor_id=attestor,
            agent_id=agent,
            epoch=5,
            state_hash=honest_state,
            tree_head=honest_tree,
            timestamp=1000005.0
        ))
    
    checks = detector.gossip_check(agent, 5)
    print(f"\n--- Epoch 5: Honest Network ---")
    for c in checks:
        print(f"  {c.attestor_a} ↔ {c.attestor_b}: {c.verdict}")
    
    # Scenario 2: Split-view attack — monitor_C sees different state
    split_state = make_hash("agent_alpha:epoch6:TAMPERED:scope_modified")
    split_tree = make_hash("tree_head:epoch6:root_FORKED")
    honest_state_6 = make_hash("agent_alpha:epoch6:scope_ok:actions_logged")
    honest_tree_6 = make_hash("tree_head:epoch6:root_def")
    
    for attestor in ["monitor_A", "monitor_B"]:
        detector.record_observation(ObservedState(
            attestor_id=attestor,
            agent_id=agent,
            epoch=6,
            state_hash=honest_state_6,
            tree_head=honest_tree_6,
            timestamp=1000006.0
        ))
    
    # Byzantine attestor or split-view log
    detector.record_observation(ObservedState(
        attestor_id="monitor_C",
        agent_id=agent,
        epoch=6,
        state_hash=split_state,
        tree_head=split_tree,
        timestamp=1000006.0
    ))
    
    checks = detector.gossip_check(agent, 6)
    print(f"\n--- Epoch 6: Split-View Attack ---")
    for c in checks:
        print(f"  {c.attestor_a} ↔ {c.attestor_b}: {c.verdict}")
    
    # Scenario 3: Propagation delay — same tree, slightly different state
    for attestor in ["monitor_A", "monitor_B"]:
        detector.record_observation(ObservedState(
            attestor_id=attestor,
            agent_id=agent,
            epoch=7,
            state_hash=make_hash("agent_alpha:epoch7:state_v1"),
            tree_head=make_hash("tree:epoch7"),
            timestamp=1000007.0
        ))
    
    detector.record_observation(ObservedState(
        attestor_id="monitor_C",
        agent_id=agent,
        epoch=7,
        state_hash=make_hash("agent_alpha:epoch7:state_v2"),  # Slightly behind
        tree_head=make_hash("tree:epoch7"),  # Same tree
        timestamp=1000007.0
    ))
    
    checks = detector.gossip_check(agent, 7)
    print(f"\n--- Epoch 7: Propagation Delay ---")
    for c in checks:
        print(f"  {c.attestor_a} ↔ {c.attestor_b}: {c.verdict}")
    
    # Results
    results = detector.detect_splits()
    byzantine = detector.identify_byzantine()
    
    print(f"\n{'=' * 60}")
    print(f"DETECTION RESULTS")
    print(f"  Total cross-checks: {results['total_checks']}")
    print(f"  Consistent: {results['consistent']}")
    print(f"  Partial divergence: {results['partial_divergence']}")
    print(f"  Split-views: {results['split_views']}")
    print(f"  Split rate: {results['split_rate']}")
    print(f"  Grade: {results['grade']}")
    
    print(f"\n  Byzantine candidates: {byzantine['byzantine_candidates']}")
    print(f"  Split counts: {byzantine['split_counts']}")
    print(f"  Confidence: {byzantine['confidence']}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: Gossip between monitors catches split-view attacks.")
    print("Without cross-checking, each attestor trusts their own view.")
    print("CT solved this: require 2+ SCTs from DIFFERENT logs.")
    print("Agent equivalent: require 2+ independent observed_hashes.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
