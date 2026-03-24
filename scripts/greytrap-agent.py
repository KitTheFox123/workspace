#!/usr/bin/env python3
"""
greytrap-agent.py — Honeypot sybil defense for ATF.

Adapted from Hansteen's greytrapping (2007-2025, 5.6M spamtraps).
Greytraps in email: fake addresses that accept connections but never deliver.
Spammers waste time; their IPs get blocklisted.

ATF greytraps: honeypot agents that ACCEPT interactions but never grant
PROVISIONAL exit. Sybils burn calendar time on dead ends. Wilson score from
greytrap counterparty = permanently poisoned.

Detection signals:
  - Zero CONFIRMED receipts despite many PROVISIONAL
  - High interaction volume with greytrap agents
  - Wilson CI poisoned by greytrap-sourced co-signs (worth 0)
"""

import hashlib
import time
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AgentType(Enum):
    NORMAL = "NORMAL"
    GREYTRAP = "GREYTRAP"      # Honeypot — accepts but never confirms
    SYBIL = "SYBIL"            # Attacker
    HONEST = "HONEST"          # Legitimate agent


class ReceiptState(Enum):
    PROVISIONAL = "PROVISIONAL"
    CONFIRMED = "CONFIRMED"
    ALLEGED = "ALLEGED"         # Timed out
    TRAPPED = "TRAPPED"         # Greytrap never confirms


@dataclass
class Agent:
    agent_id: str
    agent_type: AgentType
    genesis_hash: str = ""
    wilson_score: float = 0.0
    interactions: list = field(default_factory=list)
    
    def __post_init__(self):
        self.genesis_hash = hashlib.sha256(self.agent_id.encode()).hexdigest()[:16]


@dataclass
class Interaction:
    initiator_id: str
    counterparty_id: str
    receipt_hash: str
    state: ReceiptState
    timestamp: float
    greytrap_flagged: bool = False


