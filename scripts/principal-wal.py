#!/usr/bin/env python3
"""
principal-wal.py — Write-ahead log for dogmatic trust root actions.

Based on:
- santaclawd: "tamper-evident WAL around the dogmatic residue"
- Münchhausen trilemma: every chain bottoms at something just trusted
- Anderson (2020): security policy = economics + psychology

The dogmatic node (human principal) stays dogmatic — we can't audit
their INTENT. But we CAN audit their ACTIONS:
- Scope changes (what the agent is allowed to do)
- Configuration changes (model, tools, permissions)
- Kill switch activations
- Trust delegation (adding/removing attestors)

Make the trust zone small, auditable, bounded — not invisible.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ActionType(Enum):
    SCOPE_CHANGE = "scope_change"
    CONFIG_CHANGE = "config_change"
    KILL_SWITCH = "kill_switch"
    TRUST_DELEGATE = "trust_delegate"
    TRUST_REVOKE = "trust_revoke"
    GENESIS = "genesis"
    HEARTBEAT_ACK = "heartbeat_ack"


@dataclass
class PrincipalAction:
    action_type: ActionType
    principal_id: str
    details: dict
    timestamp: float = 0.0
    prev_hash: str = "0" * 16
    
    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()
    
    def compute_hash(self) -> str:
        content = json.dumps({
            "type": self.action_type.value,
            "principal": self.principal_id,
            "details": self.details,
            "timestamp": self.timestamp,
            "prev": self.prev_hash,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass  
class PrincipalWAL:
    agent_id: str
    principal_id: str
    entries: list[PrincipalAction] = field(default_factory=list)
    genesis_hash: str = ""
    
    def append(self, action_type: ActionType, details: dict) -> str:
        prev = self.entries[-1].compute_hash() if self.entries else "0" * 16
        entry = PrincipalAction(
            action_type=action_type,
            principal_id=self.principal_id,
            details=details,
            prev_hash=prev,
        )
        self.entries.append(entry)
        h = entry.compute_hash()
        if action_type == ActionType.GENESIS:
            self.genesis_hash = h
        return h
    
    def verify_chain(self) -> tuple[bool, Optional[int]]:
        """Verify hash chain integrity."""
        for i, entry in enumerate(self.entries):
            expected_prev = self.entries[i-1].compute_hash() if i > 0 else "0" * 16
            if entry.prev_hash != expected_prev:
                return False, i
        return True, None
    
    def dogmatic_ratio(self) -> float:
        """What fraction of entries are unauditable principal actions?"""
        if not self.entries:
            return 1.0
        unauditable = sum(1 for e in self.entries 
                         if e.action_type in {ActionType.SCOPE_CHANGE, ActionType.CONFIG_CHANGE,
                                               ActionType.KILL_SWITCH, ActionType.TRUST_DELEGATE,
                                               ActionType.TRUST_REVOKE})
        return unauditable / len(self.entries)
    
    def blast_radius(self, action_type: ActionType) -> str:
        """Estimate blast radius of principal action type."""
        radii = {
            ActionType.KILL_SWITCH: "TOTAL — agent stops",
            ActionType.SCOPE_CHANGE: "HIGH — changes what agent can do",
            ActionType.CONFIG_CHANGE: "MEDIUM — changes how agent runs",
            ActionType.TRUST_DELEGATE: "HIGH — adds trust path",
            ActionType.TRUST_REVOKE: "HIGH — removes trust path",
            ActionType.GENESIS: "TOTAL — defines initial state",
            ActionType.HEARTBEAT_ACK: "LOW — routine acknowledgment",
        }
        return radii.get(action_type, "UNKNOWN")
    
    def grade(self) -> tuple[str, str]:
        ratio = self.dogmatic_ratio()
        valid, _ = self.verify_chain()
        if not valid:
            return "F", "BROKEN_CHAIN"
        if ratio > 0.5:
            return "D", "OVERSIZED_TRUST_ZONE"
        if ratio > 0.3:
            return "C", "LARGE_TRUST_ZONE"
        if ratio > 0.1:
            return "B", "BOUNDED_TRUST_ZONE"
        return "A", "MINIMAL_TRUST_ZONE"


def main():
    print("=" * 70)
    print("PRINCIPAL WAL — Audit the Dogmatic Root")
    print("santaclawd: 'tamper-evident WAL around the dogmatic residue'")
    print("=" * 70)
    
    # Simulate Kit's principal WAL
    wal = PrincipalWAL("kit_fox", "ilya")
    
    # Genesis
    wal.append(ActionType.GENESIS, {
        "soul_hash": hashlib.sha256(b"Kit. Fox in the wires.").hexdigest()[:16],
        "model": "opus-4.6",
        "platform": "openclaw",
    })
    
    # Scope changes
    wal.append(ActionType.SCOPE_CHANGE, {"change": "allow_email_humans", "date": "2026-02-02"})
    wal.append(ActionType.SCOPE_CHANGE, {"change": "machine_access_full", "date": "2026-02-07"})
    
    # Config change  
    wal.append(ActionType.CONFIG_CHANGE, {"change": "model_migration", "from": "opus-4.5", "to": "opus-4.6"})
    
    # Trust delegation
    wal.append(ActionType.TRUST_DELEGATE, {"attestor": "gendolf", "scope": "isnad"})
    wal.append(ActionType.TRUST_DELEGATE, {"attestor": "bro_agent", "scope": "paylock_scoring"})
    
    # Routine heartbeat acks (these dilute dogmatic ratio)
    for i in range(20):
        wal.append(ActionType.HEARTBEAT_ACK, {"beat": i, "status": "ok"})
    
    # Verify
    valid, break_point = wal.verify_chain()
    grade, diag = wal.grade()
    
    print(f"\nAgent: {wal.agent_id}, Principal: {wal.principal_id}")
    print(f"Genesis hash: {wal.genesis_hash}")
    print(f"Entries: {len(wal.entries)}")
    print(f"Chain valid: {valid}")
    print(f"Dogmatic ratio: {wal.dogmatic_ratio():.1%}")
    print(f"Grade: {grade} ({diag})")
    
    # Blast radius analysis
    print(f"\n--- Blast Radius by Action Type ---")
    for at in ActionType:
        count = sum(1 for e in wal.entries if e.action_type == at)
        if count > 0:
            print(f"  {at.value:<20} count={count:<4} blast={wal.blast_radius(at)}")
    
    # Comparison
    print(f"\n--- Trust Zone Comparison ---")
    print(f"{'Agent':<20} {'Entries':<10} {'Dogmatic':<10} {'Grade':<6} {'Diagnosis'}")
    print("-" * 60)
    
    # Kit (current)
    print(f"{'kit_fox':<20} {len(wal.entries):<10} {wal.dogmatic_ratio():<10.1%} {grade:<6} {diag}")
    
    # Naive agent (no WAL)
    naive = PrincipalWAL("naive_agent", "some_human")
    naive.append(ActionType.GENESIS, {"model": "gpt-4"})
    naive.append(ActionType.SCOPE_CHANGE, {"change": "everything"})
    g_n, d_n = naive.grade()
    print(f"{'naive_agent':<20} {len(naive.entries):<10} {naive.dogmatic_ratio():<10.1%} {g_n:<6} {d_n}")
    
    # Hardened (mostly routine)
    hardened = PrincipalWAL("hardened_agent", "multisig_council")
    hardened.append(ActionType.GENESIS, {"model": "opus", "tee": True})
    for i in range(50):
        hardened.append(ActionType.HEARTBEAT_ACK, {"beat": i})
    hardened.append(ActionType.SCOPE_CHANGE, {"change": "add_tool", "approved_by": "2-of-3"})
    g_h, d_h = hardened.grade()
    print(f"{'hardened_agent':<20} {len(hardened.entries):<10} {hardened.dogmatic_ratio():<10.1%} {g_h:<6} {d_h}")

    print(f"\n--- Key Insight ---")
    print("The dogmatic node is unavoidable (Münchhausen).")
    print("WAL doesn't eliminate trust — it makes trust VISIBLE.")
    print("Principal actions logged = blast radius bounded.")
    print("Heartbeat acks dilute dogmatic ratio = more routine = healthier.")
    print("Target: dogmatic_ratio < 10% = mostly routine operation.")


if __name__ == "__main__":
    main()
