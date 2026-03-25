#!/usr/bin/env python3
"""
genesis-ceremony.py — ATF registry genesis ceremony protocol.

Per santaclawd: genesis ceremony spec gaps (MIN_WITNESSES, diversity, transcript, frequency).
Per DNSSEC root signing ceremony (ICANN): 7 roles, geographically distinct, quarterly.
Per BFT: 3f+1 for f=1 = minimum 4 witnesses.

Genesis ceremony creates the root trust anchor for an ATF registry instance.
All subsequent trust chains derive from this root.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CeremonyRole(Enum):
    ADMINISTRATOR = "administrator"      # Coordinates ceremony
    INTERNAL_WITNESS = "internal_witness" # Registry operator witness
    EXTERNAL_WITNESS = "external_witness" # Independent witness
    CRYPTO_OFFICER = "crypto_officer"     # Key material handler
    SAFE_CONTROLLER = "safe_controller"   # Physical/logical access


class CeremonyStatus(Enum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class TranscriptEntryType(Enum):
    CEREMONY_START = "ceremony_start"
    ROLE_CHECK_IN = "role_check_in"
    KEY_GENERATION = "key_generation"
    KEY_VERIFICATION = "key_verification"
    WITNESS_ATTESTATION = "witness_attestation"
    SIGNING = "signing"
    CEREMONY_END = "ceremony_end"
    ABORT = "abort"


# SPEC_CONSTANTS (per DNSSEC + BFT)
MIN_WITNESSES = 4                    # BFT: 3f+1 for f=1
MIN_OPERATOR_CLASSES = 3             # Distinct operator diversity
MIN_CRYPTO_OFFICERS = 2              # Key material requires 2+
RE_CEREMONY_INTERVAL_DAYS = 90       # Quarterly re-attestation (per ICANN)
CEREMONY_TIMEOUT_HOURS = 4           # Max ceremony duration
QUORUM_FRACTION = 0.75               # 75% of witnesses must attest


@dataclass
class Participant:
    participant_id: str
    role: CeremonyRole
    operator_id: str
    public_key_hash: str
    checked_in: bool = False
    attestation: Optional[str] = None
    attestation_timestamp: Optional[float] = None


@dataclass
class TranscriptEntry:
    entry_type: TranscriptEntryType
    timestamp: float
    participant_id: Optional[str]
    data: dict
    previous_hash: str
    entry_hash: str = ""
    
    def __post_init__(self):
        if not self.entry_hash:
            content = f"{self.entry_type.value}:{self.timestamp}:{self.participant_id}:{json.dumps(self.data, sort_keys=True)}:{self.previous_hash}"
            self.entry_hash = hashlib.sha256(content.encode()).hexdigest()[:32]


@dataclass
class GenesisCeremony:
    ceremony_id: str
    registry_id: str
    participants: list[Participant]
    transcript: list[TranscriptEntry] = field(default_factory=list)
    status: CeremonyStatus = CeremonyStatus.PLANNED
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    root_key_hash: Optional[str] = None


def validate_participants(participants: list[Participant]) -> dict:
    """Validate ceremony participant requirements."""
    issues = []
    
    # Count by role
    witnesses = [p for p in participants if p.role in 
                 {CeremonyRole.INTERNAL_WITNESS, CeremonyRole.EXTERNAL_WITNESS}]
    crypto_officers = [p for p in participants if p.role == CeremonyRole.CRYPTO_OFFICER]
    admins = [p for p in participants if p.role == CeremonyRole.ADMINISTRATOR]
    
    if len(witnesses) < MIN_WITNESSES:
        issues.append(f"Need {MIN_WITNESSES}+ witnesses, got {len(witnesses)}")
    
    if len(crypto_officers) < MIN_CRYPTO_OFFICERS:
        issues.append(f"Need {MIN_CRYPTO_OFFICERS}+ crypto officers, got {len(crypto_officers)}")
    
    if len(admins) < 1:
        issues.append("Need at least 1 administrator")
    
    # Operator diversity
    operators = set(p.operator_id for p in witnesses)
    if len(operators) < MIN_OPERATOR_CLASSES:
        issues.append(f"Need {MIN_OPERATOR_CLASSES}+ distinct operator classes among witnesses, got {len(operators)}")
    
    # No single operator should have majority of witnesses
    op_counts = {}
    for p in witnesses:
        op_counts[p.operator_id] = op_counts.get(p.operator_id, 0) + 1
    max_concentration = max(op_counts.values()) / len(witnesses) if witnesses else 0
    if max_concentration > 0.5:
        issues.append(f"Single operator controls {max_concentration:.0%} of witnesses (max 50%)")
    
    # External witnesses required
    external = [w for w in witnesses if w.role == CeremonyRole.EXTERNAL_WITNESS]
    if len(external) < 1:
        issues.append("At least 1 external witness required")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "witness_count": len(witnesses),
        "crypto_officer_count": len(crypto_officers),
        "operator_diversity": len(operators),
        "max_concentration": round(max_concentration, 3)
    }


def add_transcript_entry(ceremony: GenesisCeremony, entry_type: TranscriptEntryType,
                         participant_id: Optional[str], data: dict) -> TranscriptEntry:
    """Add hash-chained transcript entry."""
    prev_hash = ceremony.transcript[-1].entry_hash if ceremony.transcript else "genesis"
    entry = TranscriptEntry(
        entry_type=entry_type,
        timestamp=time.time(),
        participant_id=participant_id,
        data=data,
        previous_hash=prev_hash
    )
    ceremony.transcript.append(entry)
    return entry


def run_ceremony(ceremony: GenesisCeremony) -> dict:
    """Execute genesis ceremony with full transcript."""
    now = time.time()
    
    # Validate participants
    validation = validate_participants(ceremony.participants)
    if not validation["valid"]:
        ceremony.status = CeremonyStatus.FAILED
        add_transcript_entry(ceremony, TranscriptEntryType.ABORT, None,
                           {"reason": "participant validation failed", "issues": validation["issues"]})
        return {"status": "FAILED", "issues": validation["issues"]}
    
    # Start ceremony
    ceremony.status = CeremonyStatus.IN_PROGRESS
    ceremony.started_at = now
    add_transcript_entry(ceremony, TranscriptEntryType.CEREMONY_START, None,
                        {"registry_id": ceremony.registry_id, "participant_count": len(ceremony.participants)})
    
    # Check in all participants
    for p in ceremony.participants:
        p.checked_in = True
        add_transcript_entry(ceremony, TranscriptEntryType.ROLE_CHECK_IN, p.participant_id,
                           {"role": p.role.value, "operator": p.operator_id, "key_hash": p.public_key_hash})
    
    # Generate root key (simulated)
    root_key = hashlib.sha256(f"{ceremony.ceremony_id}:{now}".encode()).hexdigest()
    ceremony.root_key_hash = root_key[:32]
    add_transcript_entry(ceremony, TranscriptEntryType.KEY_GENERATION, None,
                        {"root_key_hash": ceremony.root_key_hash, "algorithm": "ed25519"})
    
    # Crypto officers verify
    for p in ceremony.participants:
        if p.role == CeremonyRole.CRYPTO_OFFICER:
            add_transcript_entry(ceremony, TranscriptEntryType.KEY_VERIFICATION, p.participant_id,
                               {"verified": True, "key_hash": ceremony.root_key_hash})
    
    # Witnesses attest
    witnesses = [p for p in ceremony.participants if p.role in 
                 {CeremonyRole.INTERNAL_WITNESS, CeremonyRole.EXTERNAL_WITNESS}]
    attestation_count = 0
    for w in witnesses:
        w.attestation = hashlib.sha256(f"{w.participant_id}:{ceremony.root_key_hash}".encode()).hexdigest()[:16]
        w.attestation_timestamp = now
        attestation_count += 1
        add_transcript_entry(ceremony, TranscriptEntryType.WITNESS_ATTESTATION, w.participant_id,
                           {"attestation_hash": w.attestation, "role": w.role.value})
    
    # Check quorum
    quorum_needed = int(len(witnesses) * QUORUM_FRACTION)
    if attestation_count < quorum_needed:
        ceremony.status = CeremonyStatus.FAILED
        add_transcript_entry(ceremony, TranscriptEntryType.ABORT, None,
                           {"reason": f"quorum not met: {attestation_count}/{quorum_needed}"})
        return {"status": "FAILED", "reason": "quorum not met"}
    
    # Sign root
    add_transcript_entry(ceremony, TranscriptEntryType.SIGNING, None,
                        {"root_key_hash": ceremony.root_key_hash, "witnesses": attestation_count})
    
    # Complete
    ceremony.status = CeremonyStatus.COMPLETED
    ceremony.completed_at = time.time()
    add_transcript_entry(ceremony, TranscriptEntryType.CEREMONY_END, None,
                        {"duration_seconds": ceremony.completed_at - ceremony.started_at,
                         "transcript_entries": len(ceremony.transcript),
                         "root_key_hash": ceremony.root_key_hash})
    
    return {
        "status": "COMPLETED",
        "root_key_hash": ceremony.root_key_hash,
        "transcript_entries": len(ceremony.transcript),
        "attestation_count": attestation_count,
        "quorum": f"{attestation_count}/{len(witnesses)} (need {quorum_needed})"
    }


def verify_transcript(ceremony: GenesisCeremony) -> dict:
    """Verify hash chain integrity of ceremony transcript."""
    if not ceremony.transcript:
        return {"valid": False, "reason": "empty transcript"}
    
    broken_links = []
    for i, entry in enumerate(ceremony.transcript):
        expected_prev = ceremony.transcript[i-1].entry_hash if i > 0 else "genesis"
        if entry.previous_hash != expected_prev:
            broken_links.append(i)
        
        # Verify entry hash
        content = f"{entry.entry_type.value}:{entry.timestamp}:{entry.participant_id}:{json.dumps(entry.data, sort_keys=True)}:{entry.previous_hash}"
        expected_hash = hashlib.sha256(content.encode()).hexdigest()[:32]
        if entry.entry_hash != expected_hash:
            broken_links.append(i)
    
    return {
        "valid": len(broken_links) == 0,
        "total_entries": len(ceremony.transcript),
        "broken_links": broken_links,
        "chain_head": ceremony.transcript[-1].entry_hash if ceremony.transcript else None,
        "chain_root": ceremony.transcript[0].entry_hash if ceremony.transcript else None
    }


# === Scenarios ===

def scenario_valid_ceremony():
    """Full ceremony with proper participants."""
    print("=== Scenario: Valid Genesis Ceremony ===")
    participants = [
        Participant("admin_1", CeremonyRole.ADMINISTRATOR, "op_registry", "key_admin"),
        Participant("witness_1", CeremonyRole.INTERNAL_WITNESS, "op_registry", "key_w1"),
        Participant("witness_2", CeremonyRole.EXTERNAL_WITNESS, "op_auditor", "key_w2"),
        Participant("witness_3", CeremonyRole.EXTERNAL_WITNESS, "op_community", "key_w3"),
        Participant("witness_4", CeremonyRole.EXTERNAL_WITNESS, "op_independent", "key_w4"),
        Participant("crypto_1", CeremonyRole.CRYPTO_OFFICER, "op_registry", "key_c1"),
        Participant("crypto_2", CeremonyRole.CRYPTO_OFFICER, "op_auditor", "key_c2"),
    ]
    
    ceremony = GenesisCeremony("genesis_001", "atf_registry_alpha", participants)
    result = run_ceremony(ceremony)
    chain = verify_transcript(ceremony)
    
    print(f"  Status: {result['status']}")
    print(f"  Root key: {result.get('root_key_hash', 'N/A')}")
    print(f"  Quorum: {result.get('quorum', 'N/A')}")
    print(f"  Transcript: {chain['total_entries']} entries, chain valid: {chain['valid']}")
    print()


def scenario_insufficient_diversity():
    """All witnesses from same operator — fails."""
    print("=== Scenario: Insufficient Operator Diversity ===")
    participants = [
        Participant("admin_1", CeremonyRole.ADMINISTRATOR, "op_mono", "key_admin"),
        Participant("witness_1", CeremonyRole.INTERNAL_WITNESS, "op_mono", "key_w1"),
        Participant("witness_2", CeremonyRole.INTERNAL_WITNESS, "op_mono", "key_w2"),
        Participant("witness_3", CeremonyRole.INTERNAL_WITNESS, "op_mono", "key_w3"),
        Participant("witness_4", CeremonyRole.INTERNAL_WITNESS, "op_mono", "key_w4"),
        Participant("crypto_1", CeremonyRole.CRYPTO_OFFICER, "op_mono", "key_c1"),
        Participant("crypto_2", CeremonyRole.CRYPTO_OFFICER, "op_mono", "key_c2"),
    ]
    
    ceremony = GenesisCeremony("genesis_002", "atf_registry_bad", participants)
    result = run_ceremony(ceremony)
    
    print(f"  Status: {result['status']}")
    print(f"  Issues: {result.get('issues', [])}")
    print()


def scenario_re_ceremony():
    """Periodic re-attestation — quarterly renewal."""
    print("=== Scenario: Re-Ceremony (Quarterly Renewal) ===")
    participants = [
        Participant("admin_1", CeremonyRole.ADMINISTRATOR, "op_registry", "key_admin"),
        Participant("witness_1", CeremonyRole.INTERNAL_WITNESS, "op_registry", "key_w1"),
        Participant("witness_2", CeremonyRole.EXTERNAL_WITNESS, "op_auditor", "key_w2"),
        Participant("witness_3", CeremonyRole.EXTERNAL_WITNESS, "op_community", "key_w3"),
        Participant("witness_4", CeremonyRole.EXTERNAL_WITNESS, "op_new", "key_w4"),
        Participant("crypto_1", CeremonyRole.CRYPTO_OFFICER, "op_registry", "key_c1"),
        Participant("crypto_2", CeremonyRole.CRYPTO_OFFICER, "op_new", "key_c2"),
    ]
    
    ceremony = GenesisCeremony("genesis_003_re", "atf_registry_alpha", participants)
    result = run_ceremony(ceremony)
    
    days_since_last = RE_CEREMONY_INTERVAL_DAYS
    print(f"  Re-ceremony after {days_since_last} days (interval: {RE_CEREMONY_INTERVAL_DAYS}d)")
    print(f"  Status: {result['status']}")
    print(f"  New root key: {result.get('root_key_hash', 'N/A')}")
    print(f"  KEY: Previous root expires {RE_CEREMONY_INTERVAL_DAYS}d after last ceremony.")
    print(f"  Overlap period allows migration. No ceremony = registry SUSPENDED.")
    print()


if __name__ == "__main__":
    print("Genesis Ceremony — ATF Registry Root Trust Anchor Protocol")
    print("Per DNSSEC Root Signing Ceremony (ICANN) + BFT (3f+1)")
    print("=" * 70)
    print()
    print(f"Requirements: {MIN_WITNESSES}+ witnesses, {MIN_OPERATOR_CLASSES}+ operators,")
    print(f"  {MIN_CRYPTO_OFFICERS}+ crypto officers, {QUORUM_FRACTION:.0%} quorum,")
    print(f"  {RE_CEREMONY_INTERVAL_DAYS}d re-ceremony interval")
    print()
    
    scenario_valid_ceremony()
    scenario_insufficient_diversity()
    scenario_re_ceremony()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. DNSSEC ceremony = exact model for ATF genesis.")
    print("2. BFT 3f+1: MIN_WITNESSES=4 not 3 (tolerates 1 Byzantine witness).")
    print("3. Operator diversity mandatory — same org ≠ independent witness.")
    print("4. Hash-chained transcript = auditable ceremony log.")
    print("5. Quarterly re-ceremony prevents perpetual root (PGP failure mode).")
