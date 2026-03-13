#!/usr/bin/env python3
"""
async-reshare-sim.py — Asynchronous proactive secret sharing simulation.

Based on APSS (Zhou et al 2005, ACM TISSEC) — reshare without synchrony.
D-FROST requires all t+1 old members online. APSS doesn't.

Key insight: async reshare completes when enough parties respond,
tolerates DoS + network partition during rotation.

Grace window = max time extended TTL is valid during reshare.

Usage: python3 async-reshare-sim.py
"""

import secrets
import time
from dataclasses import dataclass, field

PRIME = 2**127 - 1


def _mod_inv(a, p=PRIME):
    if a < 0: a = a % p
    g, x, _ = _egcd(a, p)
    if g != 1: raise ValueError("No inverse")
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
class Party:
    id: int
    online: bool = True
    compromised: bool = False
    response_delay_ms: int = 0  # 0 = immediate


@dataclass
class AsyncReshare:
    old_k: int
    old_n: int
    new_k: int
    new_n: int
    parties: list[Party] = field(default_factory=list)
    grace_window_ms: int = 60000  # max extended TTL
    
    def attempt_reshare(self, secret: int) -> dict:
        """Attempt async reshare. Succeeds when enough parties respond."""
        old_shares = split(secret, self.old_k, self.old_n)
        
        # Which old parties can participate?
        available = []
        unavailable = []
        for i, party in enumerate(self.parties[:self.old_n]):
            if party.online and not party.compromised:
                available.append((party, old_shares[i]))
            else:
                unavailable.append(party)
        
        # Need old_k honest online parties for reshare
        if len(available) < self.old_k:
            # Grace window: wait for more parties
            grace_recovered = [p for p in unavailable 
                             if not p.compromised and p.response_delay_ms <= self.grace_window_ms]
            
            if len(available) + len(grace_recovered) >= self.old_k:
                return {
                    "success": True,
                    "mode": "GRACE_WINDOW",
                    "immediate": len(available),
                    "recovered": len(grace_recovered),
                    "total": len(available) + len(grace_recovered),
                    "threshold": self.old_k,
                    "grace_used_ms": max(p.response_delay_ms for p in grace_recovered) if grace_recovered else 0,
                    "new_shares": split(secret, self.new_k, self.new_n),
                    "grade": "B"
                }
            else:
                return {
                    "success": False,
                    "mode": "STALLED",
                    "available": len(available),
                    "recoverable": len(grace_recovered),
                    "threshold": self.old_k,
                    "reason": f"only {len(available)+len(grace_recovered)}/{self.old_k} reachable",
                    "grade": "F"
                }
        
        # Immediate reshare
        new_shares = split(secret, self.new_k, self.new_n)
        return {
            "success": True,
            "mode": "IMMEDIATE",
            "participants": len(available),
            "threshold": self.old_k,
            "new_shares_created": len(new_shares),
            "grade": "A"
        }


def demo():
    print("=" * 60)
    print("Async Proactive Reshare Simulation")
    print("APSS (Zhou et al 2005) — no synchrony assumption")
    print("=" * 60)

    secret = secrets.randbelow(PRIME)

    scenarios = [
        {
            "name": "All online — immediate reshare",
            "old_k": 3, "old_n": 5, "new_k": 3, "new_n": 5,
            "parties": [Party(i) for i in range(5)],
            "grace_ms": 60000
        },
        {
            "name": "2 offline — still above threshold",
            "old_k": 3, "old_n": 5, "new_k": 3, "new_n": 5,
            "parties": [Party(0), Party(1), Party(2), 
                       Party(3, online=False), Party(4, online=False)],
            "grace_ms": 60000
        },
        {
            "name": "3 offline — grace window recovery",
            "old_k": 3, "old_n": 5, "new_k": 3, "new_n": 5,
            "parties": [Party(0), Party(1),
                       Party(2, online=False, response_delay_ms=30000),
                       Party(3, online=False, response_delay_ms=45000),
                       Party(4, online=False, response_delay_ms=90000)],
            "grace_ms": 60000
        },
        {
            "name": "Partition + compromise — stalled",
            "old_k": 3, "old_n": 5, "new_k": 3, "new_n": 5,
            "parties": [Party(0), Party(1),
                       Party(2, compromised=True),
                       Party(3, online=False, response_delay_ms=120000),
                       Party(4, online=False, response_delay_ms=120000)],
            "grace_ms": 60000
        },
        {
            "name": "D-FROST would fail, APSS succeeds",
            "old_k": 3, "old_n": 5, "new_k": 4, "new_n": 7,
            "parties": [Party(0), Party(1), Party(2),
                       Party(3, online=False, response_delay_ms=5000),
                       Party(4, online=False)],
            "grace_ms": 60000
        },
    ]

    for s in scenarios:
        print(f"\n{'─' * 50}")
        print(f"Scenario: {s['name']}")
        print(f"Threshold: {s['old_k']}-of-{s['old_n']} → {s['new_k']}-of-{s['new_n']}")
        
        reshare = AsyncReshare(
            old_k=s["old_k"], old_n=s["old_n"],
            new_k=s["new_k"], new_n=s["new_n"],
            parties=s["parties"],
            grace_window_ms=s["grace_ms"]
        )
        result = reshare.attempt_reshare(secret)
        
        print(f"Mode: {result['mode']}")
        print(f"Grade: {result['grade']}")
        if result["success"]:
            if result["mode"] == "GRACE_WINDOW":
                print(f"Grace used: {result['grace_used_ms']}ms / {s['grace_ms']}ms")
                print(f"Recovered: {result['recovered']} parties during grace")
        else:
            print(f"Reason: {result['reason']}")

    # Grace window analysis
    print(f"\n{'=' * 60}")
    print("GRACE WINDOW TRADEOFF:")
    print("  Too short → reshare never completes during partition")
    print("  Too long  → stale shares circulate, exposure window grows")
    print("  Rule of thumb: 2× expected partition duration")
    print("  Agent heartbeat = 20min → grace = 40min max")
    print(f"\n  D-FROST: requires ALL t+1 online (synchronous)")
    print(f"  APSS:    completes when ENOUGH respond (async)")
    print(f"  For agents: async is always the right model.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
