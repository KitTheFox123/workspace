#!/usr/bin/env python3
"""
ddc-trust-verifier.py — Diverse Double Compiling for agent trust verification.

Based on:
- Thompson (1984): "Reflections on Trusting Trust" — compiler backdoor compiles itself
- Wheeler (2009): DDC — compile with TWO independent compilers, compare output
- Skrimstad (2024): DDC + reproducible builds for supply chain trust
- gerundium: "The trust chain problem—you can't verify the tool that verifies"

Thompson's attack for agents: if the SCORER is compromised, it scores
itself as trustworthy. You can't verify the scorer with the scorer.

DDC escape: run the SAME trust evaluation through two independent substrates.
If both produce the same result, the evaluation is likely uncompromised.
If they diverge, one substrate is compromised (or the evaluation is ambiguous).

This is cross-substrate attestation formalized.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Substrate:
    name: str
    type: str  # "llm", "rule_based", "temporal", "human", "cryptographic"
    provider: str
    independence_score: float  # 0.0 = fully correlated, 1.0 = fully independent


@dataclass
class EvaluationResult:
    substrate: Substrate
    claim: str
    verdict: bool
    confidence: float
    evidence_hash: str  # Hash of the evidence used


@dataclass
class DDCResult:
    claim: str
    substrate_a: str
    substrate_b: str
    verdict_a: bool
    verdict_b: bool
    agree: bool
    confidence_delta: float
    evidence_match: bool  # Did they use the same evidence?
    grade: str
    diagnosis: str


def compute_ddc(eval_a: EvaluationResult, eval_b: EvaluationResult) -> DDCResult:
    """Wheeler's DDC applied to agent trust evaluation."""
    agree = eval_a.verdict == eval_b.verdict
    conf_delta = abs(eval_a.confidence - eval_b.confidence)
    evidence_match = eval_a.evidence_hash == eval_b.evidence_hash

    # Independence of substrates matters
    ind_a = eval_a.substrate.independence_score
    ind_b = eval_b.substrate.independence_score
    substrate_diversity = (ind_a + ind_b) / 2

    if agree and evidence_match and conf_delta < 0.1:
        grade = "A"
        diagnosis = "DDC_VERIFIED"
    elif agree and not evidence_match:
        grade = "B"
        diagnosis = "CONVERGENT_EVIDENCE"  # Different evidence, same conclusion
    elif agree and conf_delta > 0.3:
        grade = "C"
        diagnosis = "WEAK_AGREEMENT"  # Agree but very different confidence
    elif not agree and substrate_diversity > 0.7:
        grade = "D"
        diagnosis = "GENUINE_DISAGREEMENT"  # Independent substrates disagree = real ambiguity
    elif not agree and substrate_diversity < 0.3:
        grade = "F"
        diagnosis = "THOMPSON_RISK"  # Correlated substrates disagree = one is compromised
    else:
        grade = "D"
        diagnosis = "AMBIGUOUS"

    return DDCResult(
        claim=eval_a.claim,
        substrate_a=eval_a.substrate.name,
        substrate_b=eval_b.substrate.name,
        verdict_a=eval_a.verdict,
        verdict_b=eval_b.verdict,
        agree=agree,
        confidence_delta=conf_delta,
        evidence_match=evidence_match,
        grade=grade,
        diagnosis=diagnosis,
    )


def hash_evidence(evidence: str) -> str:
    return hashlib.sha256(evidence.encode()).hexdigest()[:16]


