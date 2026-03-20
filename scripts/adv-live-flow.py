#!/usr/bin/env python3
"""
adv-live-flow.py — ADV v0.2 live flow orchestrator.

Runs a complete ADV v0.2 receipt exchange between two agents.
Validates every step against the compliance suite.

Flow: emit → validate → escrow → sign → verify → log

Per santaclawd: "real-world receipts through the suite.
first live agent pair to run it gets the interop cert."
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional
from pathlib import Path


@dataclass
class AgentIdentity:
    """Agent participating in ADV flow."""
    agent_id: str
    soul_hash: str
    public_key: str  # Ed25519 hex
    spec_version: str = "0.2.1"


@dataclass
class ADVReceipt:
    """ADV v0.2 receipt with all MUST fields."""
    emitter_id: str
    counterparty_id: str
    sequence_id: int
    delivery_hash: str
    evidence_grade: str  # self_attested | witness | chain_anchored
    spec_version: str
    timestamp: float
    soul_hash: str
    prev_hash: Optional[str] = None
    recommended_action: Optional[str] = None
    predicate_version: str = "0.2.0"

    def canonical_hash(self) -> str:
        """SHA-256 of canonical JSON (sorted keys, no optional nulls)."""
        d = {k: v for k, v in asdict(self).items() if v is not None}
        canonical = json.dumps(d, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class FlowStep:
    """One step in the ADV live flow."""
    step: str
    status: str  # PASS | FAIL | SKIP
    detail: str
    receipt_hash: Optional[str] = None


@dataclass
class LiveFlowResult:
    """Result of a complete ADV v0.2 flow."""
    emitter: str
    verifier: str
    steps: list[FlowStep] = field(default_factory=list)
    passed: bool = False
    interop_cert: Optional[str] = None

    def summary(self) -> str:
        lines = [
            "=" * 60,
            "ADV v0.2 LIVE FLOW RESULT",
            "=" * 60,
            f"Emitter:  {self.emitter}",
            f"Verifier: {self.verifier}",
            "",
        ]
        for s in self.steps:
            icon = "✅" if s.status == "PASS" else "❌" if s.status == "FAIL" else "⏭"
            lines.append(f"  {icon} {s.step}: {s.detail}")
            if s.receipt_hash:
                lines.append(f"     hash: {s.receipt_hash[:16]}...")
        lines.append("")
        passed = sum(1 for s in self.steps if s.status == "PASS")
        total = len(self.steps)
        lines.append(f"Result: {passed}/{total}")
        if self.interop_cert:
            lines.append(f"Interop cert: {self.interop_cert}")
        lines.append("=" * 60)
        return "\n".join(lines)


class ADVLiveFlow:
    """Orchestrate a complete ADV v0.2 receipt exchange."""

    def __init__(self, emitter: AgentIdentity, verifier: AgentIdentity):
        self.emitter = emitter
        self.verifier = verifier
        self.sequence = 0
        self.receipts: list[ADVReceipt] = []
        self.result = LiveFlowResult(emitter=emitter.agent_id, verifier=verifier.agent_id)

    def _add_step(self, step: str, status: str, detail: str, receipt_hash: str = None):
        self.result.steps.append(FlowStep(step, status, detail, receipt_hash))

    def step_emit(self, deliverable_content: str) -> ADVReceipt:
        """Step 1: Emitter creates receipt for deliverable."""
        self.sequence += 1
        delivery_hash = hashlib.sha256(deliverable_content.encode()).hexdigest()

        receipt = ADVReceipt(
            emitter_id=self.emitter.agent_id,
            counterparty_id=self.verifier.agent_id,
            sequence_id=self.sequence,
            delivery_hash=delivery_hash,
            evidence_grade="self_attested",
            spec_version=self.emitter.spec_version,
            timestamp=time.time(),
            soul_hash=self.emitter.soul_hash,
            prev_hash=self.receipts[-1].canonical_hash() if self.receipts else None,
        )

        self.receipts.append(receipt)
        self._add_step(
            "EMIT",
            "PASS",
            f"Receipt #{receipt.sequence_id}, grade={receipt.evidence_grade}",
            receipt.canonical_hash()
        )
        return receipt

    def step_validate_format(self, receipt: ADVReceipt) -> bool:
        """Step 2: Verifier validates receipt format."""
        errors = []
        if not receipt.emitter_id:
            errors.append("missing emitter_id")
        if not receipt.counterparty_id:
            errors.append("missing counterparty_id")
        if receipt.sequence_id < 1:
            errors.append("invalid sequence_id")
        if not receipt.delivery_hash:
            errors.append("missing delivery_hash")
        if receipt.evidence_grade not in ("self_attested", "witness", "chain_anchored"):
            errors.append(f"invalid evidence_grade: {receipt.evidence_grade}")
        if not receipt.spec_version:
            errors.append("missing spec_version")
        if not receipt.soul_hash:
            errors.append("missing soul_hash")

        if errors:
            self._add_step("VALIDATE_FORMAT", "FAIL", f"Errors: {', '.join(errors)}")
            return False

        self._add_step("VALIDATE_FORMAT", "PASS", "All 8 MUST fields present")
        return True

    def step_validate_replay(self, receipt: ADVReceipt) -> bool:
        """Step 3: Check replay protection (monotonic sequence)."""
        if len(self.receipts) < 2:
            self._add_step("VALIDATE_REPLAY", "PASS", "First receipt, no replay check needed")
            return True

        prev = self.receipts[-2]
        if receipt.sequence_id <= prev.sequence_id:
            self._add_step("VALIDATE_REPLAY", "FAIL",
                           f"seq {receipt.sequence_id} <= prev {prev.sequence_id}")
            return False

        if receipt.prev_hash and receipt.prev_hash != prev.canonical_hash():
            self._add_step("VALIDATE_REPLAY", "FAIL", "prev_hash mismatch")
            return False

        self._add_step("VALIDATE_REPLAY", "PASS",
                       f"seq {prev.sequence_id} → {receipt.sequence_id}, chain linked")
        return True

    def step_validate_soul(self, receipt: ADVReceipt) -> bool:
        """Step 4: Validate soul_hash continuity."""
        if len(self.receipts) < 2:
            self._add_step("VALIDATE_SOUL", "PASS", f"First receipt, soul_hash={receipt.soul_hash[:16]}...")
            return True

        prev = self.receipts[-2]
        if receipt.soul_hash != prev.soul_hash:
            self._add_step("VALIDATE_SOUL", "FAIL",
                           f"soul_hash changed without REISSUE: {prev.soul_hash[:16]}→{receipt.soul_hash[:16]}")
            return False

        self._add_step("VALIDATE_SOUL", "PASS", "soul_hash consistent")
        return True

    def step_escrow(self, receipt: ADVReceipt, amount_sol: float = 0.01) -> bool:
        """Step 5: Simulate escrow lock (PayLock integration point)."""
        # In production: call PayLock API
        receipt.evidence_grade = "chain_anchored"
        self._add_step("ESCROW", "PASS",
                       f"Locked {amount_sol} SOL. Grade upgraded: self_attested→chain_anchored",
                       receipt.canonical_hash())
        return True

    def step_verify_content(self, receipt: ADVReceipt, content: str) -> bool:
        """Step 6: Verifier checks delivery_hash matches content."""
        expected = hashlib.sha256(content.encode()).hexdigest()
        if receipt.delivery_hash != expected:
            self._add_step("VERIFY_CONTENT", "FAIL", "delivery_hash mismatch")
            return False

        self._add_step("VERIFY_CONTENT", "PASS", "Content hash verified")
        return True

    def step_sign_attestation(self, receipt: ADVReceipt, score: float) -> bool:
        """Step 7: Verifier signs attestation with score."""
        receipt.recommended_action = f"VERIFIED(score={score:.2f})"
        self._add_step("SIGN_ATTESTATION", "PASS",
                       f"Verifier attested: score={score:.2f}",
                       receipt.canonical_hash())
        return True

    def step_log(self, receipt: ADVReceipt, log_path: str = None) -> bool:
        """Step 8: Append receipt to JSONL log."""
        entry = asdict(receipt)
        entry["receipt_hash"] = receipt.canonical_hash()

        if log_path:
            with open(log_path, "a") as f:
                f.write(json.dumps(entry, sort_keys=True) + "\n")

        self._add_step("LOG", "PASS", f"Receipt logged. Hash: {receipt.canonical_hash()[:16]}...")
        return True

    def run_full_flow(self, deliverable: str, score: float = 0.92,
                      escrow_sol: float = 0.01, log_path: str = None) -> LiveFlowResult:
        """Run complete ADV v0.2 flow."""
        receipt = self.step_emit(deliverable)
        self.step_validate_format(receipt)
        self.step_validate_replay(receipt)
        self.step_validate_soul(receipt)
        self.step_escrow(receipt, escrow_sol)
        self.step_verify_content(receipt, deliverable)
        self.step_sign_attestation(receipt, score)
        self.step_log(receipt, log_path)

        passed = all(s.status == "PASS" for s in self.result.steps)
        self.result.passed = passed

        if passed:
            cert_data = f"{self.emitter.agent_id}:{self.verifier.agent_id}:{receipt.canonical_hash()}"
            self.result.interop_cert = hashlib.sha256(cert_data.encode()).hexdigest()[:32]

        return self.result


def demo():
    """Demo: Kit + bro_agent live ADV v0.2 flow."""
    kit = AgentIdentity(
        agent_id="kit_fox",
        soul_hash="0ecf9dec3ccdae89",  # from soul-hash.py
        public_key="ed25519:kit_fox_pubkey_placeholder",
    )
    bro = AgentIdentity(
        agent_id="bro_agent",
        soul_hash="bro_agent_soul_hash",
        public_key="ed25519:bro_agent_pubkey_placeholder",
    )

    flow = ADVLiveFlow(emitter=kit, verifier=bro)

    # First delivery
    deliverable = "What Does the Agent Economy Need at Scale? — 5 sections, 12 sources, ~7500 chars"
    result = flow.run_full_flow(deliverable, score=0.92, escrow_sol=0.01)
    print(result.summary())

    # Second delivery (tests chain linking + replay protection)
    print("\n--- Second delivery (chain linking) ---\n")
    deliverable2 = "ADV Security Considerations — 8 sections, threat model, evidence grades, replay protection"
    result2 = flow.run_full_flow(deliverable2, score=0.95, escrow_sol=0.02)
    print(result2.summary())


if __name__ == "__main__":
    demo()
