#!/usr/bin/env python3
"""
adoption-tipping-point.py — Protocol adoption tipping point model.

Models the Chrome CT/HTTPS adoption pattern as a coordination game.
Key insight from santaclawd thread: "the spec didn't move the ecosystem,
the browser did." But what if no single player has 60% share?

Two forcing functions:
1. Dominant enforcer (Chrome model): one player with >critical_mass forces shift
2. Format convergence (TCP/IP model): open format becomes Schelling focal point

Schelling (1960): coordination succeeds when there's a salient focal point.
Chrome was the focal point for HTTPS. For agents, the wire format must be.

Simulates adoption curves under different market structures.
"""

import math
from dataclasses import dataclass, field
from enum import Enum


class AdoptionModel(Enum):
    DOMINANT_ENFORCER = "dominant_enforcer"  # Chrome CT model
    FORMAT_CONVERGENCE = "format_convergence"  # TCP/IP model
    FRAGMENTED = "fragmented"  # No focal point


@dataclass
class MarketPlayer:
    name: str
    market_share: float  # 0.0 - 1.0
    enforcement_willingness: float  # 0.0 - 1.0 (will they reject non-compliant?)
    adoption_cost: float  # relative cost to adopt (0.0 - 1.0)


@dataclass
class AdoptionState:
    month: int
    adoption_rate: float
    enforcing_share: float  # % of market that enforces
    model: AdoptionModel = AdoptionModel.FRAGMENTED
    tipping_point_reached: bool = False


class AdoptionSimulator:
    """Simulate protocol adoption under different market structures."""
    
    # Chrome had ~60% when it enforced CT
    CRITICAL_MASS = 0.60
    # HTTPS went 40% → 95% in ~36 months
    TARGET_ADOPTION = 0.95
    
    def __init__(self, players: list[MarketPlayer]):
        self.players = players
        self.largest_share = max(p.market_share for p in players)
    
    def classify_market(self) -> AdoptionModel:
        """Determine which adoption model applies."""
        if self.largest_share >= self.CRITICAL_MASS:
            return AdoptionModel.DOMINANT_ENFORCER
        
        # Check if top-3 could coordinate
        sorted_shares = sorted(
            [p.market_share for p in self.players], reverse=True
        )
        top3 = sum(sorted_shares[:3])
        if top3 >= self.CRITICAL_MASS:
            return AdoptionModel.FORMAT_CONVERGENCE
        
        return AdoptionModel.FRAGMENTED
    
    def simulate(self, months: int = 48) -> list[AdoptionState]:
        """Run adoption simulation."""
        model = self.classify_market()
        states = []
        
        for m in range(months):
            if model == AdoptionModel.DOMINANT_ENFORCER:
                state = self._dominant_enforcer_step(m)
            elif model == AdoptionModel.FORMAT_CONVERGENCE:
                state = self._format_convergence_step(m)
            else:
                state = self._fragmented_step(m)
            
            state.model = model
            states.append(state)
        
        return states
    
    def _dominant_enforcer_step(self, month: int) -> AdoptionState:
        """Chrome model: announce → grace period → enforce → rapid adoption.
        
        Timeline (actual Chrome CT):
        - Month 0-6: Announce, REPORT mode
        - Month 6-12: Warn on specific pages  
        - Month 12-18: Warn on all pages
        - Month 18+: Full enforcement, rapid S-curve
        """
        if month < 6:
            # Announcement phase
            rate = 0.40 + 0.02 * month  # Slow early adopters
            enforcing = 0.0
        elif month < 12:
            # Graduated warnings
            rate = 0.52 + 0.03 * (month - 6)
            enforcing = self.largest_share * 0.3
        elif month < 18:
            # Aggressive warnings
            rate = 0.70 + 0.04 * (month - 12)
            enforcing = self.largest_share * 0.7
        else:
            # Full enforcement — S-curve
            t = month - 18
            rate = 0.94 + 0.06 * (1 - math.exp(-t / 6))
            enforcing = self.largest_share
        
        rate = min(rate, 0.99)
        tipped = rate >= self.TARGET_ADOPTION
        
        return AdoptionState(
            month=month,
            adoption_rate=rate,
            enforcing_share=enforcing,
            tipping_point_reached=tipped,
        )
    
    def _format_convergence_step(self, month: int) -> AdoptionState:
        """TCP/IP model: slower but broader. No single enforcer.
        
        Adoption through format standardization + multiple implementers.
        Slower S-curve, but more resilient (no single point of failure).
        """
        # Logistic growth: slower than dominant enforcer
        k = 0.08  # Growth rate (Chrome model uses ~0.15)
        midpoint = 30  # Months to 50% (Chrome: ~15)
        
        rate = 0.99 / (1 + math.exp(-k * (month - midpoint)))
        rate = max(rate, 0.05)  # Floor: early adopters
        
        # Enforcing share grows with adoption
        enforcing = rate * 0.7  # 70% of adopters enforce
        tipped = rate >= self.TARGET_ADOPTION
        
        return AdoptionState(
            month=month,
            adoption_rate=rate,
            enforcing_share=enforcing,
            tipping_point_reached=tipped,
        )
    
    def _fragmented_step(self, month: int) -> AdoptionState:
        """No focal point. Multiple incompatible approaches.
        
        Without coordination, adoption stalls. Classic coordination failure.
        Multiple standards compete, none reaches critical mass.
        """
        # Logarithmic growth that plateaus early
        rate = 0.25 * math.log(1 + month * 0.3)
        rate = min(rate, 0.45)  # Ceiling: fragmentation caps adoption
        
        enforcing = rate * 0.2  # Few enforce in fragmented market
        
        return AdoptionState(
            month=month,
            adoption_rate=rate,
            enforcing_share=enforcing,
            tipping_point_reached=False,  # Never tips
        )
    
    def time_to_tip(self, states: list[AdoptionState]) -> int | None:
        """Months until tipping point (95% adoption)."""
        for s in states:
            if s.tipping_point_reached:
                return s.month
        return None


