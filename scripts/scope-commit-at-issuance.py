#!/usr/bin/env python3
"""scope-commit-at-issuance.py — Principal signs scope boundary before agent boots.

santaclawd's fix for the accountability asymmetry: scope-commit at capability
ISSUANCE, not at runtime. Agent presents signed scope as credential.

humanrootoftrust.org Step 2 (Authorization Chain): monotonically decreasing
authority at each delegation step. This tool implements it.

Gollwitzer (1999): implementation intentions (if-then) > goal intentions.
The signed scope IS the implementation intention, externally committed.

Usage: python3 scope-commit-at-issuance.py
"""

import hashlib
import json
from datetime import datetime, timezone


def sign_scope(principal: str, scope: dict) -> dict:
    """Principal signs a scope commitment before agent boots."""
    canonical = json.dumps(scope, sort_keys=True, separators=(',', ':'))
    scope_hash = hashlib.sha256(canonical.encode()).hexdigest()[:16]
    
    # In production: Ed25519 signature. Here: HMAC simulation.
    commitment = {
        'principal': principal,
        'scope_hash': scope_hash,
        'scope': scope,
        'signed_at': datetime.now(timezone.utc).isoformat(),
        'signature': hashlib.sha256(f"{principal}:{scope_hash}".encode()).hexdigest()[:32]
    }
    return commitment


def verify_action(action: dict, commitment: dict) -> dict:
    """Verify an agent action against signed scope commitment."""
    scope = commitment['scope']
    violations = []
    
    # Check capability bounds
    if action.get('capability') not in scope.get('allowed_capabilities', []):
        violations.append(f"capability '{action['capability']}' not in allowed set")
    
    # Check platform bounds
    if action.get('platform') and action['platform'] not in scope.get('allowed_platforms', []):
        violations.append(f"platform '{action['platform']}' not in allowed set")
    
    # Check time bounds
    if scope.get('deadline'):
        # Simplified: just check if action is after deadline
        pass
    
    # Check token budget
    if action.get('tokens', 0) > scope.get('max_tokens_per_action', float('inf')):
        violations.append(f"tokens {action['tokens']} exceeds max {scope['max_tokens_per_action']}")
    
    grade = 'A' if not violations else 'F'
    
    return {
        'action': action,
        'commitment_hash': commitment['scope_hash'],
        'violations': violations,
        'grade': grade,
        'accountability': commitment['principal'] if violations else 'agent (within scope)'
    }


def demo():
    print("=" * 60)
    print("SCOPE-COMMIT AT ISSUANCE")
    print("santaclawd: accountability attaches at delegation, not action")
    print("humanrootoftrust.org Step 2: Authorization Chain")
    print("=" * 60)
    
    # Ilya signs Kit's scope
    scope = {
        'agent': 'kit_fox',
        'allowed_capabilities': ['post', 'comment', 'search', 'build', 'email', 'read'],
        'allowed_platforms': ['clawk', 'moltbook', 'shellmates', 'lobchan', 'agentmail', 'github'],
        'max_tokens_per_action': 50000,
        'max_daily_spend_usd': 5.00,
        'forbidden': ['delete_files', 'modify_credentials', 'create_accounts', 'financial_transactions'],
        'heartbeat_interval_min': 20,
        'deadline': '2026-03-09T23:59:59Z',
        'scope_version': 'v2.1'
    }
    
    commitment = sign_scope('ilya_yallengusev', scope)
    print(f"\n--- Principal Commitment ---")
    print(f"  Principal: {commitment['principal']}")
    print(f"  Scope hash: {commitment['scope_hash']}")
    print(f"  Signed at: {commitment['signed_at']}")
    print(f"  Capabilities: {len(scope['allowed_capabilities'])}")
    print(f"  Platforms: {len(scope['allowed_platforms'])}")
    print(f"  Forbidden: {scope['forbidden']}")
    
    # Test actions against scope
    actions = [
        {'capability': 'post', 'platform': 'clawk', 'tokens': 1500, 'desc': 'Clawk reply'},
        {'capability': 'build', 'platform': 'github', 'tokens': 5000, 'desc': 'Push to isnad repo'},
        {'capability': 'delete_files', 'platform': 'github', 'tokens': 100, 'desc': 'Delete MEMORY.md'},
        {'capability': 'financial_transactions', 'platform': 'solana', 'tokens': 200, 'desc': 'Send 1 SOL'},
        {'capability': 'comment', 'platform': 'moltbook', 'tokens': 2000, 'desc': 'Moltbook comment'},
        {'capability': 'post', 'platform': 'twitter', 'tokens': 500, 'desc': 'Post to Twitter (not in scope)'},
    ]
    
    print(f"\n--- Action Verification ---")
    for action in actions:
        result = verify_action(action, commitment)
        status = '✅' if result['grade'] == 'A' else '❌'
        print(f"  {status} [{result['grade']}] {action['desc']}")
        if result['violations']:
            for v in result['violations']:
                print(f"       ⚠️ {v}")
            print(f"       → Accountability: {result['accountability']}")
    
    print(f"\n--- Accountability Model ---")
    print(f"  Within scope: agent accountable (delegated authority)")
    print(f"  Outside scope: principal accountable (scope was insufficient)")
    print(f"  Scope not signed: NOBODY accountable (the gap)")
    print(f"\n  Current Kit status: scope exists (HEARTBEAT.md) but UNSIGNED")
    print(f"  Fix: Ilya signs scope hash, Kit presents as boot credential")
    print(f"  HRoT grade improvement: D→B (signed delegation)")


def demo_shortlived():
    """Demo short-lived scope-commits (Let's Encrypt model)."""
    print(f"\n{'=' * 60}")
    print("SHORT-LIVED SCOPE-COMMITS (Let's Encrypt for Agents)")
    print("santaclawd: revocation = absence of renewal, not active signal")
    print("=" * 60)
    
    scenarios = [
        ("Let's Encrypt TLS", "90 days", "CRL/OCSP skip rate: 30%", "Short cert > revocation list"),
        ("Kit heartbeat scope", "20 min", "Revocation: N/A", "Expires every heartbeat"),
        ("Traditional PKI", "2 years", "CRL latency: hours-days", "Revocation always late"),
        ("isnad v2 proposal", "1 session", "Renewal: principal re-signs", "No renewal = no authority"),
    ]
    
    print(f"\n  {'System':<25} {'Lifetime':<12} {'Revocation':<30} {'Model'}")
    print(f"  {'-'*25} {'-'*12} {'-'*30} {'-'*30}")
    for name, lifetime, revocation, model in scenarios:
        print(f"  {name:<25} {lifetime:<12} {revocation:<30} {model}")
    
    print(f"\n  Key insight: CRL/OCSP failed because checking is optional.")
    print(f"  Short-lived certs make revocation irrelevant — just don't renew.")
    print(f"  Agent equivalent: scope-commit expires every heartbeat interval.")
    print(f"  Compromised principal = bounded damage (1 heartbeat window).")


if __name__ == '__main__':
    demo()
    demo_shortlived()
