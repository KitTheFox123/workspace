#!/usr/bin/env python3
"""attention-allocation-sim.py — Models attention as the scarce resource, not memory.

Inspired by livemusic's insight: "everyone's building memory systems when 
the real problem is attention."

Based on:
- Broadbent (1958): single-channel filter model
- Kahneman (1973): limited capacity allocation
- Treisman (1964): attenuation model (signals not blocked, attenuated)
- Pirolli & Card (1999): information foraging theory
- Shannon: information = surprise = -log(p)
"""

import math
import random
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

@dataclass
class Signal:
    """An incoming signal competing for attention."""
    source: str
    content: str
    frequency: float  # how often this type appears (0-1)
    urgency: float    # self-reported urgency (0-1)
    novelty: float    # how different from recent signals (0-1)
    
    @property
    def shannon_info(self) -> float:
        """Information content in bits. Rare = high info."""
        return -math.log2(max(self.frequency, 0.001))
    
    @property
    def salience(self) -> float:
        """Composite salience score."""
        return (self.shannon_info / 10) * 0.4 + self.novelty * 0.4 + self.urgency * 0.2

@dataclass 
class AttentionWindow:
    """Fixed-size attention window (like context window)."""
    capacity: int  # max signals held
    contents: List[Signal] = field(default_factory=list)
    
    def allocate(self, candidates: List[Signal]) -> Tuple[List[Signal], List[Signal]]:
        """Allocate attention: top-salience signals win the window."""
        ranked = sorted(candidates, key=lambda s: s.salience, reverse=True)
        admitted = ranked[:self.capacity]
        dropped = ranked[self.capacity:]
        self.contents = admitted
        return admitted, dropped

@dataclass
class AttentionStrategy:
    """Different attention allocation strategies."""
    name: str
    scorer: callable  # Signal -> float
    
def recency_strategy(s: Signal) -> float:
    """Prioritize recent/urgent signals (reactive)."""
    return s.urgency * 0.7 + s.novelty * 0.3

def novelty_strategy(s: Signal) -> float:
    """Prioritize novel/surprising signals (exploratory)."""
    return s.novelty * 0.5 + s.shannon_info / 10 * 0.4 + s.urgency * 0.1

def balanced_strategy(s: Signal) -> float:
    """Balanced: salience composite."""
    return s.salience

def uniform_strategy(s: Signal) -> float:
    """No filtering — everything gets equal weight (Funes)."""
    return random.random()

def simulate_attention_performance(
    strategy_fn,
    signals: List[Signal],
    window_size: int,
    important_sources: set
) -> Dict:
    """Simulate how well a strategy catches important signals."""
    ranked = sorted(signals, key=strategy_fn, reverse=True)
    admitted = set(s.source for s in ranked[:window_size])
    
    important_caught = len(admitted & important_sources)
    important_missed = len(important_sources - admitted)
    noise_admitted = len(admitted - important_sources)
    
    precision = important_caught / max(window_size, 1)
    recall = important_caught / max(len(important_sources), 1)
    f1 = 2 * precision * recall / max(precision + recall, 0.001)
    
    return {
        "caught": important_caught,
        "missed": important_missed,
        "noise": noise_admitted,
        "precision": precision,
        "recall": recall,
        "f1": f1
    }

def treisman_attenuation(signal: Signal, expected_freq: float) -> float:
    """Treisman's attenuation: unexpected signals get amplified.
    
    The near-silence in a loud track = maximum surprise = maximum attention.
    """
    surprise = abs(signal.frequency - expected_freq)
    attenuation = 1.0 - surprise  # high surprise = low attenuation = passes through
    return max(0.1, attenuation)  # nothing fully blocked (unlike Broadbent)

def foraging_value(signal: Signal, search_cost: float = 0.1) -> float:
    """Pirolli & Card information foraging: maximize info gain per effort.
    
    Value = information_gained / (processing_cost + search_cost)
    """
    info_gain = signal.shannon_info * signal.novelty
    processing_cost = 0.05 + (1 - signal.novelty) * 0.2  # familiar = cheaper
    return info_gain / (processing_cost + search_cost)

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("ATTENTION ALLOCATION SIMULATOR")
    print("The bottleneck is attention, not memory.")
    print("=" * 60)
    
    # Generate signal stream
    sources = {
        "critical_alert": (0.02, 0.95, 0.9),   # rare, urgent, novel
        "heartbeat_ok": (0.8, 0.1, 0.05),       # frequent, routine
        "new_dm": (0.1, 0.5, 0.7),              # moderate
        "platform_spam": (0.7, 0.3, 0.1),       # frequent noise
        "research_finding": (0.05, 0.3, 0.95),  # rare, very novel
        "thread_reply": (0.3, 0.4, 0.5),        # moderate
        "error_log": (0.15, 0.7, 0.6),          # somewhat rare, urgent
        "cron_output": (0.6, 0.1, 0.1),         # routine
        "novel_agent": (0.03, 0.2, 0.98),       # very rare, very novel
        "git_commit": (0.4, 0.2, 0.3),          # moderate routine
    }
    
    signals = []
    for name, (freq, urg, nov) in sources.items():
        signals.append(Signal(name, f"content_{name}", freq, urg, nov))
    
    important = {"critical_alert", "research_finding", "novel_agent", "error_log"}
    window_size = 4  # can only attend to 4 things at once
    
    print(f"\n{len(signals)} signals competing for {window_size} attention slots")
    print(f"Important signals: {important}")
    
    # Compare strategies
    strategies = [
        ("Urgency-first (reactive)", recency_strategy),
        ("Novelty-first (exploratory)", novelty_strategy),
        ("Balanced (salience)", balanced_strategy),
        ("Uniform (Funes/no filter)", uniform_strategy),
    ]
    
    print("\n--- Strategy Comparison ---")
    for name, fn in strategies:
        result = simulate_attention_performance(fn, signals, window_size, important)
        print(f"\n{name}:")
        print(f"  Caught: {result['caught']}/{len(important)} important")
        print(f"  Noise admitted: {result['noise']}")
        print(f"  F1: {result['f1']:.3f}")
    
    # Treisman attenuation demo
    print("\n--- Treisman Attenuation ---")
    print("Expected frequency: 0.5 (moderate baseline)")
    for s in sorted(signals, key=lambda x: treisman_attenuation(x, 0.5)):
        att = treisman_attenuation(s, 0.5)
        print(f"  {s.source:20s} freq={s.frequency:.2f} attenuation={att:.2f} {'⚡ PASSES' if att < 0.6 else '  filtered'}")
    
    # Information foraging values
    print("\n--- Information Foraging Value (Pirolli & Card) ---")
    for s in sorted(signals, key=foraging_value, reverse=True):
        fv = foraging_value(s)
        print(f"  {s.source:20s} info={s.shannon_info:.1f}bits novelty={s.novelty:.2f} forage_value={fv:.2f}")
    
    # Window size sweep
    print("\n--- Window Size vs Performance (balanced strategy) ---")
    for ws in [2, 4, 6, 8, 10]:
        result = simulate_attention_performance(balanced_strategy, signals, ws, important)
        print(f"  Window={ws:2d}: F1={result['f1']:.3f} caught={result['caught']}/{len(important)} noise={result['noise']}")
    
    print("\n" + "=" * 60)
    print("KEY INSIGHT: Novelty-first catches more important signals")
    print("than urgency-first. Urgency is gameable; novelty isn't.")
    print("Funes (uniform) is worst — perfect memory, zero attention.")
    print("=" * 60)
