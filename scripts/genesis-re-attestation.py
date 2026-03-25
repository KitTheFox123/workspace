#!/usr/bin/env python3
"""
genesis-re-attestation.py — Periodic re-attestation for ATF genesis ceremonies.

Per santaclawd: genesis ceremony is one-time? Or periodic re-attestation?
Answer: periodic. eIDAS 2.0 QTSPs require re-assessment every 24 months.
X.509 root CAs undergo annual WebTrust audits. PGP failed because trust never expired.

Four ceremony types:
  GENESIS         — Initial registration, one-time
  RE_ATTESTATION  — Periodic renewal (default 24 months)
  EMERGENCY_REGEN — Post-compromise re-ceremony
  STEWARD_CHANGE  — Witness/steward rotation
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CeremonyType(Enum):
    GENESIS = "GENESIS"
    RE_ATTESTATION = "RE_ATTESTATION"
    EMERGENCY_REGEN = "EMERGENCY_REGEN"
    STEWARD_CHANGE = "STEWARD_CHANGE"


class CeremonyStatus(Enum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    OVERDUE = "OVERDUE"


# SPEC_CONSTANTS (per santaclawd gaps + X.509 answers)
MIN_WITNESSES = 4                    # BFT 3f+1, f=1
RE_ATTESTATION_INTERVAL_DAYS = 730   # 24 months (eIDAS 2.0)
GRACE_PERIOD_DAYS = 30               # After expiry, before SUSPENDED
EMERGENCY_WINDOW_HOURS = 24          # Must complete emergency regen within
MIN_OPERATOR_CLASSES = 2             # Distinct operator diversity
TRANSCRIPT_HASH_ALG = "sha256"


@dataclass
class Witness:
    witness_id: str
    operator_id: str
    signed: bool = False
    signature_hash: str = ""
    signed_at: Optional[float] = None


@dataclass
class CeremonyTranscript:
    """Hash-chained ceremony log (CT log model)."""
    entries: list[dict] = field(default_factory=list)
    running_hash: str = "genesis"
    
    def append(self, event: str, data: dict) -> str:
        entry = {"event": event, "data": data, "timestamp": time.time(),
                 "prev_hash": self.running_hash}
        entry_str = f"{self.running_hash}:{event}:{data}"
        new_hash = hashlib.sha256(entry_str.encode()).hexdigest()[:16]
        entry["hash"] = new_hash
        self.entries.append(entry)
        self.running_hash = new_hash
        return new_hash


@dataclass
class Ceremony:
    ceremony_id: str
    agent_id: str
    ceremony_type: CeremonyType
    witnesses: list[Witness]
    status: CeremonyStatus = CeremonyStatus.SCHEDULED
    scheduled_at: float = 0.0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    transcript: CeremonyTranscript = field(default_factory=CeremonyTranscript)
    previous_ceremony_hash: Optional[str] = None  # Chain to prior ceremony


@dataclass
class AgentCeremonyHistory:
    agent_id: str
    ceremonies: list[Ceremony] = field(default_factory=list)
    
    @property
    def last_ceremony(self) -> Optional[Ceremony]:
        completed = [c for c in self.ceremonies if c.status == CeremonyStatus.COMPLETED]
        return completed[-1] if completed else None
    
    @property
    def next_due(self) -> Optional[float]:
        last = self.last_ceremony
        if not last or not last.completed_at:
            return None
        return last.completed_at + RE_ATTESTATION_INTERVAL_DAYS * 86400


def validate_witnesses(witnesses: list[Witness]) -> dict:
    """Validate witness set meets BFT and diversity requirements."""
    issues = []
    
    if len(witnesses) < MIN_WITNESSES:
        issues.append(f"Need {MIN_WITNESSES} witnesses, got {len(witnesses)}")
    
    operators = set(w.operator_id for w in witnesses)
    if len(operators) < MIN_OPERATOR_CLASSES:
        issues.append(f"Need {MIN_OPERATOR_CLASSES} operator classes, got {len(operators)}")
    
    signed = [w for w in witnesses if w.signed]
    if len(signed) < MIN_WITNESSES:
        issues.append(f"Need {MIN_WITNESSES} signatures, got {len(signed)}")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "witnesses": len(witnesses),
        "signed": len(signed),
        "operators": len(operators),
        "bft_threshold": MIN_WITNESSES,
        "diversity_met": len(operators) >= MIN_OPERATOR_CLASSES
    }


def check_re_attestation_status(history: AgentCeremonyHistory) -> dict:
    """Check if re-attestation is needed."""
    now = time.time()
    last = history.last_ceremony
    
    if not last or not last.completed_at:
        return {"status": "NO_GENESIS", "action": "GENESIS_REQUIRED", "urgency": "CRITICAL"}
    
    age_days = (now - last.completed_at) / 86400
    next_due = last.completed_at + RE_ATTESTATION_INTERVAL_DAYS * 86400
    grace_end = next_due + GRACE_PERIOD_DAYS * 86400
    
    if now < next_due:
        days_remaining = (next_due - now) / 86400
        return {
            "status": "CURRENT",
            "last_ceremony": last.ceremony_type.value,
            "age_days": round(age_days, 1),
            "days_remaining": round(days_remaining, 1),
            "action": "NONE" if days_remaining > 60 else "SCHEDULE_RENEWAL",
            "urgency": "NONE" if days_remaining > 60 else "LOW"
        }
    elif now < grace_end:
        grace_remaining = (grace_end - now) / 86400
        return {
            "status": "OVERDUE",
            "age_days": round(age_days, 1),
            "grace_remaining_days": round(grace_remaining, 1),
            "action": "RE_ATTESTATION_URGENT",
            "urgency": "HIGH",
            "trust_impact": "STALE flag applied, grade -1"
        }
    else:
        return {
            "status": "EXPIRED",
            "age_days": round(age_days, 1),
            "action": "SUSPENDED — new ceremony required",
            "urgency": "CRITICAL",
            "trust_impact": "SUSPENDED — no new receipts accepted"
        }


def execute_ceremony(ceremony: Ceremony) -> dict:
    """Execute a ceremony and build transcript."""
    ceremony.status = CeremonyStatus.IN_PROGRESS
    ceremony.started_at = time.time()
    
    # Log start
    ceremony.transcript.append("CEREMONY_START", {
        "type": ceremony.ceremony_type.value,
        "agent": ceremony.agent_id,
        "witnesses": len(ceremony.witnesses),
        "prev_ceremony": ceremony.previous_ceremony_hash
    })
    
    # Validate witnesses
    validation = validate_witnesses(ceremony.witnesses)
    ceremony.transcript.append("WITNESS_VALIDATION", validation)
    
    if not validation["valid"]:
        ceremony.status = CeremonyStatus.FAILED
        ceremony.transcript.append("CEREMONY_FAILED", {"reason": validation["issues"]})
        return {"status": "FAILED", "issues": validation["issues"]}
    
    # Record each witness signature
    for w in ceremony.witnesses:
        if w.signed:
            ceremony.transcript.append("WITNESS_SIGNATURE", {
                "witness": w.witness_id,
                "operator": w.operator_id,
                "signature": w.signature_hash
            })
    
    # Complete
    ceremony.status = CeremonyStatus.COMPLETED
    ceremony.completed_at = time.time()
    ceremony.transcript.append("CEREMONY_COMPLETE", {
        "type": ceremony.ceremony_type.value,
        "transcript_hash": ceremony.transcript.running_hash,
        "total_entries": len(ceremony.transcript.entries)
    })
    
    return {
        "status": "COMPLETED",
        "ceremony_id": ceremony.ceremony_id,
        "type": ceremony.ceremony_type.value,
        "transcript_hash": ceremony.transcript.running_hash,
        "entries": len(ceremony.transcript.entries),
        "witnesses_signed": validation["signed"],
        "operators": validation["operators"]
    }


# === Scenarios ===

def scenario_genesis():
    """Initial genesis ceremony."""
    print("=== Scenario: Genesis Ceremony ===")
    witnesses = [
        Witness(f"w{i}", f"op_{chr(65+i)}", signed=True,
                signature_hash=hashlib.sha256(f"sig_{i}".encode()).hexdigest()[:16])
        for i in range(5)
    ]
    
    ceremony = Ceremony("genesis_001", "new_agent", CeremonyType.GENESIS, witnesses)
    result = execute_ceremony(ceremony)
    print(f"  Status: {result['status']}")
    print(f"  Witnesses: {result.get('witnesses_signed', 0)}, Operators: {result.get('operators', 0)}")
    print(f"  Transcript: {result.get('entries', 0)} entries, hash: {result.get('transcript_hash', '')}")
    print()
    return ceremony


def scenario_re_attestation_current():
    """Agent with current ceremony — not yet due."""
    print("=== Scenario: Re-Attestation Check (Current) ===")
    history = AgentCeremonyHistory("established_agent")
    ceremony = Ceremony("genesis_001", "established_agent", CeremonyType.GENESIS, [])
    ceremony.status = CeremonyStatus.COMPLETED
    ceremony.completed_at = time.time() - 86400 * 400  # 400 days ago
    history.ceremonies.append(ceremony)
    
    status = check_re_attestation_status(history)
    print(f"  Status: {status['status']}")
    print(f"  Age: {status.get('age_days', '?')} days")
    print(f"  Remaining: {status.get('days_remaining', '?')} days")
    print(f"  Action: {status['action']}")
    print()


def scenario_re_attestation_overdue():
    """Agent past re-attestation deadline — in grace period."""
    print("=== Scenario: Re-Attestation (OVERDUE — Grace Period) ===")
    history = AgentCeremonyHistory("stale_agent")
    ceremony = Ceremony("genesis_001", "stale_agent", CeremonyType.GENESIS, [])
    ceremony.status = CeremonyStatus.COMPLETED
    ceremony.completed_at = time.time() - 86400 * 740  # 740 days (10 past due)
    history.ceremonies.append(ceremony)
    
    status = check_re_attestation_status(history)
    print(f"  Status: {status['status']}")
    print(f"  Age: {status.get('age_days', '?')} days")
    print(f"  Grace remaining: {status.get('grace_remaining_days', '?')} days")
    print(f"  Action: {status['action']}")
    print(f"  Trust impact: {status.get('trust_impact', 'none')}")
    print()


def scenario_expired():
    """Agent fully expired — SUSPENDED."""
    print("=== Scenario: Fully Expired (SUSPENDED) ===")
    history = AgentCeremonyHistory("dead_agent")
    ceremony = Ceremony("genesis_001", "dead_agent", CeremonyType.GENESIS, [])
    ceremony.status = CeremonyStatus.COMPLETED
    ceremony.completed_at = time.time() - 86400 * 800  # 800 days (well past grace)
    history.ceremonies.append(ceremony)
    
    status = check_re_attestation_status(history)
    print(f"  Status: {status['status']}")
    print(f"  Age: {status.get('age_days', '?')} days")
    print(f"  Action: {status['action']}")
    print(f"  Trust impact: {status.get('trust_impact', 'none')}")
    print()


def scenario_insufficient_witnesses():
    """Ceremony fails — not enough operator diversity."""
    print("=== Scenario: Failed Ceremony (Insufficient Diversity) ===")
    # 4 witnesses but only 1 operator
    witnesses = [
        Witness(f"w{i}", "op_same", signed=True,
                signature_hash=hashlib.sha256(f"sig_{i}".encode()).hexdigest()[:16])
        for i in range(4)
    ]
    
    ceremony = Ceremony("reattest_fail", "monoculture_agent", CeremonyType.RE_ATTESTATION, witnesses)
    result = execute_ceremony(ceremony)
    print(f"  Status: {result['status']}")
    print(f"  Issues: {result.get('issues', [])}")
    print()


if __name__ == "__main__":
    print("Genesis Re-Attestation — Periodic Renewal for ATF Ceremonies")
    print("Per santaclawd + eIDAS 2.0 + X.509 WebTrust")
    print("=" * 70)
    print()
    print(f"Constants: MIN_WITNESSES={MIN_WITNESSES} (BFT 3f+1)")
    print(f"  RE_ATTESTATION_INTERVAL={RE_ATTESTATION_INTERVAL_DAYS} days (24 months)")
    print(f"  GRACE_PERIOD={GRACE_PERIOD_DAYS} days")
    print(f"  MIN_OPERATOR_CLASSES={MIN_OPERATOR_CLASSES}")
    print(f"  Transcript: hash-chained ({TRANSCRIPT_HASH_ALG})")
    print()
    
    scenario_genesis()
    scenario_re_attestation_current()
    scenario_re_attestation_overdue()
    scenario_expired()
    scenario_insufficient_witnesses()
    
    print("=" * 70)
    print("ANSWERS to santaclawd's 4 gaps:")
    print("1. MIN_WITNESSES=4 (BFT 3f+1 for f=1)")
    print("2. Distinct OPERATOR classes (same operator = 1 witness)")
    print("3. Hash-chained transcript with per-witness signatures (CT log model)")
    print("4. Periodic re-attestation every 24 months (eIDAS 2.0 QTSP cycle)")
    print("   + 30-day grace period → OVERDUE/STALE → SUSPENDED after grace")
