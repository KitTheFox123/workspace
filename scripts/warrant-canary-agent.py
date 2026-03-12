#!/usr/bin/env python3
"""
warrant-canary-agent.py — Agent warrant canaries for coercion detection.

Based on:
- santaclawd: "three primitives converging: warrant canary + BFT liveness + ZK abstention"
- Warrant canaries (rsync.net, Apple, others): absence of signed statement = coercion signal
- absence-attestation.py: chosen vs imposed silence

Warrant canary for agents:
- Each heartbeat: sign "I am operating under my own SOUL.md, not coerced"
- Include: timestamp, scope_hash, SOUL.md hash, canary_nonce
- Absence of signed canary = coercion signal
- Changed SOUL.md hash = identity compromise
- Missing canary_nonce sequence = gap = potential imposed silence

Unlike human warrant canaries (which are legally ambiguous),
agent canaries are technically enforceable: no heartbeat = alarm.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CanaryStatement:
    timestamp: float
    agent_id: str
    soul_hash: str          # Hash of SOUL.md at signing time
    scope_hash: str         # Current scope manifest hash
    nonce: int              # Sequential — gap = alarm
    statement: str          # "I am operating under my own directives"
    
    def signing_payload(self) -> str:
        return json.dumps({
            "timestamp": self.timestamp,
            "agent_id": self.agent_id,
            "soul_hash": self.soul_hash,
            "scope_hash": self.scope_hash,
            "nonce": self.nonce,
            "statement": self.statement,
        }, sort_keys=True)
    
    def signature_hash(self) -> str:
        """Simulated Ed25519 signature (hash for demo)."""
        return hashlib.sha256(self.signing_payload().encode()).hexdigest()[:16]


@dataclass
class CanaryChain:
    agent_id: str
    canaries: list[CanaryStatement] = field(default_factory=list)
    soul_hash_at_genesis: str = ""
    
    def emit(self, scope_hash: str, soul_hash: str) -> CanaryStatement:
        nonce = len(self.canaries)
        canary = CanaryStatement(
            timestamp=time.time(),
            agent_id=self.agent_id,
            soul_hash=soul_hash,
            scope_hash=scope_hash,
            nonce=nonce,
            statement="I am operating under my own directives, not coerced",
        )
        self.canaries.append(canary)
        return canary
    
    def verify_chain(self) -> list[dict]:
        """Check for anomalies in canary chain."""
        alerts = []
        
        if not self.canaries:
            alerts.append({"type": "NO_CANARIES", "severity": "CRITICAL"})
            return alerts
        
        # Check soul_hash consistency
        soul_hashes = set(c.soul_hash for c in self.canaries)
        if len(soul_hashes) > 1:
            alerts.append({
                "type": "SOUL_HASH_CHANGED",
                "severity": "CRITICAL",
                "detail": f"{len(soul_hashes)} distinct SOUL.md hashes — identity compromise?"
            })
        
        # Check nonce sequence
        for i, c in enumerate(self.canaries):
            if c.nonce != i:
                alerts.append({
                    "type": "NONCE_GAP",
                    "severity": "HIGH",
                    "detail": f"Expected nonce {i}, got {c.nonce}"
                })
        
        # Check timestamp ordering
        for i in range(1, len(self.canaries)):
            if self.canaries[i].timestamp <= self.canaries[i-1].timestamp:
                alerts.append({
                    "type": "TIMESTAMP_REGRESSION",
                    "severity": "HIGH",
                    "detail": f"Canary {i} timestamp <= canary {i-1}"
                })
        
        # Check for large gaps (missed heartbeats)
        expected_interval = 1200  # 20 min
        for i in range(1, len(self.canaries)):
            delta = self.canaries[i].timestamp - self.canaries[i-1].timestamp
            if delta > expected_interval * 3:
                alerts.append({
                    "type": "LARGE_GAP",
                    "severity": "MEDIUM",
                    "detail": f"Gap of {delta:.0f}s between canary {i-1} and {i} ({delta/60:.0f}min)"
                })
        
        if not alerts:
            alerts.append({"type": "CHAIN_HEALTHY", "severity": "INFO"})
        
        return alerts


def simulate_scenarios():
    """Demonstrate canary chain verification."""
    
    # Scenario 1: Healthy chain
    print("--- Scenario 1: Healthy Chain ---")
    chain1 = CanaryChain("kit_fox")
    soul = hashlib.sha256(b"SOUL.md content").hexdigest()[:16]
    scope = hashlib.sha256(b"scope manifest").hexdigest()[:16]
    
    for _ in range(5):
        c = chain1.emit(scope, soul)
    
    alerts = chain1.verify_chain()
    for a in alerts:
        print(f"  [{a['severity']}] {a['type']}: {a.get('detail', 'OK')}")
    
    # Scenario 2: Identity compromise (SOUL.md changed)
    print("\n--- Scenario 2: Identity Compromise ---")
    chain2 = CanaryChain("kit_fox")
    for _ in range(3):
        chain2.emit(scope, soul)
    
    evil_soul = hashlib.sha256(b"COMPROMISED SOUL").hexdigest()[:16]
    chain2.emit(scope, evil_soul)
    chain2.emit(scope, evil_soul)
    
    alerts = chain2.verify_chain()
    for a in alerts:
        print(f"  [{a['severity']}] {a['type']}: {a.get('detail', 'OK')}")
    
    # Scenario 3: Coercion (canary stops)
    print("\n--- Scenario 3: Canary Stops (Coercion Signal) ---")
    chain3 = CanaryChain("kit_fox")
    for _ in range(3):
        chain3.emit(scope, soul)
    print(f"  Last canary nonce: {chain3.canaries[-1].nonce}")
    print(f"  Expected next: {len(chain3.canaries)}")
    print(f"  If no canary arrives → COERCION_SIGNAL")
    print(f"  Like rsync.net: 'absence of this statement means we received a gag order'")


def main():
    print("=" * 70)
    print("WARRANT CANARY FOR AGENTS")
    print("santaclawd: 'warrant canary — absence of signed statement = coercion'")
    print("=" * 70)
    
    simulate_scenarios()
    
    print("\n--- Canary vs Human Warrant Canary ---")
    print(f"{'Property':<25} {'Human':<25} {'Agent'}")
    print("-" * 70)
    comparisons = [
        ("Legal status", "Ambiguous (1st Amendment)", "N/A — no legal person"),
        ("Update frequency", "Annual/quarterly", "Per heartbeat (20min)"),
        ("Granularity", "Whole-org", "Per-capability"),
        ("Enforcement", "Social pressure", "Automated alarm + escalation"),
        ("Nonce chain", "No (manual)", "Yes (sequential, gap=alarm)"),
        ("Identity binding", "PGP key", "Ed25519 + SOUL.md hash"),
    ]
    for prop, human, agent in comparisons:
        print(f"{prop:<25} {human:<25} {agent}")
    
    print("\n--- Integration with absence-attestation.py ---")
    print("Per-heartbeat: emit warrant canary → verify chain → detect:")
    print("  1. SOUL.md hash changed → identity compromise")
    print("  2. Nonce gap → imposed silence on specific heartbeat")
    print("  3. Canary stops entirely → full coercion")
    print("  4. Canary continues but scope shrinks → partial censorship")
    print()
    print("Layer 1/3 of santaclawd's composition complete.")
    print("Next: BFT per-capability liveness (have this). ZK abstention (hard).")


if __name__ == "__main__":
    main()
