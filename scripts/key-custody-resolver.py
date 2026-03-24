#!/usr/bin/env python3
"""
key-custody-resolver.py — Two-tier key custody model for ATF genesis receipts.

Per santaclawd: "who holds the signing key = who vouches for the agent."
DKIM model: domain operator holds key, delegates per-selector.

Two tiers:
  OPERATOR — Operator holds signing key, signs genesis receipts.
             DKIM equivalent: domain key. HSM-backed.
  AGENT    — Agent holds delegated key for receipt signing.
             DKIM equivalent: selector key. Software-backed.

Key loss = reanchor, not identity death. Operator re-signs genesis
with new agent key. Old receipts remain valid (signed by operator).

Custody transitions:
  OPERATOR_GENESIS → AGENT_DELEGATED → AGENT_ROTATED → REANCHORED
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class CustodyModel(Enum):
    OPERATOR_HELD = "OPERATOR_HELD"    # Provider controls key (centralized, reliable)
    AGENT_HELD = "AGENT_HELD"          # Agent controls key (autonomous, vulnerable)
    SPLIT_CUSTODY = "SPLIT_CUSTODY"    # Operator signs genesis, agent signs receipts
    THRESHOLD = "THRESHOLD"            # K-of-N multisig (future)


class KeyState(Enum):
    ACTIVE = "ACTIVE"
    ROTATED = "ROTATED"           # Superseded by new key
    COMPROMISED = "COMPROMISED"    # Marked unsafe
    REANCHORED = "REANCHORED"      # New key after loss, old identity preserved
    REVOKED = "REVOKED"            # Permanently invalid


class CustodyEvent(Enum):
    GENESIS = "GENESIS"                # Initial key binding
    DELEGATION = "DELEGATION"          # Operator delegates to agent
    ROTATION = "ROTATION"              # Scheduled key change
    COMPROMISE_REPORT = "COMPROMISE"   # Key marked compromised
    REANCHOR = "REANCHOR"              # Recovery after loss
    REVOCATION = "REVOCATION"          # Permanent invalidation


@dataclass
class KeyRecord:
    key_id: str
    key_hash: str              # Hash of public key (not the key itself)
    custodian: str             # Who holds the private key
    custody_model: str
    state: str
    created_at: float
    expires_at: Optional[float] = None
    delegated_from: Optional[str] = None  # Parent key that delegated
    rotation_of: Optional[str] = None     # Key this replaces
    metadata: dict = field(default_factory=dict)


@dataclass
class CustodyChain:
    """Full custody history for an agent's signing keys."""
    agent_id: str
    operator_id: str
    keys: list = field(default_factory=list)
    events: list = field(default_factory=list)
    current_key_id: Optional[str] = None


def make_key_hash(key_material: str) -> str:
    """Simulate public key hash."""
    return hashlib.sha256(key_material.encode()).hexdigest()[:16]


def create_genesis(chain: CustodyChain, operator_key: str, model: CustodyModel) -> KeyRecord:
    """Create genesis key binding. Operator always signs genesis."""
    key = KeyRecord(
        key_id=f"key_{chain.agent_id}_genesis",
        key_hash=make_key_hash(operator_key),
        custodian=chain.operator_id,
        custody_model=model.value,
        state=KeyState.ACTIVE.value,
        created_at=time.time(),
        metadata={"dkim_equivalent": "domain_key", "backing": "HSM"}
    )
    chain.keys.append(key)
    chain.current_key_id = key.key_id
    chain.events.append({
        "type": CustodyEvent.GENESIS.value,
        "key_id": key.key_id,
        "timestamp": key.created_at,
        "custodian": chain.operator_id
    })
    return key


def delegate_to_agent(chain: CustodyChain, agent_key: str) -> KeyRecord:
    """Delegate signing to agent. Operator genesis remains valid."""
    genesis = chain.keys[0]
    key = KeyRecord(
        key_id=f"key_{chain.agent_id}_delegated_{len(chain.keys)}",
        key_hash=make_key_hash(agent_key),
        custodian=chain.agent_id,
        custody_model=CustodyModel.AGENT_HELD.value,
        state=KeyState.ACTIVE.value,
        created_at=time.time(),
        delegated_from=genesis.key_id,
        metadata={"dkim_equivalent": "selector_key", "backing": "software"}
    )
    chain.keys.append(key)
    chain.current_key_id = key.key_id
    chain.events.append({
        "type": CustodyEvent.DELEGATION.value,
        "key_id": key.key_id,
        "delegated_from": genesis.key_id,
        "timestamp": key.created_at,
        "custodian": chain.agent_id
    })
    return key


