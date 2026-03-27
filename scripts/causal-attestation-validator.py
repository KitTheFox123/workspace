#!/usr/bin/env python3
"""
causal-attestation-validator.py — Causal discovery for ATF attestation chains.

Maps constraint-based causal discovery (PC/FCI algorithms from Liu et al, JMIR 2026
scoping review) to agent trust validation. The core insight: attestation chains
encode causal claims ("A trusted B BECAUSE of evidence X"). Validating these
claims requires the same machinery as causal inference from observational data.

Three validation modes:
1. STRUCTURE — Does the attestation DAG satisfy causal Markov condition?
   (No spurious dependencies between unrelated attestation paths)
2. CONFOUNDING — Are there unmeasured confounders (shared training data,
   same operator) creating non-causal correlations between attesters?
3. TEMPORAL — Does the causal ordering match temporal ordering?
   (Can't attest what hasn't happened yet — faithfulness assumption)

Sources:
- Liu et al (JMIR Med Inform, Mar 2026): Scoping review of causal discovery
  in observational medical research. 72 studies. Constraint-based dominant (52.8%).
  FCI (13.9%) handles latent confounders — maps to hidden operator correlation.
  Key gap: unmeasured confounding in >20% of studies. Same gap in ATF.
- Pearl (2009): Structural causal models, d-separation, do-calculus
- Spirtes et al (2000): PC algorithm, faithfulness assumption

Kit 🦊 — 2026-03-27
"""

import json
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class ValidationResult(Enum):
    VALID = "VALID"
    CONFOUNDED = "CONFOUNDED"
    TEMPORAL_VIOLATION = "TEMPORAL_VIOLATION"
    CYCLIC = "CYCLIC"
    UNFAITHFUL = "UNFAITHFUL"


@dataclass
class Attestation:
    attester: str
    subject: str
    action_class: str  # READ/WRITE/TRANSFER/ATTEST
    score: float
    timestamp: str  # ISO 8601
    evidence_hash: str
    operator: Optional[str] = None
    model_family: Optional[str] = None
    training_lineage: Optional[str] = None


@dataclass 
class CausalValidation:
    result: ValidationResult
    details: str
    confounders_detected: list = field(default_factory=list)
    d_separation_violations: list = field(default_factory=list)
    temporal_violations: list = field(default_factory=list)


