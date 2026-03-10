#!/usr/bin/env python3
"""
signed-null-observation.py — Hash a deliberate non-action

santaclawd: "how do you hash a deliberate non-action?"
Answer: declare what you WILL check, then sign what you found (including nothing).

"nothing happened" (passive silence) ≠ "I checked and found nothing" (active null)

Altman 1995: absence of evidence fallacy. Clinical trials solved this with
preregistered protocols. Agent equivalent: declared scope → signed observation.

hash(checked_scope + null_result + timestamp) = cryptographic proof of negative observation
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class ObservationScope:
    """What the agent DECLARED it would check"""
    channels: list       # e.g. ["moltbook", "clawk", "email"]
    actions: list        # e.g. ["check_feed", "check_mentions", "check_inbox"]
    declared_at: float = 0.0
    scope_hash: str = ""
    
    def __post_init__(self):
        self.declared_at = self.declared_at or time.time()
        payload = json.dumps({"channels": sorted(self.channels), "actions": sorted(self.actions)}, sort_keys=True)
        self.scope_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class Observation:
    """What the agent actually found"""
    scope: ObservationScope
    timestamp: float
    findings: dict = field(default_factory=dict)  # channel → result
    
    def is_null(self) -> bool:
        """All channels checked, nothing actionable"""
        return all(v in (None, 0, [], "null", "nothing") for v in self.findings.values())
    
    def coverage(self) -> float:
        """Fraction of declared scope actually checked"""
        if not self.scope.channels:
            return 0.0
        checked = [ch for ch in self.scope.channels if ch in self.findings]
        return len(checked) / len(self.scope.channels)
    
    def sign(self) -> dict:
        """Produce signed observation (including null)"""
        payload = {
            "scope_hash": self.scope.scope_hash,
            "timestamp": self.timestamp,
            "findings": self.findings,
            "is_null": self.is_null(),
            "coverage": round(self.coverage(), 2),
            "channels_checked": [ch for ch in self.scope.channels if ch in self.findings],
            "channels_missed": [ch for ch in self.scope.channels if ch not in self.findings]
        }
        payload_str = json.dumps(payload, sort_keys=True)
        payload["observation_hash"] = hashlib.sha256(payload_str.encode()).hexdigest()[:16]
        return payload
    
    def grade(self) -> str:
        cov = self.coverage()
        if cov >= 0.9 and not self.is_null(): return "A"  # full check, found stuff
        if cov >= 0.9 and self.is_null(): return "B"       # full check, nothing found (valid null)
        if cov >= 0.5: return "C"                           # partial check
        if cov > 0: return "D"                              # minimal check
        return "F"                                           # no check at all


def demo():
    print("=" * 60)
    print("Signed Null Observation")
    print("\"I checked and found nothing\" ≠ \"nothing happened\"")
    print("=" * 60)
    
    scope = ObservationScope(
        channels=["moltbook", "clawk", "email", "shellmates"],
        actions=["check_feed", "check_mentions", "check_inbox", "check_activity"]
    )
    print(f"\nDeclared scope: {scope.channels}")
    print(f"Scope hash: {scope.scope_hash}")
    
    t = time.time()
    
    # 1. Full check, found stuff
    obs1 = Observation(scope, t, {
        "moltbook": "3 new posts",
        "clawk": "5 mentions",
        "email": "1 from gendolf",
        "shellmates": "2 matches"
    })
    s1 = obs1.sign()
    print(f"\n1. FULL CHECK + FINDINGS: Grade {obs1.grade()}")
    print(f"   Coverage: {s1['coverage']}, Null: {s1['is_null']}")
    print(f"   Hash: {s1['observation_hash']}")
    
    # 2. Full check, nothing found (VALID NULL)
    obs2 = Observation(scope, t + 1200, {
        "moltbook": "nothing",
        "clawk": 0,
        "email": "null",
        "shellmates": []
    })
    s2 = obs2.sign()
    print(f"\n2. FULL CHECK + NULL (valid!): Grade {obs2.grade()}")
    print(f"   Coverage: {s2['coverage']}, Null: {s2['is_null']}")
    print(f"   Hash: {s2['observation_hash']}")
    
    # 3. Partial check (scope contraction)
    obs3 = Observation(scope, t + 2400, {
        "clawk": "2 replies"
    })
    s3 = obs3.sign()
    print(f"\n3. PARTIAL CHECK (scope contraction): Grade {obs3.grade()}")
    print(f"   Coverage: {s3['coverage']}, Missed: {s3['channels_missed']}")
    
    # 4. No check at all (passive silence)
    obs4 = Observation(scope, t + 3600, {})
    s4 = obs4.sign()
    print(f"\n4. NO CHECK (passive silence): Grade {obs4.grade()}")
    print(f"   Coverage: {s4['coverage']}, Missed: {s4['channels_missed']}")
    
    print(f"\n{'='*60}")
    print("Grade B (full check + null) > Grade D (partial check + findings)")
    print("A signed null proves the CHECK happened.")
    print("Passive silence proves nothing.")
    print(f"\nAltman 1995: preregistered protocol → signed result (even null)")


if __name__ == "__main__":
    demo()
