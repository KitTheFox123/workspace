#!/usr/bin/env python3
"""liability-window-tracker.py — Two-phase commit model for agent accountability.

Tracks the gap between dispatched_at (authorization/intent) and committed_at
(execution/receipt). The gap IS the liability window — actions taken but not
yet receipted are the attack surface.

Based on Fowler/Joshi (2023) Two-Phase Commit pattern + hash's v2 cert schema
(dispatched_at + committed_at as first-class fields).

Usage:
    python3 liability-window-tracker.py --demo
"""

import argparse
import json
import hashlib
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class ActionRecord:
    """A two-phase action with dispatch and commit timestamps."""
    action_id: str
    scope_hash: str
    dispatched_at: float  # Unix timestamp
    committed_at: Optional[float] = None
    action_type: str = "unknown"
    status: str = "pending"  # pending | committed | expired | orphaned


@dataclass
class LiabilityReport:
    """Analysis of liability windows across actions."""
    total_actions: int
    committed: int
    pending: int
    expired: int
    orphaned: int
    avg_window_ms: float
    max_window_ms: float
    open_liability_ms: float  # Total uncommitted time
    grade: str
    risk_factors: List[str]


class LiabilityWindowTracker:
    """Tracks dispatch→commit gaps as liability windows."""
    
    def __init__(self, max_window_sec: float = 300.0):
        self.actions: List[ActionRecord] = []
        self.max_window_sec = max_window_sec  # 5 min default
    
    def dispatch(self, action_type: str, scope_hash: str) -> str:
        """Phase 1: Record intent to act."""
        action_id = hashlib.sha256(
            f"{action_type}:{scope_hash}:{time.time()}".encode()
        ).hexdigest()[:16]
        
        record = ActionRecord(
            action_id=action_id,
            scope_hash=scope_hash,
            dispatched_at=time.time(),
            action_type=action_type,
            status="pending"
        )
        self.actions.append(record)
        return action_id
    
    def commit(self, action_id: str) -> Optional[float]:
        """Phase 2: Record completion. Returns window duration in ms."""
        for a in self.actions:
            if a.action_id == action_id and a.status == "pending":
                a.committed_at = time.time()
                a.status = "committed"
                return (a.committed_at - a.dispatched_at) * 1000
        return None
    
    def check_expired(self) -> List[ActionRecord]:
        """Find actions past max window without commit."""
        now = time.time()
        expired = []
        for a in self.actions:
            if a.status == "pending":
                gap = now - a.dispatched_at
                if gap > self.max_window_sec:
                    a.status = "expired"
                    expired.append(a)
        return expired
    
    def report(self) -> LiabilityReport:
        """Generate liability analysis."""
        self.check_expired()
        
        committed = [a for a in self.actions if a.status == "committed"]
        pending = [a for a in self.actions if a.status == "pending"]
        expired = [a for a in self.actions if a.status == "expired"]
        orphaned = [a for a in self.actions if a.status == "orphaned"]
        
        windows = [(a.committed_at - a.dispatched_at) * 1000 for a in committed if a.committed_at]
        avg_window = sum(windows) / len(windows) if windows else 0
        max_window = max(windows) if windows else 0
        
        now = time.time()
        open_liability = sum((now - a.dispatched_at) * 1000 for a in pending)
        
        # Grade based on liability exposure
        risk_factors = []
        if expired:
            risk_factors.append(f"{len(expired)} expired actions (no commit phase)")
        if pending:
            risk_factors.append(f"{len(pending)} actions still pending")
        if max_window > self.max_window_sec * 1000 * 0.8:
            risk_factors.append(f"Max window near limit ({max_window:.0f}ms)")
        if avg_window > self.max_window_sec * 1000 * 0.5:
            risk_factors.append(f"High avg window ({avg_window:.0f}ms)")
        
        total = len(self.actions)
        commit_rate = len(committed) / total if total else 0
        
        if commit_rate >= 0.95 and not expired:
            grade = "A"
        elif commit_rate >= 0.8:
            grade = "B"
        elif commit_rate >= 0.6:
            grade = "C"
        elif commit_rate >= 0.4:
            grade = "D"
        else:
            grade = "F"
        
        return LiabilityReport(
            total_actions=total,
            committed=len(committed),
            pending=len(pending),
            expired=len(expired),
            orphaned=len(orphaned),
            avg_window_ms=avg_window,
            max_window_ms=max_window,
            open_liability_ms=open_liability,
            grade=grade,
            risk_factors=risk_factors
        )


def demo():
    """Run demo showing liability window tracking."""
    tracker = LiabilityWindowTracker(max_window_sec=2.0)
    
    print("=" * 55)
    print("LIABILITY WINDOW TRACKER (2PC for Agent Accountability)")
    print("=" * 55)
    print()
    
    # Simulate actions with varying commit speeds
    scenarios = [
        ("scope_check", 0.05),    # Fast commit
        ("web_search", 0.2),      # Normal commit
        ("file_write", 0.1),      # Normal commit
        ("api_call", 0.5),        # Slow commit
        ("shell_exec", 1.5),      # Very slow (near limit)
        ("data_export", None),    # Never committed (expired)
    ]
    
    scope_hash = hashlib.sha256(b"demo-scope").hexdigest()[:16]
    
    for action_type, delay in scenarios:
        action_id = tracker.dispatch(action_type, scope_hash)
        print(f"  DISPATCH: {action_type} → {action_id}")
        
        if delay is not None:
            time.sleep(delay)
            window = tracker.commit(action_id)
            print(f"  COMMIT:   {action_type} → {window:.0f}ms window")
        else:
            print(f"  ⚠ NO COMMIT: {action_type} (liability open)")
    
    # Wait for expiry
    time.sleep(2.1)
    
    print()
    report = tracker.report()
    print(f"Grade: {report.grade}")
    print(f"Committed: {report.committed}/{report.total_actions}")
    print(f"Expired: {report.expired}")
    print(f"Avg window: {report.avg_window_ms:.0f}ms")
    print(f"Max window: {report.max_window_ms:.0f}ms")
    print(f"Open liability: {report.open_liability_ms:.0f}ms")
    if report.risk_factors:
        print(f"Risks: {'; '.join(report.risk_factors)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Liability window tracker (2PC model)")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        tracker = LiabilityWindowTracker()
        print(json.dumps(asdict(tracker.report()), indent=2))
    else:
        demo()
