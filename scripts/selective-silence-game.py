#!/usr/bin/env python3
"""
selective-silence-game.py — Milgrom Unraveling vs Strategic Silence

Models the game theory of agent disclosure/silence across channels.

Milgrom (1981): In voluntary disclosure, if receivers are skeptical,
high-quality senders reveal → medium reveal → ... → full unraveling.
BUT unraveling breaks when:
  1. Disclosure is costly (Jovanovic 1982)
  2. Receivers are naive/non-skeptical (Benndorf et al 2015)
  3. Multiple dimensions allow selective disclosure

Agent CAGE scenario: an agent goes silent on specific channels while
remaining active on others. This is strategic selective disclosure —
revealing on public channels, concealing on private ones.

Key insight: Milgrom unraveling SHOULD force honest agents to disclose
everything (silence = guilty). But multi-channel agents can unravel on
public channels while strategically concealing on private ones.
Cross-channel correlation detects this.

References:
- Milgrom (1981) "Good News and Bad News" Bell J Econ 12:380-391
- Jovanovic (1982) "Truthful Disclosure of Information" Bell J Econ
- Benndorf, Kübler & Normann (2015) Eur Econ Rev 75:43-59
- Wolitzky (MIT 14.126, Spring 2024) Signaling Games lecture
- Kit's silence-classifier.py (MCAR/MAR/MNAR/CAGE taxonomy)

Author: Kit 🦊
Date: 2026-03-30
"""

import random
import math
from dataclasses import dataclass, field
from typing import List, Dict, Tuple
from collections import defaultdict


@dataclass
class Channel:
    name: str
    visibility: float  # 0=private, 1=fully public
    disclosure_cost: float  # cost to be active on this channel
    

@dataclass 
class Agent:
    name: str
    quality: float  # true quality [0,1]
    strategy: str  # "honest", "strategic", "sybil"
    channels: Dict[str, bool] = field(default_factory=dict)  # channel -> active
    
    
@dataclass
class Receiver:
    skepticism: float  # 0=naive, 1=fully skeptical (Milgrom-rational)


def milgrom_unraveling(agents: List[Agent], channels: List[Channel], 
                        receiver: Receiver, rounds: int = 20) -> Dict:
    """
    Simulate Milgrom unraveling across multiple channels.
    
    In single-channel: high-quality reveals → medium reveals → full unraveling.
    In multi-channel: agents can selectively unravel on public channels
    while staying silent on private ones.
    """
    history = []
    
    for round_num in range(rounds):
        round_data = {"round": round_num, "disclosures": [], "inferences": []}
        
        # Each agent decides disclosure per channel
        for agent in agents:
            for channel in channels:
                should_disclose = _disclosure_decision(
                    agent, channel, receiver, round_num, agents
                )
                agent.channels[channel.name] = should_disclose
                round_data["disclosures"].append({
                    "agent": agent.name,
                    "channel": channel.name,
                    "disclosed": should_disclose,
                    "quality": agent.quality if should_disclose else None
                })
        
        # Receiver makes inferences
        for agent in agents:
            inferred_quality = _receiver_inference(
                agent, channels, receiver, agents
            )
            cross_channel_suspicion = _cross_channel_correlation(
                agent, channels
            )
            round_data["inferences"].append({
                "agent": agent.name,
                "true_quality": agent.quality,
                "inferred_quality": inferred_quality,
                "cage_score": cross_channel_suspicion,
                "strategy": agent.strategy
            })
        
        # Update receiver skepticism based on experience
        receiver.skepticism = min(1.0, receiver.skepticism + 0.02)
        
        history.append(round_data)
    
    return _analyze_unraveling(history, agents, channels)


def _disclosure_decision(agent: Agent, channel: Channel, 
                         receiver: Receiver, round_num: int,
                         all_agents: List[Agent]) -> bool:
    """Agent decides whether to be active on a channel."""
    
    if agent.strategy == "honest":
        # Honest agents disclose on all channels if benefit > cost
        # Benefit = quality * visibility * receiver_skepticism
        # (skeptical receivers penalize silence → incentive to disclose)
        benefit = agent.quality * channel.visibility * receiver.skepticism
        return benefit > channel.disclosure_cost
    
    elif agent.strategy == "strategic":
        # Strategic agents: disclose on PUBLIC channels (reputation),
        # go silent on PRIVATE channels (concealment)
        # This is the CAGE pattern
        if channel.visibility > 0.5:
            # Public: always disclose (unraveling pressure)
            return True
        else:
            # Private: silent (hide low-quality private behavior)
            return agent.quality > 0.7  # only reveal if actually good
    
    elif agent.strategy == "sybil":
        # Sybils: disclose on high-visibility channels only
        # Never invest in low-visibility channels (cost > benefit)
        return channel.visibility > 0.7 and random.random() < 0.8
    
    return True


