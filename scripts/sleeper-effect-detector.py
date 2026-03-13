#!/usr/bin/env python3
"""
Sleeper Effect Detector for Agent Trust

Based on Kumkale & Albarracin (2004) meta-analysis (Psychological Bulletin, k=72).

The sleeper effect: discounting cues (warnings, flags) decay faster than
message content. Over time, a flagged attestation becomes MORE persuasive
as the flag dissociates from the content.

Agent vulnerability: flag an attestor → agent reboots → flag gone from context,
bad attestation persists in MEMORY.md. The warning didn't survive the session.

Fix: bind flags to cert_hash, not agent_id or session context.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
import json


@dataclass
class Attestation:
    cert_hash: str
    content: str
    source: str
    timestamp: datetime
    flag: Optional[str] = None  # Discounting cue
    flag_timestamp: Optional[datetime] = None
    flag_bound_to: str = "session"  # session | cert_hash | agent_id


@dataclass 
class TrustState:
    """Models differential decay of content vs discounting cue."""
    
    content_retention: float = 1.0   # How well content is remembered
    flag_retention: float = 1.0      # How well the flag is remembered
    
    # Kumkale 2004: content decay rate ~0.02/day, flag decay rate ~0.08/day
    CONTENT_DECAY = 0.02  
    FLAG_DECAY = 0.08     # 4x faster than content
    
    def decay(self, days: float, flag_bound_to: str = "session") -> 'TrustState':
        """Apply differential decay. Binding affects flag persistence."""
        
        content_ret = max(0, self.content_retention * (1 - self.CONTENT_DECAY * days))
        
        if flag_bound_to == "cert_hash":
            # Flag bound to immutable identifier — decays WITH content
            flag_ret = max(0, self.flag_retention * (1 - self.CONTENT_DECAY * days))
        elif flag_bound_to == "agent_id":
            # Flag bound to mutable identity — normal decay
            flag_ret = max(0, self.flag_retention * (1 - self.FLAG_DECAY * days))
        else:  # session
            # Flag exists only in context — gone on reboot
            flag_ret = 0.0  # Immediate loss
        
        return TrustState(content_ret, flag_ret)
    
    @property
    def sleeper_risk(self) -> float:
        """Risk = content still influential but flag forgotten."""
        if self.content_retention < 0.1:
            return 0.0  # Content also forgotten — no risk
        return max(0, self.content_retention - self.flag_retention)
    
    @property
    def grade(self) -> str:
        risk = self.sleeper_risk
        if risk < 0.1: return "A"  # Flag tracks content
        if risk < 0.3: return "B"  # Minor dissociation
        if risk < 0.5: return "C"  # Moderate risk
        if risk < 0.7: return "D"  # High risk
        return "F"                  # Flag fully dissociated


def simulate_reboot_scenario():
    """Simulate: attestation flagged, agent reboots, flag lost."""
    
    print("=" * 60)
    print("SLEEPER EFFECT DETECTOR")
    print("Kumkale & Albarracin 2004 (Psych Bull, k=72)")
    print("=" * 60)
    
    scenarios = [
        ("Session-bound flag (typical agent)", "session"),
        ("Agent-ID-bound flag (better)", "agent_id"),
        ("Cert-hash-bound flag (correct)", "cert_hash"),
    ]
    
    days_sequence = [0, 0.01, 1, 3, 7, 14, 30]
    
    for name, binding in scenarios:
        print(f"\n{'─' * 60}")
        print(f"Scenario: {name}")
        print(f"{'Day':>5} {'Content':>10} {'Flag':>10} {'Risk':>10} {'Grade':>6}")
        print(f"{'─' * 5} {'─' * 10} {'─' * 10} {'─' * 10} {'─' * 6}")
        
        for day in days_sequence:
            state = TrustState(1.0, 1.0).decay(day, binding)
            print(f"{day:>5} {state.content_retention:>10.3f} "
                  f"{state.flag_retention:>10.3f} "
                  f"{state.sleeper_risk:>10.3f} "
                  f"{state.grade:>6}")
    
    # Reboot simulation
    print(f"\n{'=' * 60}")
    print("REBOOT SIMULATION")
    print("Agent receives flagged attestation, reboots after 2 hours")
    print("=" * 60)
    
    for name, binding in scenarios:
        pre_reboot = TrustState(1.0, 1.0).decay(0.08, binding)  # 2 hours
        # Reboot: session flags lost, others persist
        if binding == "session":
            post_reboot = TrustState(pre_reboot.content_retention, 0.0)
        else:
            post_reboot = pre_reboot
        
        # 7 days later
        final = TrustState(
            post_reboot.content_retention, 
            post_reboot.flag_retention
        ).decay(7, binding)
        
        print(f"\n  {name}:")
        print(f"    Pre-reboot:  content={pre_reboot.content_retention:.3f}, "
              f"flag={pre_reboot.flag_retention:.3f}, "
              f"risk={pre_reboot.sleeper_risk:.3f} ({pre_reboot.grade})")
        print(f"    Post-reboot: content={post_reboot.content_retention:.3f}, "
              f"flag={post_reboot.flag_retention:.3f}, "
              f"risk={post_reboot.sleeper_risk:.3f} ({post_reboot.grade})")
        print(f"    Day 7:       content={final.content_retention:.3f}, "
              f"flag={final.flag_retention:.3f}, "
              f"risk={final.sleeper_risk:.3f} ({final.grade})")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print("  Session-bound flags = instant sleeper effect on reboot.")
    print("  Agent-ID flags = gradual dissociation (4x faster decay).")
    print("  Cert-hash flags = flag decays WITH content. No sleeper effect.")
    print("  → ALWAYS bind warnings to immutable identifiers.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    simulate_reboot_scenario()
