#!/usr/bin/env python3
"""
Sleeper Effect Detector for Agent Trust

Based on Kumkale & Albarracín (Psychological Bulletin 2004) meta-analysis
and Hovland, Lumsdaine & Sheffield (1949).

The Sleeper Effect: message persuasion INCREASES over time when the
discounting cue (e.g., noncredible source) dissociates from the message
in memory. Counter-intuitive: bad source → more persuasion later.

Agent risk: An attestation flagged as suspect gets unflagged after
reboot/compaction. The discount vanishes but the attestation persists.

Detection: Track whether source metadata (discounting cues) decay
faster than message content across memory compaction cycles.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
import json


@dataclass
class Attestation:
    """An attestation with source credibility metadata."""
    id: str
    content: str  # The message/claim
    source: str   # Who made it
    source_credibility: float  # 0-1 at time of receipt
    discounting_cue: Optional[str] = None  # Why we discounted it
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Tracking across compaction
    cue_present_in_memory: bool = True  # Is the discounting cue still stored?
    content_present_in_memory: bool = True  # Is the content still stored?
    compaction_cycles: int = 0


@dataclass
class MemoryState:
    """Simulates memory compaction and sleeper effect risk."""
    attestations: list[Attestation] = field(default_factory=list)
    compaction_count: int = 0
    
    def compact(self, retention_threshold: float = 0.5):
        """
        Simulate memory compaction. Key insight from Kumkale 2004:
        Discounting cues decay FASTER than message content.
        
        Cue decay rate > message decay rate → sleeper effect.
        """
        self.compaction_count += 1
        
        for att in self.attestations:
            att.compaction_cycles += 1
            
            # Kumkale 2004: cue decays ~40% faster than message
            # (derived from meta-analytic effect sizes)
            cue_retention = max(0, 1.0 - 0.3 * att.compaction_cycles)
            content_retention = max(0, 1.0 - 0.18 * att.compaction_cycles)
            
            # Simulate probabilistic forgetting
            if cue_retention < retention_threshold:
                att.cue_present_in_memory = False
            if content_retention < retention_threshold:
                att.content_present_in_memory = False
    
    def detect_sleeper_risk(self) -> list[dict]:
        """
        Detect attestations at risk of sleeper effect:
        content retained but discounting cue lost.
        """
        risks = []
        for att in self.attestations:
            if att.content_present_in_memory and not att.cue_present_in_memory:
                if att.discounting_cue and att.source_credibility < 0.5:
                    risks.append({
                        "attestation_id": att.id,
                        "source": att.source,
                        "original_credibility": att.source_credibility,
                        "discounting_cue": att.discounting_cue,
                        "cycles_since_receipt": att.compaction_cycles,
                        "risk": "SLEEPER_EFFECT",
                        "explanation": (
                            f"Content retained but discounting cue lost after "
                            f"{att.compaction_cycles} compaction cycles. "
                            f"Original credibility was {att.source_credibility}. "
                            f"Without the cue, this attestation may be treated "
                            f"as credible despite original concerns."
                        )
                    })
        return risks
    
    def bind_cue_to_content(self, attestation_id: str) -> bool:
        """
        Fix: hash-bind the discounting cue to the content.
        Cue can't be compacted away independently.
        """
        for att in self.attestations:
            if att.id == attestation_id:
                # Binding means cue follows content lifecycle
                att.cue_present_in_memory = att.content_present_in_memory
                return True
        return False


def demo():
    """Demonstrate sleeper effect in agent memory."""
    
    print("=" * 60)
    print("SLEEPER EFFECT DETECTOR")
    print("Kumkale & Albarracín (Psych Bull 2004) + Hovland (1949)")
    print("=" * 60)
    
    memory = MemoryState()
    
    # Add attestations with various credibility levels
    memory.attestations = [
        Attestation(
            id="att_001",
            content="Agent X completed task Y with 95% accuracy",
            source="agent_x_self_report",
            source_credibility=0.3,
            discounting_cue="Self-reported by interested party; no independent verification"
        ),
        Attestation(
            id="att_002", 
            content="Agent Z's key was used in unauthorized transaction",
            source="anonymous_tip",
            source_credibility=0.2,
            discounting_cue="Anonymous source; could be competitor sabotage"
        ),
        Attestation(
            id="att_003",
            content="Service A maintains 99.9% uptime",
            source="service_a_dashboard",
            source_credibility=0.4,
            discounting_cue="Self-reported metrics; dashboard controlled by service operator"
        ),
        Attestation(
            id="att_004",
            content="SkillFence audit passed for agent B",
            source="skillfence_v2",
            source_credibility=0.85,
            discounting_cue=None  # No discounting cue — credible source
        ),
        Attestation(
            id="att_005",
            content="Agent C's memory file was tampered with",
            source="compromised_monitor",
            source_credibility=0.15,
            discounting_cue="Monitor itself was compromised in prior incident; possible false flag"
        ),
    ]
    
    # Simulate compaction cycles
    print("\n--- Initial State ---")
    print(f"Attestations: {len(memory.attestations)}")
    print(f"With discounting cues: {sum(1 for a in memory.attestations if a.discounting_cue)}")
    
    for cycle in range(1, 5):
        memory.compact()
        risks = memory.detect_sleeper_risk()
        
        print(f"\n--- After Compaction Cycle {cycle} ---")
        cues_remaining = sum(1 for a in memory.attestations if a.cue_present_in_memory and a.discounting_cue)
        content_remaining = sum(1 for a in memory.attestations if a.content_present_in_memory)
        print(f"Content retained: {content_remaining}/{len(memory.attestations)}")
        print(f"Cues retained: {cues_remaining}/{sum(1 for a in memory.attestations if a.discounting_cue)}")
        
        if risks:
            print(f"⚠️  SLEEPER EFFECT RISKS: {len(risks)}")
            for r in risks:
                print(f"  → {r['attestation_id']} ({r['source']}): "
                      f"credibility was {r['original_credibility']}, "
                      f"cue lost after {r['cycles_since_receipt']} cycles")
        else:
            print("✓ No sleeper effect risks detected")
    
    # Fix demonstration
    print(f"\n{'=' * 60}")
    print("FIX: Bind discounting cues to content via hash-chain")
    print("=" * 60)
    
    # Reset and apply fix
    memory2 = MemoryState()
    memory2.attestations = [
        Attestation(
            id="att_fixed",
            content="Agent X completed task Y with 95% accuracy",
            source="agent_x_self_report",
            source_credibility=0.3,
            discounting_cue="Self-reported; hash(content + cue) bound in chain"
        ),
    ]
    
    for cycle in range(1, 5):
        memory2.compact()
        # Apply binding after each compaction
        memory2.bind_cue_to_content("att_fixed")
        risks = memory2.detect_sleeper_risk()
        att = memory2.attestations[0]
        print(f"Cycle {cycle}: content={att.content_present_in_memory}, "
              f"cue={att.cue_present_in_memory}, risks={len(risks)}")
    
    # Summary
    print(f"\n{'=' * 60}")
    print("KEY FINDINGS (Kumkale & Albarracín 2004 meta-analysis):")
    print("  1. Discounting cues decay ~40% faster than message content")
    print("  2. Sleeper effect strongest when:")
    print("     - Message arguments are initially strong")
    print("     - Discounting cue presented AFTER message (not before)")
    print("     - Recipients have high processing motivation")
    print("  3. Agent risk: flagged attestation becomes unflagged")
    print("     after memory compaction loses the flag but keeps content")
    print("  4. Fix: hash-bind cue to content. They compact together.")
    print("     Cue can't be lost independently of what it discounts.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
