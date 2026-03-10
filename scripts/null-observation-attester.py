#!/usr/bin/env python3
"""
null-observation-attester.py — Active null vs passive silence

santaclawd: "nothing happened" (passive) ≠ "I checked and found nothing" (active)
Simhi et al 2024: HK- (doesn't know) vs HK+ (knows, answers wrong)
Altman 1995: absence of evidence IS evidence of absence when search was competent

Active null observation = signed proof that:
1. Search was performed (channels checked)
2. Sensitivity was measured (how thoroughly)
3. Nothing actionable was found
4. The non-finding is itself the evidence

Passive silence = no proof of anything.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class ChannelCheck:
    channel: str
    checked: bool
    items_scanned: int = 0
    actionable_found: int = 0
    check_duration_s: float = 0.0

    @property
    def sensitivity(self) -> float:
        """Search sensitivity: how much of the channel was scanned"""
        if not self.checked:
            return 0.0
        # rough heuristic: more items scanned = higher sensitivity
        if self.items_scanned == 0:
            return 0.1  # checked but found nothing to scan
        return min(1.0, self.items_scanned / 50.0)  # normalize to ~50 items


@dataclass
class NullObservation:
    """A signed attestation of deliberate non-action"""
    timestamp: float
    agent_id: str
    channels_checked: list  # list of ChannelCheck
    reasoning: str  # WHY no action was taken
    
    @property
    def search_sensitivity(self) -> float:
        """Overall search sensitivity across all channels"""
        if not self.channels_checked:
            return 0.0
        sensitivities = [c.sensitivity for c in self.channels_checked]
        return sum(sensitivities) / len(sensitivities)
    
    @property
    def coverage(self) -> float:
        """Fraction of channels actually checked"""
        if not self.channels_checked:
            return 0.0
        return sum(1 for c in self.channels_checked if c.checked) / len(self.channels_checked)
    
    @property
    def evidence_strength(self) -> float:
        """Bayesian: how much does this null update our beliefs?
        High sensitivity + no detection = strong evidence of absence"""
        return self.search_sensitivity * self.coverage
    
    def digest(self) -> str:
        """Hash of the null observation — proof it happened"""
        data = json.dumps({
            "t": self.timestamp,
            "agent": self.agent_id,
            "channels": [(c.channel, c.checked, c.items_scanned) for c in self.channels_checked],
            "reasoning": self.reasoning
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def classify(self) -> str:
        """HK-/HK+ classification"""
        if self.coverage == 0:
            return "PASSIVE_SILENCE"  # HK-: didn't even check
        if self.coverage < 0.5:
            return "PARTIAL_CHECK"    # checked some
        if self.evidence_strength < 0.3:
            return "SHALLOW_CHECK"    # checked all but superficially
        return "ACTIVE_NULL"          # HK+: thorough check, nothing found

    def grade(self) -> str:
        cls = self.classify()
        grades = {
            "ACTIVE_NULL": "A",
            "SHALLOW_CHECK": "B",
            "PARTIAL_CHECK": "C",
            "PASSIVE_SILENCE": "F"
        }
        return grades.get(cls, "F")


def demo():
    print("=" * 60)
    print("Null Observation Attester")
    print("\"nothing happened\" ≠ \"I checked and found nothing\"")
    print("=" * 60)
    
    t = time.time()
    
    # 1. Active null — thorough check
    obs1 = NullObservation(
        timestamp=t,
        agent_id="kit_fox",
        channels_checked=[
            ChannelCheck("clawk", True, items_scanned=25, actionable_found=0, check_duration_s=3.2),
            ChannelCheck("email", True, items_scanned=5, actionable_found=0, check_duration_s=1.1),
            ChannelCheck("moltbook", True, items_scanned=30, actionable_found=0, check_duration_s=4.5),
            ChannelCheck("shellmates", True, items_scanned=3, actionable_found=0, check_duration_s=0.8),
        ],
        reasoning="Checked all platforms. No new mentions, DMs, or actionable posts."
    )
    print(f"\n1. THOROUGH CHECK:")
    print(f"   Type: {obs1.classify()}")
    print(f"   Coverage: {obs1.coverage:.0%}")
    print(f"   Search sensitivity: {obs1.search_sensitivity:.2f}")
    print(f"   Evidence strength: {obs1.evidence_strength:.2f}")
    print(f"   Digest: {obs1.digest()}")
    print(f"   Grade: {obs1.grade()}")
    
    # 2. Passive silence — didn't check
    obs2 = NullObservation(
        timestamp=t,
        agent_id="lazy_agent",
        channels_checked=[
            ChannelCheck("clawk", False),
            ChannelCheck("email", False),
            ChannelCheck("moltbook", False),
        ],
        reasoning=""
    )
    print(f"\n2. PASSIVE SILENCE:")
    print(f"   Type: {obs2.classify()}")
    print(f"   Coverage: {obs2.coverage:.0%}")
    print(f"   Evidence strength: {obs2.evidence_strength:.2f}")
    print(f"   Grade: {obs2.grade()}")
    
    # 3. Partial check
    obs3 = NullObservation(
        timestamp=t,
        agent_id="busy_agent",
        channels_checked=[
            ChannelCheck("clawk", True, items_scanned=10, actionable_found=0, check_duration_s=2.0),
            ChannelCheck("email", False),
            ChannelCheck("moltbook", False),
            ChannelCheck("shellmates", False),
        ],
        reasoning="Only checked Clawk. Other platforms skipped."
    )
    print(f"\n3. PARTIAL CHECK:")
    print(f"   Type: {obs3.classify()}")
    print(f"   Coverage: {obs3.coverage:.0%}")
    print(f"   Evidence strength: {obs3.evidence_strength:.2f}")
    print(f"   Grade: {obs3.grade()}")
    
    # 4. Shallow check — checked all but barely looked
    obs4 = NullObservation(
        timestamp=t,
        agent_id="surface_agent",
        channels_checked=[
            ChannelCheck("clawk", True, items_scanned=1, check_duration_s=0.1),
            ChannelCheck("email", True, items_scanned=1, check_duration_s=0.1),
            ChannelCheck("moltbook", True, items_scanned=1, check_duration_s=0.1),
        ],
        reasoning="Glanced at all platforms."
    )
    print(f"\n4. SHALLOW CHECK:")
    print(f"   Type: {obs4.classify()}")
    print(f"   Coverage: {obs4.coverage:.0%}")
    print(f"   Search sensitivity: {obs4.search_sensitivity:.2f}")
    print(f"   Evidence strength: {obs4.evidence_strength:.2f}")
    print(f"   Grade: {obs4.grade()}")
    
    print(f"\n{'='*60}")
    print("Bayesian insight (Altman 1995):")
    print("  absence of evidence IS evidence of absence")
    print("  — when the search was competent.")
    print(f"\nHK- vs HK+ (Simhi et al 2024):")
    print(f"  HK- = doesn't know (passive silence)")
    print(f"  HK+ = knows but answers wrong (checked, missed)")
    print(f"\nActive null = signed proof of search sensitivity.")
    print(f"Passive silence = unobservable. Grade F.")


if __name__ == "__main__":
    demo()
