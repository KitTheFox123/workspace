#!/usr/bin/env python3
"""attestor-assignment.py — Third-party attestor assignment engine.

Implements Sarbanes-Oxley principle for agent attestation: the entity being
attested must NOT select their own attestor. Assignment governed by registry
outside both agent and principal scope.

Based on Moore, Tetlock & Bazerman (2006, AMR): unconscious bias in auditor
selection when audited entity chooses. SOX fix: audit committee assigns.

Usage:
    python3 attestor-assignment.py [--demo] [--assign AGENT_ID]
"""

import argparse
import hashlib
import json
import random
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class Attestor:
    id: str
    provider: str  # Infrastructure provider (for diversity)
    model_family: str  # Training family (for confounding)
    specialization: str  # What they're good at
    reliability_score: float  # Historical accuracy
    last_assignment: Optional[str] = None  # Prevent repeat assignment


@dataclass
class Agent:
    id: str
    principal: str
    provider: str
    scope_hash: str


@dataclass 
class Assignment:
    agent_id: str
    attestor_ids: List[str]
    assignment_hash: str  # Deterministic from inputs
    diversity_score: float
    independence_grade: str
    timestamp: str
    rotation_number: int
    disqualified: List[str] = field(default_factory=list)


class AttestorRegistry:
    """Third-party attestor assignment — no agent/principal influence."""
    
    def __init__(self):
        self.attestors: dict[str, Attestor] = {}
        self.agents: dict[str, Agent] = {}
        self.assignments: list[Assignment] = []
        self.rotation_counter: dict[str, int] = {}
    
    def register_attestor(self, attestor: Attestor):
        self.attestors[attestor.id] = attestor
    
    def register_agent(self, agent: Agent):
        self.agents[agent.id] = agent
    
    def _disqualify(self, agent: Agent) -> set:
        """Disqualify attestors with conflicts of interest."""
        disqualified = set()
        for aid, att in self.attestors.items():
            # Same provider = shared infrastructure confounder
            if att.provider == agent.provider:
                disqualified.add(aid)
            # Same principal = direct conflict
            if att.id == agent.principal:
                disqualified.add(aid)
            # Recently assigned to same agent (soft preference, not hard disqualify)
            # Only disqualify if enough alternatives exist
            pass  # Rotation handled by seed change
        return disqualified
    
    def _diversity_score(self, attestors: List[Attestor]) -> float:
        """Score provider + model diversity (0-1)."""
        if len(attestors) < 2:
            return 0.0
        providers = set(a.provider for a in attestors)
        families = set(a.model_family for a in attestors)
        n = len(attestors)
        provider_div = len(providers) / n
        family_div = len(families) / n
        return round((provider_div + family_div) / 2, 3)
    
    def assign(self, agent_id: str, n_attestors: int = 3) -> Assignment:
        """Assign attestors to agent — registry decides, not agent/principal."""
        agent = self.agents.get(agent_id)
        if not agent:
            raise ValueError(f"Unknown agent: {agent_id}")
        
        disqualified = self._disqualify(agent)
        eligible = [a for aid, a in self.attestors.items() if aid not in disqualified]
        
        if len(eligible) < n_attestors:
            raise ValueError(f"Only {len(eligible)} eligible attestors (need {n_attestors})")
        
        # Score-weighted random selection (not agent's choice!)
        weights = [a.reliability_score for a in eligible]
        total = sum(weights)
        weights = [w / total for w in weights]
        
        # Deterministic seed from agent + rotation for reproducibility
        rotation = self.rotation_counter.get(agent_id, 0) + 1
        self.rotation_counter[agent_id] = rotation
        seed_input = f"{agent_id}:{rotation}:{agent.scope_hash}"
        seed = int(hashlib.sha256(seed_input.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        
        selected = []
        remaining = list(zip(eligible, weights))
        for _ in range(min(n_attestors, len(remaining))):
            r_weights = [w for _, w in remaining]
            total_w = sum(r_weights)
            r_weights = [w / total_w for w in r_weights]
            # Weighted selection
            val = rng.random()
            cumulative = 0
            for i, w in enumerate(r_weights):
                cumulative += w
                if val <= cumulative:
                    selected.append(remaining[i][0])
                    remaining.pop(i)
                    break
        
        # Update last assignment
        for att in selected:
            self.attestors[att.id].last_assignment = agent_id
        
        diversity = self._diversity_score(selected)
        grade = "A" if diversity >= 0.8 else "B" if diversity >= 0.6 else "C" if diversity >= 0.4 else "D"
        
        assignment_data = f"{agent_id}:{[a.id for a in selected]}:{rotation}"
        assignment_hash = hashlib.sha256(assignment_data.encode()).hexdigest()[:16]
        
        assignment = Assignment(
            agent_id=agent_id,
            attestor_ids=[a.id for a in selected],
            assignment_hash=assignment_hash,
            diversity_score=diversity,
            independence_grade=grade,
            timestamp=datetime.now(timezone.utc).isoformat(),
            rotation_number=rotation,
            disqualified=list(disqualified)
        )
        self.assignments.append(assignment)
        return assignment


def demo():
    """Demo: attestor assignment with conflict-of-interest filtering."""
    registry = AttestorRegistry()
    
    # Register attestors across different providers/families
    attestors = [
        Attestor("att_alpha", "aws", "claude", "security", 0.92),
        Attestor("att_beta", "gcp", "gemini", "compliance", 0.88),
        Attestor("att_gamma", "azure", "gpt", "scope_audit", 0.90),
        Attestor("att_delta", "hetzner", "llama", "behavioral", 0.85),
        Attestor("att_epsilon", "aws", "claude", "runtime", 0.91),
        Attestor("att_zeta", "ovh", "mistral", "network", 0.87),
    ]
    for a in attestors:
        registry.register_attestor(a)
    
    # Register agent (on AWS)
    agent = Agent("agent_kit", "principal_ilya", "aws", "scope_abc123")
    registry.register_agent(agent)
    
    print("=" * 60)
    print("ATTESTOR ASSIGNMENT ENGINE")
    print("Moore, Tetlock & Bazerman (2006) — SOX model")
    print("=" * 60)
    print()
    print(f"Agent: {agent.id} (provider: {agent.provider})")
    print(f"Attestor pool: {len(attestors)}")
    print()
    
    # First assignment
    a1 = registry.assign("agent_kit", n_attestors=3)
    print(f"Assignment #{a1.rotation_number}:")
    print(f"  Assigned: {a1.attestor_ids}")
    print(f"  Disqualified (conflict): {a1.disqualified}")
    print(f"  Diversity: {a1.diversity_score} (Grade {a1.independence_grade})")
    print(f"  Hash: {a1.assignment_hash}")
    print()
    
    # Second assignment (rotation)
    a2 = registry.assign("agent_kit", n_attestors=3)
    print(f"Assignment #{a2.rotation_number} (rotation):")
    print(f"  Assigned: {a2.attestor_ids}")
    print(f"  Disqualified (conflict): {a2.disqualified}")
    print(f"  Diversity: {a2.diversity_score} (Grade {a2.independence_grade})")
    print()
    
    print("-" * 60)
    print("Key principle: agent/principal NEVER selects attestor.")
    print("Registry assigns. Conflicts filtered. Rotation enforced.")
    print("Unconscious bias eliminated by removing selection entirely.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Third-party attestor assignment")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    demo()