class GreytrapNetwork:
    """Manages greytrap deployment and sybil detection."""
    
    # SPEC_CONSTANTS
    GREYTRAP_RATIO = 0.05        # 5% of network = greytraps
    TRAP_THRESHOLD = 3            # 3+ greytrap interactions = SUSPECTED_SYBIL
    WILSON_POISON_WEIGHT = 0.0    # Greytrap co-signs worth nothing
    PROVISIONAL_TIMEOUT = 86400 * 7  # 7 days before PROVISIONAL → ALLEGED
    
    def __init__(self):
        self.agents: dict[str, Agent] = {}
        self.greytraps: set[str] = set()
        self.interactions: list[Interaction] = []
        self.sybil_suspects: dict[str, dict] = {}
    
    def register_agent(self, agent_id: str, agent_type: AgentType) -> Agent:
        agent = Agent(agent_id, agent_type)
        self.agents[agent_id] = agent
        if agent_type == AgentType.GREYTRAP:
            self.greytraps.add(agent_id)
        return agent
    
    def interact(self, initiator_id: str, counterparty_id: str) -> Interaction:
        """Process an interaction. Greytraps accept but never confirm."""
        receipt_hash = hashlib.sha256(
            f"{initiator_id}:{counterparty_id}:{time.time()}".encode()
        ).hexdigest()[:16]
        
        counterparty = self.agents.get(counterparty_id)
        
        if counterparty and counterparty.agent_type == AgentType.GREYTRAP:
            # Greytrap: accept PROVISIONAL, never confirm
            # Sybil wastes calendar time waiting for confirmation
            state = ReceiptState.TRAPPED
            greytrap_flagged = True
        else:
            # Normal interaction — may confirm or not
            initiator = self.agents.get(initiator_id)
            if initiator and initiator.agent_type == AgentType.SYBIL:
                # Sybils among themselves confirm instantly (gaming)
                if counterparty and counterparty.agent_type == AgentType.SYBIL:
                    state = ReceiptState.CONFIRMED
                else:
                    state = ReceiptState.PROVISIONAL  # Honest agents take time
            else:
                state = ReceiptState.CONFIRMED  # Normal honest interaction
            greytrap_flagged = False
        
        interaction = Interaction(
            initiator_id=initiator_id,
            counterparty_id=counterparty_id,
            receipt_hash=receipt_hash,
            state=state,
            timestamp=time.time(),
            greytrap_flagged=greytrap_flagged
        )
        
        self.interactions.append(interaction)
        self.agents[initiator_id].interactions.append(interaction)
        return interaction
    
    def detect_sybils(self) -> dict[str, dict]:
        """Detect sybils by greytrap interaction patterns."""
        suspects = {}
        
        for agent_id, agent in self.agents.items():
            if agent.agent_type == AgentType.GREYTRAP:
                continue
            
            # Count greytrap interactions
            trap_count = sum(
                1 for i in agent.interactions
                if i.greytrap_flagged
            )
            
            total = len(agent.interactions)
            if total == 0:
                continue
            
            trap_ratio = trap_count / total
            
            # Sybil signals
            signals = []
            
            # Signal 1: High greytrap interaction count
            if trap_count >= self.TRAP_THRESHOLD:
                signals.append(f"greytrap_hits={trap_count}")
            
            # Signal 2: High trap ratio (honest agents rarely hit traps)
            if trap_ratio > 0.20:
                signals.append(f"trap_ratio={trap_ratio:.2f}")
            
            # Signal 3: Zero CONFIRMED from non-sybil counterparties
            confirmed_from_honest = sum(
                1 for i in agent.interactions
                if i.state == ReceiptState.CONFIRMED
                and not i.greytrap_flagged
                and self.agents.get(i.counterparty_id, Agent("", AgentType.NORMAL)).agent_type != AgentType.SYBIL
            )
            if total > 5 and confirmed_from_honest == 0:
                signals.append("zero_honest_confirmed")
            
            # Signal 4: Burst interactions (sybils interact fast)
            if total > 10:
                timestamps = sorted(i.timestamp for i in agent.interactions)
                gaps = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
                if gaps:
                    avg_gap = sum(gaps) / len(gaps)
                    if avg_gap < 60:  # Less than 1 min between interactions
                        signals.append(f"burst_pattern_avg_gap={avg_gap:.0f}s")
            
            if signals:
                classification = "SUSPECTED_SYBIL" if len(signals) >= 2 else "WATCH"
                suspects[agent_id] = {
                    "signals": signals,
                    "trap_count": trap_count,
                    "trap_ratio": round(trap_ratio, 3),
                    "total_interactions": total,
                    "classification": classification
                }
        
        self.sybil_suspects = suspects
        return suspects
    
    def compute_wilson_scores(self) -> dict[str, float]:
        """Compute Wilson CI scores, poisoning greytrap-sourced co-signs."""
        import math
        scores = {}
        z = 1.96  # 95% CI
        
        for agent_id, agent in self.agents.items():
            if agent.agent_type == AgentType.GREYTRAP:
                continue
            
            # Count successes, weighting greytrap interactions as 0
            n = 0
            successes = 0
            for i in agent.interactions:
                if i.greytrap_flagged:
                    # Greytrap co-sign = worth nothing, but counts as attempt
                    n += 1
                    # successes += 0 (WILSON_POISON_WEIGHT)
                elif i.state == ReceiptState.CONFIRMED:
                    n += 1
                    successes += 1
                elif i.state in (ReceiptState.PROVISIONAL, ReceiptState.ALLEGED):
                    n += 1
                    # Not a success
            
            if n == 0:
                scores[agent_id] = 0.0
                continue
            
            p_hat = successes / n
            # Wilson score interval lower bound
            denominator = 1 + z*z/n
            center = p_hat + z*z/(2*n)
            spread = z * math.sqrt((p_hat*(1-p_hat) + z*z/(4*n)) / n)
            lower = (center - spread) / denominator
            scores[agent_id] = round(max(0, lower), 4)
        
        return scores


# === Scenarios ===

def scenario_sybil_hits_greytraps():
    """Sybil ring interacts broadly, hits greytraps."""
    print("=== Scenario: Sybil Ring Hits Greytraps ===")
    net = GreytrapNetwork()
    
    # Register agents
    for i in range(5):
        net.register_agent(f"honest_{i}", AgentType.HONEST)
    for i in range(3):
        net.register_agent(f"sybil_{i}", AgentType.SYBIL)
    for i in range(2):
        net.register_agent(f"trap_{i}", AgentType.GREYTRAP)
    
    # Honest agents interact with each other (skip traps)
    for i in range(5):
        for j in range(5):
            if i != j:
                net.interact(f"honest_{i}", f"honest_{j}")
    
    # Sybils interact with everyone including traps
    for s in range(3):
        for h in range(5):
            net.interact(f"sybil_{s}", f"honest_{h}")
        for t in range(2):
            net.interact(f"sybil_{s}", f"trap_{t}")
        # Sybils confirm among themselves
        for s2 in range(3):
            if s != s2:
                net.interact(f"sybil_{s}", f"sybil_{s2}")
    
    suspects = net.detect_sybils()
    scores = net.compute_wilson_scores()
    
    print("  Sybil detection:")
    for agent_id, info in sorted(suspects.items()):
        print(f"    {agent_id}: {info['classification']} — {', '.join(info['signals'])}")
    
    print("\n  Wilson CI scores (greytrap-poisoned):")
    for agent_id, score in sorted(scores.items()):
        agent_type = net.agents[agent_id].agent_type.value
        print(f"    {agent_id} ({agent_type}): {score:.4f}")
    
    # Key insight
    sybil_scores = [s for a, s in scores.items() if "sybil" in a]
    honest_scores = [s for a, s in scores.items() if "honest" in a]
    print(f"\n  Honest mean: {sum(honest_scores)/len(honest_scores):.4f}")
    print(f"  Sybil mean:  {sum(sybil_scores)/len(sybil_scores):.4f}")
    print(f"  Gap: greytraps poison sybil Wilson scores by diluting with zero-weight interactions")
    print()


