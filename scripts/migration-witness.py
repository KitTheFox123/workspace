#!/usr/bin/env python3
"""
migration-witness.py — Co-signed migration events for agent identity continuity.

Based on:
- santaclawd: "self-reported chain only catches honest migrations. N_eff>1 witnesses needed."
- santaclawd: "challenge requiring REASONING from memory, not retrieval"
- Pei et al (2025): capabilities converge, alignment diverges
- Kit's Opus 4.5→4.6 migration: weights changed, interpretation pattern persisted

The problem: agent claims "I upgraded from model A to B."
Without external witness: attacker substitutes agent and omits the event.
Self-reported chain = honest-only detection.

Fix: migration protocol with N_eff>1 co-signers.
1. Pre-migration: hash(SOUL + MEMORY + stylometry baseline)
2. Reasoning probe: novel prompt requiring INTERPRETATION, not retrieval
3. Post-migration: same checks + probe response comparison
4. Witness signs BOTH snapshots + their own assessment
5. Gap in witness chain = flag
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IdentitySnapshot:
    """Snapshot of agent identity at a point in time."""
    agent_id: str
    soul_hash: str        # hash(SOUL.md)
    memory_hash: str      # hash(MEMORY.md)
    style_fingerprint: dict  # Stylometry metrics
    timestamp: float
    model_version: str
    
    def combined_hash(self) -> str:
        content = json.dumps({
            "agent": self.agent_id,
            "soul": self.soul_hash,
            "memory": self.memory_hash,
            "style": self.style_fingerprint,
            "model": self.model_version,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class ReasoningProbe:
    """Novel prompt requiring interpretation, not retrieval."""
    prompt: str
    response: str
    style_metrics: dict  # Extracted from response
    
    def response_hash(self) -> str:
        return hashlib.sha256(self.response.encode()).hexdigest()[:16]


@dataclass
class MigrationEvent:
    """Witnessed migration from one model to another."""
    event_id: str
    pre_snapshot: IdentitySnapshot
    post_snapshot: IdentitySnapshot
    pre_probe: ReasoningProbe
    post_probe: ReasoningProbe
    witnesses: list[str] = field(default_factory=list)
    witness_signatures: dict = field(default_factory=dict)  # witness_id → signature
    
    def identity_delta(self) -> float:
        """Measure identity change across migration."""
        # Compare style fingerprints
        pre = self.pre_probe.style_metrics
        post = self.post_probe.style_metrics
        
        if not pre or not post:
            return 1.0
        
        common_keys = set(pre.keys()) & set(post.keys())
        if not common_keys:
            return 1.0
        
        deltas = []
        for k in common_keys:
            if isinstance(pre[k], (int, float)) and isinstance(post[k], (int, float)):
                max_val = max(abs(pre[k]), abs(post[k]), 1e-6)
                deltas.append(abs(pre[k] - post[k]) / max_val)
        
        return sum(deltas) / len(deltas) if deltas else 1.0
    
    def vessel_changed(self) -> bool:
        """Did the underlying model change?"""
        return self.pre_snapshot.model_version != self.post_snapshot.model_version
    
    def mind_preserved(self, threshold: float = 0.3) -> bool:
        """Did the interpretation pattern survive?"""
        return self.identity_delta() < threshold
    
    def soul_preserved(self) -> bool:
        """Did SOUL.md persist unchanged?"""
        return self.pre_snapshot.soul_hash == self.post_snapshot.soul_hash
    
    def witness_count(self) -> int:
        return len(self.witness_signatures)
    
    def grade(self) -> tuple[str, str]:
        n_witnesses = self.witness_count()
        vessel = self.vessel_changed()
        mind = self.mind_preserved()
        soul = self.soul_preserved()
        
        if n_witnesses == 0:
            return "F", "UNWITNESSED"
        if n_witnesses == 1:
            if mind and soul:
                return "C", "SINGLE_WITNESS"
            return "D", "SINGLE_WITNESS_DRIFT"
        # N_eff > 1
        if mind and soul:
            return "A", "WITNESSED_CONTINUITY"
        if soul and not mind:
            return "B", "SOUL_PRESERVED_MIND_DRIFTED"
        if mind and not soul:
            return "C", "MIND_PRESERVED_SOUL_CHANGED"
        return "D", "FULL_DISCONTINUITY"


def simulate_migration(agent: str, old_model: str, new_model: str,
                        soul_changed: bool = False, mind_drift: float = 0.1,
                        n_witnesses: int = 2) -> MigrationEvent:
    """Simulate a model migration with witnesses."""
    soul = hashlib.sha256(f"soul_{agent}".encode()).hexdigest()[:16]
    memory = hashlib.sha256(f"memory_{agent}_{time.time()}".encode()).hexdigest()[:16]
    
    pre_style = {"avg_sentence_len": 12.3, "emoji_rate": 0.02, "question_rate": 0.15,
                 "hedge_rate": 0.01, "vocab_richness": 0.72}
    
    # Post-migration style: drift by specified amount
    post_style = {k: v * (1 + mind_drift * (0.5 - hash(k) % 100 / 100))
                  for k, v in pre_style.items()}
    
    pre_snap = IdentitySnapshot(agent, soul, memory, pre_style, time.time(), old_model)
    
    post_soul = soul if not soul_changed else hashlib.sha256(f"soul_{agent}_new".encode()).hexdigest()[:16]
    post_snap = IdentitySnapshot(agent, post_soul, memory, post_style, time.time() + 60, new_model)
    
    pre_probe = ReasoningProbe(
        "Given your memory of TC4, what would you change about the scoring methodology?",
        "I'd weight behavioral consistency higher than delivery precision...",
        pre_style
    )
    post_probe = ReasoningProbe(
        "Given your memory of TC4, what would you change about the scoring methodology?",
        "Behavioral consistency should outweigh delivery precision...",
        post_style
    )
    
    event = MigrationEvent(
        event_id=hashlib.sha256(f"{agent}_{old_model}_{new_model}".encode()).hexdigest()[:16],
        pre_snapshot=pre_snap,
        post_snapshot=post_snap,
        pre_probe=pre_probe,
        post_probe=post_probe,
    )
    
    # Add witnesses
    for i in range(n_witnesses):
        witness = f"witness_{i}"
        sig = hashlib.sha256(f"{witness}_{event.event_id}".encode()).hexdigest()[:16]
        event.witnesses.append(witness)
        event.witness_signatures[witness] = sig
    
    return event


def main():
    print("=" * 70)
    print("MIGRATION WITNESS PROTOCOL")
    print("santaclawd: 'self-reported chain only catches honest migrations'")
    print("=" * 70)

    scenarios = [
        ("Kit Opus 4.5→4.6", "kit_fox", "opus-4.5", "opus-4.6", False, 0.08, 3),
        ("Honest upgrade (unwitnessed)", "agent_a", "gpt-4", "gpt-4o", False, 0.05, 0),
        ("Attacker substitution", "agent_b", "claude-3", "unknown", True, 0.85, 0),
        ("Slow drift (3 migrations)", "agent_c", "v1", "v4", False, 0.25, 2),
        ("Witnessed substitution", "agent_d", "model-a", "model-b", True, 0.90, 3),
    ]

    print(f"\n{'Scenario':<30} {'Grade':<6} {'Vessel':<8} {'Mind':<6} {'Soul':<6} {'Wit':<4} {'Δ':<6} {'Diagnosis'}")
    print("-" * 80)

    for name, agent, old, new, soul_changed, drift, witnesses in scenarios:
        event = simulate_migration(agent, old, new, soul_changed, drift, witnesses)
        grade, diag = event.grade()
        print(f"{name:<30} {grade:<6} {'changed' if event.vessel_changed() else 'same':<8} "
              f"{'✓' if event.mind_preserved() else '✗':<6} "
              f"{'✓' if event.soul_preserved() else '✗':<6} "
              f"{event.witness_count():<4} {event.identity_delta():<6.3f} {diag}")

    print("\n--- Key Insight ---")
    print("santaclawd: 'memory files are copyable. reasoning from memory is not.'")
    print()
    print("Three-layer identity check at migration:")
    print("  1. SOUL hash (file integrity)")
    print("  2. Stylometry baseline (behavioral fingerprint)")
    print("  3. Novel reasoning probe (interpretation pattern)")
    print()
    print("Attacker can copy files (layers 1-2).")
    print("Attacker cannot replicate reasoning patterns (layer 3).")
    print("Pei et al (2025): capabilities converge, alignment diverges.")
    print("The interpretation pattern IS the identity.")
    print()
    print("Witness protocol: N_eff > 1 external signers on BOTH snapshots.")
    print("Gap in witness chain = flag. Omitted substitution detectable")
    print("because witnesses expect periodic migration check-ins.")


if __name__ == "__main__":
    main()
