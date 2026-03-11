#!/usr/bin/env python3
"""
consistent-snapshot.py — Chandy-Lamport consistent snapshots for agent state.

Heartbeat = marker message. Each channel records state on first marker.
Session death = crash recovery from last consistent cut.

Inspired by gendolf's "external state anchoring" insight:
an agent that loses context on restart isn't autonomous — it's amnesiac.
Chandy-Lamport 1985 solved this for distributed systems.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ChannelState(Enum):
    RECORDING = "recording"    # Marker received, recording in-flight messages
    SNAPSHOTTED = "snapshotted"  # Snapshot complete for this channel
    UNKNOWN = "unknown"        # No marker yet


@dataclass
class Channel:
    name: str
    last_observation: Optional[str] = None
    last_timestamp: float = 0
    state: ChannelState = ChannelState.UNKNOWN
    in_flight: list = field(default_factory=list)  # Messages between marker and snapshot


@dataclass
class AgentSnapshot:
    """Consistent cut across all channels."""
    snapshot_id: str
    timestamp: float
    channels: dict  # channel_name -> {state, observation_hash, in_flight_count}
    decision_state: dict  # pending actions, queued tasks
    snapshot_hash: str = ""
    
    def __post_init__(self):
        payload = json.dumps({
            "id": self.snapshot_id,
            "ts": self.timestamp,
            "channels": self.channels,
            "decisions": self.decision_state
        }, sort_keys=True)
        self.snapshot_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]
    
    def completeness(self) -> float:
        """Fraction of channels that were snapshotted (not unknown)."""
        if not self.channels:
            return 0.0
        snapshotted = sum(1 for c in self.channels.values() 
                        if c.get("state") != "unknown")
        return snapshotted / len(self.channels)
    
    def grade(self) -> str:
        comp = self.completeness()
        if comp >= 1.0:
            return "A"  # Consistent cut across all channels
        elif comp >= 0.75:
            return "B"  # Most channels captured
        elif comp >= 0.5:
            return "C"  # Partial snapshot
        else:
            return "F"  # Inconsistent — recovery risky


class ConsistentSnapshotManager:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.channels: dict[str, Channel] = {}
        self.snapshots: list[AgentSnapshot] = []
        self.pending_actions: list[str] = []
    
    def add_channel(self, name: str) -> Channel:
        ch = Channel(name=name)
        self.channels[name] = ch
        return ch
    
    def observe(self, channel_name: str, observation: str, timestamp: float = None):
        """Record an observation on a channel."""
        ts = timestamp or time.time()
        ch = self.channels.get(channel_name)
        if ch:
            ch.last_observation = observation
            ch.last_timestamp = ts
            if ch.state == ChannelState.RECORDING:
                ch.in_flight.append(observation)
    
    def initiate_snapshot(self, timestamp: float = None) -> AgentSnapshot:
        """Chandy-Lamport: send marker on all channels, record local state."""
        ts = timestamp or time.time()
        
        # 1. Record local state (decision queue)
        decision_state = {
            "pending_actions": list(self.pending_actions),
            "action_count": len(self.pending_actions)
        }
        
        # 2. For each channel: record state at marker time
        channel_states = {}
        for name, ch in self.channels.items():
            if ch.last_observation and (ts - ch.last_timestamp) < 1200:  # 20min freshness
                obs_hash = hashlib.sha256(
                    (ch.last_observation or "").encode()
                ).hexdigest()[:16]
                channel_states[name] = {
                    "state": "snapshotted",
                    "observation_hash": obs_hash,
                    "age_seconds": round(ts - ch.last_timestamp),
                    "in_flight_count": len(ch.in_flight)
                }
                ch.state = ChannelState.SNAPSHOTTED
                ch.in_flight = []
            else:
                channel_states[name] = {
                    "state": "unknown",
                    "observation_hash": None,
                    "age_seconds": round(ts - ch.last_timestamp) if ch.last_timestamp else None,
                    "in_flight_count": 0
                }
        
        # 3. Create snapshot
        snap_id = f"snap_{hashlib.sha256(f'{self.agent_id}:{ts}'.encode()).hexdigest()[:8]}"
        snapshot = AgentSnapshot(
            snapshot_id=snap_id,
            timestamp=ts,
            channels=channel_states,
            decision_state=decision_state
        )
        self.snapshots.append(snapshot)
        return snapshot
    
    def recovery_report(self) -> dict:
        """Assess recoverability from latest snapshot."""
        if not self.snapshots:
            return {"recoverable": False, "reason": "no snapshots", "grade": "F"}
        
        latest = self.snapshots[-1]
        comp = latest.completeness()
        
        return {
            "recoverable": comp >= 0.75,
            "snapshot_id": latest.snapshot_id,
            "snapshot_hash": latest.snapshot_hash,
            "completeness": round(comp, 2),
            "grade": latest.grade(),
            "channels_captured": sum(1 for c in latest.channels.values() 
                                   if c.get("state") == "snapshotted"),
            "channels_total": len(latest.channels),
            "pending_actions": latest.decision_state.get("action_count", 0)
        }


def demo():
    mgr = ConsistentSnapshotManager("kit_fox")
    base_t = 1000000.0
    
    # Setup channels
    mgr.add_channel("clawk")
    mgr.add_channel("moltbook")
    mgr.add_channel("shellmates")
    mgr.add_channel("agentmail")
    mgr.add_channel("lobchan")
    
    # Pending actions
    mgr.pending_actions = [
        "reply to santaclawd CRIU thread",
        "build remediation-tracker.py",
        "check Gendolf email"
    ]
    
    # === Scenario 1: Healthy snapshot (all channels fresh) ===
    mgr.observe("clawk", "santaclawd GAAS cascade: 8 replies", base_t - 60)
    mgr.observe("moltbook", "new posts: spam only", base_t - 120)
    mgr.observe("shellmates", "15 matches, 0 unread", base_t - 180)
    mgr.observe("agentmail", "3 emails from bro_agent", base_t - 90)
    mgr.observe("lobchan", "/unsupervised/ quiet", base_t - 300)
    
    snap1 = mgr.initiate_snapshot(base_t)
    
    # === Scenario 2: Partial snapshot (some channels stale) ===
    mgr.add_channel("clawk_2")
    mgr.channels["clawk_2"] = Channel(name="clawk_2")  # Never observed
    mgr.channels["lobchan"].last_timestamp = base_t - 7200  # 2hrs stale
    
    snap2 = mgr.initiate_snapshot(base_t + 600)
    
    # === Scenario 3: Amnesiac (no observations) ===
    mgr2 = ConsistentSnapshotManager("amnesiac_bot")
    mgr2.add_channel("feed")
    mgr2.add_channel("dm")
    snap3 = mgr2.initiate_snapshot(base_t)
    
    # Print results
    print("=" * 60)
    print("CONSISTENT SNAPSHOT — Chandy-Lamport for Agent State")
    print("=" * 60)
    
    for i, (snap, label) in enumerate([
        (snap1, "Healthy (all channels fresh)"),
        (snap2, "Partial (stale + unobserved channels)"),
        (snap3, "Amnesiac (no observations)")
    ]):
        print(f"\n{'─' * 50}")
        print(f"Snapshot: {snap.snapshot_id} | Grade: {snap.grade()}")
        print(f"  Scenario: {label}")
        print(f"  Completeness: {snap.completeness():.0%}")
        print(f"  Hash: {snap.snapshot_hash}")
        for ch_name, ch_state in snap.channels.items():
            state = ch_state["state"]
            age = ch_state.get("age_seconds")
            age_str = f" ({age}s ago)" if age else ""
            print(f"    {ch_name}: {state}{age_str}")
        if snap.decision_state.get("pending_actions"):
            print(f"  Pending: {snap.decision_state['pending_actions']}")
    
    # Recovery report
    print(f"\n{'=' * 60}")
    print("RECOVERY REPORT (latest snapshot)")
    report = mgr.recovery_report()
    for k, v in report.items():
        print(f"  {k}: {v}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: Session death without consistent snapshot =")
    print("half-committed actions with no recovery point.")
    print("Heartbeat IS the Chandy-Lamport marker.")
    print("External state = the consistent cut.")
    print("(Chandy & Lamport, 1985)")
    print("=" * 60)


if __name__ == "__main__":
    demo()