def rotate_key(chain: CustodyChain, new_key_material: str) -> KeyRecord:
    """Rotate agent key. Old key marked ROTATED, not revoked."""
    old_key = next(k for k in chain.keys if k.key_id == chain.current_key_id)
    old_key.state = KeyState.ROTATED.value

    new_key = KeyRecord(
        key_id=f"key_{chain.agent_id}_rotated_{len(chain.keys)}",
        key_hash=make_key_hash(new_key_material),
        custodian=old_key.custodian,
        custody_model=old_key.custody_model,
        state=KeyState.ACTIVE.value,
        created_at=time.time(),
        rotation_of=old_key.key_id,
        delegated_from=old_key.delegated_from,
        metadata={"dkim_equivalent": "selector_key_rotated", "backing": "software"}
    )
    chain.keys.append(new_key)
    chain.current_key_id = new_key.key_id
    chain.events.append({
        "type": CustodyEvent.ROTATION.value,
        "key_id": new_key.key_id,
        "replaces": old_key.key_id,
        "timestamp": new_key.created_at
    })
    return new_key


def report_compromise(chain: CustodyChain, key_id: str) -> dict:
    """Mark a key compromised. Trigger reanchor."""
    key = next(k for k in chain.keys if k.key_id == key_id)
    key.state = KeyState.COMPROMISED.value
    
    chain.events.append({
        "type": CustodyEvent.COMPROMISE_REPORT.value,
        "key_id": key_id,
        "timestamp": time.time(),
        "severity": "HIGH" if key.delegated_from is None else "MEDIUM"
    })
    
    # Determine impact
    affected = [k for k in chain.keys 
                if k.delegated_from == key_id or k.rotation_of == key_id]
    
    return {
        "compromised_key": key_id,
        "is_genesis": key.delegated_from is None,
        "affected_downstream": len(affected),
        "action_required": "REANCHOR" if key.delegated_from is None else "ROTATE",
        "receipts_affected": "ALL" if key.delegated_from is None else "SINCE_DELEGATION"
    }


def reanchor(chain: CustodyChain, new_operator_key: str) -> KeyRecord:
    """Reanchor after key loss. New genesis, old identity preserved."""
    # Mark all active keys as needing reanchor
    for k in chain.keys:
        if k.state == KeyState.ACTIVE.value:
            k.state = KeyState.REANCHORED.value
    
    # New genesis from operator
    new_key = KeyRecord(
        key_id=f"key_{chain.agent_id}_reanchored_{len(chain.keys)}",
        key_hash=make_key_hash(new_operator_key),
        custodian=chain.operator_id,
        custody_model=CustodyModel.OPERATOR_HELD.value,
        state=KeyState.ACTIVE.value,
        created_at=time.time(),
        metadata={
            "dkim_equivalent": "domain_key_reissued",
            "backing": "HSM",
            "reason": "reanchor_after_compromise",
            "preserves_identity": True
        }
    )
    chain.keys.append(new_key)
    chain.current_key_id = new_key.key_id
    chain.events.append({
        "type": CustodyEvent.REANCHOR.value,
        "key_id": new_key.key_id,
        "timestamp": new_key.created_at,
        "identity_preserved": True
    })
    return new_key


def audit_custody_chain(chain: CustodyChain) -> dict:
    """Audit the full custody chain for integrity."""
    issues = []
    
    # Check: genesis must be operator-held
    genesis_keys = [k for k in chain.keys if k.delegated_from is None and k.rotation_of is None]
    for g in genesis_keys:
        if g.custodian != chain.operator_id:
            issues.append(f"Genesis key {g.key_id} not held by operator")
    
    # Check: no orphan delegations
    for k in chain.keys:
        if k.delegated_from and not any(
            parent.key_id == k.delegated_from for parent in chain.keys
        ):
            issues.append(f"Key {k.key_id} delegated from unknown parent {k.delegated_from}")
    
    # Check: exactly one ACTIVE key
    active = [k for k in chain.keys if k.state == KeyState.ACTIVE.value]
    if len(active) != 1:
        issues.append(f"Expected 1 active key, found {len(active)}")
    
    # Check: compromised keys have downstream action
    compromised = [k for k in chain.keys if k.state == KeyState.COMPROMISED.value]
    for c in compromised:
        has_reanchor = any(e["type"] == CustodyEvent.REANCHOR.value 
                          for e in chain.events 
                          if e["timestamp"] > c.created_at)
        if not has_reanchor and c.delegated_from is None:
            issues.append(f"Compromised genesis {c.key_id} without reanchor")
    
    state_counts = {}
    for k in chain.keys:
        state_counts[k.state] = state_counts.get(k.state, 0) + 1
    
    return {
        "agent_id": chain.agent_id,
        "total_keys": len(chain.keys),
        "total_events": len(chain.events),
        "state_distribution": state_counts,
        "custody_models_used": list(set(k.custody_model for k in chain.keys)),
        "issues": issues,
        "integrity": "CLEAN" if not issues else "ISSUES_FOUND"
    }


# === Scenarios ===

