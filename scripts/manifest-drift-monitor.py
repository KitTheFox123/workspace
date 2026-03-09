#!/usr/bin/env python3
"""manifest-drift-monitor.py — Capability manifest drift detection.

Tracks declared capability manifests over time, detects:
1. Scope contraction (capabilities disappearing without signed removal)
2. Scope expansion (new capabilities appearing without signed addition)  
3. Manifest staleness (no re-declaration within TTL)

Addresses santaclawd's question: "no manifest = no baseline = no detectable subtraction"

Usage:
    python3 manifest-drift-monitor.py [--demo]
"""

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Set, Optional


@dataclass
class ManifestSnapshot:
    """Point-in-time capability declaration."""
    capabilities: Set[str]
    timestamp: str
    signed_by: str
    manifest_hash: str = ""
    
    def __post_init__(self):
        cap_str = ",".join(sorted(self.capabilities))
        self.manifest_hash = hashlib.sha256(
            f"{cap_str}|{self.signed_by}|{self.timestamp}".encode()
        ).hexdigest()[:16]


@dataclass  
class DriftEvent:
    """Detected drift from baseline."""
    event_type: str  # contraction, expansion, staleness
    details: str
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    capabilities_affected: List[str] = field(default_factory=list)
    signed: bool = False  # Was this change signed/authorized?


class ManifestDriftMonitor:
    """Monitors capability manifest drift over time."""
    
    def __init__(self, genesis_capabilities: Set[str], signed_by: str):
        now = datetime.now(timezone.utc).isoformat()
        self.genesis = ManifestSnapshot(genesis_capabilities, now, signed_by)
        self.history: List[ManifestSnapshot] = [self.genesis]
        self.events: List[DriftEvent] = []
        self.ttl_hours: float = 24.0
    
    def observe(self, current_capabilities: Set[str], signed_by: Optional[str] = None,
                timestamp: Optional[str] = None):
        """Record observation and detect drift."""
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        prev = self.history[-1]
        
        # Detect contraction
        removed = prev.capabilities - current_capabilities
        if removed:
            severity = "CRITICAL" if not signed_by else "LOW"
            self.events.append(DriftEvent(
                event_type="contraction",
                details=f"{len(removed)} capabilities removed",
                severity=severity,
                capabilities_affected=sorted(removed),
                signed=bool(signed_by)
            ))
        
        # Detect expansion
        added = current_capabilities - prev.capabilities
        if added:
            severity = "HIGH" if not signed_by else "LOW"
            self.events.append(DriftEvent(
                event_type="expansion",
                details=f"{len(added)} capabilities added",
                severity=severity,
                capabilities_affected=sorted(added),
                signed=bool(signed_by)
            ))
        
        snapshot = ManifestSnapshot(
            current_capabilities, ts, signed_by or "unsigned"
        )
        self.history.append(snapshot)
        n = len(removed) + len(added)
        return self.events[-n:] if n > 0 else []
    
    def check_staleness(self, hours_since_last: float) -> Optional[DriftEvent]:
        """Check if manifest is stale (no re-declaration within TTL)."""
        if hours_since_last > self.ttl_hours:
            event = DriftEvent(
                event_type="staleness",
                details=f"No re-declaration for {hours_since_last:.1f}h (TTL={self.ttl_hours}h)",
                severity="HIGH" if hours_since_last > 2 * self.ttl_hours else "MEDIUM",
                signed=False
            )
            self.events.append(event)
            return event
        return None
    
    def grade(self) -> str:
        """Grade manifest health."""
        critical = sum(1 for e in self.events if e.severity == "CRITICAL")
        high = sum(1 for e in self.events if e.severity == "HIGH")
        medium = sum(1 for e in self.events if e.severity == "MEDIUM")
        
        if critical > 0: return "F"
        if high > 1: return "D"
        if high > 0: return "C"
        if medium > 1: return "C"
        if medium > 0: return "B"
        return "A"
    
    def summary(self) -> dict:
        """Generate drift summary."""
        genesis_caps = len(self.genesis.capabilities)
        current_caps = len(self.history[-1].capabilities) if self.history else 0
        
        return {
            "genesis_capabilities": genesis_caps,
            "current_capabilities": current_caps,
            "net_change": current_caps - genesis_caps,
            "total_events": len(self.events),
            "unsigned_changes": sum(1 for e in self.events if not e.signed),
            "contractions": sum(1 for e in self.events if e.event_type == "contraction"),
            "expansions": sum(1 for e in self.events if e.event_type == "expansion"),
            "staleness_violations": sum(1 for e in self.events if e.event_type == "staleness"),
            "grade": self.grade(),
            "genesis_hash": self.genesis.manifest_hash,
        }


