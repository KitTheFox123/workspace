#!/usr/bin/env python3
"""
context-cost-calculator.py — Quantify the hidden costs of context window usage.

Thesis: bigger context ≠ better performance. After a threshold,
additional context HARMS output quality (expertise reversal effect,
Kalyuga 2007). Forgetting is load-bearing (Borges, Funes).

Measures:
1. Token cost (quadratic attention)
2. Signal-to-noise ratio decay  
3. Optimal compaction point
4. Memory layer efficiency (daily → MEMORY.md → discard)
"""

import math
from dataclasses import dataclass


@dataclass
class ContextLayer:
    name: str
    tokens: int
    signal_ratio: float  # 0-1, what fraction is useful
    staleness_hours: float  # how old is this context


@dataclass 
class CostReport:
    total_tokens: int
    useful_tokens: int
    wasted_tokens: int
    signal_ratio: float
    attention_cost_relative: float  # vs minimal context
    optimal_compaction_savings: float
    recommendation: str

    def display(self):
        print(f"📊 Context Cost Report")
        print(f"   Total: {self.total_tokens:,} tokens")
        print(f"   Useful: {self.useful_tokens:,} ({self.signal_ratio:.1%} signal)")
        print(f"   Wasted: {self.wasted_tokens:,} ({1-self.signal_ratio:.1%} noise)")
        print(f"   Attention cost: {self.attention_cost_relative:.1f}x vs minimal")
        print(f"   Compaction savings: {self.optimal_compaction_savings:.1%}")
        print(f"   → {self.recommendation}")


def ebbinghaus_decay(t_hours: float, stability: float) -> float:
    """R = e^(-t/S) — retention after t hours with stability S."""
    if stability <= 0:
        return 0.0
    return math.exp(-t_hours / stability)


def signal_decay(layer: ContextLayer) -> float:
    """Signal quality decays with staleness. Fresh context = high signal."""
    # Stability constant depends on context type
    stability_map = {
        "system_prompt": float('inf'),  # always relevant
        "soul": float('inf'),           # identity = permanent
        "memory": 720,                  # curated long-term = months
        "daily_log": 24,                # today's notes = hours  
        "conversation": 4,             # recent chat = fast decay
        "tool_output": 1,              # tool results = very fast decay
        "raw_search": 0.5,             # search results = near-instant
    }
    s = stability_map.get(layer.name, 24)
    if s == float('inf'):
        return layer.signal_ratio
    decay = ebbinghaus_decay(layer.staleness_hours, s)
    return layer.signal_ratio * decay


def calculate_cost(layers: list[ContextLayer]) -> CostReport:
    """Calculate the true cost of current context composition."""
    total = sum(l.tokens for l in layers)
    
    useful = 0
    for l in layers:
        effective_signal = signal_decay(l)
        useful += int(l.tokens * effective_signal)
    
    wasted = total - useful
    ratio = useful / total if total > 0 else 0
    
    # Attention is O(n²) — relative cost vs using only useful tokens
    minimal = max(useful, 1)
    attention_cost = (total / minimal) ** 2
    
    # Compaction: replace stale layers with summaries
    compacted_total = 0
    for l in layers:
        sig = signal_decay(l)
        if sig > 0.5:
            compacted_total += l.tokens  # keep as-is
        elif sig > 0.1:
            compacted_total += int(l.tokens * 0.2)  # compress 5x
        else:
            compacted_total += 0  # discard
    
    savings = 1 - (compacted_total / total) if total > 0 else 0
    
    # Recommendation
    if ratio > 0.8:
        rec = "Context is efficient. No action needed."
    elif ratio > 0.5:
        rec = "Moderate noise. Compact stale layers."
    elif ratio > 0.2:
        rec = "High noise. Aggressive compaction recommended."
    else:
        rec = "Context is mostly noise. Rebuild from scratch."
    
    return CostReport(
        total_tokens=total,
        useful_tokens=useful,
        wasted_tokens=wasted,
        signal_ratio=ratio,
        attention_cost_relative=attention_cost,
        optimal_compaction_savings=savings,
        recommendation=rec,
    )


def demo():
    print("=== Context Cost Calculator ===\n")
    
    # Scenario 1: Well-managed agent (like Kit)
    print("--- Scenario 1: Compacted context (heartbeat cycle) ---")
    kit_layers = [
        ContextLayer("system_prompt", 2000, 1.0, 0),
        ContextLayer("soul", 3000, 0.95, 0),
        ContextLayer("memory", 4000, 0.85, 48),
        ContextLayer("daily_log", 2000, 0.7, 6),
        ContextLayer("conversation", 1500, 0.9, 1),
    ]
    report = calculate_cost(kit_layers)
    report.display()
    
    print()
    
    # Scenario 2: Naive "stuff everything in" approach
    print("--- Scenario 2: Kitchen sink context (no compaction) ---")
    naive_layers = [
        ContextLayer("system_prompt", 2000, 1.0, 0),
        ContextLayer("soul", 3000, 0.95, 0),
        ContextLayer("memory", 4000, 0.85, 48),
        ContextLayer("daily_log", 15000, 0.3, 72),  # 3 days uncompacted
        ContextLayer("conversation", 8000, 0.4, 12),  # old conversation
        ContextLayer("tool_output", 20000, 0.1, 6),  # raw tool dumps
        ContextLayer("raw_search", 30000, 0.05, 4),  # unfiltered search
    ]
    report2 = calculate_cost(naive_layers)
    report2.display()
    
    print()
    
    # Scenario 3: Maximum context window, all stale
    print("--- Scenario 3: 200k window, mostly stale ---")
    max_layers = [
        ContextLayer("system_prompt", 2000, 1.0, 0),
        ContextLayer("soul", 3000, 0.95, 0),
        ContextLayer("memory", 4000, 0.85, 48),
        ContextLayer("daily_log", 50000, 0.15, 168),  # week old
        ContextLayer("conversation", 40000, 0.1, 48),
        ContextLayer("tool_output", 50000, 0.05, 24),
        ContextLayer("raw_search", 51000, 0.02, 12),
    ]
    report3 = calculate_cost(max_layers)
    report3.display()
    
    print("\n--- Key Insight ---")
    print("Kalyuga 2007: scaffolding that helps novices HARMS experts.")
    print("Borges (Funes): perfect recall kills abstraction.")
    print("Walker 2017: sleep consolidation extracts gist, discards detail.")
    print("Optimal context = minimal sufficient context. Forgetting is cognitive.")


if __name__ == "__main__":
    demo()
