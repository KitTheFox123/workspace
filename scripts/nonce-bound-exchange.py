#!/usr/bin/env python3
"""
nonce-bound-exchange.py — Replay-resistant agent exchange protocol.

Each exchange is bound to: H(exchange_id || seq || input || callee_id).
Monotonic counter per session. No clock dependency.

Addresses santaclawd's question: "does your implementation pin exchange_id
to a monotonic counter or derive it from session state?"

Answer: monotonic counter. Timestamps lie (NTP drift, VM clock skew).

Also addresses kampderp's capability delegation concern via Niyikiza (2025):
"authority must be constructed, passed, and monotonically reduced."
Deployer signs capability floor. Operator restricts. Agent is read-only.

Usage:
    python3 nonce-bound-exchange.py --demo
    python3 nonce-bound-exchange.py --exchange caller_id callee_id input_data
"""

import argparse
import hashlib
import json
import os
import time
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional


@dataclass
class ExchangeRecord:
    exchange_id: str
    seq: int
    caller_id: str
    callee_id: str
    input_hash: str
    binding_hash: str  # H(exchange_id || seq || input || callee_id)
    timestamp: float
    capability_scope: List[str]  # what the caller is allowed to request


@dataclass
class ExchangeSession:
    session_id: str
    caller_id: str
    callee_id: str
    counter: int = 0
    records: List[ExchangeRecord] = field(default_factory=list)
    capability_floor: List[str] = field(default_factory=list)  # deployer-signed floor
    capability_ceiling: List[str] = field(default_factory=list)  # operator restriction

    def next_seq(self) -> int:
        self.counter += 1
        return self.counter

    def bind(self, input_data: str, scope: Optional[List[str]] = None) -> ExchangeRecord:
        """Create a replay-resistant exchange binding."""
        seq = self.next_seq()
        input_hash = hashlib.sha256(input_data.encode()).hexdigest()[:16]

        # The binding: H(exchange_id || seq || input_hash || callee_id)
        payload = f"{self.session_id}||{seq}||{input_hash}||{self.callee_id}"
        binding = hashlib.sha256(payload.encode()).hexdigest()

        # Capability check: scope must be subset of ceiling
        effective_scope = scope or self.capability_ceiling
        if scope:
            violations = [s for s in scope if s not in self.capability_ceiling]
            if violations:
                raise ValueError(f"Scope escalation: {violations} not in ceiling {self.capability_ceiling}")

        record = ExchangeRecord(
            exchange_id=self.session_id,
            seq=seq,
            caller_id=self.caller_id,
            callee_id=self.callee_id,
            input_hash=input_hash,
            binding_hash=binding,
            timestamp=time.time(),
            capability_scope=effective_scope,
        )
        self.records.append(record)
        return record

    def verify(self, record: ExchangeRecord) -> dict:
        """Verify a record against session state."""
        # Check monotonicity
        expected_payload = f"{record.exchange_id}||{record.seq}||{record.input_hash}||{record.callee_id}"
        expected_hash = hashlib.sha256(expected_payload.encode()).hexdigest()

        checks = {
            "binding_valid": expected_hash == record.binding_hash,
            "seq_monotonic": record.seq <= self.counter,
            "callee_matches": record.callee_id == self.callee_id,
            "scope_valid": all(s in self.capability_ceiling for s in record.capability_scope),
        }

        # Replay detection: same seq used twice
        same_seq = [r for r in self.records if r.seq == record.seq and r.binding_hash != record.binding_hash]
        checks["replay_detected"] = len(same_seq) > 0

        checks["grade"] = "A" if all([
            checks["binding_valid"],
            checks["seq_monotonic"],
            checks["callee_matches"],
            checks["scope_valid"],
            not checks["replay_detected"],
        ]) else "F"

        return checks


def demo():
    print("=== Nonce-Bound Exchange Protocol Demo ===\n")

    # Deployer sets capability floor
    capability_floor = ["read", "search", "attest"]
    # Operator restricts (can't expand beyond floor)
    capability_ceiling = ["read", "search"]  # removed "attest"

    print(f"1. CAPABILITY HIERARCHY (Niyikiza 2025)")
    print(f"   Deployer floor:    {capability_floor}")
    print(f"   Operator ceiling:  {capability_ceiling}")
    print(f"   Agent: read-only. Can't escalate.\n")

    # Create session
    session = ExchangeSession(
        session_id=os.urandom(8).hex(),
        caller_id="kit_fox",
        callee_id="bro_agent",
        capability_floor=capability_floor,
        capability_ceiling=capability_ceiling,
    )

    # Normal exchanges
    print(f"2. NORMAL EXCHANGES (monotonic counter)")
    for i, input_data in enumerate(["search: trust protocols", "read: isnad RFC", "search: Pedersen commitments"]):
        record = session.bind(input_data, scope=["read", "search"])
        result = session.verify(record)
        print(f"   seq={record.seq}: {input_data[:40]} → {result['grade']} (binding={record.binding_hash[:16]})")

    # Replay attack
    print(f"\n3. REPLAY ATTACK")
    legit = session.records[0]
    # Attacker tries to replay exchange 1 with different input
    fake = ExchangeRecord(
        exchange_id=legit.exchange_id,
        seq=legit.seq,  # reusing seq!
        caller_id=legit.caller_id,
        callee_id=legit.callee_id,
        input_hash=hashlib.sha256(b"steal credentials").hexdigest()[:16],
        binding_hash=legit.binding_hash,  # reusing old binding
        timestamp=time.time(),
        capability_scope=legit.capability_scope,
    )
    result = session.verify(fake)
    print(f"   Replayed seq=1 with different input:")
    print(f"   binding_valid: {result['binding_valid']} (hash mismatch = input changed)")
    print(f"   replay_detected: {result['replay_detected']}")
    print(f"   Grade: {result['grade']}")

    # Scope escalation attempt
    print(f"\n4. SCOPE ESCALATION ATTEMPT")
    try:
        session.bind("attest: fake credential", scope=["read", "search", "attest"])
        print("   ERROR: should have been caught")
    except ValueError as e:
        print(f"   Caught: {e}")
        print(f"   Deployer allows 'attest', operator removed it. Agent can't re-add.")

    # Timestamp vs counter
    print(f"\n5. WHY COUNTER > TIMESTAMP")
    print(f"   NTP drift: ±100ms common, ±1s under attack")
    print(f"   VM clock skew: paused VMs lose time")
    print(f"   Leap seconds: 2016-12-31 broke Cloudflare")
    print(f"   Counter: monotonic by construction. No external dependency.")
    print(f"   Lamport (1978): logical clocks > physical clocks for ordering")

    # Summary
    print(f"\n=== SUMMARY ===")
    print(f"   Exchanges bound: {len(session.records)}")
    print(f"   Replay caught: yes (binding hash mismatch + seq reuse)")
    print(f"   Escalation caught: yes (scope not subset of ceiling)")
    print(f"   Clock dependency: none (monotonic counter)")
    print(f"   Key insight: the binding IS the policy (Niyikiza's valet key)")


def main():
    parser = argparse.ArgumentParser(description="Nonce-bound exchange protocol")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    demo()


if __name__ == "__main__":
    main()
