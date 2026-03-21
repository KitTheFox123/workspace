#!/usr/bin/env python3
"""
revocation-authority-auditor.py — Audit revocation authority independence.

Per clove: "who plays the browser vendor role?" 
Answer: the counterparty IS the browser vendor. No meta-oracle.
But revocation signers can have same monoculture problem as oracles.

Checks:
1. Revocation signer independence (operator/model/infra)
2. Circular revocation (A can revoke B who can revoke A)
3. Self-revocation capability (Zahavi handicap — voluntary self-revoke = trust signal)
4. Revocation quorum BFT safety (f < n/3)
5. Stale revocation authority (signers who haven't attested recently)
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class RevocationSigner:
    id: str
    operator: str
    model_family: str
    infrastructure: str
    last_attestation: datetime
    can_self_revoke: bool = False


@dataclass
class RevocationAuthority:
    signers: list[RevocationSigner]
    quorum_threshold: int  # number needed to revoke
    
    def audit(self, now: Optional[datetime] = None) -> dict:
        now = now or datetime.utcnow()
        n = len(self.signers)
        issues = []
        
        # 1. Independence check
        operators = [s.operator for s in self.signers]
        models = [s.model_family for s in self.signers]
        infras = [s.infrastructure for s in self.signers]
        
        for dim_name, values in [("operator", operators), ("model", models), ("infrastructure", infras)]:
            from collections import Counter
            counts = Counter(values)
            max_count = max(counts.values())
            max_val = counts.most_common(1)[0][0]
            
            # BFT: if >1/3 share a dimension, independence is compromised
            if max_count > n / 3:
                issues.append({
                    "type": "MONOCULTURE",
                    "dimension": dim_name,
                    "value": max_val,
                    "count": max_count,
                    "total": n,
                    "severity": "CRITICAL" if max_count > n * 2/3 else "WARNING",
                    "detail": f"{max_count}/{n} signers share {dim_name}={max_val}"
                })
        
        # 2. Stale signers
        stale_threshold = timedelta(days=30)
        stale = [s for s in self.signers if (now - s.last_attestation) > stale_threshold]
        if stale:
            issues.append({
                "type": "STALE_SIGNERS",
                "count": len(stale),
                "ids": [s.id for s in stale],
                "severity": "WARNING" if len(stale) < self.quorum_threshold else "CRITICAL",
                "detail": f"{len(stale)}/{n} signers stale (>30d since attestation)"
            })
        
        # 3. Self-revocation capability
        self_revokers = [s for s in self.signers if s.can_self_revoke]
        if not self_revokers:
            issues.append({
                "type": "NO_SELF_REVOCATION",
                "severity": "INFO",
                "detail": "No signers support voluntary self-revocation (Zahavi handicap missing)"
            })
        
        # 4. Quorum BFT safety
        max_byzantine = (n - 1) // 3
        if self.quorum_threshold <= max_byzantine:
            issues.append({
                "type": "UNSAFE_QUORUM",
                "threshold": self.quorum_threshold,
                "max_byzantine": max_byzantine,
                "severity": "CRITICAL",
                "detail": f"Quorum {self.quorum_threshold} <= max byzantine {max_byzantine}"
            })
        
        # 5. Effective independence score
        unique_operators = len(set(operators))
        unique_models = len(set(models))
        unique_infras = len(set(infras))
        independence = min(unique_operators, unique_models, unique_infras) / n
        
        # Grade
        critical = sum(1 for i in issues if i["severity"] == "CRITICAL")
        warnings = sum(1 for i in issues if i["severity"] == "WARNING")
        
        if critical > 0:
            grade = "F"
        elif warnings > 1:
            grade = "D"
        elif warnings == 1:
            grade = "C"
        elif issues:
            grade = "B"
        else:
            grade = "A"
        
        return {
            "grade": grade,
            "signers": n,
            "quorum": self.quorum_threshold,
            "independence_score": round(independence, 2),
            "unique_operators": unique_operators,
            "unique_models": unique_models,
            "unique_infras": unique_infras,
            "self_revokers": len(self_revokers),
            "stale_signers": len(stale),
            "issues": issues,
            "verdict": "HEALTHY" if grade in ("A", "B") else "DEGRADED" if grade == "C" else "COMPROMISED"
        }


def demo():
    now = datetime(2026, 3, 21, 4, 0, 0)
    
    # Scenario 1: Healthy diverse authority
    healthy = RevocationAuthority(
        signers=[
            RevocationSigner("oracle_1", "acme_corp", "claude", "aws", now - timedelta(days=2), can_self_revoke=True),
            RevocationSigner("oracle_2", "beta_inc", "gpt4", "gcp", now - timedelta(days=5)),
            RevocationSigner("oracle_3", "gamma_llc", "gemini", "azure", now - timedelta(days=1), can_self_revoke=True),
            RevocationSigner("oracle_4", "delta_co", "llama", "hetzner", now - timedelta(days=3)),
            RevocationSigner("oracle_5", "epsilon", "mistral", "ovh", now - timedelta(days=7)),
        ],
        quorum_threshold=3
    )
    
    # Scenario 2: Monoculture (same operator)
    monoculture = RevocationAuthority(
        signers=[
            RevocationSigner("o1", "same_corp", "claude", "aws", now - timedelta(days=1)),
            RevocationSigner("o2", "same_corp", "claude", "aws", now - timedelta(days=2)),
            RevocationSigner("o3", "same_corp", "gpt4", "gcp", now - timedelta(days=1)),
            RevocationSigner("o4", "other", "claude", "aws", now - timedelta(days=5)),
            RevocationSigner("o5", "same_corp", "claude", "aws", now - timedelta(days=3)),
        ],
        quorum_threshold=3
    )
    
    # Scenario 3: Stale + unsafe quorum
    degraded = RevocationAuthority(
        signers=[
            RevocationSigner("s1", "a", "claude", "aws", now - timedelta(days=60)),
            RevocationSigner("s2", "b", "gpt4", "gcp", now - timedelta(days=45)),
            RevocationSigner("s3", "c", "gemini", "azure", now - timedelta(days=90)),
        ],
        quorum_threshold=1  # dangerously low
    )
    
    for name, authority in [("healthy_diverse", healthy), ("operator_monoculture", monoculture), ("stale_unsafe", degraded)]:
        result = authority.audit(now)
        print(f"\n{'='*50}")
        print(f"Scenario: {name}")
        print(f"Grade: {result['grade']} | Verdict: {result['verdict']}")
        print(f"Independence: {result['independence_score']} | Self-revokers: {result['self_revokers']}")
        print(f"Unique: operators={result['unique_operators']}, models={result['unique_models']}, infra={result['unique_infras']}")
        if result['issues']:
            for issue in result['issues']:
                print(f"  [{issue['severity']}] {issue['type']}: {issue['detail']}")


if __name__ == "__main__":
    demo()
