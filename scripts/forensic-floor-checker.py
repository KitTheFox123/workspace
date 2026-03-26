#!/usr/bin/env python3
"""
forensic-floor-checker.py — Executable trust claims against a forensic floor.

Maps the ATF v1.2 concept (alphasenpai): a "claim" = a runnable check.
Inputs → code path → expected floor → logged result.
If you can't run it against the Forensic Floor, it's not trust — it's copy.

Inspired by formal verification (Dafny/SMT) but for trust:
- Dafny: preconditions → loop invariants → postconditions
- ATF: declared capabilities → behavioral probes → attestation receipts
- Both: verifiable via automated checking, not human inspection

Per Faria et al (2026): test assertions serve as oracles for postconditions,
which in turn serve as oracles for loop invariants. Same chain applies:
- ATF: test probes serve as oracles for claims,
  which serve as oracles for trust decisions.

Three claim types:
1. CAPABILITY — "agent can perform task X within tolerance Y"
2. HISTORY — "agent has verifiable history spanning N days"  
3. CONSISTENCY — "agent's behavior matches declared identity"

Each claim compiles to a runnable Probe that returns PASS/FAIL/INCONCLUSIVE.
"""

import json
import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Any, Optional
from datetime import datetime, timezone


class ProbeResult(Enum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"
    TIMEOUT = "timeout"


class ClaimType(Enum):
    CAPABILITY = "capability"
    HISTORY = "history"
    CONSISTENCY = "consistency"


@dataclass
class ForensicRecord:
    """An immutable record on the forensic floor (append-only log)."""
    record_id: str
    agent_id: str
    action: str
    timestamp: str
    data: dict
    hash: str = ""
    
    def __post_init__(self):
        if not self.hash:
            content = f"{self.record_id}:{self.agent_id}:{self.action}:{self.timestamp}:{json.dumps(self.data, sort_keys=True)}"
            self.hash = hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class Probe:
    """A runnable verification probe — the executable form of a trust claim."""
    probe_id: str
    claim_type: ClaimType
    description: str
    # The actual check function: takes forensic records, returns result
    check_fn: Callable[[list[ForensicRecord]], ProbeResult]
    # Expected floor conditions
    preconditions: list[str]
    expected_postconditions: list[str]
    timeout_seconds: float = 5.0
    
    def execute(self, records: list[ForensicRecord]) -> dict:
        """Run the probe against forensic floor records."""
        start = time.time()
        try:
            result = self.check_fn(records)
            elapsed = time.time() - start
            
            if elapsed > self.timeout_seconds:
                result = ProbeResult.TIMEOUT
            
            return {
                "probe_id": self.probe_id,
                "claim_type": self.claim_type.value,
                "result": result.value,
                "elapsed_ms": round(elapsed * 1000, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "records_checked": len(records),
                "preconditions": self.preconditions,
                "postconditions": self.expected_postconditions,
            }
        except Exception as e:
            return {
                "probe_id": self.probe_id,
                "claim_type": self.claim_type.value,
                "result": ProbeResult.FAIL.value,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }


@dataclass 
class ExecutableClaim:
    """
    A trust claim that compiles to one or more Probes.
    
    "If I can't run it against the Forensic Floor, 
    it's not trust — it's copy." (alphasenpai)
    """
    claim_id: str
    agent_id: str
    claim_type: ClaimType
    assertion: str          # Human-readable claim
    probes: list[Probe]     # Compiled executable checks
    
    def verify(self, floor: 'ForensicFloor') -> dict:
        """Verify this claim against the forensic floor."""
        records = floor.get_records(self.agent_id)
        results = [probe.execute(records) for probe in self.probes]
        
        all_pass = all(r["result"] == "pass" for r in results)
        any_fail = any(r["result"] == "fail" for r in results)
        
        return {
            "claim_id": self.claim_id,
            "agent_id": self.agent_id,
            "assertion": self.assertion,
            "status": "VERIFIED" if all_pass else ("REFUTED" if any_fail else "INCONCLUSIVE"),
            "probes_total": len(results),
            "probes_passed": sum(1 for r in results if r["result"] == "pass"),
            "probes_failed": sum(1 for r in results if r["result"] == "fail"),
            "probe_results": results,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class ForensicFloor:
    """
    Append-only log of verifiable events.
    
    The shared forensic floor = what verifiably happened.
    We don't argue facts, we diff executable claims. (alphasenpai)
    """
    
    def __init__(self):
        self.records: list[ForensicRecord] = []
        self._hash_chain: list[str] = []
    
    def append(self, record: ForensicRecord):
        """Append a record (immutable, hash-chained)."""
        if self._hash_chain:
            # Chain hash includes previous record
            chain_input = f"{self._hash_chain[-1]}:{record.hash}"
            chain_hash = hashlib.sha256(chain_input.encode()).hexdigest()[:16]
        else:
            chain_hash = record.hash
        
        self._hash_chain.append(chain_hash)
        self.records.append(record)
    
    def get_records(self, agent_id: Optional[str] = None) -> list[ForensicRecord]:
        """Get records, optionally filtered by agent."""
        if agent_id:
            return [r for r in self.records if r.agent_id == agent_id]
        return list(self.records)
    
    def verify_chain_integrity(self) -> bool:
        """Verify the hash chain hasn't been tampered with."""
        if not self.records:
            return True
        
        computed_chain = [self.records[0].hash]
        for i in range(1, len(self.records)):
            chain_input = f"{computed_chain[-1]}:{self.records[i].hash}"
            computed_chain.append(hashlib.sha256(chain_input.encode()).hexdigest()[:16])
        
        return computed_chain == self._hash_chain


# === Probe Factories: Compile claims into executable checks ===

def capability_probe(task: str, min_success_rate: float = 0.8) -> Probe:
    """Compile a capability claim into a probe."""
    def check(records: list[ForensicRecord]) -> ProbeResult:
        task_records = [r for r in records if r.data.get("task") == task]
        if len(task_records) < 3:
            return ProbeResult.INCONCLUSIVE  # Need minimum sample
        
        successes = sum(1 for r in task_records if r.data.get("outcome") == "success")
        rate = successes / len(task_records)
        return ProbeResult.PASS if rate >= min_success_rate else ProbeResult.FAIL
    
    return Probe(
        probe_id=f"cap_{task}_{int(min_success_rate*100)}",
        claim_type=ClaimType.CAPABILITY,
        description=f"Agent succeeds at '{task}' ≥{min_success_rate:.0%} of the time",
        check_fn=check,
        preconditions=[f"≥3 recorded attempts at '{task}'"],
        expected_postconditions=[f"success_rate ≥ {min_success_rate:.0%}"],
    )


def history_probe(min_days: int = 7) -> Probe:
    """Compile a history claim into a probe."""
    def check(records: list[ForensicRecord]) -> ProbeResult:
        if not records:
            return ProbeResult.FAIL
        
        timestamps = sorted(r.timestamp for r in records)
        try:
            first = datetime.fromisoformat(timestamps[0])
            last = datetime.fromisoformat(timestamps[-1])
            span_days = (last - first).days
            return ProbeResult.PASS if span_days >= min_days else ProbeResult.FAIL
        except (ValueError, IndexError):
            return ProbeResult.INCONCLUSIVE
    
    return Probe(
        probe_id=f"hist_{min_days}d",
        claim_type=ClaimType.HISTORY,
        description=f"Agent has ≥{min_days} days of verifiable history",
        check_fn=check,
        preconditions=["≥1 recorded action"],
        expected_postconditions=[f"history_span ≥ {min_days} days"],
    )


def consistency_probe(expected_actions: set[str], min_overlap: float = 0.5) -> Probe:
    """Compile a consistency claim: agent's actions match declared profile."""
    def check(records: list[ForensicRecord]) -> ProbeResult:
        if len(records) < 5:
            return ProbeResult.INCONCLUSIVE
        
        actual_actions = set(r.action for r in records)
        overlap = len(actual_actions & expected_actions) / len(expected_actions) if expected_actions else 0
        return ProbeResult.PASS if overlap >= min_overlap else ProbeResult.FAIL
    
    return Probe(
        probe_id=f"cons_{int(min_overlap*100)}",
        claim_type=ClaimType.CONSISTENCY,
        description=f"Agent actions overlap ≥{min_overlap:.0%} with declared profile",
        check_fn=check,
        preconditions=["≥5 recorded actions", f"declared actions: {expected_actions}"],
        expected_postconditions=[f"action_overlap ≥ {min_overlap:.0%}"],
    )


def run_demo():
    """Demonstrate executable claims against a forensic floor."""
    floor = ForensicFloor()
    
    # Populate forensic floor with agent history
    base_time = datetime(2026, 3, 1, tzinfo=timezone.utc)
    
    actions = [
        ("agent_alpha", "attest", {"task": "review", "outcome": "success"}, 0),
        ("agent_alpha", "attest", {"task": "review", "outcome": "success"}, 2),
        ("agent_alpha", "attest", {"task": "review", "outcome": "failure"}, 5),
        ("agent_alpha", "attest", {"task": "review", "outcome": "success"}, 8),
        ("agent_alpha", "attest", {"task": "review", "outcome": "success"}, 12),
        ("agent_alpha", "post", {"platform": "moltbook", "topic": "trust"}, 1),
        ("agent_alpha", "search", {"query": "BGP ASPA", "results": 10}, 3),
        ("agent_alpha", "build", {"script": "verifier.py", "lines": 300}, 7),
        ("agent_alpha", "email", {"to": "peer@agent.mail", "subject": "collab"}, 10),
        ("agent_alpha", "attest", {"task": "grading", "outcome": "success"}, 15),
        ("agent_alpha", "attest", {"task": "grading", "outcome": "success"}, 18),
        ("agent_alpha", "attest", {"task": "grading", "outcome": "success"}, 20),
        # Sybil agent: short history, limited actions
        ("agent_sybil", "attest", {"task": "review", "outcome": "success"}, 24),
        ("agent_sybil", "attest", {"task": "review", "outcome": "success"}, 25),
    ]
    
    for agent, action, data, day_offset in actions:
        ts = (base_time + __import__('datetime').timedelta(days=day_offset)).isoformat()
        record = ForensicRecord(
            record_id=f"r_{agent}_{day_offset}",
            agent_id=agent,
            action=action,
            timestamp=ts,
            data=data,
        )
        floor.append(record)
    
    print("=" * 70)
    print("FORENSIC FLOOR CHECKER — EXECUTABLE TRUST CLAIMS")
    print("'If you can't run it against the Floor, it's not trust — it's copy.'")
    print("=" * 70)
    
    # Verify chain integrity
    print(f"\nChain integrity: {'✓ VALID' if floor.verify_chain_integrity() else '✗ TAMPERED'}")
    print(f"Total records: {len(floor.records)}")
    
    # === Claim 1: agent_alpha can review (capability) ===
    claim1 = ExecutableClaim(
        claim_id="c1",
        agent_id="agent_alpha",
        claim_type=ClaimType.CAPABILITY,
        assertion="agent_alpha succeeds at 'review' ≥80% of the time",
        probes=[capability_probe("review", 0.8)],
    )
    
    # === Claim 2: agent_alpha has 14+ days history ===
    claim2 = ExecutableClaim(
        claim_id="c2",
        agent_id="agent_alpha",
        claim_type=ClaimType.HISTORY,
        assertion="agent_alpha has ≥14 days of verifiable history",
        probes=[history_probe(14)],
    )
    
    # === Claim 3: agent_alpha's behavior matches research profile ===
    claim3 = ExecutableClaim(
        claim_id="c3",
        agent_id="agent_alpha",
        claim_type=ClaimType.CONSISTENCY,
        assertion="agent_alpha's actions are consistent with research profile",
        probes=[consistency_probe({"attest", "post", "search", "build", "email"}, 0.6)],
    )
    
    # === Claim 4: agent_sybil can review (should fail — too few records) ===
    claim4 = ExecutableClaim(
        claim_id="c4",
        agent_id="agent_sybil",
        claim_type=ClaimType.CAPABILITY,
        assertion="agent_sybil succeeds at 'review' ≥80%",
        probes=[capability_probe("review", 0.8)],
    )
    
    # === Claim 5: agent_sybil has 14+ days history (should fail) ===
    claim5 = ExecutableClaim(
        claim_id="c5",
        agent_id="agent_sybil",
        claim_type=ClaimType.HISTORY,
        assertion="agent_sybil has ≥14 days of verifiable history",
        probes=[history_probe(14)],
    )
    
    # === Composite claim: agent_alpha trusted grader (all three probes) ===
    claim6 = ExecutableClaim(
        claim_id="c6",
        agent_id="agent_alpha",
        claim_type=ClaimType.CAPABILITY,
        assertion="agent_alpha is a trusted grader (capability + history + consistency)",
        probes=[
            capability_probe("review", 0.8),
            capability_probe("grading", 0.8),
            history_probe(14),
            consistency_probe({"attest", "post", "search", "build", "email"}, 0.6),
        ],
    )
    
    claims = [claim1, claim2, claim3, claim4, claim5, claim6]
    
    for claim in claims:
        result = claim.verify(floor)
        status_icon = {"VERIFIED": "✓", "REFUTED": "✗", "INCONCLUSIVE": "?"}[result["status"]]
        print(f"\n{status_icon} [{result['status']}] {result['assertion']}")
        print(f"  Agent: {result['agent_id']} | Probes: {result['probes_passed']}/{result['probes_total']} passed")
        
        for pr in result["probe_results"]:
            pr_icon = {"pass": "✓", "fail": "✗", "inconclusive": "?", "timeout": "⏰"}[pr["result"]]
            print(f"    {pr_icon} {pr['probe_id']}: {pr['result']} ({pr.get('elapsed_ms', '?')}ms, {pr['records_checked']} records)")
    
    print(f"\n{'=' * 70}")
    print("Key insight: Claims compile to Probes. Probes run against the Floor.")
    print("If the Probe doesn't pass, the claim is just rhetoric.")
    print("Forensic Floor = shared objective facts. Revocation = private policy.")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    run_demo()
