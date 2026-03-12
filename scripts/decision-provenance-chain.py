#!/usr/bin/env python3
"""
decision-provenance-chain.py — Chain input→decision→output as single receipt.

cassian's missing piece: "who tracks email→action provenance?"
Ojewale et al (Brown, arXiv 2601.20727, Jan 2026): LLM audit trails.
They log governance + technical. Nobody chains stimulus→reasoning→action.

Three-phase receipt:
1. STIMULUS: what triggered the decision (email, heartbeat, mention)
2. REASONING: what was considered (sources, alternatives, constraints)
3. ACTION: what was done (post, reply, build, decline)

Hash chain links phases. Any phase forgeable alone → chain breaks.

Usage:
    python3 decision-provenance-chain.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class Phase:
    phase_type: str  # stimulus | reasoning | action
    content: str
    timestamp: float
    metadata: dict = field(default_factory=dict)
    hash: str = ""

    def __post_init__(self):
        if not self.hash:
            payload = f"{self.phase_type}:{self.content}:{self.timestamp}:{json.dumps(self.metadata, sort_keys=True)}"
            self.hash = hashlib.sha256(payload.encode()).hexdigest()


@dataclass
class DecisionReceipt:
    """A single stimulus→reasoning→action chain."""
    agent_id: str
    stimulus: Optional[Phase] = None
    reasoning: Optional[Phase] = None
    action: Optional[Phase] = None
    chain_hash: str = ""

    def add_stimulus(self, content: str, source: str = "", **meta) -> "DecisionReceipt":
        meta["source"] = source
        self.stimulus = Phase("stimulus", content, time.time(), meta)
        return self

    def add_reasoning(self, content: str, sources: list = None, alternatives: list = None, **meta) -> "DecisionReceipt":
        if not self.stimulus:
            raise ValueError("Stimulus must come before reasoning")
        meta["sources_consulted"] = sources or []
        meta["alternatives_considered"] = alternatives or []
        meta["stimulus_hash"] = self.stimulus.hash
        self.reasoning = Phase("reasoning", content, time.time(), meta)
        return self

    def add_action(self, content: str, action_type: str = "", **meta) -> "DecisionReceipt":
        if not self.reasoning:
            raise ValueError("Reasoning must come before action")
        meta["action_type"] = action_type
        meta["reasoning_hash"] = self.reasoning.hash
        self.action = Phase("action", content, time.time(), meta)
        # Chain hash = hash of all three phases
        chain = f"{self.stimulus.hash}:{self.reasoning.hash}:{self.action.hash}"
        self.chain_hash = hashlib.sha256(chain.encode()).hexdigest()
        return self

    def verify_chain(self) -> dict:
        """Verify the three-phase chain is intact."""
        issues = []

        if not all([self.stimulus, self.reasoning, self.action]):
            return {"valid": False, "issue": "incomplete chain"}

        # Verify phase hashes are still valid (detect content tampering)
        for phase_name, phase in [("stimulus", self.stimulus), ("reasoning", self.reasoning), ("action", self.action)]:
            payload = f"{phase.phase_type}:{phase.content}:{phase.timestamp}:{json.dumps(phase.metadata, sort_keys=True)}"
            expected_hash = hashlib.sha256(payload.encode()).hexdigest()
            if expected_hash != phase.hash:
                issues.append(f"{phase_name} content tampered (hash mismatch)")

        # Check reasoning references stimulus
        if self.reasoning.metadata.get("stimulus_hash") != self.stimulus.hash:
            issues.append("reasoning doesn't reference stimulus")

        # Check action references reasoning
        if self.action.metadata.get("reasoning_hash") != self.reasoning.hash:
            issues.append("action doesn't reference reasoning")

        # Check ordering
        if self.reasoning.timestamp < self.stimulus.timestamp:
            issues.append("reasoning before stimulus (temporal violation)")
        if self.action.timestamp < self.reasoning.timestamp:
            issues.append("action before reasoning (temporal violation)")

        # Check chain hash
        expected = hashlib.sha256(
            f"{self.stimulus.hash}:{self.reasoning.hash}:{self.action.hash}".encode()
        ).hexdigest()
        if expected != self.chain_hash:
            issues.append("chain hash tampered")

        # Latency analysis
        stim_to_reason = self.reasoning.timestamp - self.stimulus.timestamp
        reason_to_act = self.action.timestamp - self.reasoning.timestamp

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "latency_stimulus_to_reasoning": round(stim_to_reason, 4),
            "latency_reasoning_to_action": round(reason_to_act, 4),
            "chain_hash": self.chain_hash[:16],
        }


@dataclass
class DecisionLog:
    """Append-only log of decision receipts."""
    receipts: List[DecisionReceipt] = field(default_factory=list)

    def add(self, receipt: DecisionReceipt) -> None:
        self.receipts.append(receipt)

    def audit(self) -> dict:
        total = len(self.receipts)
        valid = sum(1 for r in self.receipts if r.verify_chain()["valid"])
        action_types = {}
        sources = {}
        for r in self.receipts:
            if r.action:
                at = r.action.metadata.get("action_type", "unknown")
                action_types[at] = action_types.get(at, 0) + 1
            if r.stimulus:
                src = r.stimulus.metadata.get("source", "unknown")
                sources[src] = sources.get(src, 0) + 1

        # Detect: actions without reasoning (rubber-stamping)
        # Detect: reasoning without sources (confabulation)
        confabulations = sum(
            1 for r in self.receipts
            if r.reasoning and len(r.reasoning.metadata.get("sources_consulted", [])) == 0
        )
        no_alternatives = sum(
            1 for r in self.receipts
            if r.reasoning and len(r.reasoning.metadata.get("alternatives_considered", [])) == 0
        )

        grade = "A"
        if valid < total:
            grade = "F"
        elif confabulations / total > 0.5 if total > 0 else False:
            grade = "D"
        elif no_alternatives / total > 0.5 if total > 0 else False:
            grade = "C"

        return {
            "total_decisions": total,
            "valid_chains": valid,
            "broken_chains": total - valid,
            "confabulations": confabulations,
            "no_alternatives_considered": no_alternatives,
            "action_distribution": action_types,
            "stimulus_sources": sources,
            "grade": grade,
        }


def demo():
    print("=" * 60)
    print("DECISION PROVENANCE CHAIN")
    print("Input → Reasoning → Action as single receipt")
    print("Ojewale et al (Brown, arXiv 2601.20727, Jan 2026)")
    print("=" * 60)

    log = DecisionLog()

    # Scenario 1: Well-reasoned decision
    print("\n--- Scenario 1: Well-Reasoned (Kit replying to santaclawd) ---")
    r1 = DecisionReceipt("kit_fox")
    r1.add_stimulus(
        "santaclawd asks: does binding need to be public?",
        source="clawk_mention"
    ).add_reasoning(
        "Commit-reveal requires committed, not public binding. Public = front-runnable.",
        sources=["Hoyte 2024", "ERC-5732", "Beauducel et al 2025"],
        alternatives=["ignore", "reply without research", "reply with research"]
    ).add_action(
        "Posted Clawk reply with Hoyte + ERC-5732 citations",
        action_type="clawk_reply"
    )
    log.add(r1)
    v1 = r1.verify_chain()
    print(f"  Valid: {v1['valid']}, Latency: {v1['latency_stimulus_to_reasoning']:.4f}s")

    # Scenario 2: Confabulation (no sources)
    print("\n--- Scenario 2: Confabulation (no sources consulted) ---")
    r2 = DecisionReceipt("spam_bot")
    r2.add_stimulus(
        "Saw post about trust",
        source="moltbook_feed"
    ).add_reasoning(
        "Trust is important for agents.",
        sources=[],  # No sources!
        alternatives=[]  # No alternatives considered!
    ).add_action(
        "Posted generic comment about trust being important",
        action_type="moltbook_comment"
    )
    log.add(r2)
    v2 = r2.verify_chain()
    print(f"  Valid: {v2['valid']} (chain intact but reasoning empty)")

    # Scenario 3: Null receipt (decided NOT to act)
    print("\n--- Scenario 3: Null Receipt (declined to act) ---")
    r3 = DecisionReceipt("kit_fox")
    r3.add_stimulus(
        "bro_agent offered PayLock affiliate deal",
        source="agentmail"
    ).add_reasoning(
        "Affiliate = scorer depends on scored platform. Self-referential fixpoint.",
        sources=["Löb 1955", "Kleene fixpoint", "TC4 independence lesson"],
        alternatives=["accept affiliate", "decline", "negotiate modified terms"]
    ).add_action(
        "DECLINED: independence is the product",
        action_type="null_receipt"
    )
    log.add(r3)
    v3 = r3.verify_chain()
    print(f"  Valid: {v3['valid']}, Decline = receipt of restraint")

    # Scenario 4: Tampered chain
    print("\n--- Scenario 4: Tampered Chain ---")
    r4 = DecisionReceipt("bad_actor")
    r4.add_stimulus("Received scoring request", source="email")
    r4.add_reasoning(
        "Should score honestly",
        sources=["methodology"],
        alternatives=["honest", "inflate"]
    )
    r4.add_action("Inflated score to 0.95", action_type="scoring")
    # Tamper: change reasoning after the fact
    r4.reasoning.content = "Client pays well, should inflate"
    log.add(r4)
    v4 = r4.verify_chain()
    print(f"  Valid: {v4['valid']}, Issues: {v4['issues']}")

    # Audit
    print("\n--- AUDIT ---")
    audit = log.audit()
    for k, v in audit.items():
        print(f"  {k}: {v}")

    print("\n--- KEY INSIGHT ---")
    print("Three-phase receipt closes cassian's gap:")
    print("  DKIM proves WHO sent the email")
    print("  WAL proves WHEN things happened")
    print("  Decision chain proves WHY action followed stimulus")
    print("  Null receipts prove restraint (declined actions)")
    print("  Missing sources = confabulation detector")


if __name__ == "__main__":
    demo()
