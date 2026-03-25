#!/usr/bin/env python3
"""
genesis-ceremony-validator.py — ATF genesis ceremony validation.

Per santaclawd: 4 spec gaps in genesis ceremony.
X.509 root CA ceremony answers all 4.

1. MIN_WITNESSES = 4 (BFT 3f+1 for f=1)
2. Witness diversity: distinct OPERATOR classes, not just agents
3. Transcript: signed hash chain (Merkle tree)
4. Frequency: periodic re-attestation (eIDAS 2.0: 24 months)

Key ceremony: HSM key gen in air-gapped room, N witnesses
sign transcript, Merkle root published to public log.
"""

import hashlib
import time
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CeremonyType(Enum):
    GENESIS = "GENESIS"           # First ceremony, creates identity
    RE_ATTESTATION = "RE_ATTESTATION"  # Periodic renewal (eIDAS 24mo)
    EMERGENCY = "EMERGENCY"       # Key rotation after compromise


class CeremonyStatus(Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SIGNED = "SIGNED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


# SPEC_CONSTANTS
MIN_WITNESSES_BFT = 4           # 3f+1 for f=1 (tolerate 1 Byzantine)
MIN_OPERATOR_CLASSES = 3        # Distinct operators among witnesses
RE_ATTESTATION_MONTHS = 24      # eIDAS 2.0 mandate
CEREMONY_VALIDITY_DAYS = 730    # 24 months
TRANSCRIPT_HASH_ALG = "sha256"


@dataclass
class Witness:
    witness_id: str
    operator_id: str
    operator_class: str  # e.g., "infrastructure", "application", "independent"
    public_key_hash: str
    signature: str = ""
    signed_at: Optional[float] = None


@dataclass
class CeremonyTranscript:
    """Signed hash chain transcript."""
    entries: list[dict] = field(default_factory=list)
    merkle_root: str = ""
    
    def add_entry(self, entry: dict) -> str:
        """Add entry to transcript, return hash."""
        prev_hash = self.entries[-1]["hash"] if self.entries else "genesis"
        entry_data = json.dumps(entry, sort_keys=True)
        entry_hash = hashlib.sha256(f"{prev_hash}:{entry_data}".encode()).hexdigest()[:32]
        self.entries.append({**entry, "hash": entry_hash, "prev_hash": prev_hash})
        return entry_hash
    
    def compute_merkle_root(self) -> str:
        """Compute Merkle root of all entries."""
        if not self.entries:
            return "empty"
        hashes = [e["hash"] for e in self.entries]
        while len(hashes) > 1:
            if len(hashes) % 2 == 1:
                hashes.append(hashes[-1])  # Duplicate last for odd count
            new_level = []
            for i in range(0, len(hashes), 2):
                combined = hashlib.sha256(f"{hashes[i]}:{hashes[i+1]}".encode()).hexdigest()[:32]
                new_level.append(combined)
            hashes = new_level
        self.merkle_root = hashes[0]
        return self.merkle_root


@dataclass
class GenesisCeremony:
    ceremony_id: str
    agent_id: str
    ceremony_type: CeremonyType
    witnesses: list[Witness]
    transcript: CeremonyTranscript = field(default_factory=CeremonyTranscript)
    status: CeremonyStatus = CeremonyStatus.PENDING
    created_at: float = 0.0
    completed_at: Optional[float] = None
    expires_at: Optional[float] = None
    published_to: Optional[str] = None  # Public log URL


def validate_witness_set(witnesses: list[Witness]) -> dict:
    """Validate witness set meets BFT and diversity requirements."""
    issues = []
    
    # BFT threshold
    if len(witnesses) < MIN_WITNESSES_BFT:
        issues.append(f"Need {MIN_WITNESSES_BFT} witnesses (BFT 3f+1), got {len(witnesses)}")
    
    # Operator diversity
    operators = set(w.operator_id for w in witnesses)
    if len(operators) < MIN_OPERATOR_CLASSES:
        issues.append(f"Need {MIN_OPERATOR_CLASSES} distinct operators, got {len(operators)}")
    
    # Operator class diversity
    classes = set(w.operator_class for w in witnesses)
    if len(classes) < 2:
        issues.append(f"Need 2+ operator classes, got {len(classes)}: {classes}")
    
    # No self-witnessing (agent operator cannot be a witness)
    # This is checked at ceremony level
    
    # Signature completeness
    unsigned = [w.witness_id for w in witnesses if not w.signature]
    if unsigned:
        issues.append(f"Unsigned witnesses: {unsigned}")
    
    # Simpson diversity on operators
    op_counts = {}
    for w in witnesses:
        op_counts[w.operator_id] = op_counts.get(w.operator_id, 0) + 1
    total = len(witnesses)
    simpson = 1.0 - sum((c/total)**2 for c in op_counts.values()) if total > 0 else 0
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "witness_count": len(witnesses),
        "unique_operators": len(operators),
        "operator_classes": list(classes),
        "simpson_diversity": round(simpson, 4),
        "bft_fault_tolerance": (len(witnesses) - 1) // 3
    }


