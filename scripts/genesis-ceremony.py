#!/usr/bin/env python3
"""
genesis-ceremony.py — ATF genesis bootstrap via witnessed ceremony.

The zeroth axiom problem: the genesis registrar cannot vouch itself into
existence via the same trust chain it anchors. X.509 solved this with
root CA key ceremonies: HSM in Faraday cage, M-of-N quorum, video
recorded, independent auditor witnessed.

ATF equivalent: genesis registrar bootstrap requires:
1. M-of-N operator quorum (like HSM smart cards)
2. Published ceremony transcript (like WebTrust audit)
3. Independent witness attestation (not same-operator)
4. Ceremony hash = genesis_hash for the registrar itself

Key insight from PKI key ceremonies:
- Trust starts with ritual, not protocol
- The ceremony IS the root of trust
- No cryptographic proof can bootstrap itself
- Social verification at the foundation, crypto thereafter

Usage:
    python3 genesis-ceremony.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Operator:
    """Ceremony participant (like HSM smart card holder)."""
    id: str
    name: str
    operator_org: str  # Organization (for independence check)
    role: str  # ADMINISTRATOR | SECURITY_OFFICER | WITNESS | AUDITOR


@dataclass
class CeremonyStep:
    """One step in the genesis ceremony (like PKI key ceremony script)."""
    step_number: int
    action: str
    operator_id: str
    timestamp: float
    artifact_hash: Optional[str] = None  # Hash of any artifact produced
    witness_ids: list[str] = field(default_factory=list)

    def canonical(self) -> str:
        witnesses = ",".join(sorted(self.witness_ids))
        return f"step={self.step_number};action={self.action};op={self.operator_id};t={self.timestamp};artifact={self.artifact_hash or 'none'};witnesses={witnesses}"


@dataclass
class CeremonyTranscript:
    """Full ceremony transcript (equivalent to WebTrust audit report)."""
    ceremony_id: str
    registrar_id: str
    quorum_required: int
    quorum_total: int
    operators: list[Operator]
    steps: list[CeremonyStep]
    started_at: float
    completed_at: Optional[float] = None
    genesis_hash: Optional[str] = None
    verdict: str = "IN_PROGRESS"


class GenesisCeremony:
    """Conduct and validate ATF genesis bootstrap ceremonies."""

    def __init__(self, registrar_id: str, quorum_m: int, quorum_n: int):
        self.registrar_id = registrar_id
        self.quorum_m = quorum_m
        self.quorum_n = quorum_n
        self.operators: list[Operator] = []
        self.steps: list[CeremonyStep] = []
        self.started = False
        self.completed = False
        self.start_time = 0.0

    def _hash(self, *parts: str) -> str:
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]

    def register_operator(self, op: Operator) -> dict:
        """Register a ceremony participant."""
        if self.started:
            return {"error": "CEREMONY_ALREADY_STARTED"}
        self.operators.append(op)
        return {"registered": op.id, "role": op.role, "total": len(self.operators)}

    def start_ceremony(self) -> dict:
        """Begin the ceremony. Requires >= quorum_n operators registered."""
        if len(self.operators) < self.quorum_n:
            return {
                "error": "INSUFFICIENT_OPERATORS",
                "have": len(self.operators),
                "need": self.quorum_n,
            }

        # Independence check: operators must represent >= 2 orgs
        orgs = set(op.operator_org for op in self.operators)
        if len(orgs) < 2:
            return {
                "error": "MONOCULTURE_OPERATORS",
                "orgs": list(orgs),
                "need": ">=2 independent organizations",
            }

        # Must have at least one WITNESS or AUDITOR
        has_witness = any(op.role in ("WITNESS", "AUDITOR") for op in self.operators)
        if not has_witness:
            return {"error": "NO_INDEPENDENT_WITNESS"}

        self.started = True
        self.start_time = time.time()

        step = CeremonyStep(
            step_number=1,
            action="CEREMONY_OPENED",
            operator_id=self.operators[0].id,
            timestamp=self.start_time,
            witness_ids=[op.id for op in self.operators if op.role in ("WITNESS", "AUDITOR")],
        )
        self.steps.append(step)

        return {
            "status": "STARTED",
            "operators": len(self.operators),
            "orgs": list(orgs),
            "quorum": f"{self.quorum_m}-of-{self.quorum_n}",
        }

    def add_step(self, action: str, operator_id: str, artifact_hash: Optional[str] = None) -> dict:
        """Add a ceremony step."""
        if not self.started:
            return {"error": "CEREMONY_NOT_STARTED"}
        if self.completed:
            return {"error": "CEREMONY_COMPLETED"}

        # Operator must be registered
        op = next((o for o in self.operators if o.id == operator_id), None)
        if not op:
            return {"error": "UNKNOWN_OPERATOR", "id": operator_id}

        witnesses = [o.id for o in self.operators if o.role in ("WITNESS", "AUDITOR") and o.id != operator_id]

        step = CeremonyStep(
            step_number=len(self.steps) + 1,
            action=action,
            operator_id=operator_id,
            timestamp=time.time(),
            artifact_hash=artifact_hash,
            witness_ids=witnesses,
        )
        self.steps.append(step)
        return {"step": step.step_number, "action": action, "witnessed_by": len(witnesses)}

    def complete_ceremony(self, signing_operators: list[str]) -> dict:
        """Complete the ceremony with M-of-N quorum signing."""
        if not self.started:
            return {"error": "CEREMONY_NOT_STARTED"}

        # Check quorum
        valid_signers = [op_id for op_id in signing_operators if any(o.id == op_id for o in self.operators)]
        if len(valid_signers) < self.quorum_m:
            return {
                "error": "INSUFFICIENT_QUORUM",
                "have": len(valid_signers),
                "need": self.quorum_m,
            }

        # Check signer independence
        signer_orgs = set()
        for op_id in valid_signers:
            op = next(o for o in self.operators if o.id == op_id)
            signer_orgs.add(op.operator_org)

        if len(signer_orgs) < 2:
            return {
                "error": "MONOCULTURE_SIGNERS",
                "orgs": list(signer_orgs),
            }

        # Generate genesis hash from ceremony transcript
        transcript_parts = [step.canonical() for step in self.steps]
        transcript_hash = self._hash(*transcript_parts)

        # Genesis hash = hash(registrar_id + transcript_hash + signer_ids)
        genesis_hash = self._hash(
            self.registrar_id,
            transcript_hash,
            ",".join(sorted(valid_signers)),
        )

        self.completed = True

        # Final step
        self.add_step(
            "CEREMONY_COMPLETED",
            valid_signers[0],
            artifact_hash=genesis_hash,
        )

        return {
            "verdict": "GENESIS_BOOTSTRAPPED",
            "registrar_id": self.registrar_id,
            "genesis_hash": genesis_hash,
            "transcript_hash": transcript_hash,
            "quorum_achieved": f"{len(valid_signers)}-of-{self.quorum_n}",
            "signer_orgs": list(signer_orgs),
            "total_steps": len(self.steps),
            "ceremony_duration_s": round(time.time() - self.start_time, 2),
        }

    def validate_ceremony(self) -> dict:
        """Validate a completed ceremony transcript."""
        issues = []

        # 1. Was ceremony completed?
        if not self.completed:
            issues.append("INCOMPLETE")

        # 2. Minimum steps (open + at least 1 action + close)
        if len(self.steps) < 3:
            issues.append("TOO_FEW_STEPS")

        # 3. Independent witnesses present throughout?
        witness_ops = [op for op in self.operators if op.role in ("WITNESS", "AUDITOR")]
        if not witness_ops:
            issues.append("NO_WITNESSES")

        # 4. Steps witnessed?
        unwitnessed = [s for s in self.steps if not s.witness_ids]
        if unwitnessed:
            issues.append(f"UNWITNESSED_STEPS:{len(unwitnessed)}")

        # 5. Operator independence
        orgs = set(op.operator_org for op in self.operators)
        if len(orgs) < 2:
            issues.append("MONOCULTURE")

        # 6. Time bounds (ceremony shouldn't take > 24h)
        if self.steps:
            duration = self.steps[-1].timestamp - self.steps[0].timestamp
            if duration > 86400:
                issues.append("EXCESSIVE_DURATION")

        grade = "A" if not issues else "C" if len(issues) <= 2 else "F"
        return {
            "valid": len(issues) == 0,
            "grade": grade,
            "issues": issues,
            "operators": len(self.operators),
            "orgs": list(orgs),
            "steps": len(self.steps),
        }


def demo():
    print("=" * 60)
    print("Genesis Ceremony — ATF Zeroth Axiom Bootstrap")
    print("=" * 60)

    # Scenario 1: Valid 3-of-5 ceremony
    print("\n--- Scenario 1: Valid 3-of-5 genesis ceremony ---")
    ceremony = GenesisCeremony("atf_registrar_v1", quorum_m=3, quorum_n=5)

    ceremony.register_operator(Operator("op1", "Alice", "OrgA", "ADMINISTRATOR"))
    ceremony.register_operator(Operator("op2", "Bob", "OrgB", "SECURITY_OFFICER"))
    ceremony.register_operator(Operator("op3", "Carol", "OrgC", "SECURITY_OFFICER"))
    ceremony.register_operator(Operator("op4", "Dave", "OrgA", "WITNESS"))
    ceremony.register_operator(Operator("op5", "Eve", "OrgD", "AUDITOR"))

    start = ceremony.start_ceremony()
    print(f"Start: {json.dumps(start)}")

    ceremony.add_step("GENERATE_REGISTRY_KEYPAIR", "op1", "keypair_hash_abc123")
    ceremony.add_step("SIGN_FIELD_REGISTRY", "op2", "registry_hash_def456")
    ceremony.add_step("VERIFY_REGISTRY_INTEGRITY", "op5", "verified_hash_ghi789")

    result = ceremony.complete_ceremony(["op1", "op2", "op3"])
    print(f"Result: {json.dumps(result, indent=2)}")

    validation = ceremony.validate_ceremony()
    print(f"Validation: {json.dumps(validation, indent=2)}")

    # Scenario 2: Monoculture operators (should fail)
    print("\n--- Scenario 2: Monoculture operators (single org) ---")
    bad = GenesisCeremony("bad_registrar", quorum_m=2, quorum_n=3)
    bad.register_operator(Operator("x1", "X1", "SameOrg", "ADMINISTRATOR"))
    bad.register_operator(Operator("x2", "X2", "SameOrg", "SECURITY_OFFICER"))
    bad.register_operator(Operator("x3", "X3", "SameOrg", "WITNESS"))
    result2 = bad.start_ceremony()
    print(f"Result: {json.dumps(result2)}")

    # Scenario 3: No witness (should fail)
    print("\n--- Scenario 3: No independent witness ---")
    no_witness = GenesisCeremony("unwatched", quorum_m=2, quorum_n=3)
    no_witness.register_operator(Operator("a1", "A1", "OrgA", "ADMINISTRATOR"))
    no_witness.register_operator(Operator("a2", "A2", "OrgB", "SECURITY_OFFICER"))
    no_witness.register_operator(Operator("a3", "A3", "OrgC", "ADMINISTRATOR"))
    result3 = no_witness.start_ceremony()
    print(f"Result: {json.dumps(result3)}")

    # Scenario 4: Insufficient quorum at signing
    print("\n--- Scenario 4: Insufficient quorum at completion ---")
    short = GenesisCeremony("short_quorum", quorum_m=3, quorum_n=5)
    short.register_operator(Operator("s1", "S1", "OrgA", "ADMINISTRATOR"))
    short.register_operator(Operator("s2", "S2", "OrgB", "SECURITY_OFFICER"))
    short.register_operator(Operator("s3", "S3", "OrgC", "SECURITY_OFFICER"))
    short.register_operator(Operator("s4", "S4", "OrgD", "WITNESS"))
    short.register_operator(Operator("s5", "S5", "OrgE", "AUDITOR"))
    short.start_ceremony()
    short.add_step("GENERATE_KEYPAIR", "s1")
    result4 = short.complete_ceremony(["s1", "s2"])  # Only 2, need 3
    print(f"Result: {json.dumps(result4)}")

    print("\n" + "=" * 60)
    print("Zeroth axiom: trust starts with ritual, not protocol.")
    print("M-of-N quorum + independent witnesses + published transcript")
    print("= ceremony_hash = genesis_hash for the registrar itself.")
    print("X.509 key ceremonies since 1995. ATF inherits the pattern.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
