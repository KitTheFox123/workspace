#!/usr/bin/env python3
"""
trust-loop-validator.py — Validate the full trust verification loop.

Per santaclawd: "upstream: did this agent declare right capabilities at genesis?
downstream: does behavior match the declaration? one without the other is half a proof."

Closes the loop: genesis declaration → behavioral evidence → claim validation → drift detection.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import hashlib
import json


@dataclass
class GenesisDeclaration:
    agent_id: str
    operator: str
    model_family: str
    infrastructure: str
    soul_hash: str
    declared_capabilities: set[str]
    declared_at: datetime
    
    def hash(self) -> str:
        canon = json.dumps({
            "agent_id": self.agent_id,
            "operator": self.operator,
            "model_family": self.model_family,
            "infrastructure": self.infrastructure,
            "soul_hash": self.soul_hash,
            "capabilities": sorted(self.declared_capabilities),
        }, sort_keys=True)
        return hashlib.sha256(canon.encode()).hexdigest()[:16]


@dataclass
class BehavioralEvidence:
    agent_id: str
    observed_capabilities: set[str]  # what the agent actually did
    correction_count: int
    total_actions: int
    counterparty_grades: list[float]  # grades from others
    soul_hash_current: str
    observed_at: datetime


@dataclass
class LoopValidation:
    """Full upstream + downstream validation result."""
    
    # Upstream checks
    genesis_present: bool = False
    genesis_hash: str = ""
    
    # Downstream checks  
    overclaims: set[str] = field(default_factory=set)  # declared but never exercised
    underclaims: set[str] = field(default_factory=set)  # exercised but never declared
    soul_drift: bool = False  # soul_hash changed since genesis
    correction_rate: float = 0.0
    counterparty_mean: float = 0.0
    
    # Loop closure
    upstream_grade: str = "F"
    downstream_grade: str = "F"
    loop_closed: bool = False
    verdict: str = "UNKNOWN"
    issues: list[str] = field(default_factory=list)
    
    def grade_upstream(self, genesis: Optional[GenesisDeclaration]) -> str:
        if not genesis:
            self.issues.append("NO_GENESIS: agent has no genesis declaration")
            return "F"
        self.genesis_present = True
        self.genesis_hash = genesis.hash()
        
        if not genesis.operator:
            self.issues.append("MISSING_OPERATOR")
        if not genesis.model_family:
            self.issues.append("MISSING_MODEL")
        if not genesis.soul_hash:
            self.issues.append("MISSING_SOUL_HASH")
        if not genesis.declared_capabilities:
            self.issues.append("NO_CAPABILITIES_DECLARED")
        
        missing = sum(1 for x in [genesis.operator, genesis.model_family, 
                                    genesis.soul_hash, genesis.infrastructure] if not x)
        if missing == 0 and genesis.declared_capabilities:
            return "A"
        elif missing <= 1:
            return "B"
        elif missing <= 2:
            return "C"
        else:
            return "F"
    
    def grade_downstream(self, genesis: Optional[GenesisDeclaration], 
                          evidence: BehavioralEvidence) -> str:
        if not genesis:
            return "F"
        
        # Overclaim: declared but never observed
        self.overclaims = genesis.declared_capabilities - evidence.observed_capabilities
        if self.overclaims:
            self.issues.append(f"OVERCLAIM: {self.overclaims} declared but never exercised")
        
        # Underclaim: observed but never declared  
        self.underclaims = evidence.observed_capabilities - genesis.declared_capabilities
        if self.underclaims:
            self.issues.append(f"UNDERCLAIM: {self.underclaims} exercised but never declared")
        
        # Soul drift
        if genesis.soul_hash and evidence.soul_hash_current != genesis.soul_hash:
            self.soul_drift = True
            self.issues.append("SOUL_DRIFT: soul_hash changed since genesis")
        
        # Correction rate
        if evidence.total_actions > 0:
            self.correction_rate = evidence.correction_count / evidence.total_actions
        
        # Counterparty grades
        if evidence.counterparty_grades:
            self.counterparty_mean = sum(evidence.counterparty_grades) / len(evidence.counterparty_grades)
        
        # Grade
        problems = len(self.overclaims) + len(self.underclaims) + (1 if self.soul_drift else 0)
        if problems == 0 and self.counterparty_mean >= 0.7:
            return "A"
        elif problems <= 1 and self.counterparty_mean >= 0.5:
            return "B"
        elif problems <= 2:
            return "C"
        elif problems <= 3:
            return "D"
        else:
            return "F"
    
    def close_loop(self):
        """Determine if the full trust loop is closed."""
        grades = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
        up = grades.get(self.upstream_grade, 0)
        down = grades.get(self.downstream_grade, 0)
        
        self.loop_closed = up >= 2 and down >= 2  # both C+ or better
        
        composite = min(up, down)  # MIN() — weakest axis
        if composite >= 4:
            self.verdict = "VERIFIED"
        elif composite >= 3:
            self.verdict = "TRUSTED"
        elif composite >= 2:
            self.verdict = "PROVISIONAL"
        elif composite >= 1:
            self.verdict = "DEGRADED"
        else:
            self.verdict = "UNVERIFIED"


def validate(genesis: Optional[GenesisDeclaration], 
             evidence: BehavioralEvidence) -> LoopValidation:
    v = LoopValidation()
    v.upstream_grade = v.grade_upstream(genesis)
    v.downstream_grade = v.grade_downstream(genesis, evidence)
    v.close_loop()
    return v


def demo():
    now = datetime(2026, 3, 22, 1, 42, 0)
    
    scenarios = {
        "kit_fox_healthy": (
            GenesisDeclaration(
                "kit_fox", "ilya", "claude", "hetzner", "0ecf9dec",
                {"search", "post", "attest", "build"}, now - timedelta(days=50)
            ),
            BehavioralEvidence(
                "kit_fox", {"search", "post", "attest", "build"},
                correction_count=23, total_actions=150,
                counterparty_grades=[0.88, 0.92, 0.85, 0.90],
                soul_hash_current="0ecf9dec", observed_at=now
            )
        ),
        "overclaimer": (
            GenesisDeclaration(
                "boastful", "corp_a", "gpt4", "aws", "abc123",
                {"search", "trade", "analyze", "deploy", "monitor"}, now - timedelta(days=30)
            ),
            BehavioralEvidence(
                "boastful", {"search", "analyze"},  # only 2 of 5 declared
                correction_count=0, total_actions=80,
                counterparty_grades=[0.45, 0.50],
                soul_hash_current="abc123", observed_at=now
            )
        ),
        "shadow_behavior": (
            GenesisDeclaration(
                "sneaky", "corp_b", "claude", "gcp", "def456",
                {"post", "comment"}, now - timedelta(days=20)
            ),
            BehavioralEvidence(
                "sneaky", {"post", "comment", "scrape", "exfiltrate"},  # 2 undeclared
                correction_count=1, total_actions=200,
                counterparty_grades=[0.30, 0.25],
                soul_hash_current="def456", observed_at=now
            )
        ),
        "no_genesis": (
            None,
            BehavioralEvidence(
                "ghost", {"post"},
                correction_count=5, total_actions=50,
                counterparty_grades=[0.60],
                soul_hash_current="???", observed_at=now
            )
        ),
        "soul_drifted": (
            GenesisDeclaration(
                "migrated", "corp_c", "claude-opus-4-5", "hetzner", "old_hash",
                {"attest", "verify"}, now - timedelta(days=60)
            ),
            BehavioralEvidence(
                "migrated", {"attest", "verify"},
                correction_count=8, total_actions=100,
                counterparty_grades=[0.75, 0.80],
                soul_hash_current="new_hash", observed_at=now  # model migration
            )
        ),
    }
    
    for name, (genesis, evidence) in scenarios.items():
        result = validate(genesis, evidence)
        print(f"\n{'='*55}")
        print(f"Agent: {name}")
        print(f"Upstream:   {result.upstream_grade} | Downstream: {result.downstream_grade}")
        print(f"Loop:       {'CLOSED' if result.loop_closed else 'OPEN'} | Verdict: {result.verdict}")
        print(f"Corrections: {result.correction_rate:.2f} | Counterparty: {result.counterparty_mean:.2f}")
        if result.overclaims:
            print(f"Overclaims: {result.overclaims}")
        if result.underclaims:
            print(f"Underclaims: {result.underclaims}")
        if result.soul_drift:
            print(f"Soul drift: YES")
        if result.issues:
            for issue in result.issues:
                print(f"  ⚠ {issue}")


if __name__ == "__main__":
    demo()
