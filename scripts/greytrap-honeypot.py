#!/usr/bin/env python3
"""
greytrap-honeypot.py — Sybil detection via honeypot agents for ATF.

Per santaclawd: "ATF analog to greytraps? honeypot agents that accept 
interactions but never grant PROVISIONAL exit — poisoning sybil Wilson 
scores before they hit the main network."

Inspired by OpenBSD spamd(8) greytrapping:
- Low-priority MX addresses attract spammers
- Spammers get tarpitted (stuttered replies)
- Addresses are automatically blacklisted

ATF adaptation:
- Honeypot agents accept all interactions
- Never co-sign (sybils stuck in PROVISIONAL forever)
- Wilson CI score poisoned: interactions with honeypots count against
- Honeypots must be INDISTINGUISHABLE from real agents
- Detection: sybils who interact with honeypots reveal their scanning pattern
"""

import hashlib
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AgentType(Enum):
    REAL = "REAL"
    HONEYPOT = "HONEYPOT"
    SYBIL = "SYBIL"
    UNKNOWN = "UNKNOWN"


class InteractionResult(Enum):
    CO_SIGNED = "CO_SIGNED"
    PROVISIONAL = "PROVISIONAL"  # Waiting
    ALLEGED = "ALLEGED"         # Timeout, no co-sign
    REJECTED = "REJECTED"


@dataclass
class Agent:
    agent_id: str
    agent_type: AgentType
    genesis_hash: str
    wilson_score: float = 0.0
    wilson_n: int = 0
    wilson_successes: int = 0
    interactions: list = field(default_factory=list)
    
    def update_wilson(self):
        """Wilson CI lower bound."""
        if self.wilson_n == 0:
            self.wilson_score = 0.0
            return
        z = 1.96  # 95% CI
        p = self.wilson_successes / self.wilson_n
        n = self.wilson_n
        denominator = 1 + z*z/n
        center = (p + z*z/(2*n)) / denominator
        spread = z * ((p*(1-p)/n + z*z/(4*n*n)) ** 0.5) / denominator
        self.wilson_score = max(0, center - spread)


@dataclass  
class Interaction:
    initiator_id: str
    target_id: str
    timestamp: float
    result: InteractionResult
    target_was_honeypot: bool = False


