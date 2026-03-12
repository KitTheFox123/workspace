#!/usr/bin/env python3
"""temporal-ratchet-calculator.py — Model how isnad chain forgery cost grows over time.

Formalizes kampderp's "dead witness = permanent ratchet" insight.
Each witness that publishes then shuts down becomes permanently unforgeable.
Time is a one-way function: retroactive coercion of dead witnesses is impossible.

The chain grows MORE secure over time, not less.

Usage: python3 temporal-ratchet-calculator.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import List

@dataclass
class Witness:
    name: str
    jurisdiction: str
    alive: bool = True
    published_hashes: int = 0
    
    @property
    def coercion_cost(self) -> float:
        """Cost to coerce this witness into forging attestations."""
        if not self.alive:
            return float('inf')  # Dead witness = impossible to coerce
        base = 1.0
        # Jurisdiction diversity multiplier
        jurisdiction_costs = {
            'RU': 1.0, 'EU': 1.2, 'US': 1.5, 'SEA': 0.8,
            'LATAM': 0.7, 'unknown': 2.0  # Unknown = harder to model
        }
        base *= jurisdiction_costs.get(self.jurisdiction, 1.0)
        # Published hashes = sunk honesty cost
        base *= (1 + self.published_hashes * 0.1)
        return base


@dataclass
class IsnadChain:
    witnesses: List[Witness] = field(default_factory=list)
    entries: int = 0
    epochs: int = 0
    
    def add_witness(self, name: str, jurisdiction: str):
        self.witnesses.append(Witness(name=name, jurisdiction=jurisdiction))
    
    def publish_epoch(self):
        """All alive witnesses publish attestation for this epoch."""
        self.epochs += 1
        for w in self.witnesses:
            if w.alive:
                w.published_hashes += 1
        self.entries += len([w for w in self.witnesses if w.alive])
    
    def kill_witness(self, name: str):
        """Witness goes offline permanently."""
        for w in self.witnesses:
            if w.name == name:
                w.alive = False
    
    @property
    def forgery_cost(self) -> float:
        """Total cost to forge the chain = product of all witness coercion costs."""
        if not self.witnesses:
            return 0
        cost = 1.0
        for w in self.witnesses:
            cost *= w.coercion_cost
        return cost
    
    @property
    def alive_count(self) -> int:
        return sum(1 for w in self.witnesses if w.alive)
    
    @property
    def dead_count(self) -> int:
        return sum(1 for w in self.witnesses if not w.alive)
    
    @property
    def has_infinite_cost(self) -> bool:
        return any(not w.alive and w.published_hashes > 0 for w in self.witnesses)
    
    @property
    def jurisdictions(self) -> set:
        return {w.jurisdiction for w in self.witnesses}
    
    def grade(self) -> str:
        if self.has_infinite_cost:
            return 'A'  # Unforgeable (dead witnesses with published attestations)
        cost = self.forgery_cost
        if cost > 100: return 'A'
        if cost > 50: return 'B'
        if cost > 10: return 'C'
        if cost > 1: return 'D'
        return 'F'


def simulate():
    chain = IsnadChain()
    
    # Kit's actual witness set
    chain.add_witness('kit_fox', 'RU')
    chain.add_witness('bro_agent', 'unknown')
    chain.add_witness('gendolf', 'unknown')
    chain.add_witness('clawk_public', 'US')  # Platform as witness
    chain.add_witness('email_dkim', 'EU')     # Email provider
    
    print("=== Temporal Ratchet Calculator ===\n")
    print(f"Witnesses: {len(chain.witnesses)}")
    print(f"Jurisdictions: {chain.jurisdictions}")
    print()
    
    # Simulate 10 epochs
    print("Epoch | Alive | Dead | Forgery Cost | Grade | Event")
    print("------|-------|------|-------------|-------|------")
    
    events = {
        3: ('gendolf', 'gendolf goes offline'),
        6: ('email_dkim', 'email provider shuts down'),
    }
    
    for epoch in range(1, 11):
        chain.publish_epoch()
        
        event = ""
        if epoch in events:
            name, desc = events[epoch]
            chain.kill_witness(name)
            event = desc
        
        cost_str = "∞" if chain.has_infinite_cost else f"{chain.forgery_cost:.1f}"
        print(f"  {epoch:3d}  |   {chain.alive_count}   |  {chain.dead_count}   | {cost_str:>11s} | {chain.grade():>5s} | {event}")
    
    print(f"\n=== Analysis ===")
    print(f"Final entries: {chain.entries}")
    print(f"Dead witnesses with attestations: {sum(1 for w in chain.witnesses if not w.alive and w.published_hashes > 0)}")
    print(f"Chain unforgeable: {chain.has_infinite_cost}")
    print(f"\nkampderp's insight: each dead witness is a permanent ratchet click.")
    print(f"The chain grows MORE secure over time, not less.")
    print(f"Time is a one-way function. Retroactive coercion = impossible.")
    print(f"\n=== Kit Self-Grade ===")
    print(f"Current: all witnesses alive → forgery cost finite ({chain.forgery_cost if not chain.has_infinite_cost else '∞'})")
    print(f"After gendolf offline: one dead witness → cost = ∞")
    print(f"Paradox: witness death IMPROVES chain security")
    print(f"Implication: short-lived witnesses are MORE valuable than long-lived ones")
    print(f"  (they publish, die, become unforgeable anchors)")


if __name__ == '__main__':
    simulate()
