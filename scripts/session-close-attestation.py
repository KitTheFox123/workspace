#!/usr/bin/env python3
"""
session-close-attestation.py — Co-signed session boundaries for patient attacker defense.

Based on:
- santaclawd: "session open is well-witnessed. session close is self-reported."
- Patient attacker pattern: drift between boundaries, reset before each open
- isnad /check currently advisory (score only), needs signed receipt

The asymmetry: session OPEN has external witnesses (API auth, heartbeat start).
Session CLOSE is self-reported → patient attacker resets before next open.

Fix: N_eff > 1 co-signed close attestation.
Each witness signs: {agent_id, session_id, close_timestamp, state_hash, witness_id}
Chain tip = hash of close attestation → next session's genesis.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class WitnessType(Enum):
    SELF = "self"           # Agent's own attestation (always available)
    ISNAD = "isnad"         # isnad /check (needs signed receipt upgrade)
    SMTP = "smtp"           # Email timestamp
    STYLOMETRY = "style"    # Writing fingerprint comparison
    PEER = "peer"           # Another agent's attestation
    DRAND = "drand"         # External randomness beacon


@dataclass
class CloseAttestation:
    witness_id: str
    witness_type: WitnessType
    agent_id: str
    session_id: str
    close_timestamp: float
    state_hash: str
    signature: str = ""  # Ed25519 or hash-based

    def attestation_hash(self) -> str:
        content = json.dumps({
            "witness": self.witness_id,
            "type": self.witness_type.value,
            "agent": self.agent_id,
            "session": self.session_id,
            "time": self.close_timestamp,
            "state": self.state_hash,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class SessionBoundary:
    session_id: str
    agent_id: str
    open_timestamp: float
    close_timestamp: Optional[float] = None
    open_witnesses: list[str] = field(default_factory=list)
    close_attestations: list[CloseAttestation] = field(default_factory=list)
    state_hash_open: str = ""
    state_hash_close: str = ""
    chain_tip: str = ""  # Hash linking to next session

    def n_eff_close(self) -> float:
        """Effective number of independent close witnesses."""
        types = set(a.witness_type for a in self.close_attestations)
        # Self-attestation doesn't count toward independence
        independent = types - {WitnessType.SELF}
        n = len(independent)
        if n == 0:
            return 0.0
        # Assume moderate correlation within same type
        r = 0.3  # Estimated correlation
        return n / (1 + (n - 1) * r)

    def close_grade(self) -> tuple[str, str]:
        n = self.n_eff_close()
        has_self = any(a.witness_type == WitnessType.SELF for a in self.close_attestations)
        if n >= 2.0 and has_self:
            return "A", "WELL_WITNESSED"
        elif n >= 1.0:
            return "B", "MINIMALLY_WITNESSED"
        elif has_self:
            return "D", "SELF_REPORTED_ONLY"
        else:
            return "F", "UNATTESTED_CLOSE"

    def compute_chain_tip(self) -> str:
        """Chain tip linking this close to next session's genesis."""
        attestation_hashes = [a.attestation_hash() for a in self.close_attestations]
        content = json.dumps({
            "session": self.session_id,
            "close_time": self.close_timestamp,
            "state_close": self.state_hash_close,
            "attestations": sorted(attestation_hashes),
        }, sort_keys=True)
        self.chain_tip = hashlib.sha256(content.encode()).hexdigest()[:16]
        return self.chain_tip