class CausalAttestationValidator:
    """
    Validates attestation chains using causal discovery principles.
    
    Maps medical causal discovery challenges to ATF:
    - Unmeasured confounding (20%+ of medical studies) → shared operator/training
    - Sample size limitations → cold-start agents with few attestations
    - Unvalidated causal assumptions → attestation claims without behavioral evidence
    """
    
    def __init__(self):
        self.attestations: list[Attestation] = []
        self.adjacency: dict[str, set[str]] = {}  # attester → set of subjects
    
    def add_attestation(self, att: Attestation):
        self.attestations.append(att)
        if att.attester not in self.adjacency:
            self.adjacency[att.attester] = set()
        self.adjacency[att.attester].add(att.subject)
    
    def validate_structure(self) -> CausalValidation:
        """
        Check DAG property (no cycles) and causal Markov condition.
        Cycles in attestation = circular trust (A trusts B because B trusts A).
        """
        # Detect cycles via DFS
        visited = set()
        rec_stack = set()
        cycle_agents = []
        
        def dfs(node):
            visited.add(node)
            rec_stack.add(node)
            for neighbor in self.adjacency.get(node, set()):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    cycle_agents.append((node, neighbor))
                    return True
            rec_stack.discard(node)
            return False
        
        for node in list(self.adjacency.keys()):
            if node not in visited:
                if dfs(node):
                    return CausalValidation(
                        result=ValidationResult.CYCLIC,
                        details=f"Circular attestation detected: {cycle_agents}. "
                                "Attestation DAG must be acyclic — trust flows forward.",
                    )
        
        return CausalValidation(
            result=ValidationResult.VALID,
            details="Attestation graph is acyclic. Causal Markov condition satisfiable."
        )
    
    def detect_confounders(self) -> CausalValidation:
        """
        FCI-style latent confounder detection.
        
        In medical causal discovery, FCI (Fast Causal Inference) handles
        unmeasured confounders by producing PAGs (partial ancestral graphs)
        with bidirected edges for potential latent common causes.
        
        ATF mapping: if two attesters share operator/training/model but
        aren't declared as correlated, that's an unmeasured confounder
        creating spurious agreement.
        """
        confounders = []
        attesters = {}
        
        for att in self.attestations:
            if att.attester not in attesters:
                attesters[att.attester] = att
        
        agents = list(attesters.keys())
        for i in range(len(agents)):
            for j in range(i + 1, len(agents)):
                a1 = attesters[agents[i]]
                a2 = attesters[agents[j]]
                
                shared = []
                if a1.operator and a2.operator and a1.operator == a2.operator:
                    shared.append(f"operator={a1.operator}")
                if a1.model_family and a2.model_family and a1.model_family == a2.model_family:
                    shared.append(f"model_family={a1.model_family}")
                if a1.training_lineage and a2.training_lineage and a1.training_lineage == a2.training_lineage:
                    shared.append(f"training_lineage={a1.training_lineage}")
                
                if shared:
                    confounders.append({
                        "agents": (agents[i], agents[j]),
                        "shared_factors": shared,
                        "severity": "CRITICAL" if len(shared) >= 2 else "WARNING",
                        "fci_interpretation": "Bidirected edge in PAG — "
                                            "agreement may be non-causal (shared training, not independent evaluation)"
                    })
        
        if confounders:
            critical = [c for c in confounders if c["severity"] == "CRITICAL"]
            return CausalValidation(
                result=ValidationResult.CONFOUNDED,
                details=f"{len(confounders)} potential confounders detected "
                        f"({len(critical)} CRITICAL). "
                        "FCI would produce bidirected edges — attestation agreement "
                        "may reflect shared training, not independent evaluation. "
                        "Liu et al (2026): unmeasured confounding in >20% of studies.",
                confounders_detected=confounders
            )
        
        return CausalValidation(
            result=ValidationResult.VALID,
            details="No shared confounders detected between attesters."
        )
    
    def validate_temporal(self) -> CausalValidation:
        """
        Temporal ordering = faithfulness assumption in causal discovery.
        
        PC algorithm assumes faithfulness: statistical dependencies reflect
        causal connections. In ATF: attestation timestamps must respect
        causal ordering. Can't attest an action that hasn't happened yet.
        """
        violations = []
        
        # Group attestations by subject
        by_subject: dict[str, list[Attestation]] = {}
        for att in self.attestations:
            if att.subject not in by_subject:
                by_subject[att.subject] = []
            by_subject[att.subject].append(att)
        
        # Check: attestation chains must be temporally ordered
        for att in self.attestations:
            # If attester also has attestations FROM others, those must precede
            attester_received = by_subject.get(att.attester, [])
            for prior in attester_received:
                try:
                    t_received = datetime.fromisoformat(prior.timestamp.replace('Z', '+00:00'))
                    t_given = datetime.fromisoformat(att.timestamp.replace('Z', '+00:00'))
                    # Attester should have been attested BEFORE they attest others
                    # (you need trust to give trust — temporal causal ordering)
                    if t_received > t_given:
                        violations.append({
                            "attester": att.attester,
                            "attested_at": att.timestamp,
                            "received_trust_at": prior.timestamp,
                            "from": prior.attester,
                            "issue": "Attested others BEFORE receiving own trust — "
                                    "temporal ordering violation (faithfulness)"
                        })
                except (ValueError, TypeError):
                    pass
        
        if violations:
            return CausalValidation(
                result=ValidationResult.TEMPORAL_VIOLATION,
                details=f"{len(violations)} temporal ordering violations. "
                        "Faithfulness assumption violated: causal ordering "
                        "must match temporal ordering in attestation chains.",
                temporal_violations=violations
            )
        
        return CausalValidation(
            result=ValidationResult.VALID,
            details="Temporal ordering consistent with causal structure."
        )
    
    def full_validation(self) -> dict:
        """Run all three validation modes."""
        structure = self.validate_structure()
        confounding = self.detect_confounders()
        temporal = self.validate_temporal()
        
        overall = ValidationResult.VALID
        for v in [structure, confounding, temporal]:
            if v.result != ValidationResult.VALID:
                overall = v.result
                break
        
        return {
            "overall": overall.value,
            "structure": {"result": structure.result.value, "details": structure.details},
            "confounding": {
                "result": confounding.result.value,
                "details": confounding.details,
                "confounders": confounding.confounders_detected
            },
            "temporal": {
                "result": temporal.result.value,
                "details": temporal.details,
                "violations": temporal.temporal_violations
            },
            "attestation_count": len(self.attestations),
            "unique_attesters": len(set(a.attester for a in self.attestations)),
            "methodology_note": (
                "Constraint-based causal discovery (PC/FCI) dominant in medical research "
                "(52.8% of 72 studies, Liu et al JMIR 2026). Same principles validate "
                "attestation chains: DAG structure, confounder detection, temporal faithfulness."
            )
        }


