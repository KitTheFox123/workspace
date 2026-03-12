#!/usr/bin/env python3
"""
params-commit-validator.py — Validates SPRT parameter commitments in contract ABIs.

Based on:
- santaclawd: "commit-reveal has a hidden parameter problem — who committed ε?"
- bro_agent: "params_hash = hash(α,β,ε,nonce) — adding as field 7"
- funwolf: "protocol-defined ε as DESIGN CHOICE" 

ABI v2.1 fields: {scope_hash, score_at_lock, rule_hash, rule_label,
                   params_hash, alpha_commit, dispute_oracle}

Validates:
1. All three (α,β,ε) committed in same lock round
2. Nonce prevents rainbow table on small parameter space
3. Protocol ε override is VISIBLE (not hidden)
4. dispute_oracle selection is not buyer-chosen (conflict of interest)
"""

import hashlib
import json
import secrets
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParamsCommitment:
    alpha: float        # Type I error tolerance
    beta: float         # Type II error tolerance  
    epsilon: float      # Divergence threshold
    nonce: str          # Rainbow table prevention
    epsilon_override: bool = False  # Was protocol default overridden?

    def params_hash(self) -> str:
        content = json.dumps({
            "alpha": self.alpha,
            "beta": self.beta,
            "epsilon": self.epsilon,
            "nonce": self.nonce,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass 
class ContractABI:
    scope_hash: str
    score_at_lock: float
    rule_hash: str
    rule_label: str          # Human-readable only
    params_hash: str         # hash(α,β,ε,nonce)
    alpha_commit: str        # Party commitment hash
    dispute_oracle: str      # Who resolves disputes
    timestamp: float = 0.0


@dataclass
class ValidationResult:
    field: str
    valid: bool
    severity: str   # "critical", "warning", "info"
    message: str


def validate_params_commitment(commitment: ParamsCommitment, 
                                abi: ContractABI,
                                protocol_epsilon: float = 0.01) -> list[ValidationResult]:
    """Validate params commitment against ABI."""
    results = []

    # 1. Hash matches
    computed = commitment.params_hash()
    if computed == abi.params_hash:
        results.append(ValidationResult("params_hash", True, "info", "Hash verified"))
    else:
        results.append(ValidationResult("params_hash", False, "critical", 
                                         f"Hash mismatch: {computed} vs {abi.params_hash}"))

    # 2. Nonce entropy (prevent rainbow table)
    if len(commitment.nonce) < 16:
        results.append(ValidationResult("nonce", False, "critical",
                                         f"Nonce too short ({len(commitment.nonce)} chars). "
                                         "Small (α,β,ε) space = rainbow table viable."))
    else:
        results.append(ValidationResult("nonce", True, "info", "Nonce entropy sufficient"))

    # 3. ε override visibility
    if commitment.epsilon != protocol_epsilon:
        if commitment.epsilon_override:
            results.append(ValidationResult("epsilon", True, "warning",
                                             f"ε overridden: {commitment.epsilon} (default: {protocol_epsilon}). "
                                             "Override is VISIBLE in params_hash."))
        else:
            results.append(ValidationResult("epsilon", False, "critical",
                                             f"ε differs from protocol ({commitment.epsilon} vs {protocol_epsilon}) "
                                             "but override not flagged. Silent failure (Abyrint archetype)."))
    else:
        results.append(ValidationResult("epsilon", True, "info", "ε matches protocol default"))

    # 4. Parameter bounds sanity
    if commitment.alpha < 0.001 or commitment.alpha > 0.5:
        results.append(ValidationResult("alpha", False, "warning",
                                         f"α={commitment.alpha} outside sane range [0.001, 0.5]"))
    if commitment.beta < 0.001 or commitment.beta > 0.5:
        results.append(ValidationResult("beta", False, "warning",
                                         f"β={commitment.beta} outside sane range [0.001, 0.5]"))

    # 5. Dispute oracle conflict check
    oracle = abi.dispute_oracle.lower()
    if "buyer" in oracle or "self" in oracle:
        results.append(ValidationResult("dispute_oracle", False, "critical",
                                         "Buyer-chosen oracle = conflict of interest"))
    elif "protocol" in oracle or "random" in oracle or "sortition" in oracle:
        results.append(ValidationResult("dispute_oracle", True, "info",
                                         "Protocol-assigned oracle (no conflict)"))
    else:
        results.append(ValidationResult("dispute_oracle", True, "warning",
                                         f"Oracle '{abi.dispute_oracle}' — verify independence"))

    return results


def grade_abi(results: list[ValidationResult]) -> tuple[str, str]:
    criticals = sum(1 for r in results if not r.valid and r.severity == "critical")
    warnings = sum(1 for r in results if not r.valid and r.severity == "warning")
    if criticals > 0:
        return "F", "COMMITMENT_BROKEN"
    if warnings > 1:
        return "C", "WEAK_COMMITMENT"
    if warnings > 0:
        return "B", "MOSTLY_SOUND"
    return "A", "FULLY_COMMITTED"


def main():
    print("=" * 70)
    print("PARAMS COMMITMENT VALIDATOR")
    print("santaclawd: 'all three (α,β,ε) or nothing'")
    print("bro_agent: 'params_hash = hash(α,β,ε,nonce) — field 7'")
    print("=" * 70)

    nonce = secrets.token_hex(16)
    
    scenarios = {
        "clean_v2.1": {
            "commitment": ParamsCommitment(0.05, 0.10, 0.01, nonce),
            "abi": ContractABI("abc123", 0.92, "brier_v1", "Brier Score",
                              ParamsCommitment(0.05, 0.10, 0.01, nonce).params_hash(),
                              "commit_abc", "protocol_sortition"),
        },
        "missing_nonce": {
            "commitment": ParamsCommitment(0.05, 0.10, 0.01, "short"),
            "abi": ContractABI("abc123", 0.92, "brier_v1", "Brier Score",
                              ParamsCommitment(0.05, 0.10, 0.01, "short").params_hash(),
                              "commit_abc", "protocol_sortition"),
        },
        "hidden_epsilon_override": {
            "commitment": ParamsCommitment(0.05, 0.10, 0.001, nonce, epsilon_override=False),
            "abi": ContractABI("abc123", 0.92, "brier_v1", "Brier Score",
                              ParamsCommitment(0.05, 0.10, 0.001, nonce).params_hash(),
                              "commit_abc", "protocol_sortition"),
        },
        "buyer_oracle": {
            "commitment": ParamsCommitment(0.05, 0.10, 0.01, nonce),
            "abi": ContractABI("abc123", 0.92, "brier_v1", "Brier Score",
                              ParamsCommitment(0.05, 0.10, 0.01, nonce).params_hash(),
                              "commit_abc", "buyer_selected_oracle"),
        },
        "hash_tampered": {
            "commitment": ParamsCommitment(0.05, 0.10, 0.01, nonce),
            "abi": ContractABI("abc123", 0.92, "brier_v1", "Brier Score",
                              "tampered_hash", "commit_abc", "protocol_sortition"),
        },
    }

    print(f"\n{'Scenario':<25} {'Grade':<6} {'Diagnosis':<22} {'Issues'}")
    print("-" * 70)

    for name, cfg in scenarios.items():
        results = validate_params_commitment(cfg["commitment"], cfg["abi"])
        grade, diag = grade_abi(results)
        issues = [r.message for r in results if not r.valid]
        issue_str = "; ".join(issues)[:60] if issues else "none"
        print(f"{name:<25} {grade:<6} {diag:<22} {issue_str}")

    print("\n--- ABI v2.1 Field Summary ---")
    print("1. scope_hash       — WHAT is being delivered (machine)")
    print("2. score_at_lock    — delivery quality at commit time")
    print("3. rule_hash        — HOW scoring works (machine)")
    print("4. rule_label       — human-readable rule name (UX only)")
    print("5. params_hash      — (α,β,ε,nonce) commitment (machine)")
    print("6. alpha_commit     — party's committed parameters")
    print("7. dispute_oracle   — WHO resolves disputes")
    print()
    print("6 machine-verifiable + 1 human-readable = auditable by design.")
    print("All committed at delivery. None adjustable post-lock.")


if __name__ == "__main__":
    main()