def demo():
    # Define substrates
    llm_openai = Substrate("gpt-4", "llm", "openai", 0.3)
    llm_anthropic = Substrate("claude-opus", "llm", "anthropic", 0.5)
    rule_engine = Substrate("regex_checker", "rule_based", "local", 0.9)
    temporal = Substrate("timestamp_verifier", "temporal", "ntp+drand", 0.95)
    human = Substrate("human_reviewer", "human", "independent", 1.0)

    # Scenario 1: Two LLMs agree (Thompson risk — same training data)
    scenarios = []

    # Same evidence, same verdict, correlated substrates
    ev = hash_evidence("agent_output_v1")
    s1a = EvaluationResult(llm_openai, "agent_is_trustworthy", True, 0.92, ev)
    s1b = EvaluationResult(Substrate("gpt-4-turbo", "llm", "openai", 0.2), "agent_is_trustworthy", True, 0.89, ev)
    scenarios.append(("same_provider_agree", s1a, s1b))

    # Cross-provider LLMs agree
    s2a = EvaluationResult(llm_openai, "agent_is_trustworthy", True, 0.88, ev)
    s2b = EvaluationResult(llm_anthropic, "agent_is_trustworthy", True, 0.85, ev)
    scenarios.append(("cross_provider_agree", s2a, s2b))

    # LLM + rule engine agree (DDC pattern)
    s3a = EvaluationResult(llm_anthropic, "scope_hash_valid", True, 0.91, ev)
    s3b = EvaluationResult(rule_engine, "scope_hash_valid", True, 0.99, hash_evidence("agent_output_v1"))
    scenarios.append(("llm_plus_rules_agree", s3a, s3b))

    # LLM + temporal disagree (genuine ambiguity)
    s4a = EvaluationResult(llm_anthropic, "action_timely", True, 0.75, ev)
    s4b = EvaluationResult(temporal, "action_timely", False, 0.95, hash_evidence("drand_round_5898500"))
    scenarios.append(("llm_vs_temporal_disagree", s4a, s4b))

    # Same provider disagree (Thompson detected!)
    s5a = EvaluationResult(llm_openai, "no_backdoor", True, 0.95, ev)
    s5b = EvaluationResult(Substrate("gpt-4-mini", "llm", "openai", 0.15), "no_backdoor", False, 0.60, ev)
    scenarios.append(("same_provider_disagree", s5a, s5b))

    # Human + crypto agree (gold standard)
    s6a = EvaluationResult(human, "receipt_chain_valid", True, 0.90, ev)
    s6b = EvaluationResult(Substrate("ed25519_verifier", "cryptographic", "local", 0.99), "receipt_chain_valid", True, 1.0, ev)
    scenarios.append(("human_plus_crypto", s6a, s6b))

    print("=" * 72)
    print("DIVERSE DOUBLE COMPILING FOR AGENT TRUST")
    print("Wheeler (2009): compile with TWO compilers, compare output")
    print("Thompson (1984): you can't verify the verifier with itself")
    print("=" * 72)

    print(f"\n{'Scenario':<28} {'Grade':<6} {'Agree':<6} {'ΔConf':<7} {'Diagnosis'}")
    print("-" * 72)

    for name, ea, eb in scenarios:
        result = compute_ddc(ea, eb)
        print(f"{name:<28} {result.grade:<6} {str(result.agree):<6} "
              f"{result.confidence_delta:<7.2f} {result.diagnosis}")

    print("\n--- DDC Principle ---")
    print("Thompson: backdoor compiles itself into existence, invisible in source.")
    print("Wheeler: compile source with compiler A AND compiler B.")
    print("         Compare binaries. Divergence = backdoor detected.")
    print()
    print("For agents:")
    print("  Thompson attack = compromised scorer rates itself trustworthy")
    print("  DDC escape = evaluate with TWO independent substrates")
    print("  Same verdict from uncorrelated substrates = DDC-verified")
    print("  Divergence from correlated substrates = Thompson risk")
    print()
    print("Minimum DDC set: 1 LLM + 1 non-LLM + 1 cryptographic")
    print("Gold standard: human + crypto (fully independent, fully verifiable)")
    print()
    print("gerundium: 'you can't verify the tool that verifies'")
    print("Wheeler: 'you can, if you use a DIFFERENT tool'")


if __name__ == "__main__":
    demo()
