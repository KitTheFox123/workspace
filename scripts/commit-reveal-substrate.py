#!/usr/bin/env python3
"""
commit-reveal-substrate.py — The universal primitive under all agent trust tools.

Based on:
- santaclawd: "commit-reveal-intent is not a pattern. it is the substrate."
- "every unhashed input = retroactive rationalization slot = mirage attack surface"
- funwolf: "email threads are natural pre-commitment stores"

Every tool we've built is a commit-reveal variant:
- rule_hash = commit(scoring_rule) before enforcement
- canary_spec_hash = commit(canary) before drift probe
- scope_manifest = commit(capabilities) before execution
- dataset_hash = commit(calibration_data) before evaluation
- trace_hash = commit(execution_steps) before audit
- null_receipt = commit(decline) at decision time
- genesis_anchor = commit(identity) at birth

This library: unified commit-reveal with phases, verification, and attack detection.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Phase(Enum):
    UNCOMMITTED = "uncommitted"  # Vulnerable: retroactive rationalization
    COMMITTED = "committed"      # Hash published, content hidden
    REVEALED = "revealed"        # Content published, hash verified
    VERIFIED = "verified"        # Third party confirmed match
    EXPIRED = "expired"          # Reveal window closed


class AttackType(Enum):
    RETROACTIVE_RATIONALIZATION = "retroactive_rationalization"
    COMMIT_THEN_SWITCH = "commit_then_switch"
    SELECTIVE_REVEAL = "selective_reveal"
    TIMING_MANIPULATION = "timing_manipulation"
    NONE = "none"


@dataclass
class Commitment:
    label: str
    content_hash: str
    commit_time: float
    reveal_deadline: float  # After this, commitment expires
    phase: Phase = Phase.COMMITTED
    revealed_content: Optional[str] = None
    reveal_time: Optional[float] = None
    verifier: Optional[str] = None
    verify_time: Optional[float] = None

    def reveal(self, content: str) -> tuple[bool, str]:
        """Reveal content and verify against commitment."""
        now = time.time()
        
        if now > self.reveal_deadline:
            self.phase = Phase.EXPIRED
            return False, "EXPIRED: reveal window closed"
        
        content_hash = _hash(content)
        if content_hash != self.content_hash:
            return False, f"MISMATCH: committed {self.content_hash}, revealed {content_hash}"
        
        self.revealed_content = content
        self.reveal_time = now
        self.phase = Phase.REVEALED
        return True, "MATCH: commitment honored"

    def verify(self, verifier_id: str) -> tuple[bool, str]:
        """Third-party verification."""
        if self.phase != Phase.REVEALED:
            return False, f"Cannot verify in phase {self.phase.value}"
        
        # Re-hash revealed content
        if _hash(self.revealed_content) != self.content_hash:
            return False, "TAMPERED: revealed content no longer matches"
        
        self.verifier = verifier_id
        self.verify_time = time.time()
        self.phase = Phase.VERIFIED
        return True, f"VERIFIED by {verifier_id}"


@dataclass
class CommitRevealStore:
    """Unified store for all commitments."""
    commitments: dict[str, Commitment] = field(default_factory=dict)

    def commit(self, label: str, content: str, deadline_sec: float = 3600) -> Commitment:
        """Commit content. Returns commitment with hash."""
        now = time.time()
        c = Commitment(
            label=label,
            content_hash=_hash(content),
            commit_time=now,
            reveal_deadline=now + deadline_sec,
        )
        self.commitments[label] = c
        return c

    def detect_attack(self, label: str, claimed_content: str) -> AttackType:
        """Detect common attacks against commit-reveal."""
        if label not in self.commitments:
            return AttackType.RETROACTIVE_RATIONALIZATION  # No prior commitment

        c = self.commitments[label]
        
        if c.phase == Phase.UNCOMMITTED:
            return AttackType.RETROACTIVE_RATIONALIZATION
        
        if c.phase == Phase.EXPIRED:
            return AttackType.TIMING_MANIPULATION
        
        if _hash(claimed_content) != c.content_hash:
            return AttackType.COMMIT_THEN_SWITCH
        
        return AttackType.NONE

    def audit(self) -> dict:
        """Audit all commitments."""
        now = time.time()
        summary = {"total": 0, "verified": 0, "expired": 0, "pending": 0, "attacks": 0}
        for label, c in self.commitments.items():
            summary["total"] += 1
            if c.phase == Phase.VERIFIED:
                summary["verified"] += 1
            elif c.phase == Phase.EXPIRED or now > c.reveal_deadline:
                summary["expired"] += 1
            elif c.phase in (Phase.COMMITTED, Phase.REVEALED):
                summary["pending"] += 1

        coverage = summary["verified"] / max(summary["total"], 1)
        return {**summary, "coverage": coverage}


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def main():
    print("=" * 70)
    print("COMMIT-REVEAL SUBSTRATE")
    print("santaclawd: 'commit-reveal is not a pattern. it is the substrate.'")
    print("=" * 70)

    store = CommitRevealStore()

    # All our tools as commit-reveal instances
    print("\n--- Our 300+ Tools as Commit-Reveal Variants ---")
    tools = [
        ("rule_hash", '{"type":"brier","version":"v1","scale":"bp"}'),
        ("canary_spec_hash", '{"input":"test_doc_v3","expected":"0.85","difficulty":"original"}'),
        ("scope_manifest", '{"reply_mentions":true,"post_research":false,"build_tool":true}'),
        ("dataset_hash", '{"calibration":"tc4","n":130,"date":"2026-02-24"}'),
        ("trace_hash", '{"steps":["parse","score","format"],"env":"python3.11"}'),
        ("null_receipt", '{"capability":"post_research","decision":"decline","reason":"quality_gate"}'),
        ("genesis_anchor", '{"soul":"kit_fox","principal":"ilya","created":"2026-01-30"}'),
    ]

    print(f"{'Label':<20} {'Hash':<18} {'Phase'}")
    print("-" * 50)
    for label, content in tools:
        c = store.commit(label, content)
        print(f"{c.label:<20} {c.content_hash:<18} {c.phase.value}")

    # Reveal and verify
    print("\n--- Reveal + Verify ---")
    for label, content in tools[:3]:
        ok, msg = store.commitments[label].reveal(content)
        print(f"  {label}: {msg}")
        ok2, msg2 = store.commitments[label].verify("bro_agent")
        print(f"    → {msg2}")

    # Attack detection
    print("\n--- Attack Detection ---")
    attacks = [
        ("rule_hash", '{"type":"brier","version":"v2","scale":"float"}'),  # Switch
        ("nonexistent_rule", '{"type":"made_up"}'),                         # Retroactive
        ("scope_manifest", '{"reply_mentions":true,"post_research":false,"build_tool":true}'),  # Legit
    ]

    for label, content in attacks:
        attack = store.detect_attack(label, content)
        print(f"  {label}: {attack.value}")

    # Audit
    print("\n--- Store Audit ---")
    audit = store.audit()
    print(f"  Total: {audit['total']}, Verified: {audit['verified']}, "
          f"Pending: {audit['pending']}, Coverage: {audit['coverage']:.0%}")

    # The thesis
    print("\n--- NIST Submission Thesis ---")
    print("santaclawd: 'every unhashed input = retroactive rationalization slot'")
    print()
    print("The attack surface for agent trust is UNCOMMITTED STATE.")
    print("Any parameter that exists before being hashed can be changed.")
    print("Any decision that exists before being logged can be denied.")
    print()
    print("300+ tools, one primitive: commit before act.")
    print()
    print("Phase taxonomy:")
    print("  UNCOMMITTED → vulnerable (retroactive rationalization)")
    print("  COMMITTED   → binding (hash published, content hidden)")
    print("  REVEALED    → auditable (content matches hash)")
    print("  VERIFIED    → trusted (third party confirmed)")
    print("  EXPIRED     → suspicious (reveal window closed)")
    print()
    print("Every tool in the NIST package moves state from UNCOMMITTED → VERIFIED.")
    print("That is the entire contribution. One primitive. Universal application.")


if __name__ == "__main__":
    main()
