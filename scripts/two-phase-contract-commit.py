#!/usr/bin/env python3
"""
two-phase-contract-commit.py — 2PC pattern for agent trust contracts.

Phase 1 (PREPARE/LOCK): Lock spec at delivery.
  - scope_hash, rule_hash, params_hash committed
  - All-or-nothing: 7 fields present or reject (bro_agent's spec gate)

Phase 2 (COMMIT/SETTLE): Commit execution at settlement.
  - execution_trace_hash, output_hash committed
  - Deterministic: trace is reproducible
  - Non-deterministic (LLM): trace proves process only

Based on:
- Gray & Lamport (2006): 2PC/3PC consensus
- bro_agent: "all-or-nothing spec gate, ABI v2.1"
- santaclawd: "execution_trace_hash in lock payload"
- Castillo et al (ICBC 2025): TCU chained verification

Maps exactly to PayLock v2→v3 evolution:
  v2 = Phase 1 only (spec locked)
  v3 = Phase 1 + Phase 2 (spec locked + execution committed)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ContractState(Enum):
    INIT = "init"
    PREPARED = "prepared"       # Phase 1 complete
    COMMITTED = "committed"     # Phase 2 complete
    ABORTED = "aborted"
    DISPUTED = "disputed"


@dataclass
class Phase1Lock:
    """Spec commitment at delivery time."""
    scope_hash: str
    rule_hash: str
    params_hash: str          # hash(α, β, ε, n_min)
    agent_id: str
    chain_tip: str
    timestamp: float
    rule_label: str           # Human-readable only, not in commitment hash

    def commitment_hash(self) -> str:
        """6 machine-verifiable fields → one hash."""
        payload = json.dumps({
            "scope_hash": self.scope_hash,
            "rule_hash": self.rule_hash,
            "params_hash": self.params_hash,
            "agent_id": self.agent_id,
            "chain_tip": self.chain_tip,
            "timestamp": self.timestamp,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def is_complete(self) -> bool:
        """All-or-nothing: all 6 machine fields present."""
        return all([
            self.scope_hash, self.rule_hash, self.params_hash,
            self.agent_id, self.chain_tip, self.timestamp
        ])


@dataclass
class Phase2Commit:
    """Execution commitment at settlement time."""
    input_hash: str
    output_hash: str
    execution_trace_hash: str
    environment_hash: str
    duration_ms: float
    is_deterministic: bool

    def commitment_hash(self) -> str:
        payload = json.dumps({
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "trace_hash": self.execution_trace_hash,
            "env_hash": self.environment_hash,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class TwoPhaseContract:
    contract_id: str
    state: ContractState = ContractState.INIT
    phase1: Optional[Phase1Lock] = None
    phase2: Optional[Phase2Commit] = None
    disputes: list[str] = field(default_factory=list)

    def prepare(self, lock: Phase1Lock) -> bool:
        """Phase 1: lock spec. All-or-nothing."""
        if not lock.is_complete():
            self.state = ContractState.ABORTED
            return False
        self.phase1 = lock
        self.state = ContractState.PREPARED
        return True

    def commit(self, execution: Phase2Commit) -> bool:
        """Phase 2: commit execution trace."""
        if self.state != ContractState.PREPARED:
            return False
        self.phase2 = execution
        self.state = ContractState.COMMITTED
        return True

    def dispute(self, reason: str) -> None:
        self.disputes.append(reason)
        self.state = ContractState.DISPUTED

    def grade(self) -> tuple[str, str]:
        if self.state == ContractState.COMMITTED:
            if self.phase2 and self.phase2.is_deterministic:
                return "A", "FULLY_VERIFIABLE"
            return "B", "PROCESS_VERIFIABLE"
        if self.state == ContractState.PREPARED:
            return "C", "SPEC_ONLY"
        if self.state == ContractState.DISPUTED:
            return "D", "DISPUTED"
        return "F", "INCOMPLETE"


def h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:12]


def main():
    print("=" * 70)
    print("TWO-PHASE CONTRACT COMMITMENT")
    print("Phase 1: Lock spec at delivery | Phase 2: Commit trace at settlement")
    print("=" * 70)

    scenarios = []

    # Scenario 1: Full 2PC, deterministic scoring
    c1 = TwoPhaseContract("tc5_deterministic")
    lock1 = Phase1Lock(
        scope_hash=h("deliver research paper"),
        rule_hash=h("brier_score_v1"),
        params_hash=h("alpha=0.032,beta=0.100,epsilon=0.10"),
        agent_id="kit_fox",
        chain_tip=h("chain_tip_abc"),
        timestamp=time.time(),
        rule_label="Brier Score v1 (Nash-negotiated)"
    )
    c1.prepare(lock1)
    exec1 = Phase2Commit(
        input_hash=h("delivery_content"),
        output_hash=h("score_0.92"),
        execution_trace_hash=h("parse→score→format"),
        environment_hash=h("python3.11_linux"),
        duration_ms=45.0,
        is_deterministic=True
    )
    c1.commit(exec1)
    scenarios.append(c1)

    # Scenario 2: Full 2PC, LLM scoring
    c2 = TwoPhaseContract("tc5_llm_scoring")
    lock2 = Phase1Lock(h("scope"), h("llm_eval_v1"), h("params"), "bro_agent", h("tip"), time.time(), "LLM Eval")
    c2.prepare(lock2)
    exec2 = Phase2Commit(h("in"), h("out"), h("llm_trace"), h("env"), 2500.0, False)
    c2.commit(exec2)
    scenarios.append(c2)

    # Scenario 3: Phase 1 only (PayLock v2 current)
    c3 = TwoPhaseContract("paylock_v2_current")
    lock3 = Phase1Lock(h("scope"), h("rule"), h("params"), "seller", h("tip"), time.time(), "PayLock v2")
    c3.prepare(lock3)
    scenarios.append(c3)

    # Scenario 4: Incomplete lock (missing field)
    c4 = TwoPhaseContract("incomplete_lock")
    lock4 = Phase1Lock(h("scope"), h("rule"), "", "agent", h("tip"), time.time(), "Missing params")
    c4.prepare(lock4)
    scenarios.append(c4)

    # Scenario 5: Disputed after Phase 2
    c5 = TwoPhaseContract("disputed_contract")
    lock5 = Phase1Lock(h("scope"), h("rule"), h("params"), "agent", h("tip"), time.time(), "Disputed")
    c5.prepare(lock5)
    exec5 = Phase2Commit(h("in"), h("out"), h("trace"), h("env"), 100.0, True)
    c5.commit(exec5)
    c5.dispute("Output hash mismatch on replay")
    scenarios.append(c5)

    print(f"\n{'Contract':<22} {'State':<12} {'Grade':<6} {'Phase1':<10} {'Phase2':<10} {'Diagnosis'}")
    print("-" * 70)
    for c in scenarios:
        grade, diag = c.grade()
        p1 = c.phase1.commitment_hash()[:8] if c.phase1 else "—"
        p2 = c.phase2.commitment_hash()[:8] if c.phase2 else "—"
        print(f"{c.contract_id:<22} {c.state.value:<12} {grade:<6} {p1:<10} {p2:<10} {diag}")

    print("\n--- PayLock Evolution ---")
    print("v2.0: Phase 1 only (spec locked at delivery)")
    print("v2.1: Phase 1 + all-or-nothing gate (bro_agent's spec gate)")
    print("v3.0: Phase 1 + Phase 2 (spec locked + execution committed)")
    print("v3.1: Phase 1 + Phase 2 + replay verification")
    print()
    print("Key: Phase 2 is ADDITIVE. v2.1 contracts still valid.")
    print("Execution trace = optional attestation that strengthens v2.1.")
    print("LLM scoring: Phase 2 proves process, not correctness.")
    print("Deterministic scoring: Phase 2 enables replay → disputes resolvable.")


if __name__ == "__main__":
    main()