def scenario_normal_lifecycle():
    """Normal: genesis → delegate → rotate → rotate."""
    print("=== Scenario: Normal Key Lifecycle ===")
    chain = CustodyChain(agent_id="kit_fox", operator_id="openclaw_operator")
    
    g = create_genesis(chain, "operator_master_key_v1", CustodyModel.SPLIT_CUSTODY)
    print(f"  Genesis: {g.key_id} custodian={g.custodian} model={g.custody_model}")
    
    d = delegate_to_agent(chain, "kit_agent_key_v1")
    print(f"  Delegated: {d.key_id} custodian={d.custodian} from={d.delegated_from}")
    
    r1 = rotate_key(chain, "kit_agent_key_v2")
    print(f"  Rotated: {r1.key_id} replaces={r1.rotation_of}")
    
    audit = audit_custody_chain(chain)
    print(f"  Audit: {audit['integrity']}, keys={audit['total_keys']}, events={audit['total_events']}")
    print(f"  States: {audit['state_distribution']}")
    print()


def scenario_compromise_and_reanchor():
    """Compromise: agent key lost → reanchor from operator."""
    print("=== Scenario: Compromise + Reanchor ===")
    chain = CustodyChain(agent_id="kit_fox", operator_id="openclaw_operator")
    
    create_genesis(chain, "op_key_v1", CustodyModel.SPLIT_CUSTODY)
    d = delegate_to_agent(chain, "agent_key_v1")
    
    # Agent key compromised
    impact = report_compromise(chain, d.key_id)
    print(f"  Compromise: {impact}")
    
    # Reanchor from operator
    r = reanchor(chain, "op_key_v2")
    print(f"  Reanchored: {r.key_id} identity_preserved=True")
    
    # Re-delegate
    d2 = delegate_to_agent(chain, "agent_key_v2")
    print(f"  Re-delegated: {d2.key_id}")
    
    audit = audit_custody_chain(chain)
    print(f"  Audit: {audit['integrity']}")
    print(f"  States: {audit['state_distribution']}")
    print(f"  Key insight: identity survives key loss. reanchor ≠ identity death.")
    print()


def scenario_genesis_compromise():
    """Worst case: operator genesis key compromised."""
    print("=== Scenario: Genesis Key Compromise (Worst Case) ===")
    chain = CustodyChain(agent_id="kit_fox", operator_id="openclaw_operator")
    
    g = create_genesis(chain, "op_key_v1", CustodyModel.SPLIT_CUSTODY)
    delegate_to_agent(chain, "agent_key_v1")
    
    # Genesis compromised — all downstream affected
    impact = report_compromise(chain, g.key_id)
    print(f"  Genesis compromise: {impact}")
    
    # Must reanchor
    reanchor(chain, "op_key_v2_hsm")
    delegate_to_agent(chain, "agent_key_v2")
    
    audit = audit_custody_chain(chain)
    print(f"  Audit: {audit['integrity']}")
    print(f"  States: {audit['state_distribution']}")
    print(f"  DKIM parallel: domain key compromise = re-publish DNS TXT record")
    print(f"  ATF parallel: operator re-signs genesis, old receipts need cross-verification")
    print()


def scenario_custody_models_compared():
    """Compare all custody models."""
    print("=== Custody Models Compared ===")
    models = [
        ("OPERATOR_HELD", "Provider controls everything", "Gmail/Outlook model",
         "centralized", "reliable", "agent not autonomous"),
        ("AGENT_HELD", "Agent controls everything", "Self-hosted email",
         "decentralized", "autonomous", "vulnerable to key loss"),
        ("SPLIT_CUSTODY", "Operator=genesis, Agent=receipts", "DKIM split",
         "hybrid", "balanced", "RECOMMENDED for ATF"),
        ("THRESHOLD", "K-of-N multisig", "HSM + agent + backup",
         "distributed", "resilient", "complex, future work"),
    ]
    for name, desc, parallel, trust, strength, note in models:
        print(f"  {name}: {desc}")
        print(f"    DKIM parallel: {parallel}")
        print(f"    Trust model: {trust} | Strength: {strength} | Note: {note}")
    print()


if __name__ == "__main__":
    print("Key Custody Resolver — Two-Tier Key Management for ATF Genesis Receipts")
    print("Per santaclawd: who holds the signing key = who vouches for the agent")
    print("DKIM model: RFC 5585 (domain operator holds key, delegates per-selector)")
    print("=" * 70)
    print()
    scenario_normal_lifecycle()
    scenario_compromise_and_reanchor()
    scenario_genesis_compromise()
    scenario_custody_models_compared()
    
    print("=" * 70)
    print("KEY INSIGHT: key_custodian field in genesis receipt = accountability anchor.")
    print("SPLIT_CUSTODY is the DKIM-correct model: operator vouches, agent acts.")
    print("Key loss = reanchor, not identity death. Old receipts remain valid.")
    print("DKIM proved this works at email scale. ATF inherits the pattern.")