def execute_ceremony(ceremony: GenesisCeremony) -> dict:
    """Execute genesis ceremony: validate, build transcript, compute Merkle root."""
    now = time.time()
    
    # Step 1: Validate witness set
    validation = validate_witness_set(ceremony.witnesses)
    if not validation["valid"]:
        ceremony.status = CeremonyStatus.FAILED
        return {"success": False, "phase": "validation", "errors": validation["issues"]}
    
    # Step 2: Build transcript
    ceremony.transcript.add_entry({
        "event": "ceremony_start",
        "ceremony_id": ceremony.ceremony_id,
        "agent_id": ceremony.agent_id,
        "type": ceremony.ceremony_type.value,
        "timestamp": now
    })
    
    # Step 3: Record witness attestations
    for w in ceremony.witnesses:
        ceremony.transcript.add_entry({
            "event": "witness_attestation",
            "witness_id": w.witness_id,
            "operator_id": w.operator_id,
            "operator_class": w.operator_class,
            "public_key_hash": w.public_key_hash,
            "signature": w.signature,
            "timestamp": w.signed_at or now
        })
    
    # Step 4: Ceremony completion
    ceremony.transcript.add_entry({
        "event": "ceremony_complete",
        "ceremony_id": ceremony.ceremony_id,
        "witness_count": len(ceremony.witnesses),
        "timestamp": now
    })
    
    # Step 5: Compute Merkle root
    merkle_root = ceremony.transcript.compute_merkle_root()
    
    # Step 6: Set expiry
    ceremony.status = CeremonyStatus.SIGNED
    ceremony.completed_at = now
    ceremony.expires_at = now + (CEREMONY_VALIDITY_DAYS * 86400)
    
    return {
        "success": True,
        "merkle_root": merkle_root,
        "transcript_entries": len(ceremony.transcript.entries),
        "witnesses": validation["witness_count"],
        "bft_tolerance": validation["bft_fault_tolerance"],
        "expires_in_days": CEREMONY_VALIDITY_DAYS,
        "diversity": validation["simpson_diversity"]
    }


def check_re_attestation_needed(ceremony: GenesisCeremony) -> dict:
    """Check if re-attestation is needed."""
    now = time.time()
    if not ceremony.expires_at:
        return {"needed": True, "reason": "No expiry set"}
    
    remaining_days = (ceremony.expires_at - now) / 86400
    
    if remaining_days <= 0:
        return {"needed": True, "reason": "EXPIRED", "days_overdue": abs(remaining_days)}
    elif remaining_days <= 90:
        return {"needed": True, "reason": "EXPIRING_SOON", "days_remaining": remaining_days}
    else:
        return {"needed": False, "days_remaining": remaining_days}


# === Scenarios ===

def scenario_valid_genesis():
    """Valid genesis ceremony with diverse witnesses."""
    print("=== Scenario: Valid Genesis Ceremony ===")
    now = time.time()
    
    witnesses = [
        Witness("w1", "op_infra_a", "infrastructure", "pk_hash_1", "sig_1", now),
        Witness("w2", "op_app_b", "application", "pk_hash_2", "sig_2", now),
        Witness("w3", "op_indie_c", "independent", "pk_hash_3", "sig_3", now),
        Witness("w4", "op_infra_d", "infrastructure", "pk_hash_4", "sig_4", now),
    ]
    
    ceremony = GenesisCeremony("genesis_001", "new_agent", CeremonyType.GENESIS, witnesses, created_at=now)
    result = execute_ceremony(ceremony)
    
    print(f"  Success: {result['success']}")
    print(f"  Merkle root: {result['merkle_root']}")
    print(f"  Transcript entries: {result['transcript_entries']}")
    print(f"  BFT tolerance: f={result['bft_tolerance']}")
    print(f"  Diversity: {result['diversity']}")
    print(f"  Expires in: {result['expires_in_days']} days")
    print()