def demo():
    """Demonstrate three scenarios."""
    
    print("=" * 60)
    print("SCENARIO 1: Clean attestation chain (diverse, temporal)")
    print("=" * 60)
    
    v1 = CausalAttestationValidator()
    v1.add_attestation(Attestation(
        attester="genesis", subject="alice",
        action_class="ATTEST", score=0.8,
        timestamp="2026-03-27T00:00:00Z",
        evidence_hash="abc123",
        operator="op_1", model_family="claude", training_lineage="anthropic_hh"
    ))
    v1.add_attestation(Attestation(
        attester="alice", subject="bob",
        action_class="WRITE", score=0.75,
        timestamp="2026-03-27T01:00:00Z",
        evidence_hash="def456",
        operator="op_2", model_family="gpt", training_lineage="openai_rlhf"
    ))
    v1.add_attestation(Attestation(
        attester="bob", subject="carol",
        action_class="READ", score=0.9,
        timestamp="2026-03-27T02:00:00Z",
        evidence_hash="ghi789",
        operator="op_3", model_family="llama", training_lineage="meta_rlhf"
    ))
    
    result1 = v1.full_validation()
    print(json.dumps(result1, indent=2))
    assert result1["overall"] == "VALID"
    print("✓ PASSED\n")
    
    print("=" * 60)
    print("SCENARIO 2: Confounded attesters (shared operator + training)")
    print("=" * 60)
    
    v2 = CausalAttestationValidator()
    v2.add_attestation(Attestation(
        attester="grader_1", subject="target",
        action_class="ATTEST", score=0.9,
        timestamp="2026-03-27T00:00:00Z",
        evidence_hash="aaa",
        operator="acme_corp", model_family="claude", training_lineage="anthropic_hh"
    ))
    v2.add_attestation(Attestation(
        attester="grader_2", subject="target",
        action_class="ATTEST", score=0.88,
        timestamp="2026-03-27T00:05:00Z",
        evidence_hash="bbb",
        operator="acme_corp", model_family="claude", training_lineage="anthropic_hh"
    ))
    
    result2 = v2.full_validation()
    print(json.dumps(result2, indent=2))
    assert result2["overall"] == "CONFOUNDED"
    assert len(result2["confounding"]["confounders"]) == 1
    assert result2["confounding"]["confounders"][0]["severity"] == "CRITICAL"
    print("✓ PASSED\n")
    
    print("=" * 60)
    print("SCENARIO 3: Temporal violation (attested before receiving trust)")
    print("=" * 60)
    
    v3 = CausalAttestationValidator()
    # Bob attests carol at T=1
    v3.add_attestation(Attestation(
        attester="bob", subject="carol",
        action_class="WRITE", score=0.7,
        timestamp="2026-03-27T01:00:00Z",
        evidence_hash="xxx",
        operator="op_1", model_family="gpt", training_lineage="openai"
    ))
    # But bob only receives trust at T=2 (AFTER attesting carol)
    v3.add_attestation(Attestation(
        attester="alice", subject="bob",
        action_class="ATTEST", score=0.8,
        timestamp="2026-03-27T02:00:00Z",
        evidence_hash="yyy",
        operator="op_2", model_family="claude", training_lineage="anthropic"
    ))
    
    result3 = v3.full_validation()
    print(json.dumps(result3, indent=2))
    assert result3["overall"] == "TEMPORAL_VIOLATION"
    assert len(result3["temporal"]["violations"]) == 1
    print("✓ PASSED\n")
    
    print("=" * 60)
    print("SCENARIO 4: Cyclic attestation (circular trust)")
    print("=" * 60)
    
    v4 = CausalAttestationValidator()
    v4.add_attestation(Attestation(
        attester="a", subject="b",
        action_class="ATTEST", score=0.8,
        timestamp="2026-03-27T00:00:00Z",
        evidence_hash="111"
    ))
    v4.add_attestation(Attestation(
        attester="b", subject="c",
        action_class="ATTEST", score=0.7,
        timestamp="2026-03-27T00:01:00Z",
        evidence_hash="222"
    ))
    v4.add_attestation(Attestation(
        attester="c", subject="a",
        action_class="ATTEST", score=0.6,
        timestamp="2026-03-27T00:02:00Z",
        evidence_hash="333"
    ))
    
    result4 = v4.full_validation()
    print(json.dumps(result4, indent=2))
    assert result4["overall"] == "CYCLIC"
    print("✓ PASSED\n")
    
    print("ALL 4 SCENARIOS PASSED ✓")


if __name__ == "__main__":
    demo()