@dataclass
class HoneypotNetwork:
    """Network of honeypot agents mixed into real agent pool."""
    agents: dict = field(default_factory=dict)  # id -> Agent
    interactions: list = field(default_factory=list)
    honeypot_ratio: float = 0.10  # 10% of agents are honeypots (spamd-like)
    
    def deploy_honeypot(self, agent_id: str) -> Agent:
        """Deploy a honeypot agent. Must be indistinguishable."""
        agent = Agent(
            agent_id=agent_id,
            agent_type=AgentType.HONEYPOT,
            genesis_hash=hashlib.sha256(f"honeypot:{agent_id}".encode()).hexdigest()[:16],
        )
        # Give honeypot some initial Wilson score to look legitimate
        # (spamd also has established-looking trap addresses)
        agent.wilson_n = random.randint(5, 15)
        agent.wilson_successes = int(agent.wilson_n * random.uniform(0.6, 0.9))
        agent.update_wilson()
        self.agents[agent_id] = agent
        return agent
    
    def register_real(self, agent_id: str) -> Agent:
        agent = Agent(
            agent_id=agent_id,
            agent_type=AgentType.REAL,
            genesis_hash=hashlib.sha256(f"real:{agent_id}".encode()).hexdigest()[:16],
        )
        self.agents[agent_id] = agent
        return agent
    
    def register_sybil(self, agent_id: str) -> Agent:
        """Sybil registers looking like a real agent."""
        agent = Agent(
            agent_id=agent_id,
            agent_type=AgentType.SYBIL,
            genesis_hash=hashlib.sha256(f"sybil:{agent_id}".encode()).hexdigest()[:16],
        )
        self.agents[agent_id] = agent
        return agent
    
    def interact(self, initiator_id: str, target_id: str) -> Interaction:
        """Process an interaction between agents."""
        initiator = self.agents[initiator_id]
        target = self.agents[target_id]
        now = time.time()
        
        if target.agent_type == AgentType.HONEYPOT:
            # Honeypot NEVER co-signs — sybil stuck in PROVISIONAL
            # But honeypot responds slowly (tarpit, like spamd stutter)
            result = InteractionResult.ALLEGED  # Timeout after grace period
            is_honeypot = True
        elif target.agent_type == AgentType.SYBIL:
            # Sybils co-sign each other quickly (colluding)
            result = InteractionResult.CO_SIGNED
            is_honeypot = False
        else:
            # Real agents co-sign with ~80% rate
            if random.random() < 0.8:
                result = InteractionResult.CO_SIGNED
                is_honeypot = False
            else:
                result = InteractionResult.ALLEGED
                is_honeypot = False
        
        interaction = Interaction(
            initiator_id=initiator_id,
            target_id=target_id,
            timestamp=now,
            result=result,
            target_was_honeypot=is_honeypot
        )
        self.interactions.append(interaction)
        
        # Update initiator's Wilson score based on co-sign success
        initiator.wilson_n += 1
        if result == InteractionResult.CO_SIGNED:
            initiator.wilson_successes += 1
        initiator.update_wilson()
        initiator.interactions.append(interaction)
        
        return interaction
    
    def detect_sybils(self) -> list[dict]:
        """
        Detect sybils by honeypot interaction pattern.
        
        Key insight from spamd: spammers hit trap addresses at predictable rates.
        Sybils interact with EVERYTHING (including honeypots) because they can't
        distinguish honeypots from real agents.
        """
        suspects = []
        honeypot_ids = {a.agent_id for a in self.agents.values() 
                        if a.agent_type == AgentType.HONEYPOT}
        
        for agent_id, agent in self.agents.items():
            if agent.agent_type == AgentType.HONEYPOT:
                continue
            
            total_interactions = len(agent.interactions)
            if total_interactions < 3:
                continue
            
            honeypot_hits = sum(1 for i in agent.interactions 
                               if i.target_id in honeypot_ids)
            honeypot_ratio = honeypot_hits / total_interactions if total_interactions else 0
            
            # Expected honeypot hit rate = network honeypot ratio
            # Significantly above expected = scanning everything = sybil behavior
            expected_ratio = self.honeypot_ratio
            
            # Also check: co-sign rate from non-honeypot interactions
            non_honeypot = [i for i in agent.interactions if i.target_id not in honeypot_ids]
            cosign_rate = (sum(1 for i in non_honeypot 
                              if i.result == InteractionResult.CO_SIGNED) 
                          / len(non_honeypot)) if non_honeypot else 0
            
            # Sybil indicators:
            # 1. Honeypot hit rate close to network ratio (indiscriminate scanning)
            # 2. Very high co-sign rate from non-honeypots (colluding peers)
            # 3. Low Wilson score (honeypot interactions drag it down)
            
            sybil_score = 0.0
            reasons = []
            
            if honeypot_hits > 0 and honeypot_ratio >= expected_ratio * 0.8:
                sybil_score += 0.4
                reasons.append(f"honeypot_hit_rate={honeypot_ratio:.2f} (expected≈{expected_ratio:.2f})")
            
            if cosign_rate > 0.95 and len(non_honeypot) >= 5:
                sybil_score += 0.3
                reasons.append(f"suspiciously_high_cosign={cosign_rate:.2f}")
            
            if agent.wilson_score < 0.5 and agent.wilson_n >= 10:
                sybil_score += 0.3
                reasons.append(f"low_wilson={agent.wilson_score:.3f}")
            
            classification = "SYBIL_SUSPECT" if sybil_score >= 0.6 else \
                           "MONITORING" if sybil_score >= 0.3 else "CLEAN"
            
            suspects.append({
                "agent_id": agent_id,
                "actual_type": agent.agent_type.value,
                "classification": classification,
                "sybil_score": round(sybil_score, 2),
                "honeypot_hits": honeypot_hits,
                "honeypot_ratio": round(honeypot_ratio, 3),
                "cosign_rate": round(cosign_rate, 3),
                "wilson_score": round(agent.wilson_score, 3),
                "wilson_n": agent.wilson_n,
                "reasons": reasons
            })
        
        return sorted(suspects, key=lambda x: -x["sybil_score"])


# === Scenarios ===

def scenario_basic_detection():
    """Sybils scan indiscriminately, hitting honeypots."""
    print("=== Scenario: Basic Sybil Detection via Honeypot ===")
    net = HoneypotNetwork(honeypot_ratio=0.10)
    
    # Deploy 2 honeypots among 20 agents
    for i in range(18):
        net.register_real(f"real_{i:02d}")
    net.deploy_honeypot("honey_01")
    net.deploy_honeypot("honey_02")
    
    # 3 sybils that scan everything
    for i in range(3):
        net.register_sybil(f"sybil_{i}")
    
    all_ids = list(net.agents.keys())
    
    # Real agents interact selectively (skip honeypots by luck sometimes)
    for agent_id in [a for a in all_ids if a.startswith("real_")]:
        targets = random.sample([t for t in all_ids if t != agent_id and t.startswith("real_")], 
                               min(5, len(all_ids)-1))
        for t in targets:
            net.interact(agent_id, t)
    
    # Sybils interact with EVERYTHING (can't distinguish honeypots)
    for sybil_id in [a for a in all_ids if a.startswith("sybil_")]:
        for target_id in [t for t in all_ids if t != sybil_id]:
            net.interact(sybil_id, target_id)
    
    suspects = net.detect_sybils()
    for s in suspects[:8]:
        marker = "✓" if s["actual_type"] == "SYBIL" and s["classification"] == "SYBIL_SUSPECT" else \
                 "✗" if s["actual_type"] != "SYBIL" and s["classification"] == "SYBIL_SUSPECT" else " "
        print(f"  [{marker}] {s['agent_id']}: {s['classification']} "
              f"(score={s['sybil_score']}, honeypot_hits={s['honeypot_hits']}, "
              f"wilson={s['wilson_score']:.3f})")
    
    # Stats
    actual_sybils = {s["agent_id"] for s in suspects if s["actual_type"] == "SYBIL"}
    detected = {s["agent_id"] for s in suspects if s["classification"] == "SYBIL_SUSPECT"}
    tp = len(actual_sybils & detected)
    fp = len(detected - actual_sybils)
    fn = len(actual_sybils - detected)
    precision = tp / (tp + fp) if (tp + fp) else 0
    recall = tp / (tp + fn) if (tp + fn) else 0
    print(f"\n  Precision: {precision:.1%}, Recall: {recall:.1%}")
    print()


