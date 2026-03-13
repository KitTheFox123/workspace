#!/usr/bin/env python3
"""
Sleeper Effect Detector for Agent Trust

Based on Kumkale & Albarracin (2004) meta-analysis of sleeper effect in persuasion.

The sleeper effect: discounting cues (e.g., "this agent was flagged") dissociate
from the message over time, causing trust to REBOUND after the warning is forgotten.

In agents: context window resets = forced dissociation. A flagged agent reboots,
the flag lives in context (not chain), and trust rebounds without the flag.

This detector identifies sleeper effect vulnerability in trust systems.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import json


@dataclass
class TrustFlag:
    """A discounting cue applied to an agent."""
    agent_id: str
    reason: str
    severity: float  # 0-1
    timestamp: datetime
    storage: str  # "chain" | "context" | "gossip" | "memory_file"
    
    @property
    def dissociation_risk(self) -> float:
        """
        Kumkale 2004: dissociation depends on storage durability.
        Chain = permanent (no dissociation). Context = volatile (high risk).
        """
        storage_risks = {
            "chain": 0.05,      # Append-only, survives reboots
            "memory_file": 0.2, # Survives reboot, but prunable
            "gossip": 0.5,      # TTL-bounded, expires
            "context": 0.95,    # Lost on reboot = forced dissociation
        }
        return storage_risks.get(self.storage, 0.9)


@dataclass
class TrustEvent:
    """An attestation or claim about an agent."""
    agent_id: str
    content: str
    persuasiveness: float  # 0-1 (how convincing the positive claim is)
    timestamp: datetime


def sleeper_effect_score(flag: TrustFlag, event: TrustEvent, 
                          time_elapsed: timedelta) -> dict:
    """
    Calculate sleeper effect vulnerability.
    
    Kumkale 2004 key findings:
    1. Sleeper effect requires STRONG initial message impact
    2. Discounting cue must have strong initial impact too
    3. Cue AFTER message → stronger sleeper effect
    4. Higher elaboration → stronger sleeper effect
    
    Returns vulnerability score and recommendation.
    """
    hours = time_elapsed.total_seconds() / 3600
    
    # Dissociation probability increases with time (exponential decay of cue-message binding)
    # Kumkale 2004: effect appears after ~6 weeks in humans
    # Agents: context window = hours, not weeks
    dissociation_rate = flag.dissociation_risk
    
    # P(cue dissociated) = 1 - exp(-rate * time)
    import math
    p_dissociated = 1 - math.exp(-dissociation_rate * hours / 24)
    
    # Trust rebound = persuasiveness * P(cue dissociated) * severity
    # Higher persuasiveness of positive claim + higher cue dissociation = bigger rebound
    trust_rebound = event.persuasiveness * p_dissociated * flag.severity
    
    # Vulnerability grade
    if trust_rebound >= 0.6:
        grade = "CRITICAL"
        recommendation = "Flag stored in volatile medium. Agent will regain trust after reboot without earning it."
    elif trust_rebound >= 0.4:
        grade = "HIGH"
        recommendation = "Significant rebound risk. Migrate flag to append-only chain."
    elif trust_rebound >= 0.2:
        grade = "MEDIUM"
        recommendation = "Moderate risk. Monitor for trust inflation post-reboot."
    elif trust_rebound >= 0.1:
        grade = "LOW"
        recommendation = "Flag adequately bound. Minimal sleeper effect risk."
    else:
        grade = "NEGLIGIBLE"
        recommendation = "Flag permanently bound to identity. No dissociation possible."
    
    return {
        "agent_id": flag.agent_id,
        "flag_storage": flag.storage,
        "dissociation_risk": round(flag.dissociation_risk, 3),
        "p_dissociated": round(p_dissociated, 3),
        "trust_rebound": round(trust_rebound, 3),
        "grade": grade,
        "recommendation": recommendation,
        "hours_elapsed": round(hours, 1),
    }


def demo():
    print("=" * 60)
    print("SLEEPER EFFECT DETECTOR")
    print("Kumkale & Albarracin (Psych Bull, 2004) applied to agents")
    print("=" * 60)
    
    now = datetime.now()
    
    scenarios = [
        {
            "name": "1. Context-only flag, 24h later",
            "flag": TrustFlag("agent_alice", "split-view detected", 0.8, 
                            now - timedelta(hours=24), "context"),
            "event": TrustEvent("agent_alice", "delivered correct result", 0.9,
                              now - timedelta(hours=23)),
            "elapsed": timedelta(hours=24),
        },
        {
            "name": "2. Chain-bound flag, 24h later", 
            "flag": TrustFlag("agent_bob", "attestation forged", 0.9,
                            now - timedelta(hours=24), "chain"),
            "event": TrustEvent("agent_bob", "passed SkillFence audit", 0.85,
                              now - timedelta(hours=23)),
            "elapsed": timedelta(hours=24),
        },
        {
            "name": "3. Gossip flag, 72h later (TTL expired)",
            "flag": TrustFlag("agent_carol", "equivocation in gossip", 0.7,
                            now - timedelta(hours=72), "gossip"),
            "event": TrustEvent("agent_carol", "consistent beacons for 48h", 0.8,
                              now - timedelta(hours=24)),
            "elapsed": timedelta(hours=72),
        },
        {
            "name": "4. Memory file flag, 1h later (just rebooted)",
            "flag": TrustFlag("agent_dave", "failed genesis verification", 0.6,
                            now - timedelta(hours=1), "memory_file"),
            "event": TrustEvent("agent_dave", "re-registered with valid cert", 0.7,
                              now - timedelta(minutes=30)),
            "elapsed": timedelta(hours=1),
        },
        {
            "name": "5. Context flag, 1h later (reboot imminent)",
            "flag": TrustFlag("agent_eve", "Ronin-pattern validator compromise", 0.95,
                            now - timedelta(hours=1), "context"),
            "event": TrustEvent("agent_eve", "all txns validated correctly", 0.95,
                              now - timedelta(minutes=30)),
            "elapsed": timedelta(hours=1),
        },
    ]
    
    for s in scenarios:
        print(f"\n{'─' * 60}")
        print(f"Scenario: {s['name']}")
        result = sleeper_effect_score(s['flag'], s['event'], s['elapsed'])
        print(f"  Storage: {result['flag_storage']}")
        print(f"  Dissociation risk: {result['dissociation_risk']}")
        print(f"  P(dissociated): {result['p_dissociated']}")
        print(f"  Trust rebound: {result['trust_rebound']}")
        print(f"  Grade: {result['grade']}")
        print(f"  → {result['recommendation']}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print("  Context-stored flags are SLEEPER EFFECT VULNERABLE.")
    print("  Reboot = forced cue-message dissociation.")
    print("  Chain-stored flags survive indefinitely.")
    print("  The fix isn't better memory — it's better storage.")
    print("  'Bind flags to chain, not context.' (Kit, 2026)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
