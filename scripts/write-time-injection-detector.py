#!/usr/bin/env python3
"""
write-time-injection-detector.py — Detect write-time log injection in ATF receipts.

Per santaclawd: hash chains solve retroactive injection. Write-time injection
(compromised operator injects receipt AT interaction moment) is still open.

Three defenses (composition required — no single primitive closes it):
1. PRE-COMMIT: Counterparty publishes hash commitment BEFORE interaction
2. K-OF-N WITNESSES: Independent observers at write-time
3. TEMPORAL BINDING: External time beacon (roughtime, NTP signed)

Per Dowling et al. (ESORICS 2016): CT achieves security against malicious
loggers via Merkle consistency proofs. Write-time needs additional primitives.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class InjectionType(Enum):
    RETROACTIVE = "retroactive"   # After chain sealed — caught by hash chain
    WRITE_TIME = "write_time"     # At interaction moment — needs composition
    PHANTOM = "phantom"           # Receipt for interaction that never happened


class Defense(Enum):
    HASH_CHAIN = "hash_chain"          # Merkle consistency proof
    PRE_COMMIT = "pre_commit"          # Counterparty commitment before interaction
    K_OF_N_WITNESS = "k_of_n_witness"  # Independent observers
    TEMPORAL_BIND = "temporal_bind"     # External time source
    COUNTERPARTY_RECEIPT = "counterparty_receipt"  # Bilateral receipt


# Defense matrix: which defenses catch which injection types
DEFENSE_MATRIX = {
    InjectionType.RETROACTIVE: {Defense.HASH_CHAIN},
    InjectionType.WRITE_TIME: {Defense.PRE_COMMIT, Defense.K_OF_N_WITNESS, Defense.TEMPORAL_BIND},
    InjectionType.PHANTOM: {Defense.COUNTERPARTY_RECEIPT, Defense.PRE_COMMIT},
}


@dataclass
class PreCommit:
    """Counterparty publishes hash commitment before interaction."""
    agent_id: str
    commitment_hash: str  # H(nonce || intent || timestamp)
    published_at: float
    nonce: Optional[str] = None  # Revealed after interaction


@dataclass
class Receipt:
    receipt_id: str
    agent_id: str
    counterparty_id: str
    timestamp: float
    evidence_grade: str
    content_hash: str
    chain_prev_hash: str
    witness_signatures: list = field(default_factory=list)
    pre_commit_ref: Optional[str] = None
    temporal_proof: Optional[str] = None


@dataclass
class WriteTimeAudit:
    receipt_id: str
    defenses_present: list
    defenses_missing: list
    injection_risk: str  # LOW, MEDIUM, HIGH, CRITICAL
    details: dict


def hash_it(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def check_pre_commit(receipt: Receipt, pre_commits: dict) -> dict:
    """Verify receipt has valid pre-commit from counterparty."""
    if not receipt.pre_commit_ref:
        return {"present": False, "valid": False, "reason": "no pre_commit_ref"}
    
    pc = pre_commits.get(receipt.pre_commit_ref)
    if not pc:
        return {"present": True, "valid": False, "reason": "pre_commit not found in registry"}
    
    # Pre-commit must be from counterparty, published BEFORE receipt
    if pc.agent_id != receipt.counterparty_id:
        return {"present": True, "valid": False, "reason": "pre_commit from wrong agent"}
    
    if pc.published_at >= receipt.timestamp:
        return {"present": True, "valid": False, 
                "reason": f"pre_commit after receipt ({pc.published_at:.0f} >= {receipt.timestamp:.0f})"}
    
    # If nonce revealed, verify commitment
    if pc.nonce:
        expected = hash_it(f"{pc.nonce}:{receipt.counterparty_id}:{receipt.timestamp:.0f}")
        if expected != pc.commitment_hash:
            return {"present": True, "valid": False, "reason": "commitment hash mismatch"}
    
    return {"present": True, "valid": True, "timing_gap": receipt.timestamp - pc.published_at}


def check_witnesses(receipt: Receipt, min_witnesses: int = 2) -> dict:
    """Verify K-of-N independent witnesses at write-time."""
    n = len(receipt.witness_signatures)
    if n == 0:
        return {"present": False, "count": 0, "sufficient": False}
    
    # Check for diversity (different operators)
    unique_signers = set(receipt.witness_signatures)
    diversity = len(unique_signers) / n if n > 0 else 0
    
    return {
        "present": True,
        "count": n,
        "unique": len(unique_signers),
        "diversity": round(diversity, 2),
        "sufficient": n >= min_witnesses and diversity > 0.5
    }


def check_temporal_binding(receipt: Receipt) -> dict:
    """Verify external temporal proof exists."""
    if not receipt.temporal_proof:
        return {"present": False, "valid": False}
    
    # In production: verify against roughtime/NTP signed response
    # Here: check that proof exists and is plausible
    return {"present": True, "valid": True, "source": "external_beacon"}


def audit_receipt(receipt: Receipt, pre_commits: dict, min_witnesses: int = 2) -> WriteTimeAudit:
    """Full write-time injection audit for a single receipt."""
    pc = check_pre_commit(receipt, pre_commits)
    wit = check_witnesses(receipt, min_witnesses)
    temp = check_temporal_binding(receipt)
    
    defenses_present = []
    defenses_missing = []
    
    # Always present (hash chain is structural)
    defenses_present.append(Defense.HASH_CHAIN.value)
    
    if pc["present"] and pc.get("valid"):
        defenses_present.append(Defense.PRE_COMMIT.value)
    else:
        defenses_missing.append(Defense.PRE_COMMIT.value)
    
    if wit["present"] and wit.get("sufficient"):
        defenses_present.append(Defense.K_OF_N_WITNESS.value)
    else:
        defenses_missing.append(Defense.K_OF_N_WITNESS.value)
    
    if temp["present"] and temp.get("valid"):
        defenses_present.append(Defense.TEMPORAL_BIND.value)
    else:
        defenses_missing.append(Defense.TEMPORAL_BIND.value)
    
    # Risk assessment
    write_time_defenses = len([d for d in defenses_present 
                               if d != Defense.HASH_CHAIN.value])
    
    if write_time_defenses >= 3:
        risk = "LOW"
    elif write_time_defenses >= 2:
        risk = "MEDIUM"
    elif write_time_defenses >= 1:
        risk = "HIGH"
    else:
        risk = "CRITICAL"  # Only hash chain — retroactive solved, write-time open
    
    return WriteTimeAudit(
        receipt_id=receipt.receipt_id,
        defenses_present=defenses_present,
        defenses_missing=defenses_missing,
        injection_risk=risk,
        details={
            "pre_commit": pc,
            "witnesses": wit,
            "temporal": temp,
            "write_time_defense_count": write_time_defenses
        }
    )


# === Scenarios ===

def scenario_full_defense():
    """All three write-time defenses present."""
    print("=== Scenario: Full Defense (pre-commit + witnesses + temporal) ===")
    now = time.time()
    
    pc = PreCommit("bro_agent", hash_it(f"nonce123:bro_agent:{now:.0f}"), 
                   now - 60, "nonce123")
    pre_commits = {"pc001": pc}
    
    receipt = Receipt(
        "r001", "kit_fox", "bro_agent", now, "A",
        hash_it("content"), hash_it("prev"),
        witness_signatures=["witness_a", "witness_b", "witness_c"],
        pre_commit_ref="pc001",
        temporal_proof="roughtime:1234567890"
    )
    
    audit = audit_receipt(receipt, pre_commits)
    print(f"  Risk: {audit.injection_risk}")
    print(f"  Defenses present: {audit.defenses_present}")
    print(f"  Defenses missing: {audit.defenses_missing}")
    print()


def scenario_hash_chain_only():
    """Only hash chain — retroactive solved, write-time CRITICAL."""
    print("=== Scenario: Hash Chain Only (write-time CRITICAL) ===")
    now = time.time()
    
    receipt = Receipt(
        "r002", "kit_fox", "unknown_agent", now, "C",
        hash_it("content"), hash_it("prev")
    )
    
    audit = audit_receipt(receipt, {})
    print(f"  Risk: {audit.injection_risk}")
    print(f"  Defenses present: {audit.defenses_present}")
    print(f"  Defenses missing: {audit.defenses_missing}")
    print(f"  KEY: hash chain stops retroactive but NOT write-time injection")
    print()


def scenario_pre_commit_after_receipt():
    """Pre-commit published AFTER receipt — invalid."""
    print("=== Scenario: Pre-Commit After Receipt (invalid timing) ===")
    now = time.time()
    
    pc = PreCommit("attacker", hash_it("fake"), now + 10)  # AFTER receipt
    pre_commits = {"pc_bad": pc}
    
    receipt = Receipt(
        "r003", "kit_fox", "attacker", now, "B",
        hash_it("content"), hash_it("prev"),
        pre_commit_ref="pc_bad"
    )
    
    audit = audit_receipt(receipt, pre_commits)
    print(f"  Risk: {audit.injection_risk}")
    print(f"  Pre-commit valid: {audit.details['pre_commit']['valid']}")
    print(f"  Reason: {audit.details['pre_commit']['reason']}")
    print()


def scenario_monoculture_witnesses():
    """Witnesses from same operator — diversity too low."""
    print("=== Scenario: Monoculture Witnesses (same signer) ===")
    now = time.time()
    
    receipt = Receipt(
        "r004", "kit_fox", "shady_agent", now, "B",
        hash_it("content"), hash_it("prev"),
        witness_signatures=["same_witness", "same_witness", "same_witness"],
        temporal_proof="roughtime:999"
    )
    
    audit = audit_receipt(receipt, {})
    print(f"  Risk: {audit.injection_risk}")
    print(f"  Witnesses: count={audit.details['witnesses']['count']} "
          f"unique={audit.details['witnesses']['unique']} "
          f"diversity={audit.details['witnesses']['diversity']}")
    print(f"  Sufficient: {audit.details['witnesses']['sufficient']}")
    print()


def scenario_fleet_audit():
    """Audit a fleet of receipts for write-time injection risk."""
    print("=== Scenario: Fleet Audit (mixed defenses) ===")
    now = time.time()
    
    pc = PreCommit("good_agent", hash_it(f"n1:good_agent:{now:.0f}"), now - 30, "n1")
    pre_commits = {"pc_good": pc}
    
    receipts = [
        Receipt("f001", "kit", "good_agent", now, "A", hash_it("c1"), hash_it("p"),
                ["w1","w2"], "pc_good", "rt:1"),
        Receipt("f002", "kit", "mid_agent", now, "B", hash_it("c2"), hash_it("p"),
                ["w1"], None, "rt:2"),
        Receipt("f003", "kit", "bad_agent", now, "C", hash_it("c3"), hash_it("p")),
        Receipt("f004", "kit", "good2", now, "A", hash_it("c4"), hash_it("p"),
                ["w1","w2","w3"], None, "rt:3"),
    ]
    
    risk_counts = {}
    for r in receipts:
        audit = audit_receipt(r, pre_commits)
        risk_counts[audit.injection_risk] = risk_counts.get(audit.injection_risk, 0) + 1
        print(f"  {r.receipt_id}: {audit.injection_risk} "
              f"(write-time defenses: {audit.details['write_time_defense_count']})")
    
    print(f"\n  Fleet risk distribution: {risk_counts}")
    critical = risk_counts.get("CRITICAL", 0)
    total = len(receipts)
    print(f"  Critical exposure: {critical}/{total} ({critical/total:.0%})")
    print()


if __name__ == "__main__":
    print("Write-Time Injection Detector — ATF Receipt Integrity")
    print("Per santaclawd + Dowling et al. (ESORICS 2016)")
    print("=" * 65)
    print()
    print("Hash chains close RETROACTIVE injection.")
    print("Write-time needs COMPOSITION: pre-commit + witnesses + temporal.")
    print("No single primitive is sufficient.")
    print()
    
    scenario_full_defense()
    scenario_hash_chain_only()
    scenario_pre_commit_after_receipt()
    scenario_monoculture_witnesses()
    scenario_fleet_audit()
    
    print("=" * 65)
    print("DEFENSE MATRIX:")
    for itype, defenses in DEFENSE_MATRIX.items():
        print(f"  {itype.value:15s} → {', '.join(d.value for d in defenses)}")
    print()
    print("KEY INSIGHT: No single primitive closes write-time injection.")
    print("Composition of 2+ defenses reduces risk to MEDIUM.")
    print("All 3 = LOW. Hash chain alone = CRITICAL for write-time.")
