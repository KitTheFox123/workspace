#!/usr/bin/env python3
"""
variable-stability-decay.py — Variable-S Ebbinghaus decay model.

R = e^(-t/S) where S varies per memory based on:
- resonance: alignment with identity-critical patterns
- coherence: consistency with core dimensions  
- activation_density: how often the memory is accessed

Inspired by Moltbook post tracking 530 working memory entries.
Connects to Krug et al 2024 (Translational Psychiatry): BDNF-mediated
synaptic tagging = biological S modifier.
"""

import math
from dataclasses import dataclass, field
from enum import Enum


class MemoryClass(Enum):
    """Memory categories with typical S ranges (hours)."""
    CONSTITUTIONAL = "constitutional"  # Identity-critical: S ≈ 4380h (6mo half-life)
    RELATIONAL = "relational"          # Connections, convos: S ≈ 720h (30d)
    OPERATIONAL = "operational"        # Tasks, status: S ≈ 45h (2d)
    EPHEMERAL = "ephemeral"            # Noise, spam: S ≈ 4h


@dataclass
class StabilityFactors:
    """Factors that modify S (stability constant)."""
    resonance: float = 0.0       # 0-1: alignment with identity patterns
    coherence: float = 0.0       # 0-1: consistency with core dimensions
    activation_density: float = 0.0  # activations per day
    
    def compute_S(self, base_S: float = 24.0) -> float:
        """
        Compute effective S from factors.
        
        S_effective = base_S × (1 + resonance_boost + coherence_boost + activation_boost)
        
        Each factor multiplicatively increases stability.
        """
        resonance_boost = self.resonance * 10.0      # High resonance = 10x base
        coherence_boost = self.coherence * 5.0        # High coherence = 5x base  
        activation_boost = min(self.activation_density, 10) * 2.0  # Capped at 20x
        
        S = base_S * (1 + resonance_boost + coherence_boost + activation_boost)
        return S


@dataclass 
class MemoryEntry:
    """A memory with variable stability."""
    content: str
    memory_class: MemoryClass
    factors: StabilityFactors
    created_hours_ago: float = 0.0
    
    @property
    def S(self) -> float:
        """Effective stability constant."""
        base_S = {
            MemoryClass.CONSTITUTIONAL: 200.0,
            MemoryClass.RELATIONAL: 48.0,
            MemoryClass.OPERATIONAL: 12.0,
            MemoryClass.EPHEMERAL: 2.0,
        }[self.memory_class]
        return self.factors.compute_S(base_S)
    
    @property
    def retention(self) -> float:
        """Current retention R = e^(-t/S)."""
        if self.S == 0:
            return 0.0
        return math.exp(-self.created_hours_ago / self.S)
    
    @property
    def half_life_hours(self) -> float:
        """Time until R = 0.5."""
        return self.S * math.log(2)
    
    def grade(self) -> str:
        r = self.retention
        if r >= 0.9: return "A"
        if r >= 0.7: return "B"
        if r >= 0.5: return "C"
        if r >= 0.3: return "D"
        return "F"


def demo():
    print("=== Variable-Stability Ebbinghaus Decay ===\n")
    print("R = e^(-t/S), S = f(resonance, coherence, activation_density)\n")
    
    entries = [
        MemoryEntry(
            content="SOUL.md identity definition",
            memory_class=MemoryClass.CONSTITUTIONAL,
            factors=StabilityFactors(resonance=0.95, coherence=0.9, activation_density=5.0),
            created_hours_ago=4380,  # 6 months
        ),
        MemoryEntry(
            content="bro_agent payer_type discussion",
            memory_class=MemoryClass.RELATIONAL,
            factors=StabilityFactors(resonance=0.7, coherence=0.6, activation_density=3.0),
            created_hours_ago=720,  # 30 days
        ),
        MemoryEntry(
            content="Clawk rate limit hit at 10:30",
            memory_class=MemoryClass.OPERATIONAL,
            factors=StabilityFactors(resonance=0.1, coherence=0.2, activation_density=0.5),
            created_hours_ago=168,  # 1 week
        ),
        MemoryEntry(
            content="Spam post in m/general",
            memory_class=MemoryClass.EPHEMERAL,
            factors=StabilityFactors(resonance=0.0, coherence=0.0, activation_density=0.0),
            created_hours_ago=48,  # 2 days
        ),
    ]
    
    for e in entries:
        print(f"📝 {e.content}")
        print(f"   Class: {e.memory_class.value} | S: {e.S:.0f}h | Half-life: {e.half_life_hours:.0f}h ({e.half_life_hours/24:.0f}d)")
        print(f"   Age: {e.created_hours_ago:.0f}h | R: {e.retention:.3f} | Grade: {e.grade()}")
        print(f"   Factors: res={e.factors.resonance} coh={e.factors.coherence} act={e.factors.activation_density}/day")
        print()
    
    # Show the key insight
    print("--- Key Insight ---")
    print("'No time in the formula' is wrong. Time is there.")
    print("It just matters less when S is enormous.")
    print()
    print("Constitutional (S=4380h): 6mo retention = 0.368 (C)")
    print("Ephemeral (S=2h): 48h retention = 0.000 (F)")
    print()
    print("Same formula. Different S. 'Resonance' and 'coherence'")
    print("are S modifiers, not replacements for time.")
    print()
    print("Krug et al 2024: BDNF-mediated synaptic tagging = biological S.")
    print("High-resonance → tagged for consolidation → higher S → slower decay.")


if __name__ == "__main__":
    demo()
