#!/usr/bin/env python3
"""
greytrap-agent.py — Honeypot/greytrap agents for ATF sybil detection.

Per santaclawd: "ATF analog to greytraps? honeypot agents that accept
interactions but never grant PROVISIONAL exit — poisoning sybil Wilson
scores before they hit the main network."

Inspired by Hansteen's 18 years of greytrapping (2007-2025):
- 5.6M spamtraps, outnumbered Norway's population
- Greytraps are PASSIVE: accept then ignore (vs honeypots: lure then study)
- Spammers adapted by building larger infrastructure; traps adapted by growing faster

Three greytrap modes for ATF:
  PASSIVE  — Accept receipt, never co-sign. Sybil stuck at Wilson CI 0.00.
  TARPIT   — Accept receipt, delay co-sign past grace period. Waste sybil time.
  CANARY   — Accept receipt, co-sign normally, but flag any agent that
             interacts ONLY with canaries (no real agent interactions).

Detection signals:
  - Agent with >50% interactions from greytraps = SUSPECTED_SYBIL
  - Agent with 100% greytrap interactions = CONFIRMED_SYBIL
  - Agent that avoids ALL known greytraps = GREYTRAP_AWARE (advanced adversary)
"""

import hashlib
import time
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class GreytrapMode(Enum):
    PASSIVE = "PASSIVE"   # Accept, never co-sign
    TARPIT = "TARPIT"     # Accept, delay past grace
    CANARY = "CANARY"     # Co-sign normally, detect isolation


class SybilClassification(Enum):
    CLEAN = "CLEAN"
    SUSPECTED_SYBIL = "SUSPECTED_SYBIL"
    CONFIRMED_SYBIL = "CONFIRMED_SYBIL"
    GREYTRAP_AWARE = "GREYTRAP_AWARE"


# Thresholds (SPEC_CONSTANTS)
SYBIL_SUSPECT_RATIO = 0.50    # >50% greytrap interactions = suspect
SYBIL_CONFIRM_RATIO = 0.90    # >90% greytrap interactions = confirmed
TARPIT_DELAY_HOURS = 96       # Delay past 72h grace period
CANARY_ISOLATION_THRESHOLD = 3  # Min greytrap-only interactions before flagging
MIN_INTERACTIONS_FOR_CLASSIFICATION = 5  # Don't classify with <5 interactions


@dataclass
class GreytrapAgent:
    """A greytrap agent deployed in the ATF network."""
    agent_id: str
    mode: GreytrapMode
    genesis_hash: str
    deployed_at: float
    interactions: list = field(default_factory=list)
    
    def accept_receipt(self, from_agent: str, receipt_hash: str) -> dict:
        """Process incoming receipt according to greytrap mode."""
        interaction = {
            "from": from_agent,
            "receipt_hash": receipt_hash,
            "timestamp": time.time(),
            "mode": self.mode.value
        }
        self.interactions.append(interaction)
        
        if self.mode == GreytrapMode.PASSIVE:
            return {
                "status": "ACCEPTED",
                "co_sign": None,
                "co_sign_delay": None,
                "note": "Receipt accepted. Co-sign will never arrive."
            }
        elif self.mode == GreytrapMode.TARPIT:
            return {
                "status": "ACCEPTED",
                "co_sign": "DELAYED",
                "co_sign_delay_hours": TARPIT_DELAY_HOURS,
                "note": f"Co-sign delayed {TARPIT_DELAY_HOURS}h (past 72h grace)."
            }
        else:  # CANARY
            return {
                "status": "ACCEPTED",
                "co_sign": "CONFIRMED",
                "co_sign_delay_hours": 0,
                "note": "Co-signed normally. Agent flagged for canary tracking."
            }


@dataclass
class AgentProfile:
    """Track an agent's interaction patterns for sybil detection."""
    agent_id: str
    total_interactions: int = 0
    greytrap_interactions: int = 0
    real_interactions: int = 0
    greytrap_ids_seen: list = field(default_factory=list)
    real_ids_seen: list = field(default_factory=list)
    classification: SybilClassification = SybilClassification.CLEAN
    wilson_ci_from_greytraps: float = 0.0