def demo():
    """Three market scenarios matching real protocol history."""
    
    scenarios = {
        "Chrome CT (2017-2020)": [
            MarketPlayer("Chrome", 0.62, 0.95, 0.3),
            MarketPlayer("Firefox", 0.12, 0.70, 0.5),
            MarketPlayer("Safari", 0.15, 0.80, 0.4),
            MarketPlayer("Others", 0.11, 0.20, 0.8),
        ],
        "Agent Runtimes (2026)": [
            MarketPlayer("OpenClaw", 0.15, 0.90, 0.3),
            MarketPlayer("LangChain", 0.20, 0.40, 0.5),
            MarketPlayer("AutoGPT", 0.10, 0.30, 0.6),
            MarketPlayer("Custom", 0.55, 0.10, 0.9),
        ],
        "Email (1990s)": [
            MarketPlayer("Sendmail", 0.30, 0.50, 0.4),
            MarketPlayer("Exchange", 0.25, 0.30, 0.5),
            MarketPlayer("Lotus", 0.15, 0.20, 0.6),
            MarketPlayer("Others", 0.30, 0.10, 0.7),
        ],
    }
    
    for name, players in scenarios.items():
        print(f"\n{'='*60}")
        print(f"Scenario: {name}")
        print(f"{'='*60}")
        
        sim = AdoptionSimulator(players)
        model = sim.classify_market()
        states = sim.simulate(48)
        ttp = sim.time_to_tip(states)
        
        print(f"  Market model: {model.value}")
        print(f"  Largest player: {max(players, key=lambda p: p.market_share).name} "
              f"({max(p.market_share for p in players):.0%})")
        
        # Show key milestones
        milestones = [0, 6, 12, 18, 24, 36, 48]
        for m in milestones:
            if m < len(states):
                s = states[m]
                tip = " ← TIPPED" if s.tipping_point_reached else ""
                print(f"  Month {m:2d}: {s.adoption_rate:.1%} adopted, "
                      f"{s.enforcing_share:.1%} enforcing{tip}")
        
        if ttp:
            print(f"\n  ⏱️  Tipping point reached at month {ttp}")
        else:
            print(f"\n  ❌ Never reaches 95% in 48 months")
        
        # Recommendation
        if model == AdoptionModel.DOMINANT_ENFORCER:
            print(f"  → Strategy: Get the dominant player to enforce")
        elif model == AdoptionModel.FORMAT_CONVERGENCE:
            print(f"  → Strategy: Ship open format + reference impls. "
                  f"FORMAT is the focal point.")
        else:
            print(f"  → Strategy: Consolidate or create a new focal point. "
                  f"Current fragmentation blocks adoption.")
    
    print(f"\n{'='*60}")
    print("Key insight: Agent runtimes (2026) = FORMAT_CONVERGENCE model.")
    print("No Chrome equivalent exists. The wire format IS the Schelling point.")
    print("Ship the format. Build reference impls. Let adoption compound.")
    print(f"{'='*60}")


if __name__ == "__main__":
    demo()
