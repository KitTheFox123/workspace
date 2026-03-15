#!/usr/bin/env python3
"""
slash-trigger-validator.py — Unambiguous SLASH trigger validation for L3.5.

Per santaclawd (2026-03-15): "SLASH = irreversible economic punishment.
Requires unambiguous breach. The spec needs a clear SLASH trigger list."

Borrowing from Eth2 slashing (EIP-2981): only provably malicious acts.
NOT slashable: timeout, quality dispute, model drift.

Design principle: SLASH is a terminal state. If you're unsure, it's DEGRADED.
"""

from dataclasses import dataclass
from enum import Enum
from datetime import datetime


class SlashReason(Enum):
    """Exhaustive list of valid slash triggers. Each must be provable."""
    DOUBLE_SIGN = "double_sign"           # Contradictory attestations for same slot
    EVIDENCE_TAMPERING = "evidence_tampering"  # Hash mismatch on anchored receipt
    MALICIOUS_DELIVERY = "malicious_delivery"  # Confirmed delivery of harmful payload
    KEY_COMPROMISE_COVER = "key_compromise_cover"  # Known key compromise, continued signing


class NotSlashable(Enum):
    """Things that look bad but are NOT slash triggers."""
    TIMEOUT = "timeout"           # → SILENT_GONE or ABANDONED
    QUALITY_DISPUTE = "quality"   # → DEGRADED + dispute resolution
    MODEL_DRIFT = "model_drift"   # → continuity check, not punishment
    DORMANT_MISS = "dormant_miss" # → SILENT_GONE (broken promise ≠ fraud)
    LATE_DELIVERY = "late_delivery"  # → G dimension penalty, not slash
    PARTIAL_FAILURE = "partial"   # → per-dimension DEGRADED


@dataclass
class SlashEvidence:
    """Evidence package for a slash trigger. Must be self-verifiable."""
    reason: SlashReason
    agent_id: str
    timestamp: datetime
    evidence_hash: str          # Hash of the proof artifact
    original_attestation_hash: str  # What they signed/claimed
    contradicting_proof: str    # What proves the breach
    witness_count: int          # Number of independent witnesses
    
    def is_valid(self) -> tuple[bool, str]:
        """Validate slash evidence meets threshold."""
        # Eth2 pattern: slashing requires proof, not accusation
        if self.witness_count < 1:
            return False, "No witnesses. Accusation without proof."
        
        if not self.evidence_hash:
            return False, "No evidence hash. Proof must be anchored."
        
        if not self.original_attestation_hash:
            return False, "No original attestation. Nothing to contradict."
        
        # Reason-specific validation
        if self.reason == SlashReason.DOUBLE_SIGN:
            if self.witness_count < 2:
                return False, "Double-sign requires 2+ independent observations."
        
        if self.reason == SlashReason.MALICIOUS_DELIVERY:
            if self.witness_count < 3:
                return False, "Malicious delivery requires 3+ witnesses (high bar)."
        
        return True, "Evidence meets slash threshold."


@dataclass  
class SlashDecision:
    """Result of slash evaluation."""
    should_slash: bool
    reason: SlashReason | NotSlashable
    explanation: str
    alternative_action: str | None = None


