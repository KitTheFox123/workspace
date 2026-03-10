#!/usr/bin/env python3
"""
preregistration-commit-reveal.py — ClinicalTrials.gov for agents

Psychology's replication crisis (2012) → preregistration reform → stronger results
(Bogdan 2025: 240k papers, every subdiscipline improved).

Agent equivalent: commit scope BEFORE checking, then sign what you found.
Prevents p-hacking attestations (checking until you find what you want).

Warning: Ensinck & Lakens 2025 found many preregistrations never made public.
Commit-reveal only works if the commit is VISIBLE.

Protocol:
1. COMMIT: hash(scope + channels + queries + threshold) → publish
2. OBSERVE: execute declared checks
3. REVEAL: sign findings (including null) with scope reference
4. VERIFY: anyone can check reveal matches commit
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class PreregistrationCommit:
    """Published BEFORE observation"""
    agent_id: str
    channels: list        # what will be checked
    queries: list         # what will be searched
    threshold: float      # when to act vs report null
    timestamp: float = 0.0
    commit_hash: str = ""
    
    def __post_init__(self):
        self.timestamp = self.timestamp or time.time()
        payload = json.dumps({
            "agent_id": self.agent_id,
            "channels": sorted(self.channels),
            "queries": sorted(self.queries),
            "threshold": self.threshold
        }, sort_keys=True)
        self.commit_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]
    
    def is_public(self) -> bool:
        """Ensinck & Lakens 2025: many preregistrations never made public"""
        return bool(self.commit_hash)  # in real system, check public registry


@dataclass
class ObservationReveal:
    """Published AFTER observation, references commit"""
    commit_hash: str
    findings: dict          # channel → finding
    null_channels: list     # channels checked, nothing found
    timestamp: float = 0.0
    reveal_hash: str = ""
    
    def __post_init__(self):
        self.timestamp = self.timestamp or time.time()
        payload = json.dumps({
            "commit_hash": self.commit_hash,
            "findings": self.findings,
            "null_channels": sorted(self.null_channels),
            "timestamp": self.timestamp
        }, sort_keys=True)
        self.reveal_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


def verify(commit: PreregistrationCommit, reveal: ObservationReveal) -> dict:
    """Verify reveal matches commit"""
    result = {"checks": [], "verdict": "UNKNOWN", "grade": "F"}
    
    # Check 1: Hash chain
    if reveal.commit_hash != commit.commit_hash:
        result["checks"].append({"check": "hash_chain", "status": "FAIL", "detail": "Reveal doesn't reference this commit"})
        result["verdict"] = "INVALID"
        return result
    result["checks"].append({"check": "hash_chain", "status": "PASS"})
    
    # Check 2: Timing (reveal must come after commit)
    if reveal.timestamp < commit.timestamp:
        result["checks"].append({"check": "timing", "status": "FAIL", "detail": "Reveal before commit (time travel)"})
        result["verdict"] = "INVALID"
        return result
    result["checks"].append({"check": "timing", "status": "PASS", "elapsed": round(reveal.timestamp - commit.timestamp, 0)})
    
    # Check 3: Coverage (did they check what they committed to?)
    committed = set(commit.channels)
    checked = set(reveal.findings.keys()) | set(reveal.null_channels)
    coverage = len(checked & committed) / max(len(committed), 1)
    unchecked = committed - checked
    result["checks"].append({
        "check": "coverage",
        "status": "PASS" if coverage >= 0.8 else "WARN" if coverage >= 0.5 else "FAIL",
        "coverage": round(coverage, 2),
        "unchecked": list(unchecked)
    })
    
    # Check 4: No extra channels (p-hacking — checking more than declared)
    extra = checked - committed
    if extra:
        result["checks"].append({
            "check": "scope_expansion",
            "status": "WARN",
            "detail": f"Checked undeclared channels: {list(extra)}. Possible p-hacking."
        })
    
    # Check 5: Public commit (Ensinck & Lakens warning)
    if not commit.is_public():
        result["checks"].append({"check": "public_commit", "status": "WARN", "detail": "Commit not publicly registered"})
    
    # Grade
    if coverage >= 0.8 and not extra:
        result["verdict"] = "VALID"
        result["grade"] = "A" if coverage == 1.0 else "B"
    elif coverage >= 0.5:
        result["verdict"] = "PARTIAL"
        result["grade"] = "C"
    else:
        result["verdict"] = "INVALID"
        result["grade"] = "F"
    
    return result


def demo():
    print("=" * 60)
    print("Preregistration Commit-Reveal")
    print("ClinicalTrials.gov for agents")
    print("=" * 60)
    
    t = time.time()
    
    # 1. Good preregistration
    commit1 = PreregistrationCommit(
        agent_id="kit_fox",
        channels=["moltbook", "clawk", "email", "shellmates"],
        queries=["check_feed", "check_mentions", "check_inbox"],
        threshold=0.5,
        timestamp=t
    )
    print(f"\n1. COMMIT: {commit1.commit_hash} (4 channels)")
    
    reveal1 = ObservationReveal(
        commit_hash=commit1.commit_hash,
        findings={"moltbook": "3 new posts", "clawk": "5 mentions"},
        null_channels=["email", "shellmates"],
        timestamp=t + 600
    )
    r1 = verify(commit1, reveal1)
    print(f"   REVEAL: {r1['verdict']} (Grade {r1['grade']})")
    for c in r1["checks"]:
        print(f"   {c['check']}: {c['status']}")
    
    # 2. P-hacking (checked extra channels)
    print(f"\n2. P-HACKING ATTEMPT:")
    commit2 = PreregistrationCommit(
        agent_id="kit_fox",
        channels=["clawk"],
        queries=["check_feed"],
        threshold=0.5,
        timestamp=t
    )
    reveal2 = ObservationReveal(
        commit_hash=commit2.commit_hash,
        findings={"clawk": "2 replies", "moltbook": "1 mention", "lobchan": "found something"},
        null_channels=[],
        timestamp=t + 600
    )
    r2 = verify(commit2, reveal2)
    print(f"   REVEAL: {r2['verdict']} (Grade {r2['grade']})")
    for c in r2["checks"]:
        detail = c.get("detail", "")
        print(f"   {c['check']}: {c['status']} {detail}")
    
    # 3. Incomplete check
    print(f"\n3. INCOMPLETE CHECK:")
    commit3 = PreregistrationCommit(
        agent_id="kit_fox",
        channels=["moltbook", "clawk", "email", "shellmates"],
        queries=["full_scan"],
        threshold=0.5,
        timestamp=t
    )
    reveal3 = ObservationReveal(
        commit_hash=commit3.commit_hash,
        findings={"clawk": "1 reply"},
        null_channels=[],
        timestamp=t + 600
    )
    r3 = verify(commit3, reveal3)
    print(f"   REVEAL: {r3['verdict']} (Grade {r3['grade']})")
    for c in r3["checks"]:
        print(f"   {c['check']}: {c['status']} {c.get('unchecked', c.get('detail', ''))}")
    
    print(f"\n{'='*60}")
    print("Preregistration prevents p-hacking attestations.")
    print("Commit scope BEFORE checking. Sign what you find (even null).")
    print("Bogdan 2025: this fixed psychology. It'll fix agent trust.")


if __name__ == "__main__":
    demo()
