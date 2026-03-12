#!/usr/bin/env python3
"""
grace-epoch-sim.py — Grace epoch for async shard rotation.

Practical alternative to full async DPSS (Hu et al 2025).
During grace window, both old and new shares are valid.
After window closes, old shares expire.

Simpler than O(n²) protocol, bounded by TTL, deployable today.

Usage: python3 grace-epoch-sim.py
"""

import time
import secrets
import hashlib
from dataclasses import dataclass, field

PRIME = 2**127 - 1

def _mod_inv(a, p=PRIME):
    g, x, _ = _egcd(a % p, p)
    if g != 1: raise ValueError
    return x % p

def _egcd(a, b):
    if a == 0: return b, 0, 1
    g, x, y = _egcd(b % a, a)
    return g, y - (b // a) * x, x

def split(secret, k, n):
    coeffs = [secret] + [secrets.randbelow(PRIME) for _ in range(k-1)]
    return [(i, sum(c * pow(i, j, PRIME) for j, c in enumerate(coeffs)) % PRIME) for i in range(1, n+1)]

def reconstruct(shares, k):
    shares = shares[:k]
    s = 0
    for i, (xi, yi) in enumerate(shares):
        num = den = 1
        for j, (xj, _) in enumerate(shares):
            if i != j:
                num = (num * (-xj)) % PRIME
                den = (den * (xi - xj)) % PRIME
        s = (s + yi * num * _mod_inv(den)) % PRIME
    return s


@dataclass
class GraceEpoch:
    epoch: int
    k: int
    n: int
    shares: list
    created_at: float
    grace_window_s: float  # seconds both old+new valid
    expired: bool = False

    def is_in_grace(self, now: float) -> bool:
        return now - self.created_at < self.grace_window_s

    def expire(self):
        self.expired = True
        self.shares = []  # shred


def simulate_rotation(secret, scenarios):
    print("=" * 60)
    print("Grace Epoch Rotation Simulation")
    print("Practical async shard rotation without full DPSS")
    print("=" * 60)

    results = []

    for s in scenarios:
        print(f"\n{'─' * 50}")
        print(f"Scenario: {s['name']}")

        # Create old epoch
        old = GraceEpoch(
            epoch=0, k=s['old_k'], n=s['old_n'],
            shares=split(secret, s['old_k'], s['old_n']),
            created_at=time.time() - s.get('old_age_s', 0),
            grace_window_s=s['grace_s']
        )

        # Create new epoch
        new = GraceEpoch(
            epoch=1, k=s['new_k'], n=s['new_n'],
            shares=split(secret, s['new_k'], s['new_n']),
            created_at=time.time(),
            grace_window_s=s['grace_s']
        )

        now = time.time()

        # Check old epoch status
        old_in_grace = old.is_in_grace(now)
        old_valid = not old.expired and old_in_grace

        # Reconstruct from both
        old_ok = reconstruct(old.shares, old.k) == secret if old.shares else False
        new_ok = reconstruct(new.shares, new.k) == secret

        # Simulate compromise during grace
        compromised_old = s.get('compromised_old', 0)
        compromised_new = s.get('compromised_new', 0)

        old_honest = old.n - compromised_old
        new_honest = new.n - compromised_new

        attacker_old = compromised_old >= old.k
        attacker_new = compromised_new >= new.k
        attacker_cross = (compromised_old + compromised_new) >= min(old.k, new.k)

        # Grade
        if attacker_old and old_valid:
            grade = "F"
            status = "COMPROMISED — attacker controls old epoch during grace"
        elif attacker_new:
            grade = "F"
            status = "COMPROMISED — attacker controls new epoch"
        elif attacker_cross and old_valid:
            grade = "D"
            status = "RISK — cross-epoch shares might combine"
        elif not old_valid and new_ok:
            grade = "A"
            status = "CLEAN — old expired, new valid"
        elif old_valid and new_ok:
            grade = "B"
            status = "GRACE — both epochs valid, transition in progress"
        else:
            grade = "C"
            status = "DEGRADED"

        print(f"  Old epoch: {'in grace' if old_in_grace else 'expired'} ({old.k}-of-{old.n})")
        print(f"  New epoch: valid ({new.k}-of-{new.n})")
        print(f"  Old reconstructs: {old_ok}")
        print(f"  New reconstructs: {new_ok}")
        if compromised_old or compromised_new:
            print(f"  Compromised: {compromised_old} old, {compromised_new} new")
            print(f"  Attacker controls old: {attacker_old}")
            print(f"  Attacker controls new: {attacker_new}")
        print(f"  Grade: {grade} — {status}")

        # Expire old
        if not old_in_grace:
            old.expire()
            print(f"  → Old shares shredded")

        results.append({"scenario": s['name'], "grade": grade})

    print(f"\n{'=' * 60}")
    print("COMPARISON: Grace Epoch vs Full DPSS")
    print(f"  Grace:  O(1) messages, bounded by TTL, ships today")
    print(f"  DPSS:   O(n²) optimistic (Hu 2025), 1.9-8s for n=4-64")
    print(f"  Trade:  Grace has overlap window, DPSS has protocol overhead")
    print(f"  Winner: Grace for <10 parties, DPSS for >10")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    secret = secrets.randbelow(PRIME)
    simulate_rotation(secret, [
        {
            "name": "Clean rotation (3-of-5 → 3-of-5)",
            "old_k": 3, "old_n": 5, "new_k": 3, "new_n": 5,
            "grace_s": 300, "old_age_s": 0
        },
        {
            "name": "Old expired (grace window passed)",
            "old_k": 3, "old_n": 5, "new_k": 3, "new_n": 5,
            "grace_s": 300, "old_age_s": 600
        },
        {
            "name": "Threshold upgrade (3-of-5 → 4-of-7)",
            "old_k": 3, "old_n": 5, "new_k": 4, "new_n": 7,
            "grace_s": 300, "old_age_s": 0
        },
        {
            "name": "1 compromised during grace",
            "old_k": 3, "old_n": 5, "new_k": 3, "new_n": 5,
            "grace_s": 300, "old_age_s": 0,
            "compromised_old": 1, "compromised_new": 0
        },
        {
            "name": "Ronin during grace (3/5 old compromised)",
            "old_k": 3, "old_n": 5, "new_k": 3, "new_n": 5,
            "grace_s": 300, "old_age_s": 0,
            "compromised_old": 3, "compromised_new": 0
        },
    ])