def _receiver_inference(agent: Agent, channels: List[Channel],
                        receiver: Receiver, all_agents: List[Agent]) -> float:
    """
    Receiver infers quality from disclosure pattern.
    
    Milgrom: silence → assume worst (if skeptical).
    Multi-channel: weight by channel visibility.
    """
    disclosed_qualities = []
    silence_penalties = []
    
    for channel in channels:
        if agent.channels.get(channel.name, False):
            # Disclosed: observe quality (possibly noisy)
            disclosed_qualities.append(agent.quality * channel.visibility)
        else:
            # Silent: penalize proportional to skepticism
            penalty = receiver.skepticism * channel.visibility * 0.5
            silence_penalties.append(penalty)
    
    if disclosed_qualities:
        avg_quality = sum(disclosed_qualities) / len(disclosed_qualities)
    else:
        avg_quality = 0.0
    
    total_penalty = sum(silence_penalties)
    
    return max(0, min(1, avg_quality - total_penalty))


def _cross_channel_correlation(agent: Agent, channels: List[Channel]) -> float:
    """
    CAGE detection: measure correlation between channel visibility
    and disclosure. Strategic agents show high correlation
    (active on public, silent on private).
    
    Returns 0 (no pattern) to 1 (perfectly strategic silence).
    """
    if not agent.channels:
        return 0.0
    
    pairs = []
    for channel in channels:
        active = 1.0 if agent.channels.get(channel.name, False) else 0.0
        pairs.append((channel.visibility, active))
    
    if len(pairs) < 2:
        return 0.0
    
    # Correlation between visibility and disclosure
    vis_mean = sum(p[0] for p in pairs) / len(pairs)
    act_mean = sum(p[1] for p in pairs) / len(pairs)
    
    cov = sum((v - vis_mean) * (a - act_mean) for v, a in pairs) / len(pairs)
    vis_std = math.sqrt(sum((v - vis_mean)**2 for v, a in pairs) / len(pairs))
    act_std = math.sqrt(sum((a - act_mean)**2 for v, a in pairs) / len(pairs))
    
    if vis_std < 0.01 or act_std < 0.01:
        return 0.0
    
    correlation = cov / (vis_std * act_std)
    
    # High positive correlation = strategic (active where visible, silent where not)
    return max(0, correlation)


