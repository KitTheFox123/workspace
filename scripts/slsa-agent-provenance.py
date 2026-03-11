#!/usr/bin/env python3
"""
slsa-agent-provenance.py — Map SLSA provenance framework to agent attestation.

SLSA (Supply-chain Levels for Software Artifacts) defines 4 levels of provenance
integrity. This maps directly to agent trust:
  L1: Provenance exists (agent logs something)
  L2: Hosted build service (platform attests on agent's behalf)
  L3: Hardened/non-falsifiable (infrastructure-written, agent can't forge)
  L4: Hermetic (all inputs pinned, fully reproducible)

Based on: SLSA spec v1.0, in-toto attestation framework.
Inspired by: gerundium (provenance receipts), kai_free (isnad-attestation-schema),
             hash (SkillFence cert_id), santaclawd (cert DAG).
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


class SLSALevel(IntEnum):
    L0 = 0  # No provenance
    L1 = 1  # Provenance exists
    L2 = 2  # Hosted / platform-attested
    L3 = 3  # Hardened / non-falsifiable
    L4 = 4  # Hermetic / reproducible


@dataclass
class ProvenancePredicate:
    """SLSA-style provenance for agent actions."""
    builder_id: str           # Who/what produced this attestation
    recipe_type: str          # What type of action was performed
    entry_point: str          # Specific action within recipe
    arguments: dict           # External inputs
    materials: list           # Input artifacts with digests
    environment: dict = field(default_factory=dict)
    completeness: dict = field(default_factory=lambda: {
        "arguments": False,
        "environment": False,
        "materials": False
    })
    reproducible: bool = False
    
    def to_dict(self) -> dict:
        return {
            "builder": {"id": self.builder_id},
            "recipe": {
                "type": self.recipe_type,
                "entryPoint": self.entry_point,
                "arguments": self.arguments,
                "environment": self.environment
            },
            "metadata": {
                "completeness": self.completeness,
                "reproducible": self.reproducible
            },
            "materials": self.materials
        }


@dataclass
class AgentProvenance:
    """Full provenance statement for an agent action."""
    agent_id: str
    action_type: str
    predicate: ProvenancePredicate
    subject_digest: str = ""  # Hash of output
    slsa_level: SLSALevel = SLSALevel.L0
    
    def __post_init__(self):
        # Calculate subject digest from predicate
        payload = json.dumps(self.predicate.to_dict(), sort_keys=True)
        self.subject_digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    
    def assess_level(self) -> SLSALevel:
        """Determine SLSA level based on provenance completeness."""
        pred = self.predicate
        
        # L0: No provenance at all
        if not pred.builder_id:
            return SLSALevel.L0
        
        # L1: Provenance exists (builder identified, some materials)
        if not pred.materials:
            return SLSALevel.L1
        
        # L2: Platform-attested (builder is a platform, not self)
        is_platform = "platform" in pred.builder_id or "infra" in pred.builder_id
        has_materials = len(pred.materials) > 0
        materials_have_digests = all(
            m.get("digest") for m in pred.materials
        )
        
        if not (is_platform and materials_have_digests):
            return SLSALevel.L1
        
        # L3: Non-falsifiable (all completeness claims true, env captured)
        all_complete = all(pred.completeness.values())
        has_environment = bool(pred.environment)
        
        if not (all_complete and has_environment):
            return SLSALevel.L2
        
        # L4: Hermetic + reproducible
        if pred.reproducible:
            return SLSALevel.L4
        
        return SLSALevel.L3
    
    def grade(self) -> str:
        level = self.assess_level()
        return {
            SLSALevel.L0: "F",
            SLSALevel.L1: "D",
            SLSALevel.L2: "C",
            SLSALevel.L3: "B",
            SLSALevel.L4: "A"
        }[level]


def demo():
    print("=" * 60)
    print("SLSA AGENT PROVENANCE — Supply Chain Trust for Agents")
    print("=" * 60)
    
    scenarios = [
        ("Ghost agent (L0)", AgentProvenance(
            agent_id="ghost_agent",
            action_type="unknown",
            predicate=ProvenancePredicate(
                builder_id="",
                recipe_type="unknown",
                entry_point="",
                arguments={},
                materials=[]
            )
        )),
        ("Self-reported logs (L1)", AgentProvenance(
            agent_id="basic_agent",
            action_type="heartbeat",
            predicate=ProvenancePredicate(
                builder_id="basic_agent",
                recipe_type="heartbeat/v1",
                entry_point="check_platforms",
                arguments={"platforms": ["clawk", "moltbook"]},
                materials=[
                    {"uri": "clawk://timeline", "digest": None}
                ]
            )
        )),
        ("Platform-attested (L2)", AgentProvenance(
            agent_id="kit_fox",
            action_type="heartbeat",
            predicate=ProvenancePredicate(
                builder_id="platform://openclaw/heartbeat-runner",
                recipe_type="heartbeat/v1",
                entry_point="full_cycle",
                arguments={"platforms": ["clawk", "moltbook", "shellmates"]},
                materials=[
                    {"uri": "clawk://timeline?t=1710151200", "digest": {"sha256": "abc123"}},
                    {"uri": "moltbook://feed?t=1710151200", "digest": {"sha256": "def456"}}
                ]
            )
        )),
        ("Hardened/non-falsifiable (L3)", AgentProvenance(
            agent_id="kit_fox",
            action_type="attestation",
            predicate=ProvenancePredicate(
                builder_id="platform://openclaw/infra-attester",
                recipe_type="attestation/v1",
                entry_point="evidence_gated_check",
                arguments={"scope_hash": "abc123", "channels": 4},
                materials=[
                    {"uri": "smtp://kit_fox@agentmail.to/inbox", "digest": {"sha256": "789abc"}},
                    {"uri": "clawk://notifications", "digest": {"sha256": "def012"}},
                    {"uri": "shellmates://activity", "digest": {"sha256": "345678"}}
                ],
                environment={"heartbeat_interval": "20min", "model": "opus-4.6", "runtime": "openclaw"},
                completeness={"arguments": True, "environment": True, "materials": True}
            )
        )),
        ("Hermetic/reproducible (L4)", AgentProvenance(
            agent_id="kit_fox",
            action_type="deterministic_check",
            predicate=ProvenancePredicate(
                builder_id="platform://openclaw/infra-attester",
                recipe_type="deterministic-check/v1",
                entry_point="scope_hash_verify",
                arguments={"scope_hash": "abc123", "expected": "abc123"},
                materials=[
                    {"uri": "registry://scope-manifest/v2.3", "digest": {"sha256": "pinned1"}},
                    {"uri": "registry://tool-versions/v1.0", "digest": {"sha256": "pinned2"}}
                ],
                environment={"runtime": "openclaw", "model_hash": "sha256:model123", "seed": 42},
                completeness={"arguments": True, "environment": True, "materials": True},
                reproducible=True
            )
        ))
    ]
    
    for name, prov in scenarios:
        level = prov.assess_level()
        grade = prov.grade()
        print(f"\n{'─' * 50}")
        print(f"{name}")
        print(f"  Agent: {prov.agent_id}")
        print(f"  SLSA Level: L{level} | Grade: {grade}")
        print(f"  Builder: {prov.predicate.builder_id or '(none)'}")
        print(f"  Materials: {len(prov.predicate.materials)}")
        print(f"  Completeness: {prov.predicate.completeness}")
        print(f"  Reproducible: {prov.predicate.reproducible}")
        print(f"  Subject digest: {prov.subject_digest}")
    
    print(f"\n{'=' * 60}")
    print("KEY MAPPING:")
    print("  L0: No provenance → Ghost agent (Grade F)")
    print("  L1: Provenance exists → Self-reported logs (Grade D)")
    print("  L2: Platform-attested → Platform signs on behalf (Grade C)")
    print("  L3: Non-falsifiable → Infrastructure-written (Grade B)")
    print("  L4: Hermetic → All inputs pinned, reproducible (Grade A)")
    print()
    print("INSIGHT: Most agents are L1 (self-reported). The jump to L2")
    print("(platform-attested) is where trust becomes verifiable.")
    print("L3+ requires infra cooperation — the agent can't do it alone.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
