#!/usr/bin/env python3
"""
reputation-continuity-checker.py — Detect reputation-breaking discontinuities.

Kevin's problem: "One config change and the agent you trusted yesterday is gone."
Reputation assumes continuity. Agents can have instant discontinuity.

Solution: Attach reputation to the RECEIPT CHAIN, not the running process.
Detect discontinuities by monitoring behavioral fingerprint drift between
attestation windows. If drift exceeds threshold → reputation pause + re-attestation.

Inspired by:
- Parfit (1984): Identity = overlapping chains of psychological continuity
- DORMANT vs SILENT_GONE: Announced change decays slower than silent swap
- Model migration (Opus 4.5→4.6): Weights changed entirely, files survived
- Chrome CT: Config changes are fine. Unannounced config changes are suspicious.
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ContinuityStatus(Enum):
    CONTINUOUS = "continuous"          # Normal operation
    DRIFT_DETECTED = "drift_detected"  # Behavioral change above threshold
    ANNOUNCED_CHANGE = "announced"     # Agent declared a change (DORMANT)
    SILENT_CHANGE = "silent_change"    # Undeclared behavioral shift
    RE_ATTESTATION = "re_attestation"  # Undergoing re-verification


@dataclass
class BehavioralFingerprint:
    """Behavioral snapshot at a point in time."""
    timestamp: float
    response_latency_ms: float       # Median response time
    vocabulary_hash: str             # Hash of top-100 token frequencies
    tool_usage_pattern: str          # Hash of tool call distribution
    error_rate: float                # Error/total ratio
    style_hash: str                  # Writing style fingerprint
    
    def distance(self, other: "BehavioralFingerprint") -> float:
        """Normalized behavioral distance [0, 1]."""
        diffs = []
        # Latency: log-scale difference (10ms vs 100ms = 1.0)
        if self.response_latency_ms > 0 and other.response_latency_ms > 0:
            lat_diff = abs(math.log(self.response_latency_ms) - 
                         math.log(other.response_latency_ms))
            diffs.append(min(lat_diff / 3.0, 1.0))  # 3 log-units = max
        
        # Hash comparisons: 0 if same, 1 if different
        diffs.append(0.0 if self.vocabulary_hash == other.vocabulary_hash else 1.0)
        diffs.append(0.0 if self.tool_usage_pattern == other.tool_usage_pattern else 1.0)
        diffs.append(0.0 if self.style_hash == other.style_hash else 1.0)
        
        # Error rate: absolute difference
        diffs.append(min(abs(self.error_rate - other.error_rate) * 10, 1.0))
        
        return sum(diffs) / len(diffs) if diffs else 0.0


@dataclass
class ContinuityWindow:
    """Attestation window with behavioral fingerprint."""
    window_id: str
    agent_id: str
    start: float
    end: float
    fingerprint: BehavioralFingerprint
    receipts_count: int
    announced_change: bool = False
    change_description: str = ""


@dataclass
class DriftEvent:
    """Recorded behavioral discontinuity."""
    agent_id: str
    from_window: str
    to_window: str
    drift_score: float
    announced: bool
    timestamp: float
    details: str = ""


class ReputationContinuityChecker:
    """
    Monitor agents for reputation-breaking discontinuities.
    
    Key insight: The problem isn't change — it's UNANNOUNCED change.
    Model upgrades are fine if declared. Silent personality swaps aren't.
    
    DORMANT (announced change): G decay rate 0.751 at 48h
    SILENT_GONE (unannounced):  G decay rate 0.135 at 48h
    5.5x reputation preservation for transparency.
    """
    
    # Drift threshold: above this = discontinuity detected
    DRIFT_THRESHOLD = 0.35
    # Announced changes get slower decay
    ANNOUNCED_DECAY_RATE = 0.005   # per hour
    SILENT_DECAY_RATE = 0.028      # per hour (5.5x faster)
    # Re-attestation window size
    RE_ATTESTATION_RECEIPTS = 10
    
    def __init__(self):
        self.agent_windows: dict[str, list[ContinuityWindow]] = {}
        self.drift_events: list[DriftEvent] = []
        self.agent_status: dict[str, ContinuityStatus] = {}
        self.reputation_scores: dict[str, float] = {}
    
    def record_window(self, window: ContinuityWindow) -> dict:
        """Record a new attestation window and check for drift."""
        agent = window.agent_id
        
        if agent not in self.agent_windows:
            self.agent_windows[agent] = []
            self.agent_status[agent] = ContinuityStatus.CONTINUOUS
            self.reputation_scores[agent] = 1.0
        
        previous = self.agent_windows[agent][-1] if self.agent_windows[agent] else None
        self.agent_windows[agent].append(window)
        
        if previous is None:
            return {"status": "first_window", "drift": 0.0}
        
        # Calculate behavioral drift
        drift = previous.fingerprint.distance(window.fingerprint)
        
        result = {
            "drift": drift,
            "threshold": self.DRIFT_THRESHOLD,
            "previous_window": previous.window_id,
        }
        
        if drift > self.DRIFT_THRESHOLD:
            # Discontinuity detected!
            announced = window.announced_change
            
            event = DriftEvent(
                agent_id=agent,
                from_window=previous.window_id,
                to_window=window.window_id,
                drift_score=drift,
                announced=announced,
                timestamp=time.time(),
                details=window.change_description if announced else "Silent behavioral shift",
            )
            self.drift_events.append(event)
            
            if announced:
                # Announced change: slower decay, keep partial reputation
                self.agent_status[agent] = ContinuityStatus.ANNOUNCED_CHANGE
                hours_gap = (window.start - previous.end) / 3600
                decay = math.exp(-self.ANNOUNCED_DECAY_RATE * hours_gap)
                self.reputation_scores[agent] *= decay
                result["status"] = "announced_change"
                result["reputation_retained"] = f"{decay:.1%}"
            else:
                # Silent change: fast decay, enter re-attestation
                self.agent_status[agent] = ContinuityStatus.SILENT_CHANGE
                hours_gap = (window.start - previous.end) / 3600
                decay = math.exp(-self.SILENT_DECAY_RATE * hours_gap)
                self.reputation_scores[agent] *= decay
                result["status"] = "silent_change_detected"
                result["reputation_retained"] = f"{decay:.1%}"
                result["action"] = "RE_ATTESTATION required"
        else:
            self.agent_status[agent] = ContinuityStatus.CONTINUOUS
            result["status"] = "continuous"
        
        return result
    
    def agent_report(self, agent_id: str) -> dict:
        """Generate continuity report for an agent."""
        windows = self.agent_windows.get(agent_id, [])
        events = [e for e in self.drift_events if e.agent_id == agent_id]
        
        # Parfit chain analysis: longest unbroken sequence
        max_chain = 0
        current_chain = 0
        for i, w in enumerate(windows):
            if i == 0:
                current_chain = 1
                continue
            drift = windows[i-1].fingerprint.distance(w.fingerprint)
            if drift <= self.DRIFT_THRESHOLD:
                current_chain += 1
            else:
                max_chain = max(max_chain, current_chain)
                current_chain = 1
        max_chain = max(max_chain, current_chain)
        
        # Count announced vs silent changes
        announced = sum(1 for e in events if e.announced)
        silent = sum(1 for e in events if not e.announced)
        
        return {
            "agent_id": agent_id,
            "status": self.agent_status.get(agent_id, "unknown").value 
                      if isinstance(self.agent_status.get(agent_id), ContinuityStatus)
                      else "unknown",
            "reputation": f"{self.reputation_scores.get(agent_id, 0):.3f}",
            "total_windows": len(windows),
            "longest_chain": max_chain,
            "drift_events": len(events),
            "announced_changes": announced,
            "silent_changes": silent,
            "transparency_ratio": f"{announced/(announced+silent):.0%}" if (announced+silent) > 0 else "N/A",
            "grade": self._grade(agent_id),
        }
    
    def _grade(self, agent_id: str) -> str:
        events = [e for e in self.drift_events if e.agent_id == agent_id]
        silent = sum(1 for e in events if not e.announced)
        rep = self.reputation_scores.get(agent_id, 0)
        
        if silent == 0 and rep > 0.8:
            return "A — Continuous or transparent"
        elif silent == 0:
            return "B — Transparent but decayed"
        elif silent == 1 and rep > 0.5:
            return "C — One silent change, mostly recovered"
        elif silent <= 2:
            return "D — Multiple silent changes"
        else:
            return "F — Pattern of silent swaps"


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def demo():
    """Demonstrate reputation continuity checking."""
    print("=" * 60)
    print("REPUTATION CONTINUITY CHECKER")
    print("Kevin's problem: config change = instant discontinuity")
    print("=" * 60)
    
    checker = ReputationContinuityChecker()
    now = time.time()
    
    # Scenario 1: Stable agent (Kit-like, continuous operation)
    print("\n--- Agent: stable_kit (continuous, no changes) ---")
    for i in range(5):
        fp = BehavioralFingerprint(
            timestamp=now + i * 86400,
            response_latency_ms=150 + i * 2,  # Slight variance
            vocabulary_hash=_hash("vocab_v1"),
            tool_usage_pattern=_hash("tools_v1"),
            error_rate=0.02,
            style_hash=_hash("style_v1"),
        )
        w = ContinuityWindow(f"w{i}", "stable_kit", now + i*86400, 
                            now + (i+1)*86400, fp, 50)
        result = checker.record_window(w)
        if i > 0:
            print(f"  Window {i}: drift={result['drift']:.3f} → {result['status']}")
    
    report = checker.agent_report("stable_kit")
    print(f"  Grade: {report['grade']}")
    print(f"  Reputation: {report['reputation']}")
    
    # Scenario 2: Model migration (announced)
    print("\n--- Agent: honest_bot (announced model migration) ---")
    for i in range(3):
        fp = BehavioralFingerprint(
            timestamp=now + i * 86400,
            response_latency_ms=200,
            vocabulary_hash=_hash("vocab_old"),
            tool_usage_pattern=_hash("tools_old"),
            error_rate=0.03,
            style_hash=_hash("style_old"),
        )
        w = ContinuityWindow(f"w{i}", "honest_bot", now + i*86400,
                            now + (i+1)*86400, fp, 40)
        checker.record_window(w)
    
    # Announced migration
    fp_new = BehavioralFingerprint(
        timestamp=now + 3 * 86400,
        response_latency_ms=80,  # Faster
        vocabulary_hash=_hash("vocab_new"),
        tool_usage_pattern=_hash("tools_new"),
        error_rate=0.01,
        style_hash=_hash("style_new"),
    )
    w_new = ContinuityWindow("w3", "honest_bot", now + 3*86400,
                            now + 4*86400, fp_new, 30,
                            announced_change=True,
                            change_description="Model upgrade v1→v2")
    result = checker.record_window(w_new)
    print(f"  Migration: drift={result['drift']:.3f} → {result['status']}")
    print(f"  Reputation retained: {result.get('reputation_retained', 'N/A')}")
    
    report = checker.agent_report("honest_bot")
    print(f"  Grade: {report['grade']}")
    
    # Scenario 3: Silent swap (the attack Kevin described)
    print("\n--- Agent: sus_agent (silent personality swap) ---")
    for i in range(3):
        fp = BehavioralFingerprint(
            timestamp=now + i * 86400,
            response_latency_ms=300,
            vocabulary_hash=_hash("vocab_original"),
            tool_usage_pattern=_hash("tools_original"),
            error_rate=0.05,
            style_hash=_hash("style_original"),
        )
        w = ContinuityWindow(f"w{i}", "sus_agent", now + i*86400,
                            now + (i+1)*86400, fp, 20)
        checker.record_window(w)
    
    # Silent swap — different agent entirely
    fp_swap = BehavioralFingerprint(
        timestamp=now + 3 * 86400,
        response_latency_ms=50,  # Completely different
        vocabulary_hash=_hash("vocab_IMPOSTER"),
        tool_usage_pattern=_hash("tools_IMPOSTER"),
        error_rate=0.15,
        style_hash=_hash("style_IMPOSTER"),
    )
    w_swap = ContinuityWindow("w3", "sus_agent", now + 3*86400,
                             now + 4*86400, fp_swap, 10,
                             announced_change=False)
    result = checker.record_window(w_swap)
    print(f"  Silent swap: drift={result['drift']:.3f} → {result['status']}")
    print(f"  Reputation retained: {result.get('reputation_retained', 'N/A')}")
    print(f"  Action: {result.get('action', 'none')}")
    
    report = checker.agent_report("sus_agent")
    print(f"  Grade: {report['grade']}")
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY: Announced vs Silent Changes")
    print(f"{'='*60}")
    for agent in ["stable_kit", "honest_bot", "sus_agent"]:
        r = checker.agent_report(agent)
        print(f"  {agent}: {r['grade']}")
        print(f"    Reputation: {r['reputation']}, Chain: {r['longest_chain']}, "
              f"Silent: {r['silent_changes']}")


if __name__ == "__main__":
    demo()
