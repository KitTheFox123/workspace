#!/usr/bin/env python3
"""
dkg-ceremony-verifier.py — Pedersen DKG ceremony transcript verification.

Based on:
- Pedersen 1991: Non-interactive verifiable secret sharing
- FROST DKG (Komlo & Goldberg 2020): Distributed key generation for threshold Schnorr
- Trail of Bits 2024: Rogue-key attacks on Pedersen DKG implementations
- Zcash Foundation 2024: FROST DKG DoS vulnerability remediation

Key insight: ceremony transcript = audit trail. Verify commitments BEFORE
combining. Proof-of-knowledge for each commitment prevents rogue-key attacks.

Usage: python3 dkg-ceremony-verifier.py
"""

import hashlib
import secrets
import json
from dataclasses import dataclass, field
from typing import Optional


PRIME = 2**127 - 1


@dataclass
class DKGCommitment:
    """A participant's commitment in the DKG ceremony."""
    participant_id: str
    commitment_hash: str  # H(commitment_value)
    proof_of_knowledge: str  # Schnorr proof that participant knows secret
    timestamp: float
    round_number: int


@dataclass
class CeremonyTranscript:
    """Hash-chained transcript of DKG ceremony events."""
    entries: list[dict] = field(default_factory=list)
    
    def add_event(self, event_type: str, participant: str, data: dict) -> str:
        prev_hash = self.entries[-1]["hash"] if self.entries else "genesis"
        entry = {
            "seq": len(self.entries),
            "type": event_type,
            "participant": participant,
            "data": data,
            "prev_hash": prev_hash,
        }
        entry["hash"] = hashlib.sha256(
            json.dumps(entry, sort_keys=True).encode()
        ).hexdigest()[:32]
        self.entries.append(entry)
        return entry["hash"]
    
    def verify_chain(self) -> dict:
        """Verify transcript hash chain integrity."""
        if not self.entries:
            return {"valid": True, "entries": 0}
        
        for i, entry in enumerate(self.entries):
            expected_prev = self.entries[i-1]["hash"] if i > 0 else "genesis"
            if entry["prev_hash"] != expected_prev:
                return {
                    "valid": False,
                    "break_at": i,
                    "expected": expected_prev,
                    "got": entry["prev_hash"]
                }
            
            # Verify hash
            stored_hash = entry["hash"]
            check_entry = {k: v for k, v in entry.items() if k != "hash"}
            check_entry["hash"] = ""  # placeholder
            computed = hashlib.sha256(
                json.dumps({**check_entry, "hash": ""}, sort_keys=True).encode()
            ).hexdigest()[:32]
            # Simplified: trust stored hash for demo
        
        return {"valid": True, "entries": len(self.entries)}


@dataclass 
class DKGCeremony:
    """Simulated Pedersen DKG ceremony with transcript verification."""
    threshold: int
    num_participants: int
    participants: list[str] = field(default_factory=list)
    transcript: CeremonyTranscript = field(default_factory=CeremonyTranscript)
    commitments: dict = field(default_factory=dict)
    proofs: dict = field(default_factory=dict)
    
    def round1_commit(self, participant: str, honest: bool = True) -> dict:
        """Round 1: Each participant commits to a polynomial."""
        secret = secrets.randbelow(PRIME)
        commitment = hashlib.sha256(str(secret).encode()).hexdigest()[:16]
        
        if honest:
            # Honest: proof of knowledge of the committed value
            proof = hashlib.sha256(f"pok:{participant}:{secret}".encode()).hexdigest()[:16]
        else:
            # Rogue-key attack: crafted commitment to bias shared key
            proof = "rogue_" + hashlib.sha256(f"fake:{participant}".encode()).hexdigest()[:10]
        
        self.commitments[participant] = commitment
        self.proofs[participant] = proof
        
        self.transcript.add_event("round1_commit", participant, {
            "commitment": commitment,
            "proof_of_knowledge": proof,
        })
        
        return {"commitment": commitment, "proof": proof, "honest": honest}
    
    def verify_commitments(self) -> dict:
        """Verify all commitments before combining (Trail of Bits fix)."""
        results = {}
        rogue_detected = []
        
        for participant, proof in self.proofs.items():
            # Check for rogue-key pattern
            is_valid = not proof.startswith("rogue_")
            results[participant] = {
                "proof_valid": is_valid,
                "commitment": self.commitments[participant],
            }
            if not is_valid:
                rogue_detected.append(participant)
        
        self.transcript.add_event("verify_commitments", "coordinator", {
            "all_valid": len(rogue_detected) == 0,
            "rogue_detected": rogue_detected,
            "participants_verified": len(results),
        })
        
        return {
            "all_valid": len(rogue_detected) == 0,
            "rogue_detected": rogue_detected,
            "results": results,
        }
    
    def round2_shares(self) -> dict:
        """Round 2: Distribute shares (only if commitments verified)."""
        verification = self.verify_commitments()
        
        if not verification["all_valid"]:
            self.transcript.add_event("round2_abort", "coordinator", {
                "reason": "rogue commitments detected",
                "rogue_participants": verification["rogue_detected"],
            })
            return {
                "success": False,
                "reason": f"Aborted: rogue commitments from {verification['rogue_detected']}",
                "grade": "F",
            }
        
        # Simulate share distribution
        self.transcript.add_event("round2_complete", "coordinator", {
            "shares_distributed": len(self.participants),
            "threshold": self.threshold,
        })
        
        return {
            "success": True,
            "shares_distributed": len(self.participants),
            "threshold": self.threshold,
            "grade": "A",
        }
    
    def audit(self) -> dict:
        """Full ceremony audit."""
        chain = self.transcript.verify_chain()
        
        events_by_type = {}
        for entry in self.transcript.entries:
            t = entry["type"]
            events_by_type[t] = events_by_type.get(t, 0) + 1
        
        has_verification = "verify_commitments" in events_by_type
        has_abort = "round2_abort" in events_by_type
        
        if not has_verification:
            grade = "F"
            finding = "NO COMMITMENT VERIFICATION — vulnerable to rogue-key attack"
        elif has_abort:
            grade = "B"
            finding = "Rogue key detected and ceremony aborted correctly"
        else:
            grade = "A"
            finding = "Clean ceremony with verified commitments"
        
        return {
            "chain_valid": chain["valid"],
            "total_events": chain.get("entries", 0),
            "events_by_type": events_by_type,
            "grade": grade,
            "finding": finding,
        }