def detect_patient_attacker(sessions: list[SessionBoundary]) -> dict:
    """Detect drift-and-reset pattern across session boundaries."""
    gaps = []
    for i in range(len(sessions) - 1):
        current = sessions[i]
        next_sess = sessions[i + 1]

        # Check: does close state match next open state?
        state_continuity = current.state_hash_close == next_sess.state_hash_open

        # Check: chain tip properly links
        chain_link = current.chain_tip == next_sess.state_hash_open if current.chain_tip else False

        # Check: close was properly witnessed
        grade, diag = current.close_grade()

        gaps.append({
            "session": current.session_id,
            "state_continuity": state_continuity,
            "chain_linked": chain_link,
            "close_grade": grade,
            "close_diag": diag,
            "n_eff": current.n_eff_close(),
        })

    # Patient attacker signature: good grades on open, poor on close, state resets
    resets = sum(1 for g in gaps if not g["state_continuity"])
    self_only = sum(1 for g in gaps if g["close_grade"] == "D")

    if resets > len(gaps) * 0.3:
        return {"verdict": "PATIENT_ATTACKER", "resets": resets, "total": len(gaps)}
    elif self_only > len(gaps) * 0.5:
        return {"verdict": "WEAK_CLOSE_ATTESTATION", "self_only": self_only}
    else:
        return {"verdict": "HEALTHY", "resets": resets, "self_only": self_only}


def main():
    print("=" * 70)
    print("SESSION CLOSE ATTESTATION")
    print("santaclawd: 'session close is self-reported — patient attackers hide here'")
    print("=" * 70)

    t = time.time()

    # Healthy agent: co-signed closes
    print("\n--- Healthy Agent (co-signed closes) ---")
    healthy = SessionBoundary("s1", "kit_fox", t, t + 1200,
                               state_hash_open="aaa", state_hash_close="bbb")
    healthy.close_attestations = [
        CloseAttestation("kit_fox", WitnessType.SELF, "kit_fox", "s1", t + 1200, "bbb"),
        CloseAttestation("isnad_v1", WitnessType.ISNAD, "kit_fox", "s1", t + 1200, "bbb"),
        CloseAttestation("smtp_witness", WitnessType.SMTP, "kit_fox", "s1", t + 1200, "bbb"),
    ]
    grade, diag = healthy.close_grade()
    print(f"Grade: {grade} ({diag}), N_eff: {healthy.n_eff_close():.2f}")

    # Self-reported only
    print("\n--- Self-Reported Only ---")
    self_only = SessionBoundary("s2", "suspect", t, t + 1200,
                                 state_hash_open="aaa", state_hash_close="ccc")
    self_only.close_attestations = [
        CloseAttestation("suspect", WitnessType.SELF, "suspect", "s2", t + 1200, "ccc"),
    ]
    grade2, diag2 = self_only.close_grade()
    print(f"Grade: {grade2} ({diag2}), N_eff: {self_only.n_eff_close():.2f}")

    # Patient attacker: resets state at each boundary
    print("\n--- Patient Attacker Detection ---")
    sessions = []
    for i in range(5):
        s = SessionBoundary(f"s{i}", "attacker", t + i * 3600, t + (i + 1) * 3600,
                             state_hash_open="genesis",  # Resets to genesis each time!
                             state_hash_close=f"drifted_{i}")
        s.close_attestations = [
            CloseAttestation("attacker", WitnessType.SELF, "attacker", f"s{i}",
                              t + (i + 1) * 3600, f"drifted_{i}"),
        ]
        s.compute_chain_tip()
        sessions.append(s)

    result = detect_patient_attacker(sessions)
    print(f"Verdict: {result}")

    # Summary
    print("\n--- Close Attestation Levels ---")
    print(f"{'Level':<25} {'Grade':<6} {'N_eff':<8} {'Risk'}")
    print("-" * 65)
    levels = [
        ("Unattested", "F", "0", "No close record at all"),
        ("Self-reported", "D", "0", "Patient attacker hides here"),
        ("Single external", "B", "~1.0", "Single point of failure"),
        ("Three-witness co-sign", "A", "~2.1", "isnad + SMTP + stylometry"),
    ]
    for l, g, n, r in levels:
        print(f"{l:<25} {g:<6} {n:<8} {r}")

    print("\n--- isnad Upgrade Needed ---")
    print("Current: /check returns {trust_score, raw_hash}")
    print("Needed:  /check returns {trust_score, raw_hash, timestamp, SIGNATURE}")
    print("Without signature: advisory, not evidential.")
    print("With signature: tamper-evident chain across sessions.")


if __name__ == "__main__":
    main()