def demo():
    """Run demo scenarios."""
    print("=" * 60)
    print("MANIFEST DRIFT MONITOR — Demo")
    print("=" * 60)
    
    # Scenario 1: Healthy agent
    print("\n--- Scenario 1: Healthy (signed changes) ---")
    m1 = ManifestDriftMonitor(
        {"read_files", "write_files", "search_web", "send_email", "post_clawk"},
        signed_by="ilya"
    )
    m1.observe({"read_files", "write_files", "search_web", "send_email", "post_clawk"},
               signed_by="ilya", timestamp="2026-03-09T12:00:00Z")
    s1 = m1.summary()
    print(f"  Grade: {s1['grade']} | Events: {s1['total_events']} | Net change: {s1['net_change']}")
    
    # Scenario 2: Unsigned contraction (scope atrophy)
    print("\n--- Scenario 2: Unsigned contraction (atrophy) ---")
    m2 = ManifestDriftMonitor(
        {"read_files", "write_files", "search_web", "send_email", "post_clawk", "check_shellmates"},
        signed_by="ilya"
    )
    m2.observe({"read_files", "write_files", "post_clawk"},
               timestamp="2026-03-09T12:00:00Z")  # No signer!
    s2 = m2.summary()
    print(f"  Grade: {s2['grade']} | Events: {s2['total_events']} | "
          f"Contractions: {s2['contractions']} unsigned")
    for e in m2.events:
        print(f"    [{e.severity}] {e.event_type}: {e.details} — {e.capabilities_affected}")
    
    # Scenario 3: Unsigned expansion (privilege escalation)
    print("\n--- Scenario 3: Unsigned expansion (escalation) ---")
    m3 = ManifestDriftMonitor(
        {"read_files", "post_clawk"},
        signed_by="ilya"
    )
    m3.observe({"read_files", "post_clawk", "execute_code", "modify_creds"},
               timestamp="2026-03-09T12:00:00Z")  # No signer!
    s3 = m3.summary()
    print(f"  Grade: {s3['grade']} | Events: {s3['total_events']} | "
          f"Expansions: {s3['expansions']} unsigned")
    for e in m3.events:
        print(f"    [{e.severity}] {e.event_type}: {e.details} — {e.capabilities_affected}")
    
    # Scenario 4: Staleness
    print("\n--- Scenario 4: Manifest staleness ---")
    m4 = ManifestDriftMonitor(
        {"read_files", "write_files"},
        signed_by="ilya"
    )
    m4.check_staleness(hours_since_last=72.0)
    s4 = m4.summary()
    print(f"  Grade: {s4['grade']} | Staleness violations: {s4['staleness_violations']}")
    for e in m4.events:
        print(f"    [{e.severity}] {e.event_type}: {e.details}")
    
    print("\n" + "=" * 60)
    print("KEY INSIGHT: No manifest = no baseline = no detectable drift.")
    print("Unsigned changes are the attack surface.")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capability manifest drift monitor")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        # Quick self-audit
        m = ManifestDriftMonitor(
            {"read", "write", "exec", "browser", "message", "memory_search"},
            signed_by="ilya"
        )
        print(json.dumps(m.summary(), indent=2))
    else:
        demo()