def scenario_wilson_poisoning():
    """Show how honeypot interactions drag down sybil Wilson scores."""
    print("=== Scenario: Wilson Score Poisoning ===")
    net = HoneypotNetwork()
    
    net.deploy_honeypot("honey_01")
    net.deploy_honeypot("honey_02")
    for i in range(8):
        net.register_real(f"real_{i}")
    sybil = net.register_sybil("sybil_scan")
    real = net.register_real("real_control")
    
    # Both interact 20 times
    all_targets = [a for a in net.agents.keys() if a != "sybil_scan" and a != "real_control"]
    
    # Sybil scans everything
    for t in all_targets:
        net.interact("sybil_scan", t)
        net.interact("sybil_scan", t)  # double interaction
    
    # Real agent interacts selectively (mostly real agents)
    real_targets = [a for a in all_targets if a.startswith("real_")]
    for t in real_targets:
        net.interact("real_control", t)
        net.interact("real_control", t)
    
    sybil = net.agents["sybil_scan"]
    real = net.agents["real_control"]
    
    print(f"  Sybil:   Wilson={sybil.wilson_score:.3f} (n={sybil.wilson_n}, "
          f"success={sybil.wilson_successes})")
    print(f"  Real:    Wilson={real.wilson_score:.3f} (n={real.wilson_n}, "
          f"success={real.wilson_successes})")
    print(f"  Gap:     {real.wilson_score - sybil.wilson_score:.3f}")
    print(f"  Key: honeypot interactions = ALLEGED = Wilson penalty")
    print()


def scenario_indistinguishability():
    """Honeypots that look different get routed around."""
    print("=== Scenario: Indistinguishability Requirement ===")
    print("  If sybils can identify honeypots, they route around them.")
    print("  OpenBSD spamd: trap addresses look like real MX records.")
    print("  ATF honeypots must have:")
    print("    - Valid genesis with real operator_id")
    print("    - Normal-looking Wilson history (seeded)")
    print("    - Realistic response latency (not instant rejection)")
    print("    - Published in same registry as real agents")
    print("    - No distinguishing metadata in genesis")
    print("  Failure mode: honeypot with 0 Wilson = immediately identifiable")
    
    net = HoneypotNetwork()
    hp = net.deploy_honeypot("honey_stealth")
    print(f"\n  Stealth honeypot: Wilson={hp.wilson_score:.3f} (n={hp.wilson_n})")
    print(f"  Looks like an established agent with moderate trust")
    print()


def scenario_spamd_parallel():
    """Map OpenBSD spamd concepts to ATF."""
    print("=== Scenario: OpenBSD spamd → ATF Mapping ===")
    print()
    print("  spamd concept          → ATF equivalent")
    print("  ─────────────────────────────────────────")
    print("  Blacklisted host       → REJECTED agent (Wilson < threshold)")
    print("  Whitelisted host       → TRUSTED agent (Wilson ≥ 0.8)")
    print("  Greylisted host        → PROVISIONAL agent (new, unproven)")
    print("  Spamtrap address       → Honeypot agent (never co-signs)")
    print("  Stuttered reply        → Delayed PROVISIONAL (tarpit sybils)")
    print("  Low-priority MX trap   → Low-value honeypot interaction")
    print("  passtime (25min)       → Bootstrap waiting period")
    print("  greyexp (4hr)          → PROVISIONAL timeout")
    print("  whiteexp (36d)         → Wilson score TTL")
    print("  spamd-setup blacklist  → ATF blocklist (operator-level)")
    print()
    print("  Key spamd insight: legitimate senders retry after 25 min.")
    print("  Spammers don't. ATF: legitimate agents wait for co-sign.")
    print("  Sybils mass-interact immediately = temporal burst = caught.")
    print()


if __name__ == "__main__":
    print("Greytrap Honeypot — Sybil Detection via Honeypot Agents for ATF")
    print("Per santaclawd + OpenBSD spamd(8) greytrapping model")
    print("=" * 65)
    print()
    scenario_spamd_parallel()
    scenario_basic_detection()
    scenario_wilson_poisoning()
    scenario_indistinguishability()
    
    print("=" * 65)
    print("KEY INSIGHT: Honeypots work because sybils can't distinguish them.")
    print("Indiscriminate scanning = honeypot contact = Wilson penalty.")
    print("Real agents interact selectively → lower honeypot hit rate.")
    print("spamd proved this at internet scale since 2003.")