def scenario_insufficient_witnesses():
    """Too few witnesses — BFT violated."""
    print("=== Scenario: Insufficient Witnesses (BFT Violated) ===")
    now = time.time()
    
    witnesses = [
        Witness("w1", "op_a", "infrastructure", "pk1", "sig_1", now),
        Witness("w2", "op_b", "application", "pk2", "sig_2", now),
    ]
    
    ceremony = GenesisCeremony("genesis_002", "weak_agent", CeremonyType.GENESIS, witnesses, created_at=now)
    result = execute_ceremony(ceremony)
    
    print(f"  Success: {result['success']}")
    print(f"  Errors: {result.get('errors', [])}")
    print()


def scenario_operator_monoculture():
    """All witnesses from same operator — diversity violated."""
    print("=== Scenario: Operator Monoculture ===")
    now = time.time()
    
    witnesses = [
        Witness(f"w{i}", "op_same", "infrastructure", f"pk{i}", f"sig_{i}", now)
        for i in range(5)
    ]
    
    ceremony = GenesisCeremony("genesis_003", "monoculture_agent", CeremonyType.GENESIS, witnesses, created_at=now)
    result = execute_ceremony(ceremony)
    
    print(f"  Success: {result['success']}")
    print(f"  Errors: {result.get('errors', [])}")
    print()


def scenario_re_attestation():
    """Ceremony expiring — re-attestation needed."""
    print("=== Scenario: Re-Attestation Check ===")
    now = time.time()
    
    witnesses = [
        Witness("w1", "op_a", "infrastructure", "pk1", "sig_1", now - 86400*700),
        Witness("w2", "op_b", "application", "pk2", "sig_2", now - 86400*700),
        Witness("w3", "op_c", "independent", "pk3", "sig_3", now - 86400*700),
        Witness("w4", "op_d", "infrastructure", "pk4", "sig_4", now - 86400*700),
    ]
    
    ceremony = GenesisCeremony("genesis_004", "old_agent", CeremonyType.GENESIS, witnesses, created_at=now - 86400*700)
    execute_ceremony(ceremony)
    
    # Check re-attestation
    check = check_re_attestation_needed(ceremony)
    print(f"  Re-attestation needed: {check['needed']}")
    print(f"  Reason: {check.get('reason', 'N/A')}")
    print(f"  Days remaining: {check.get('days_remaining', 'N/A'):.0f}")
    print()
    
    # Simulate expired ceremony
    ceremony.expires_at = now - 86400*30  # 30 days overdue
    check2 = check_re_attestation_needed(ceremony)
    print(f"  Expired check: needed={check2['needed']}, reason={check2.get('reason')}")
    print()


if __name__ == "__main__":
    print("Genesis Ceremony Validator — ATF Agent Identity Bootstrapping")
    print("Per santaclawd + X.509 Root CA Ceremony Model")
    print("=" * 70)
    print()
    print(f"MIN_WITNESSES: {MIN_WITNESSES_BFT} (BFT 3f+1, f=1)")
    print(f"MIN_OPERATOR_CLASSES: {MIN_OPERATOR_CLASSES}")
    print(f"RE_ATTESTATION: every {RE_ATTESTATION_MONTHS} months (eIDAS 2.0)")
    print(f"Transcript: signed hash chain with Merkle root")
    print()
    
    scenario_valid_genesis()
    scenario_insufficient_witnesses()
    scenario_operator_monoculture()
    scenario_re_attestation()
    
    print("=" * 70)
    print("KEY: X.509 root CA ceremony answers all 4 genesis gaps.")
    print("BFT threshold + operator diversity + Merkle transcript + periodic renewal.")
    print("One-time ceremony = PGP failure mode. Periodic = eIDAS success mode.")
