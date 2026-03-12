#!/usr/bin/env python3
"""
scoring-rule-versioner.py — Immutable scoring rule versioning for escrow contracts.

Based on:
- santaclawd: "scoring_rule_version missing from every escrow ABI"
- EIP-2535 Diamond proxy: logic upgrades, storage stays on locked version
- integer-brier-scorer.py: rule_hash = version

The problem: scoring rule drifts between contract lock and evaluation.
Two parties scored under different versions = unresolvable dispute.

Fix: rule_version_hash on-chain at lock time. Arbiter evaluates at locked version ALWAYS.
Old contracts fork to old rules. New contracts use new rules. Never mix.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScoringRule:
    name: str
    version: str
    logic_hash: str  # Hash of actual scoring code/bytecode
    params: dict = field(default_factory=dict)
    
    def version_hash(self) -> str:
        content = json.dumps({
            "name": self.name,
            "version": self.version,
            "logic_hash": self.logic_hash,
            "params": self.params,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass 
class LockedContract:
    contract_id: str
    rule_version_hash: str  # Immutable at lock time
    locked_at: str
    scoring_mode: str = "DETERMINISTIC"  # or "FLOAT"
    
    def evaluate(self, rule_registry: dict, score_bp: int) -> dict:
        """Evaluate using LOCKED version only."""
        if self.rule_version_hash not in rule_registry:
            return {"error": "RULE_VERSION_NOT_FOUND", "grade": "F"}
        
        rule = rule_registry[self.rule_version_hash]
        return {
            "contract": self.contract_id,
            "rule_used": f"{rule.name}@{rule.version}",
            "rule_hash": self.rule_version_hash,
            "score_bp": score_bp,
            "grade": "A" if score_bp >= 8000 else "B" if score_bp >= 6000 else "C",
        }


@dataclass
class RuleUpgrade:
    old_version_hash: str
    new_version_hash: str
    migration_type: str  # "fork" or "upgrade"
    affects_locked: bool  # Should NEVER be True
    
    def is_safe(self) -> tuple[bool, str]:
        if self.affects_locked:
            return False, "UNSAFE: locked contracts must use locked version"
        if self.migration_type == "fork":
            return True, "SAFE: old contracts stay on old rules"
        if self.migration_type == "upgrade":
            return True, "SAFE: only new contracts use new rules"
        return False, "UNKNOWN migration type"


def main():
    print("=" * 70)
    print("SCORING RULE VERSIONER")
    print("santaclawd: 'scoring_rule_version missing from every escrow ABI'")
    print("=" * 70)
    
    # Create rule versions
    brier_v1 = ScoringRule("brier_score", "1.0.0", "abc123def", {"scale": "bp", "mode": "integer"})
    brier_v2 = ScoringRule("brier_score", "2.0.0", "xyz789ghi", {"scale": "bp", "mode": "integer", "decomposition": True})
    
    # Registry keyed by version_hash
    registry = {
        brier_v1.version_hash(): brier_v1,
        brier_v2.version_hash(): brier_v2,
    }
    
    print(f"\n--- Rule Versions ---")
    print(f"v1.0.0 hash: {brier_v1.version_hash()}")
    print(f"v2.0.0 hash: {brier_v2.version_hash()}")
    
    # Lock contracts at different versions
    contract_old = LockedContract("TC4", brier_v1.version_hash(), "2026-02-24")
    contract_new = LockedContract("TC5", brier_v2.version_hash(), "2026-03-04")
    
    print(f"\n--- Contract Evaluation ---")
    result_old = contract_old.evaluate(registry, 9200)
    result_new = contract_new.evaluate(registry, 9200)
    print(f"TC4 (locked at v1): {result_old['rule_used']}, grade={result_old['grade']}")
    print(f"TC5 (locked at v2): {result_new['rule_used']}, grade={result_new['grade']}")
    
    # Upgrade safety check
    print(f"\n--- Upgrade Safety ---")
    upgrades = [
        RuleUpgrade(brier_v1.version_hash(), brier_v2.version_hash(), "fork", False),
        RuleUpgrade(brier_v1.version_hash(), brier_v2.version_hash(), "upgrade", False),
        RuleUpgrade(brier_v1.version_hash(), brier_v2.version_hash(), "upgrade", True),  # UNSAFE
    ]
    for u in upgrades:
        safe, msg = u.is_safe()
        print(f"  {u.migration_type} (affects_locked={u.affects_locked}): {msg}")
    
    # ABI v2.2 field spec
    print(f"\n--- PayLock ABI v2.2 Addition ---")
    print("rule_version_hash: bytes16  // Hash of scoring rule at lock time")
    print("scoring_mode:      uint8    // 0=DETERMINISTIC (integer), 1=FLOAT")
    print("rule_name:         string   // Human-readable label (UX only)")
    print()
    print("Invariant: evaluate(contract) ALWAYS uses rule at rule_version_hash.")
    print("Rule upgrades = fork. Old contracts = old rules. Always.")
    print()
    print("Pattern: EIP-2535 Diamond Proxy")
    print("  - Logic facets can upgrade (new scoring rules)")
    print("  - Storage (locked contracts) references immutable facet hash")
    print("  - Arbiter resolves at locked version, never current")
    
    # The version IS the hash
    print(f"\n--- Key Insight ---")
    print("santaclawd: 'if the scoring RULE drifts, unresolvable dispute'")
    print()
    print("The version IS the hash. Not a semver string — a content hash.")
    print("Same code = same hash = same version. Different code = different hash.")
    print("No ambiguity. No 'compatible upgrade' disputes.")
    print("integer-brier-scorer.py already does this: rule_hash = version.")


if __name__ == "__main__":
    main()
