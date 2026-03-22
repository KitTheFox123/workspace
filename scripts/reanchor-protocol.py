#!/usr/bin/env python3
"""
reanchor-protocol.py — Quorum reanchor after independence breach.

Per quorum: "what does reanchor look like operationally?"
Answer: new genesis commit with fresh oracle set. NOT remediation from existing.

Steps:
1. Any counterparty detects Gini breach → HALT signal
2. Collect breach evidence (which dimension, which signers correlated)
3. Generate new oracle set with independence audit
4. New genesis commit → fresh registry_hash
5. Existing receipts remain valid under old version
6. New receipts require new genesis attestation
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import Counter
from typing import Optional


@dataclass
class Oracle:
    id: str
    operator: str
    model_family: str
    infrastructure: str
    region: str


@dataclass
class BreachEvidence:
    dimension: str  # operator, model, infrastructure
    concentrated_value: str
    count: int
    total: int
    gini: float
    detected_by: str  # counterparty who detected
    detected_at: datetime


@dataclass
class ReanchorProtocol:
    old_oracles: list[Oracle]
    breach: BreachEvidence
    
    def diagnose(self) -> dict:
        """Identify which oracles must be replaced."""
        compromised = []
        retained = []
        
        for oracle in self.old_oracles:
            val = getattr(oracle, self.breach.dimension)
            if val == self.breach.concentrated_value:
                compromised.append(oracle)
            else:
                retained.append(oracle)
        
        return {
            "compromised": [o.id for o in compromised],
            "retained": [o.id for o in retained],
            "replacement_needed": len(compromised),
            "breach_dimension": self.breach.dimension,
            "breach_value": self.breach.concentrated_value,
        }
    
    def validate_replacement_set(self, new_oracles: list[Oracle]) -> dict:
        """Validate that replacement oracles fix the breach."""
        all_oracles = []
        diagnosis = self.diagnose()
        
        # Keep retained oracles + add new ones
        for o in self.old_oracles:
            if o.id in diagnosis["retained"]:
                all_oracles.append(o)
        all_oracles.extend(new_oracles)
        
        n = len(all_oracles)
        issues = []
        
        # Check all 4 dimensions
        for dim in ["operator", "model_family", "infrastructure", "region"]:
            values = [getattr(o, dim) for o in all_oracles]
            counts = Counter(values)
            max_count = max(counts.values())
            max_val = counts.most_common(1)[0][0]
            
            # Gini coefficient (simplified)
            sorted_counts = sorted(counts.values())
            cumulative = []
            running = 0
            for c in sorted_counts:
                running += c
                cumulative.append(running)
            n_vals = len(sorted_counts)
            if n_vals > 1 and running > 0:
                gini = 1 - 2 * sum(cumulative) / (n_vals * running) + 1/n_vals
            else:
                gini = 1.0
            
            if max_count > n / 3:
                issues.append({
                    "dimension": dim,
                    "value": max_val,
                    "count": max_count,
                    "gini": round(gini, 3),
                    "severity": "CRITICAL" if max_count > n * 2/3 else "WARNING"
                })
        
        # Generate new genesis hash
        oracle_data = sorted([f"{o.id}:{o.operator}:{o.model_family}:{o.infrastructure}:{o.region}" for o in all_oracles])
        genesis_hash = hashlib.sha256("\n".join(oracle_data).encode()).hexdigest()[:16]
        
        breach_fixed = not any(i["dimension"] == self.breach.dimension for i in issues)
        new_breaches = [i for i in issues if i["dimension"] != self.breach.dimension]
        
        verdict = "REANCHOR_VALID" if not issues else "BREACH_FIXED_NEW_ISSUES" if breach_fixed and new_breaches else "BREACH_NOT_FIXED"
        
        return {
            "verdict": verdict,
            "total_oracles": n,
            "retained": len(diagnosis["retained"]),
            "replaced": len(new_oracles),
            "genesis_hash": genesis_hash,
            "breach_fixed": breach_fixed,
            "remaining_issues": issues,
            "action": "COMMIT" if verdict == "REANCHOR_VALID" else "REVISE" if breach_fixed else "REJECT"
        }


def demo():
    now = datetime(2026, 3, 22, 3, 42, 0)
    
    # Original quorum with operator monoculture
    old_oracles = [
        Oracle("o1", "acme_corp", "claude", "aws", "us-east"),
        Oracle("o2", "acme_corp", "claude", "aws", "us-east"),
        Oracle("o3", "acme_corp", "gpt4", "gcp", "eu-west"),
        Oracle("o4", "beta_inc", "claude", "aws", "us-east"),
        Oracle("o5", "acme_corp", "gemini", "azure", "ap-south"),
    ]
    
    breach = BreachEvidence(
        dimension="operator",
        concentrated_value="acme_corp",
        count=4, total=5, gini=0.84,
        detected_by="kit_fox",
        detected_at=now
    )
    
    protocol = ReanchorProtocol(old_oracles, breach)
    
    # Diagnose
    diagnosis = protocol.diagnose()
    print("=== DIAGNOSIS ===")
    print(f"Compromised: {diagnosis['compromised']}")
    print(f"Retained: {diagnosis['retained']}")
    print(f"Replacements needed: {diagnosis['replacement_needed']}")
    
    # Attempt 1: Bad replacement (still concentrated)
    bad_replacements = [
        Oracle("o6", "gamma_llc", "claude", "aws", "us-east"),
        Oracle("o7", "gamma_llc", "claude", "aws", "us-east"),
        Oracle("o8", "gamma_llc", "gpt4", "aws", "us-east"),
        Oracle("o9", "gamma_llc", "claude", "aws", "us-east"),
    ]
    
    result1 = protocol.validate_replacement_set(bad_replacements)
    print(f"\n=== BAD REPLACEMENT ===")
    print(f"Verdict: {result1['verdict']} | Action: {result1['action']}")
    print(f"Breach fixed: {result1['breach_fixed']}")
    for issue in result1['remaining_issues']:
        print(f"  [{issue['severity']}] {issue['dimension']}={issue['value']} ({issue['count']}/{result1['total_oracles']})")
    
    # Attempt 2: Good replacement (diverse)
    good_replacements = [
        Oracle("o6", "gamma_llc", "mistral", "hetzner", "eu-central"),
        Oracle("o7", "delta_co", "llama", "ovh", "ap-south"),
        Oracle("o8", "epsilon", "gemini", "azure", "us-west"),
        Oracle("o9", "zeta_ai", "qwen", "alibaba", "ap-east"),
    ]
    
    result2 = protocol.validate_replacement_set(good_replacements)
    print(f"\n=== GOOD REPLACEMENT ===")
    print(f"Verdict: {result2['verdict']} | Action: {result2['action']}")
    print(f"Genesis hash: {result2['genesis_hash']}")
    print(f"Oracles: {result2['total_oracles']} ({result2['retained']} retained + {result2['replaced']} new)")
    if result2['remaining_issues']:
        for issue in result2['remaining_issues']:
            print(f"  [{issue['severity']}] {issue['dimension']}={issue['value']}")
    else:
        print("  No independence issues. Ready to commit.")


if __name__ == "__main__":
    demo()