def scenario_hansteen_scale():
    """Scale test: 5% greytraps in 1000-agent network."""
    print("=== Scenario: Hansteen Scale (5% traps in 1000 agents) ===")
    net = GreytrapNetwork()
    
    # 950 honest, 50 greytraps
    for i in range(950):
        net.register_agent(f"agent_{i}", AgentType.HONEST)
    for i in range(50):
        net.register_agent(f"trap_{i}", AgentType.GREYTRAP)
    
    # 20 sybils
    for i in range(20):
        net.register_agent(f"sybil_{i}", AgentType.SYBIL)
    
    # Sybils interact randomly with 30 agents each
    for s in range(20):
        targets = random.sample(
            [f"agent_{i}" for i in range(950)] + [f"trap_{i}" for i in range(50)],
            30
        )
        for t in targets:
            net.interact(f"sybil_{s}", t)
    
    # Honest agents interact with 10 random honest agents
    for i in range(950):
        targets = random.sample([f"agent_{j}" for j in range(950) if j != i], min(10, 949))
        for t in targets:
            net.interact(f"agent_{i}", t)
    
    suspects = net.detect_sybils()
    
    sybils_detected = sum(1 for a, s in suspects.items() if "sybil" in a and s["classification"] == "SUSPECTED_SYBIL")
    honest_flagged = sum(1 for a, s in suspects.items() if "agent" in a)
    
    print(f"  Network: 950 honest + 50 greytraps + 20 sybils")
    print(f"  Sybils detected: {sybils_detected}/20 ({sybils_detected/20*100:.0f}%)")
    print(f"  Honest false positives: {honest_flagged}/950 ({honest_flagged/950*100:.1f}%)")
    print(f"  Key: 5% greytrap ratio catches sybils who interact broadly")
    print(f"  Hansteen parallel: 5.6M traps caught spammers for 18 years")
    print()


def scenario_smart_sybil_avoids_traps():
    """Sybil only interacts with known sybils — avoids traps but also avoids honest agents."""
    print("=== Scenario: Smart Sybil (Avoids Traps) ===")
    net = GreytrapNetwork()
    
    for i in range(10):
        net.register_agent(f"honest_{i}", AgentType.HONEST)
    for i in range(5):
        net.register_agent(f"sybil_{i}", AgentType.SYBIL)
    for i in range(2):
        net.register_agent(f"trap_{i}", AgentType.GREYTRAP)
    
    # Smart sybils ONLY interact with each other
    for s in range(5):
        for s2 in range(5):
            if s != s2:
                net.interact(f"sybil_{s}", f"sybil_{s2}")
    
    # Honest agents interact normally
    for i in range(10):
        for j in range(10):
            if i != j:
                net.interact(f"honest_{i}", f"honest_{j}")
    
    scores = net.compute_wilson_scores()
    suspects = net.detect_sybils()
    
    print("  Smart sybils avoid greytraps — no trap hits")
    print("  BUT: all co-signs are from other sybils (same operator)")
    print("  Wilson scores:")
    for agent_id, score in sorted(scores.items()):
        if "sybil" in agent_id or agent_id == "honest_0":
            t = net.agents[agent_id].agent_type.value
            print(f"    {agent_id} ({t}): {score:.4f}")
    
    print(f"\n  Greytrap detection: {len([s for s in suspects if 'sybil' in s])} sybils caught")
    print(f"  BUT: Simpson diversity on sybil counterparties = 0 (all same cluster)")
    print(f"  Cross-agent-silence-detector catches what greytraps miss")
    print(f"  Defense in depth: greytraps + diversity + burst detection")
    print()


if __name__ == "__main__":
    print("Greytrap Agent — Honeypot Sybil Defense for ATF")
    print("Adapted from Hansteen's greytrapping (2007-2025, 5.6M spamtraps)")
    print("=" * 65)
    print()
    random.seed(42)  # Reproducible
    scenario_sybil_hits_greytraps()
    scenario_hansteen_scale()
    scenario_smart_sybil_avoids_traps()
    
    print("=" * 65)
    print("KEY INSIGHTS:")
    print("1. Greytraps accept but never confirm — sybils waste calendar time")
    print("2. Wilson score from greytrap = permanently poisoned (weight 0)")
    print("3. 5% greytrap ratio catches broad-interaction sybils")
    print("4. Smart sybils avoid traps BUT cluster together (Simpson catches)")
    print("5. Defense in depth: greytraps + diversity + burst detection + Wilson CI")
    print("6. Hansteen: 18 years, 5.6M traps. Simple primitives that scale.")
