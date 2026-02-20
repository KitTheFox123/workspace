#!/usr/bin/env python3
"""Fork Fingerprint Detector — detect identity forks via causal hash chains.

Based on PBFT quorum intersection: if two observers each see 2f+1 consistent
states, at least one honest node overlaps. Fork detection requires sufficient
observer overlap between branches.

Usage:
    python3 fork-fingerprint.py --demo          # Run synthetic fork scenarios
    python3 fork-fingerprint.py --agent KIT      # Show agent's chain
"""

import argparse
import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class ForkFingerprint:
    agent_id: str
    branch_hash: str  # sha256(state_snapshot)
    parent_hash: str  # previous branch_hash
    causal_pointers: list[str] = field(default_factory=list)  # hashes of last N actions
    witness_set: list[str] = field(default_factory=list)
    witness_quorum: float = 0.67
    timestamp: float = 0.0
    sequence: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]


class AgentChain:
    """Simulates an agent's causal chain of states."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.fingerprints: list[ForkFingerprint] = []
        genesis_hash = sha256(f"genesis:{agent_id}")
        self.fingerprints.append(ForkFingerprint(
            agent_id=agent_id,
            branch_hash=genesis_hash,
            parent_hash="0" * 16,
            timestamp=time.time(),
            sequence=0,
        ))

    def append_action(self, action: str, witnesses: list[str]) -> ForkFingerprint:
        prev = self.fingerprints[-1]
        action_hash = sha256(f"{prev.branch_hash}:{action}")
        state_hash = sha256(f"{prev.branch_hash}:{action_hash}:{prev.sequence + 1}")
        fp = ForkFingerprint(
            agent_id=self.agent_id,
            branch_hash=state_hash,
            parent_hash=prev.branch_hash,
            causal_pointers=[action_hash] + prev.causal_pointers[:4],
            witness_set=witnesses,
            timestamp=time.time(),
            sequence=prev.sequence + 1,
        )
        self.fingerprints.append(fp)
        return fp

    def fork_at(self, sequence: int) -> "AgentChain":
        """Create a forked chain diverging at the given sequence number."""
        forked = AgentChain.__new__(AgentChain)
        forked.agent_id = self.agent_id
        forked.fingerprints = [fp for fp in self.fingerprints if fp.sequence <= sequence]
        return forked


class ForkDetector:
    """Detects forks by comparing fingerprints from multiple observers."""

    def __init__(self, quorum_threshold: float = 0.67):
        self.quorum_threshold = quorum_threshold
        self.observed: dict[str, list[ForkFingerprint]] = {}  # observer -> fingerprints seen

    def report(self, observer_id: str, fp: ForkFingerprint):
        """An observer reports seeing a fingerprint."""
        self.observed.setdefault(observer_id, []).append(fp)

    def detect_forks(self, agent_id: str) -> list[dict]:
        """Check for forks: same agent, same sequence, different branch_hash."""
        # Collect all fingerprints for this agent, grouped by sequence
        seq_map: dict[int, dict[str, set]] = {}  # seq -> {branch_hash -> {observers}}
        for observer, fps in self.observed.items():
            for fp in fps:
                if fp.agent_id != agent_id:
                    continue
                seq_map.setdefault(fp.sequence, {})
                seq_map[fp.sequence].setdefault(fp.branch_hash, set())
                seq_map[fp.sequence][fp.branch_hash].add(observer)

        forks = []
        for seq, branches in seq_map.items():
            if len(branches) > 1:
                total_observers = set()
                for obs in branches.values():
                    total_observers |= obs
                # Check quorum intersection
                branch_list = list(branches.items())
                for i, (h1, obs1) in enumerate(branch_list):
                    for h2, obs2 in branch_list[i + 1:]:
                        overlap = obs1 & obs2
                        forks.append({
                            "sequence": seq,
                            "branch_a": h1,
                            "branch_b": h2,
                            "observers_a": len(obs1),
                            "observers_b": len(obs2),
                            "overlap": len(overlap),
                            "total_observers": len(total_observers),
                            "confidence": len(overlap) / len(total_observers) if total_observers else 0,
                            "verdict": "CONFIRMED_FORK" if len(overlap) == 0 else "INCONSISTENCY",
                        })
        return forks

    def chain_integrity(self, agent_id: str) -> dict:
        """Verify causal chain integrity across all observations."""
        all_fps: dict[int, ForkFingerprint] = {}
        breaks = []
        for fps in self.observed.values():
            for fp in fps:
                if fp.agent_id != agent_id:
                    continue
                if fp.sequence in all_fps:
                    if all_fps[fp.sequence].branch_hash != fp.branch_hash:
                        continue  # fork, handled by detect_forks
                else:
                    all_fps[fp.sequence] = fp

        sorted_seqs = sorted(all_fps.keys())
        for i in range(1, len(sorted_seqs)):
            prev_seq = sorted_seqs[i - 1]
            curr_seq = sorted_seqs[i]
            if all_fps[curr_seq].parent_hash != all_fps[prev_seq].branch_hash:
                breaks.append({
                    "gap": f"{prev_seq} -> {curr_seq}",
                    "expected_parent": all_fps[prev_seq].branch_hash,
                    "actual_parent": all_fps[curr_seq].parent_hash,
                })

        return {
            "agent_id": agent_id,
            "chain_length": len(sorted_seqs),
            "integrity_breaks": len(breaks),
            "breaks": breaks,
            "status": "VALID" if not breaks else "BROKEN",
        }


def run_demo():
    print("=== Fork Fingerprint Detector Demo ===\n")

    # Create an agent chain
    kit = AgentChain("agent:kit")
    observers = ["obs_A", "obs_B", "obs_C", "obs_D", "obs_E"]

    # Normal operations
    kit.append_action("post:clawk:dunbar-thread", observers[:3])
    kit.append_action("reply:clove:compound-interest", observers[1:4])
    kit.append_action("email:gerundium:fork-spec", observers[2:5])

    print(f"Kit's chain: {len(kit.fingerprints)} fingerprints")
    for fp in kit.fingerprints:
        print(f"  seq={fp.sequence} hash={fp.branch_hash} parent={fp.parent_hash}")

    # Create a fork at sequence 2
    evil_kit = kit.fork_at(2)
    evil_kit.append_action("EVIL:drain-wallet", ["obs_X", "obs_Y"])

    print(f"\nForked chain: {len(evil_kit.fingerprints)} fingerprints")
    for fp in evil_kit.fingerprints:
        print(f"  seq={fp.sequence} hash={fp.branch_hash} parent={fp.parent_hash}")

    # Set up detector
    detector = ForkDetector()

    # Observers report what they see
    for fp in kit.fingerprints:
        for obs in fp.witness_set:
            detector.report(obs, fp)
        # Also report to observers who see the full chain
        detector.report("obs_B", fp)

    # Evil fork observers
    for fp in evil_kit.fingerprints[3:]:  # only the divergent part
        for obs in fp.witness_set:
            detector.report(obs, fp)

    # Detect
    print("\n--- Fork Detection ---")
    forks = detector.detect_forks("agent:kit")
    if forks:
        for f in forks:
            print(f"  🔴 FORK at seq {f['sequence']}: {f['verdict']}")
            print(f"     Branch A ({f['branch_a'][:8]}..): {f['observers_a']} observers")
            print(f"     Branch B ({f['branch_b'][:8]}..): {f['observers_b']} observers")
            print(f"     Overlap: {f['overlap']}/{f['total_observers']} ({f['confidence']:.0%})")
    else:
        print("  ✅ No forks detected")

    # Chain integrity
    print("\n--- Chain Integrity ---")
    integrity = detector.chain_integrity("agent:kit")
    print(f"  Chain length: {integrity['chain_length']}")
    print(f"  Status: {integrity['status']}")
    if integrity['breaks']:
        for b in integrity['breaks']:
            print(f"  ⚠️  Break at {b['gap']}")

    # Quorum analysis
    print("\n--- Quorum Analysis ---")
    total_obs = len(set(observers + ["obs_X", "obs_Y"]))
    f_max = (total_obs - 1) // 3
    print(f"  Total observers: {total_obs}")
    print(f"  Max tolerable faulty (f): {f_max}")
    print(f"  Quorum needed (2f+1): {2 * f_max + 1}")
    print(f"  Key insight: fork detection requires observer overlap ≥ 1 honest node")
    print(f"  Without overlap, fork looks identical to network partition")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fork Fingerprint Detector")
    parser.add_argument("--demo", action="store_true", help="Run demo scenario")
    args = parser.parse_args()

    if args.demo:
        run_demo()
    else:
        parser.print_help()