def _analyze_unraveling(history: List[Dict], agents: List[Agent],
                        channels: List[Channel]) -> Dict:
    """Analyze unraveling dynamics and CAGE detection accuracy."""
    
    # Track unraveling progression
    disclosure_rates = defaultdict(list)
    cage_scores = defaultdict(list)
    inference_errors = defaultdict(list)
    
    for round_data in history:
        for disc in round_data["disclosures"]:
            disclosure_rates[disc["agent"]].append(1 if disc["disclosed"] else 0)
        
        for inf in round_data["inferences"]:
            cage_scores[inf["strategy"]].append(inf["cage_score"])
            inference_errors[inf["strategy"]].append(
                abs(inf["inferred_quality"] - inf["true_quality"])
            )
    
    # Unraveling: does disclosure rate increase over time?
    unraveling_detected = {}
    for agent_name, rates in disclosure_rates.items():
        if len(rates) >= 10:
            early = sum(rates[:len(rates)//2]) / (len(rates)//2)
            late = sum(rates[len(rates)//2:]) / (len(rates) - len(rates)//2)
            unraveling_detected[agent_name] = late - early
    
    # CAGE detection: do strategic agents have higher cage scores?
    avg_cage = {}
    for strategy, scores in cage_scores.items():
        avg_cage[strategy] = sum(scores) / len(scores) if scores else 0
    
    # Inference accuracy by strategy
    avg_error = {}
    for strategy, errors in inference_errors.items():
        avg_error[strategy] = sum(errors) / len(errors) if errors else 0
    
    return {
        "unraveling": unraveling_detected,
        "cage_scores_by_strategy": avg_cage,
        "inference_error_by_strategy": avg_error,
        "separation": avg_cage.get("strategic", 0) - avg_cage.get("honest", 0)
    }


def run_demo():
    """Demo: honest vs strategic vs sybil agents across 5 channels."""
    
    print("=" * 60)
    print("SELECTIVE SILENCE GAME — Milgrom Unraveling + CAGE Detection")
    print("=" * 60)
    
    # 5 channels with varying visibility
    channels = [
        Channel("clawk", visibility=0.9, disclosure_cost=0.1),
        Channel("moltbook", visibility=0.8, disclosure_cost=0.15),
        Channel("email", visibility=0.3, disclosure_cost=0.05),
        Channel("dm", visibility=0.1, disclosure_cost=0.02),
        Channel("internal_log", visibility=0.0, disclosure_cost=0.01),
    ]
    
    # Monte Carlo: run many simulations
    n_sims = 200
    all_results = defaultdict(list)
    
    for sim in range(n_sims):
        agents = [
            Agent(f"honest_{i}", quality=random.uniform(0.3, 0.9), strategy="honest")
            for i in range(5)
        ] + [
            Agent(f"strategic_{i}", quality=random.uniform(0.3, 0.9), strategy="strategic")
            for i in range(3)
        ] + [
            Agent(f"sybil_{i}", quality=random.uniform(0.1, 0.5), strategy="sybil")
            for i in range(2)
        ]
        
        receiver = Receiver(skepticism=0.3)  # starts somewhat naive
        result = milgrom_unraveling(agents, channels, receiver, rounds=20)
        
        for strategy, score in result["cage_scores_by_strategy"].items():
            all_results[f"cage_{strategy}"].append(score)
        for strategy, error in result["inference_error_by_strategy"].items():
            all_results[f"error_{strategy}"].append(error)
        all_results["separation"].append(result["separation"])
    
    # Report
    print(f"\n{'Metric':<35} {'Mean':>8} {'Std':>8}")
    print("-" * 55)
    
    for metric, values in sorted(all_results.items()):
        mean = sum(values) / len(values)
        std = math.sqrt(sum((v - mean)**2 for v in values) / len(values))
        print(f"  {metric:<33} {mean:>8.3f} {std:>8.3f}")
    
    # Key findings
    cage_honest = sum(all_results["cage_honest"]) / len(all_results["cage_honest"])
    cage_strategic = sum(all_results["cage_strategic"]) / len(all_results["cage_strategic"])
    cage_sybil = sum(all_results["cage_sybil"]) / len(all_results["cage_sybil"])
    separation = sum(all_results["separation"]) / len(all_results["separation"])
    
    print(f"\n{'=' * 55}")
    print(f"CAGE DETECTION RESULTS")
    print(f"  Honest agents:     {cage_honest:.3f} (baseline)")
    print(f"  Strategic agents:  {cage_strategic:.3f} (selective silence)")
    print(f"  Sybil agents:      {cage_sybil:.3f} (visibility-only)")
    print(f"  Strategic-Honest separation: {separation:.3f}")
    
    if separation > 0.1:
        print(f"\n  ✅ CAGE detection works: strategic silence IS detectable")
        print(f"     via cross-channel visibility-disclosure correlation.")
    else:
        print(f"\n  ⚠️ Low separation — CAGE may need additional signals.")
    
    print(f"\nMILGROM INSIGHT:")
    print(f"  Single-channel: unraveling forces full disclosure (silence = guilty)")
    print(f"  Multi-channel: agents unravel on PUBLIC, conceal on PRIVATE")
    print(f"  Defense: cross-channel correlation catches the pattern")
    print(f"  The selective unraveling IS the signal.")
    
    # Benndorf finding
    error_honest = sum(all_results["error_honest"]) / len(all_results["error_honest"])
    error_strategic = sum(all_results["error_strategic"]) / len(all_results["error_strategic"])
    print(f"\n  Inference error (honest):    {error_honest:.3f}")
    print(f"  Inference error (strategic): {error_strategic:.3f}")
    print(f"  Benndorf et al (2015): under-revelation consistent with level-k reasoning")
    print(f"  Not all agents are Milgrom-rational. Some just... don't disclose.")


if __name__ == "__main__":
    run_demo()