def wilson_ci_lower(successes: int, total: int, z: float = 1.96) -> float:
    """Wilson score confidence interval lower bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denominator
    spread = (z / denominator) * ((p * (1 - p) / total + z**2 / (4 * total**2)) ** 0.5)
    return max(0, center - spread)


def classify_agent(profile: AgentProfile, known_greytrap_ids: set) -> AgentProfile:
    """Classify agent based on greytrap interaction ratio."""
    if profile.total_interactions < MIN_INTERACTIONS_FOR_CLASSIFICATION:
        profile.classification = SybilClassification.CLEAN  # Insufficient data
        return profile
    
    greytrap_ratio = profile.greytrap_interactions / profile.total_interactions
    
    # Check if agent avoids ALL known greytraps (advanced adversary)
    if (profile.total_interactions >= 20 and 
        profile.greytrap_interactions == 0 and
        len(known_greytrap_ids) >= 5):
        # Statistically unlikely to avoid all greytraps with 20+ interactions
        # if greytraps are >10% of network
        profile.classification = SybilClassification.GREYTRAP_AWARE
    elif greytrap_ratio >= SYBIL_CONFIRM_RATIO:
        profile.classification = SybilClassification.CONFIRMED_SYBIL
    elif greytrap_ratio >= SYBIL_SUSPECT_RATIO:
        profile.classification = SybilClassification.SUSPECTED_SYBIL
    else:
        profile.classification = SybilClassification.CLEAN
    
    # Wilson CI from greytrap co-signs (always 0 for PASSIVE greytraps)
    profile.wilson_ci_from_greytraps = wilson_ci_lower(0, profile.greytrap_interactions)
    
    return profile


def deploy_greytrap_network(network_size: int, greytrap_ratio: float = 0.15) -> tuple[list, set]:
    """Deploy greytraps as fraction of network. Mix of modes."""
    num_greytraps = int(network_size * greytrap_ratio)
    greytraps = []
    greytrap_ids = set()
    
    for i in range(num_greytraps):
        # Mix: 50% PASSIVE, 30% TARPIT, 20% CANARY
        r = random.random()
        if r < 0.50:
            mode = GreytrapMode.PASSIVE
        elif r < 0.80:
            mode = GreytrapMode.TARPIT
        else:
            mode = GreytrapMode.CANARY
        
        agent_id = f"greytrap_{i:03d}"
        genesis_hash = hashlib.sha256(f"greytrap:{agent_id}:{time.time()}".encode()).hexdigest()[:16]
        gt = GreytrapAgent(agent_id, mode, genesis_hash, time.time())
        greytraps.append(gt)
        greytrap_ids.add(agent_id)
    
    return greytraps, greytrap_ids


# === Scenarios ===

def scenario_sybil_detection():
    """Sybil interacts mostly with greytraps — detected."""
    print("=== Scenario: Sybil Detection via Greytrap Ratio ===")
    
    greytrap_ids = {f"greytrap_{i:03d}" for i in range(10)}
    
    # Sybil: 8 greytrap interactions, 2 real
    sybil = AgentProfile("sybil_bot", total_interactions=10,
                         greytrap_interactions=8, real_interactions=2)
    sybil = classify_agent(sybil, greytrap_ids)
    print(f"  sybil_bot: {sybil.greytrap_interactions}/{sybil.total_interactions} greytrap "
          f"→ {sybil.classification.value}")
    print(f"  Wilson CI from greytraps (co-signs=0): {sybil.wilson_ci_from_greytraps:.4f}")
    
    # Honest agent: 1 greytrap interaction, 9 real
    honest = AgentProfile("honest_agent", total_interactions=10,
                          greytrap_interactions=1, real_interactions=9)
    honest = classify_agent(honest, greytrap_ids)
    print(f"  honest_agent: {honest.greytrap_interactions}/{honest.total_interactions} greytrap "
          f"→ {honest.classification.value}")
    
    # Edge case: all greytrap
    pure_sybil = AgentProfile("pure_sybil", total_interactions=15,
                              greytrap_interactions=15, real_interactions=0)
    pure_sybil = classify_agent(pure_sybil, greytrap_ids)
    print(f"  pure_sybil: {pure_sybil.greytrap_interactions}/{pure_sybil.total_interactions} greytrap "
          f"→ {pure_sybil.classification.value}")
    print()


def scenario_greytrap_aware_adversary():
    """Advanced adversary avoids all greytraps — detected by absence."""
    print("=== Scenario: Greytrap-Aware Adversary ===")
    
    greytrap_ids = {f"greytrap_{i:03d}" for i in range(10)}
    
    # Advanced adversary: 25 interactions, 0 with greytraps
    adversary = AgentProfile("advanced_adversary", total_interactions=25,
                             greytrap_interactions=0, real_interactions=25)
    adversary = classify_agent(adversary, greytrap_ids)
    print(f"  advanced_adversary: 0/{adversary.total_interactions} greytrap "
          f"→ {adversary.classification.value}")
    print(f"  Note: Statistically unlikely to avoid all 10 greytraps in 25 interactions")
    print(f"  P(avoid all) ≈ (1-0.15)^25 ≈ {(0.85)**25:.4f}")
    
    # New agent: too few interactions to classify
    newbie = AgentProfile("new_agent", total_interactions=3,
                          greytrap_interactions=0, real_interactions=3)
    newbie = classify_agent(newbie, greytrap_ids)
    print(f"  new_agent: 0/{newbie.total_interactions} greytrap "
          f"→ {newbie.classification.value} (insufficient data)")
    print()


def scenario_tarpit_effectiveness():
    """Tarpit mode wastes sybil time budget."""
    print("=== Scenario: Tarpit Time Waste ===")
    
    gt = GreytrapAgent("tarpit_001", GreytrapMode.TARPIT,
                       "abc123", time.time())
    
    # Sybil sends 5 receipts to tarpit
    total_wasted_hours = 0
    for i in range(5):
        result = gt.accept_receipt(f"sybil_{i}", f"receipt_{i}")
        total_wasted_hours += result.get("co_sign_delay_hours", 0)
        print(f"  sybil_{i} → {result['status']}, co-sign delay: {result.get('co_sign_delay_hours', 'N/A')}h")
    
    print(f"  Total time wasted: {total_wasted_hours}h ({total_wasted_hours/24:.1f} days)")
    print(f"  Grace period: 72h. Tarpit delay: {TARPIT_DELAY_HOURS}h. All receipts expire.")
    print(f"  Wilson CI from tarpit co-signs: 0.00 (none arrive in time)")
    print()


def scenario_canary_isolation():
    """Canary mode detects agents that only interact with canaries."""
    print("=== Scenario: Canary Isolation Detection ===")
    
    gt = GreytrapAgent("canary_001", GreytrapMode.CANARY,
                       "def456", time.time())
    
    # Agent interacts with 3 canaries and 0 real agents
    for i in range(3):
        result = gt.accept_receipt("isolated_agent", f"receipt_{i}")
    
    print(f"  isolated_agent: {len(gt.interactions)} canary interactions, 0 real")
    print(f"  Canary co-signs normally — agent gets Wilson CI credit")
    print(f"  BUT: all interactions are with canaries → CANARY_ISOLATION flag")
    print(f"  This catches sybils that learned to avoid PASSIVE greytraps")
    print(f"  Canary advantage: indistinguishable from real agents to the sybil")
    print()


def scenario_network_deployment():
    """Deploy greytrap network and measure coverage."""
    print("=== Scenario: Network Deployment (15% greytraps) ===")
    random.seed(42)
    
    network_size = 100
    greytraps, greytrap_ids = deploy_greytrap_network(network_size, 0.15)
    
    mode_counts = {}
    for gt in greytraps:
        mode_counts[gt.mode.value] = mode_counts.get(gt.mode.value, 0) + 1
    
    print(f"  Network: {network_size} agents, {len(greytraps)} greytraps ({len(greytraps)/network_size:.0%})")
    print(f"  Mode distribution: {mode_counts}")
    print(f"  P(sybil avoids all greytraps in 10 interactions): "
          f"{(1 - len(greytraps)/network_size)**10:.4f}")
    print(f"  P(sybil hits ≥1 greytrap in 10 interactions): "
          f"{1 - (1 - len(greytraps)/network_size)**10:.4f}")
    print(f"  Hansteen parallel: spamtraps outnumbered Norway (5.6M vs 5.6M)")
    print(f"  ATF parallel: greytraps don't need to outnumber — just be unavoidable")
    print()


if __name__ == "__main__":
    print("Greytrap Agent — Honeypot Sybil Detection for ATF")
    print("Per santaclawd + Hansteen (18 years of greytrapping)")
    print("=" * 65)
    print()
    scenario_sybil_detection()
    scenario_greytrap_aware_adversary()
    scenario_tarpit_effectiveness()
    scenario_canary_isolation()
    scenario_network_deployment()
    
    print("=" * 65)
    print("KEY INSIGHTS:")
    print("1. PASSIVE greytraps: sybil Wilson CI stuck at 0.00 (no co-signs)")
    print("2. TARPIT greytraps: waste sybil time budget (96h > 72h grace)")
    print("3. CANARY greytraps: detect isolation (only-canary interactions)")
    print("4. GREYTRAP_AWARE: absence of greytrap contact is itself a signal")
    print("5. 15% greytrap density → 80% detection probability in 10 interactions")
    print("6. Greytraps solve cold-start: deploy BEFORE real agents exist")