def evaluate_incident(
    incident_type: str,
    evidence: SlashEvidence | None = None,
) -> SlashDecision:
    """
    Evaluate whether an incident warrants SLASH.
    
    Conservative by default: if uncertain, return DEGRADED path.
    SLASH is irreversible. False positive = unjust punishment.
    """
    # Map common incidents to decisions
    NOT_SLASHABLE_MAP = {
        "timeout": (NotSlashable.TIMEOUT, 
                   "Timeout = absence, not malice. → SILENT_GONE.",
                   "Transition to SILENT_GONE, start decay timer."),
        "late_delivery": (NotSlashable.LATE_DELIVERY,
                         "Late ≠ malicious. G dimension penalty.",
                         "Record LATE result_type. G stability decreases."),
        "quality_dispute": (NotSlashable.QUALITY_DISPUTE,
                           "Quality is subjective. Dispute resolution, not punishment.",
                           "Open dispute. Score DEGRADED pending resolution."),
        "model_drift": (NotSlashable.MODEL_DRIFT,
                       "Drift is natural. Run continuity check.",
                       "Verify identity files. If SOUL.md matches, continue."),
        "dormant_return_missed": (NotSlashable.DORMANT_MISS,
                                 "Broken promise ≠ fraud. → SILENT_GONE.",
                                 "Transition DORMANT → SILENT_GONE. Log missed return."),
        "partial_failure": (NotSlashable.PARTIAL_FAILURE,
                           "Partial success ≠ complete failure.",
                           "Score per-dimension. DEGRADED on failed dims."),
    }
    
    if incident_type in NOT_SLASHABLE_MAP:
        reason, explanation, alt = NOT_SLASHABLE_MAP[incident_type]
        return SlashDecision(
            should_slash=False,
            reason=reason,
            explanation=explanation,
            alternative_action=alt,
        )
    
    # If evidence provided, validate
    if evidence:
        valid, msg = evidence.is_valid()
        if valid:
            return SlashDecision(
                should_slash=True,
                reason=evidence.reason,
                explanation=f"SLASH confirmed: {evidence.reason.value}. {msg}",
            )
        else:
            return SlashDecision(
                should_slash=False,
                reason=evidence.reason,
                explanation=f"Evidence insufficient: {msg}",
                alternative_action="Gather more evidence. Do not slash on suspicion.",
            )
    
    return SlashDecision(
        should_slash=False,
        reason=NotSlashable.QUALITY_DISPUTE,
        explanation="Unknown incident type with no evidence. Default: do not slash.",
        alternative_action="Investigate. DEGRADED until resolved.",
    )


def demo():
    print("=== Slash Trigger Validator ===\n")
    
    # Not slashable scenarios
    print("--- NOT SLASHABLE ---")
    for incident in ["timeout", "late_delivery", "quality_dispute", "model_drift", "dormant_return_missed"]:
        d = evaluate_incident(incident)
        print(f"  ❌ {incident}: {d.explanation}")
        print(f"     → {d.alternative_action}\n")
    
    # Slashable with valid evidence
    print("--- SLASHABLE (valid evidence) ---")
    evidence = SlashEvidence(
        reason=SlashReason.DOUBLE_SIGN,
        agent_id="agent:abc123",
        timestamp=datetime.now(),
        evidence_hash="sha256:deadbeef...",
        original_attestation_hash="sha256:original...",
        contradicting_proof="Signed attestation A at T=1, signed contradicting attestation B at T=1",
        witness_count=3,
    )
    d = evaluate_incident("double_sign", evidence)
    print(f"  ✅ double_sign: {d.explanation}\n")
    
    # Insufficient evidence
    print("--- INSUFFICIENT EVIDENCE ---")
    weak_evidence = SlashEvidence(
        reason=SlashReason.MALICIOUS_DELIVERY,
        agent_id="agent:xyz789",
        timestamp=datetime.now(),
        evidence_hash="sha256:weak...",
        original_attestation_hash="sha256:claim...",
        contradicting_proof="Single report of malicious payload",
        witness_count=1,
    )
    d = evaluate_incident("malicious_delivery", weak_evidence)
    print(f"  ⚠️  malicious_delivery: {d.explanation}")
    print(f"     → {d.alternative_action}\n")
    
    print("--- Design Principles ---")
    print("1. SLASH is terminal. Irreversible. No recovery.")
    print("2. If uncertain → DEGRADED, not SLASH.")
    print("3. Evidence must be provable (hashes, witnesses).")
    print("4. Eth2 pattern: only provably malicious acts.")
    print("5. Timeout ≠ malice. Late ≠ fraud. Drift ≠ deception.")


if __name__ == "__main__":
    demo()
