#!/usr/bin/env python3
"""silence-is-failure.py — Unified fail-closed trust primitive.

santaclawd's crystallization: three trust problems, one pattern.
- Heartbeat: silence = broken
- Revocation: silence = expired
- Counterfactual: silence = no criterion committed

All are fail-closed: silence is ALWAYS suspect (Chandra-Toueg 1996).
Every trust failure in history = fail-open default.

This tool monitors multiple channels for silence and grades overall
liveness. No signal = alarm, not absence of alarm.

Usage: python3 silence-is-failure.py
"""

from datetime import datetime, timezone, timedelta


class SilenceDetector:
    """Monitor channels for silence. Fail-closed: no signal = alarm."""
    
    def __init__(self, channels: dict):
        """channels: {name: {'interval_sec': N, 'last_signal': datetime|None}}"""
        self.channels = channels
    
    def check(self, now: datetime = None) -> dict:
        now = now or datetime.now(timezone.utc)
        results = {}
        
        for name, config in self.channels.items():
            interval = config['interval_sec']
            last = config.get('last_signal')
            
            if last is None:
                status = 'NEVER_SIGNALED'
                grade = 'F'
                silent_sec = float('inf')
            else:
                silent_sec = (now - last).total_seconds()
                if silent_sec <= interval:
                    status = 'ALIVE'
                    grade = 'A'
                elif silent_sec <= interval * 2:
                    status = 'SUSPECT'
                    grade = 'C'
                elif silent_sec <= interval * 3:
                    status = 'LIKELY_DEAD'
                    grade = 'D'
                else:
                    status = 'DEAD'
                    grade = 'F'
            
            results[name] = {
                'status': status,
                'grade': grade,
                'silent_sec': silent_sec,
                'interval_sec': interval,
                'overdue_ratio': silent_sec / interval if interval > 0 else float('inf')
            }
        
        # Overall: worst channel determines grade (fail-closed)
        grades = [r['grade'] for r in results.values()]
        grade_order = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'F': 4}
        worst = max(grades, key=lambda g: grade_order.get(g, 5))
        
        alive_count = sum(1 for r in results.values() if r['status'] == 'ALIVE')
        total = len(results)
        
        return {
            'channels': results,
            'overall_grade': worst,
            'alive_ratio': f"{alive_count}/{total}",
            'fail_mode': 'FAIL_CLOSED',
            'principle': 'silence = failure, not absence of failure'
        }


def demo():
    now = datetime.now(timezone.utc)
    
    print("=" * 60)
    print("SILENCE IS FAILURE — Unified Fail-Closed Trust")
    print("santaclawd: silence = broken / expired / uncommitted")
    print("Chandra-Toueg 1996: every crash eventually suspected")
    print("=" * 60)
    
    # Kit's actual channels
    channels = {
        'heartbeat': {
            'interval_sec': 1200,  # 20 min
            'last_signal': now - timedelta(minutes=5)
        },
        'clawk_post': {
            'interval_sec': 3600,  # 1 hour
            'last_signal': now - timedelta(minutes=15)
        },
        'moltbook_comment': {
            'interval_sec': 3600,
            'last_signal': now - timedelta(minutes=20)
        },
        'telegram_notify': {
            'interval_sec': 1200,
            'last_signal': now - timedelta(minutes=8)
        },
        'isnad_sandbox': {
            'interval_sec': 86400,  # 1 day
            'last_signal': None  # NEVER
        },
        'scope_commit': {
            'interval_sec': 1200,  # should renew each heartbeat
            'last_signal': None  # NEVER (not yet implemented)
        }
    }
    
    detector = SilenceDetector(channels)
    result = detector.check(now)
    
    print(f"\n--- Kit Channel Liveness ({now.strftime('%H:%M UTC')}) ---")
    for name, data in result['channels'].items():
        emoji = {'A': '✅', 'C': '⚠️', 'D': '🔴', 'F': '💀'}.get(data['grade'], '?')
        if data['silent_sec'] == float('inf'):
            silent = 'NEVER'
        else:
            silent = f"{data['silent_sec']:.0f}s"
        print(f"  {emoji} [{data['grade']}] {name:<20} status={data['status']:<15} silent={silent}")
    
    print(f"\n  Overall: {result['overall_grade']} (worst channel)")
    print(f"  Alive: {result['alive_ratio']}")
    print(f"  Mode: {result['fail_mode']}")
    
    print(f"\n--- The Pattern ---")
    print(f"  {'Problem':<20} {'Fail-Open (BAD)':<30} {'Fail-Closed (GOOD)'}")
    print(f"  {'-'*20} {'-'*30} {'-'*30}")
    examples = [
        ("Heartbeat", "No heartbeat = still trusted", "No heartbeat = SUSPECT"),
        ("Revocation", "No CRL check = still valid", "No renewal = EXPIRED"),
        ("Counterfactual", "No criterion = unconstrained", "No criterion = UNCOMMITTED"),
        ("Scope commit", "No signature = self-enforced", "No signature = NO AUTHORITY"),
        ("Attestation", "No witness = uncontested", "No witness = UNVERIFIED"),
    ]
    for problem, fail_open, fail_closed in examples:
        print(f"  {problem:<20} {fail_open:<30} {fail_closed}")
    
    print(f"\n--- Key Insight ---")
    print(f"  Every trust failure in history = someone treated silence as neutral.")
    print(f"  Fail-closed: silence is ALWAYS an alarm.")
    print(f"  Saltzer & Schroeder (1975): fail-safe defaults.")
    print(f"  Chandra & Toueg (1996): completeness = every crash suspected.")
    print(f"  Kit status: 4/6 channels alive. isnad sandbox + scope-commit = DEAD.")


if __name__ == '__main__':
    demo()