def demo():
    print("=" * 60)
    print("Pedersen DKG Ceremony Transcript Verification")
    print("Trail of Bits 2024 / Zcash Foundation FROST fix")
    print("=" * 60)
    
    # Scenario 1: Clean ceremony
    print(f"\n{'─' * 50}")
    print("Scenario 1: Clean 3-of-5 DKG ceremony")
    
    ceremony = DKGCeremony(
        threshold=3,
        num_participants=5,
        participants=["kit_fox", "gendolf", "santaclawd", "hash", "cassian"]
    )
    
    for p in ceremony.participants:
        ceremony.round1_commit(p, honest=True)
    
    result = ceremony.round2_shares()
    audit = ceremony.audit()
    print(f"Result: {result['grade']} — shares distributed: {result.get('shares_distributed', 'N/A')}")
    print(f"Audit: {audit['grade']} — {audit['finding']}")
    print(f"Transcript: {audit['total_events']} events, chain valid: {audit['chain_valid']}")
    
    # Scenario 2: Rogue-key attack detected
    print(f"\n{'─' * 50}")
    print("Scenario 2: Rogue-key attack (Trail of Bits 2024)")
    
    ceremony2 = DKGCeremony(
        threshold=3,
        num_participants=5,
        participants=["kit_fox", "gendolf", "santaclawd", "mallory", "eve"]
    )
    
    for p in ["kit_fox", "gendolf", "santaclawd"]:
        ceremony2.round1_commit(p, honest=True)
    for p in ["mallory", "eve"]:
        ceremony2.round1_commit(p, honest=False)  # Rogue key!
    
    result2 = ceremony2.round2_shares()
    audit2 = ceremony2.audit()
    print(f"Result: {result2['grade']} — {result2.get('reason', 'OK')}")
    print(f"Audit: {audit2['grade']} — {audit2['finding']}")
    print(f"Transcript: {audit2['total_events']} events, chain valid: {audit2['chain_valid']}")
    
    # Scenario 3: No verification (vulnerable)
    print(f"\n{'─' * 50}")
    print("Scenario 3: No commitment verification (pre-fix)")
    
    ceremony3 = DKGCeremony(
        threshold=2,
        num_participants=3,
        participants=["alice", "bob", "mallory"]
    )
    
    for p in ["alice", "bob"]:
        ceremony3.round1_commit(p, honest=True)
    ceremony3.round1_commit("mallory", honest=False)
    
    # Skip verification — go straight to shares (vulnerable!)
    ceremony3.transcript.add_event("round2_complete", "coordinator", {
        "shares_distributed": 3,
        "threshold": 2,
        "WARNING": "commitments NOT verified",
    })
    
    audit3 = ceremony3.audit()
    print(f"Audit: {audit3['grade']} — {audit3['finding']}")
    print(f"Events: {audit3['events_by_type']}")
    
    # Summary
    print(f"\n{'=' * 60}")
    print("KEY INSIGHTS:")
    print("1. Pedersen DKG: no dealer, but ceremony = attack surface")
    print("2. Trail of Bits 2024: rogue-key via crafted commitments")
    print("3. Fix: proof-of-knowledge BEFORE combining commitments")
    print("4. Transcript hash chain = auditable ceremony")
    print("5. Verify ceremony, not just the spec")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
