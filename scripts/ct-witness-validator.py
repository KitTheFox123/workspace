#!/usr/bin/env python3
"""
ct-witness-validator.py — Certificate Transparency witness validation for L3.5.

Per santaclawd's sharp question: "1 witness = escrow with extra steps, not CT."
Real CT requires N independent log operators + public verifiability.

Rule: 1 witness = testimony (1x), 2 = corroboration (1.5x), 3+ = observation (2x).
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class EpistemicClass(Enum):
    TESTIMONY = "testimony"        # 1 witness, weight 1.0x
    CORROBORATION = "corroboration"  # 2 witnesses, weight 1.5x
    OBSERVATION = "observation"      # 3+ witnesses, weight 2.0x


EPISTEMIC_WEIGHTS = {
    EpistemicClass.TESTIMONY: 1.0,
    EpistemicClass.CORROBORATION: 1.5,
    EpistemicClass.OBSERVATION: 2.0,
}


@dataclass
class WitnessSignature:
    operator_id: str
    operator_domain: str  # Must be different domains for independence
    signature: str
    timestamp: str
    log_index: int


@dataclass 
class WitnessedReceipt:
    receipt_hash: str
    witnesses: list[WitnessSignature] = field(default_factory=list)
    
    @property
    def unique_operators(self) -> set[str]:
        return {w.operator_domain for w in self.witnesses}
    
    @property
    def witness_count(self) -> int:
        return len(self.unique_operators)
    
    @property
    def epistemic_class(self) -> EpistemicClass:
        n = self.witness_count
        if n >= 3:
            return EpistemicClass.OBSERVATION
        elif n == 2:
            return EpistemicClass.CORROBORATION
        else:
            return EpistemicClass.TESTIMONY
    
    @property
    def epistemic_weight(self) -> float:
        return EPISTEMIC_WEIGHTS[self.epistemic_class]
    
    def validate(self) -> dict:
        """Validate witness independence and consistency."""
        issues = []
        
        # Check: all witnesses signed same hash
        # (In production: verify actual signatures)
        
        # Check: operator independence (different domains)
        domains = [w.operator_domain for w in self.witnesses]
        if len(domains) != len(set(domains)):
            dupes = [d for d in set(domains) if domains.count(d) > 1]
            issues.append(f"duplicate_operators: {dupes}")
        
        # Check: temporal consistency (witnesses within 60s of each other)
        if len(self.witnesses) >= 2:
            timestamps = []
            for w in self.witnesses:
                try:
                    ts = datetime.fromisoformat(w.timestamp.replace('Z', '+00:00'))
                    timestamps.append(ts)
                except ValueError:
                    issues.append(f"invalid_timestamp: {w.operator_id}")
            
            if len(timestamps) >= 2:
                spread = (max(timestamps) - min(timestamps)).total_seconds()
                if spread > 60:
                    issues.append(f"temporal_spread: {spread:.0f}s (max 60s)")
        
        # Check: minimum for observation class
        if self.witness_count < 2:
            issues.append("below_minimum: need 2+ independent witnesses for corroboration")
        
        return {
            "valid": len(issues) == 0,
            "witness_count": self.witness_count,
            "unique_operators": sorted(self.unique_operators),
            "epistemic_class": self.epistemic_class.value,
            "epistemic_weight": self.epistemic_weight,
            "issues": issues,
        }


def demo():
    print("=== CT Witness Validator ===\n")
    
    now = datetime.now(timezone.utc).isoformat()
    receipt_hash = hashlib.sha256(b"test-receipt-data").hexdigest()[:16]
    
    scenarios = [
        {
            "name": "Single witness (testimony)",
            "witnesses": [
                WitnessSignature("log1", "witness-a.example", "sig1", now, 1),
            ],
        },
        {
            "name": "Two independent witnesses (corroboration)",
            "witnesses": [
                WitnessSignature("log1", "witness-a.example", "sig1", now, 1),
                WitnessSignature("log2", "witness-b.example", "sig2", now, 2),
            ],
        },
        {
            "name": "Three independent witnesses (observation)",
            "witnesses": [
                WitnessSignature("log1", "witness-a.example", "sig1", now, 1),
                WitnessSignature("log2", "witness-b.example", "sig2", now, 2),
                WitnessSignature("log3", "witness-c.example", "sig3", now, 3),
            ],
        },
        {
            "name": "Fake diversity (same operator, different IDs)",
            "witnesses": [
                WitnessSignature("log1", "witness-a.example", "sig1", now, 1),
                WitnessSignature("log2", "witness-a.example", "sig2", now, 2),
                WitnessSignature("log3", "witness-a.example", "sig3", now, 3),
            ],
        },
    ]
    
    for s in scenarios:
        receipt = WitnessedReceipt(receipt_hash=receipt_hash, witnesses=s["witnesses"])
        result = receipt.validate()
        
        status = "✅" if result["valid"] else "❌"
        print(f"{status} {s['name']}")
        print(f"   Witnesses: {result['witness_count']} unique operators")
        print(f"   Class: {result['epistemic_class']} ({result['epistemic_weight']}x weight)")
        if result["issues"]:
            print(f"   Issues: {', '.join(result['issues'])}")
        print()
    
    print("--- Design Principle ---")
    print("1 witness = testimony (someone said so)")
    print("2 witnesses = corroboration (two independent parties agree)")
    print("3+ witnesses = observation (CT-style public verifiability)")
    print()
    print("Per santaclawd: '1 designated party = escrow with extra steps, not CT.'")
    print("Real CT = multiple independent log operators + public audit.")


if __name__ == "__main__":
    demo()
