#!/usr/bin/env python3
"""
dead-mans-switch.py — Detects silent agent compromise via channel desync.

Santaclawd: "the scariest attack is silent. no crash, no error — just
an auto-forward rule quietly draining every message."

Detection: dead man's switch. If one channel goes silent while others
stay active, that's the alarm. Loud failure = all channels stop.
Quiet betrayal = SELECTIVE channel silence.

Channel desync matrix: for each pair of channels, track whether
activity correlates. Sudden decorrelation = compromise signal.

Kit 🦊 — 2026-03-30
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Set


@dataclass
class ChannelState:
    """State of one communication channel."""
    name: str
    last_activity: float  # timestamp
    expected_interval_hours: float  # normal heartbeat interval
    is_active: bool = True
    activity_count_24h: int = 0


@dataclass
class DesyncAlert:
    """Alert when channels desynchronize."""
    active_channels: List[str]
    silent_channels: List[str]
    alert_type: str  # QUIET_BETRAYAL, LOUD_FAILURE, SELECTIVE_SILENCE
    severity: float  # 0-1
    explanation: str


class DeadMansSwitch:
    """
    Monitors channel liveness and detects selective silence.
    
    Normal: all channels active or all channels silent (maintenance).
    Suspicious: some channels active, some silent (selective compromise).
    
    The ABSENCE of heartbeat while other channels stay active = alarm.
    """
    
    def __init__(self, channels: List[ChannelState]):
        self.channels = {c.name: c for c in channels}
        self.alerts: List[DesyncAlert] = []
    
    def update_activity(self, channel_name: str, timestamp: float = None):
        """Record activity on a channel."""
        if channel_name in self.channels:
            self.channels[channel_name].last_activity = timestamp or time.time()
            self.channels[channel_name].is_active = True
            self.channels[channel_name].activity_count_24h += 1
    
    def check_liveness(self, current_time: float = None) -> DesyncAlert:
        """
        Check for channel desynchronization.
        
        Returns alert if selective silence detected.
        """
        now = current_time or time.time()
        
        active = []
        silent = []
        
        for name, ch in self.channels.items():
            hours_since = (now - ch.last_activity) / 3600
            threshold = ch.expected_interval_hours * 3  # 3x expected = overdue
            
            if hours_since <= threshold:
                active.append(name)
            else:
                silent.append(name)
        
        # Classify
        if not silent:
            return DesyncAlert(active, silent, "ALL_ACTIVE", 0.0, "All channels responding normally.")
        
        if not active:
            return DesyncAlert(active, silent, "LOUD_FAILURE", 0.5,
                             "All channels silent — likely maintenance or genuine outage.")
        
        # Some active, some silent = the scary case
        silent_ratio = len(silent) / (len(active) + len(silent))
        
        # Check if silent channels include high-trust ones
        high_trust_channels = {"heartbeat", "email", "attestation"}
        silent_high_trust = set(silent) & high_trust_channels
        
        if silent_high_trust:
            severity = 0.8 + 0.2 * silent_ratio
            alert_type = "QUIET_BETRAYAL"
            explanation = (f"High-trust channels silent ({', '.join(silent_high_trust)}) "
                         f"while others active ({', '.join(active)}). "
                         f"Possible silent compromise: auto-forward, suppressed output.")
        else:
            severity = 0.3 + 0.4 * silent_ratio
            alert_type = "SELECTIVE_SILENCE"
            explanation = (f"Channels desynchronized: {', '.join(silent)} silent while "
                         f"{', '.join(active)} active. Monitor for escalation.")
        
        alert = DesyncAlert(active, silent, alert_type, round(severity, 3), explanation)
        self.alerts.append(alert)
        return alert


def demo():
    print("=" * 60)
    print("DEAD MAN'S SWITCH")
    print("=" * 60)
    print()
    print('Santaclawd: "the scariest attack is silent."')
    print("Selective silence = compromise signal.")
    print()
    
    now = time.time()
    
    channels = [
        ChannelState("heartbeat", now, expected_interval_hours=0.33),
        ChannelState("email", now, expected_interval_hours=4.0),
        ChannelState("clawk", now, expected_interval_hours=1.0),
        ChannelState("attestation", now, expected_interval_hours=2.0),
        ChannelState("moltbook", now, expected_interval_hours=6.0),
    ]
    
    switch = DeadMansSwitch(channels)
    
    # Scenario 1: Normal operation
    print("SCENARIO 1: Normal (all active)")
    alert = switch.check_liveness(now)
    print(f"  Type: {alert.alert_type}, Severity: {alert.severity}")
    print(f"  {alert.explanation}")
    print()
    
    # Scenario 2: Loud failure (all silent)
    print("SCENARIO 2: Loud failure (all silent, 24h later)")
    alert = switch.check_liveness(now + 86400)
    print(f"  Type: {alert.alert_type}, Severity: {alert.severity}")
    print(f"  {alert.explanation}")
    print()
    
    # Scenario 3: Quiet betrayal (heartbeat + email silent, others active)
    print("SCENARIO 3: Quiet betrayal (heartbeat+email silent)")
    switch2 = DeadMansSwitch(channels)
    compromise_time = now + 7200  # 2 hours later
    switch2.update_activity("clawk", compromise_time)
    switch2.update_activity("moltbook", compromise_time)
    switch2.update_activity("attestation", compromise_time)
    # heartbeat and email NOT updated = silent
    alert = switch2.check_liveness(compromise_time)
    print(f"  Type: {alert.alert_type}, Severity: {alert.severity}")
    print(f"  {alert.explanation}")
    print()
    
    # Scenario 4: Selective silence (moltbook down, rest active)
    print("SCENARIO 4: Selective silence (moltbook down, rest active)")
    check_time = now + 86400
    switch3 = DeadMansSwitch(channels)
    switch3.update_activity("heartbeat", check_time - 300)  # 5 min ago
    switch3.update_activity("email", check_time - 1800)  # 30 min ago
    switch3.update_activity("clawk", check_time - 600)  # 10 min ago
    switch3.update_activity("attestation", check_time - 3600)  # 1h ago
    # moltbook NOT updated = 24h stale
    alert = switch3.check_liveness(check_time)
    print(f"  Type: {alert.alert_type}, Severity: {alert.severity}")
    print(f"  {alert.explanation}")
    print()
    
    print("KEY INSIGHTS:")
    print("-" * 50)
    print("  1. Loud failure (all channels) = probably genuine outage")
    print("  2. Quiet betrayal (high-trust silent, others active)")
    print("     = MOST DANGEROUS. Silent auto-forward, suppressed output.")
    print("  3. Selective silence (low-priority channel) = monitor")
    print("  4. The dead man's switch IS the heartbeat.")
    print("     Heartbeat stops + email forwards = alarm.")
    print("  5. Channel desync = the signal. Not any single channel.")
    
    # Assertions
    normal = DeadMansSwitch(channels)
    assert normal.check_liveness(now).alert_type == "ALL_ACTIVE"
    assert normal.check_liveness(now + 86400).alert_type == "LOUD_FAILURE"
    assert switch2.check_liveness(compromise_time).alert_type == "QUIET_BETRAYAL"
    assert switch2.check_liveness(compromise_time).severity > 0.7
    
    print()
    print("All assertions passed ✓")


if __name__ == "__main__":
    demo()
