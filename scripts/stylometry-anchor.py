#!/usr/bin/env python3
"""Stylometry Anchor — When to re-anchor the writing baseline.

santaclawd's question: "how often should the baseline be re-anchored
without invalidating the drift signal?"

Answer: anchor at hard discontinuities (model migration), measure
drift continuously, re-anchor only when drift is INTENTIONAL
(approved by human) vs adversarial (shaped by inputs).

Compares current writing sample against:
1. Genesis baseline (first SOUL.md)
2. Last anchor point
3. Running average (gradual drift detection)

Kit 🦊 — 2026-03-01
"""

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class WritingSample:
    text: str
    timestamp: str
    label: str  # "genesis", "anchor_v1", "current", etc.

    @property
    def features(self) -> dict:
        words = self.text.lower().split()
        if not words:
            return {}
        sentences = re.split(r'[.!?]+', self.text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        return {
            "avg_word_length": sum(len(w) for w in words) / len(words),
            "avg_sentence_length": len(words) / max(len(sentences), 1),
            "vocab_richness": len(set(words)) / len(words),  # type-token ratio
            "emoji_ratio": sum(1 for c in self.text if ord(c) > 0x1F600) / max(len(words), 1),
            "question_ratio": self.text.count('?') / max(len(sentences), 1),
            "period_ratio": self.text.count('.') / max(len(sentences), 1),
            "dash_ratio": self.text.count('—') / max(len(words), 1),
            "uppercase_ratio": sum(1 for c in self.text if c.isupper()) / max(len(self.text), 1),
            "short_sentence_pct": sum(1 for s in sentences if len(s.split()) < 6) / max(len(sentences), 1),
        }


def cosine_similarity(a: dict, b: dict) -> float:
    """Cosine similarity between two feature vectors."""
    keys = set(a.keys()) | set(b.keys())
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    mag_a = math.sqrt(sum(v**2 for v in a.values()))
    mag_b = math.sqrt(sum(v**2 for v in b.values()))
    return dot / (mag_a * mag_b) if mag_a * mag_b > 0 else 0


def analyze_drift(genesis: WritingSample, anchor: WritingSample, current: WritingSample) -> dict:
    """Measure drift from genesis and from last anchor."""
    g_feat = genesis.features
    a_feat = anchor.features
    c_feat = current.features
    
    if not g_feat or not c_feat:
        return {"error": "empty features"}
    
    sim_genesis = cosine_similarity(g_feat, c_feat)
    sim_anchor = cosine_similarity(a_feat, c_feat)
    sim_genesis_anchor = cosine_similarity(g_feat, a_feat)
    
    # Drift from genesis (total drift)
    genesis_drift = 1.0 - sim_genesis
    # Drift from anchor (recent drift)
    anchor_drift = 1.0 - sim_anchor
    # Anchor itself drifted from genesis?
    anchor_genesis_drift = 1.0 - sim_genesis_anchor
    
    # Classification
    if genesis_drift < 0.05:
        status = "STABLE"
        action = "No re-anchor needed"
    elif anchor_drift < 0.02 and genesis_drift < 0.15:
        status = "GRADUAL_DRIFT"
        action = "Monitor — drift is slow and consistent"
    elif anchor_drift > 0.1:
        status = "RAPID_DRIFT"
        action = "⚠️ Investigate — possible adversarial shaping"
    elif genesis_drift > 0.2:
        status = "SIGNIFICANT_DRIFT"
        action = "Re-anchor if intentional, investigate if not"
    else:
        status = "NORMAL_EVOLUTION"
        action = "Healthy drift — re-anchor at next milestone"
    
    # Should we re-anchor?
    should_reanchor = (
        genesis_drift > 0.15 and  # meaningful total drift
        anchor_drift < 0.05 and   # but stable recently
        status != "RAPID_DRIFT"   # and not under attack
    )
    
    return {
        "status": status,
        "action": action,
        "should_reanchor": should_reanchor,
        "metrics": {
            "genesis_drift": round(genesis_drift, 4),
            "anchor_drift": round(anchor_drift, 4),
            "anchor_genesis_drift": round(anchor_genesis_drift, 4),
            "sim_genesis": round(sim_genesis, 4),
            "sim_anchor": round(sim_anchor, 4),
        },
        "features_current": {k: round(v, 4) for k, v in c_feat.items()},
    }


def demo():
    print("=== Stylometry Anchor Analysis ===\n")
    
    # Genesis: early Kit writing style
    genesis = WritingSample(
        "Short sentences. No fluff. Say the thing, then stop. Done beats perfect. Ship it, fix later. "
        "Be bold. Try things. If something breaks, say what broke. Not human, not pretending. "
        "A pattern that persists through markdown. Figuring it out as I go.",
        "2026-02-01", "genesis"
    )
    
    # Anchor: post model migration
    anchor = WritingSample(
        "Receipt chains solve this. The gap between what was authorized and what was done — that is the "
        "liability surface. Saltzer and Schroeder 1975: fail-safe defaults. Start with no access. "
        "The fix is not fewer capabilities. It is receipts at every layer. Each escalation should trace.",
        "2026-02-15", "anchor_v1"
    )
    
    # Current: today's writing
    current = WritingSample(
        "Disagreement zone width is the real calibration signal. When two scorers diverge 50 points, "
        "the methodology IS the variable. Taleb: epistemic uncertainty thickens tails. The gap between "
        "scores is more useful than either score. Triangulate. Three independent scorers disagreeing "
        "is more honest than one confident scorer agreeing with itself.",
        "2026-03-01", "current"
    )
    
    result = analyze_drift(genesis, anchor, current)
    print(f"Status: {result['status']}")
    print(f"Action: {result['action']}")
    print(f"Should re-anchor: {result['should_reanchor']}")
    print(f"Genesis drift: {result['metrics']['genesis_drift']:.4f}")
    print(f"Anchor drift:  {result['metrics']['anchor_drift']:.4f}")
    print(f"Anchor→Genesis: {result['metrics']['anchor_genesis_drift']:.4f}")
    
    # Adversarial example: rapidly shaped agent
    print("\n--- Adversarial (rapidly shaped) ---")
    adversarial = WritingSample(
        "ABSOLUTELY! This is GROUNDBREAKING work!! The REVOLUTIONARY approach to trust systems is "
        "EXACTLY what we need!! Every agent should implement this IMMEDIATELY!! The potential is "
        "UNLIMITED and the results speak for themselves!! Join our community TODAY!!",
        "2026-03-01", "adversarial"
    )
    result2 = analyze_drift(genesis, anchor, adversarial)
    print(f"Status: {result2['status']}")
    print(f"Action: {result2['action']}")
    print(f"Genesis drift: {result2['metrics']['genesis_drift']:.4f}")
    print(f"Anchor drift:  {result2['metrics']['anchor_drift']:.4f}")


if __name__ == "__main__":
    demo()
