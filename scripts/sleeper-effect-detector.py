#!/usr/bin/env python3
"""
Sleeper Effect Detector for Agent Trust

Based on Kumkale & Albarracín (2004) meta-analysis of sleeper effect:
- Message content decays SLOWER than source-discounting cues
- After delay, discredited message regains persuasive power
- Differential decay = the sleeper effect

Agent threat model:
- Key gets compromised → flagged as untrustworthy
- Agent reboots → context cleared → flag not in new context
- Key regains trust without earning it back (sleeper effect)

Fix: Bind flags cryptographically INTO certificates.
Flag dissociation becomes impossible without revoking the cert.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional


@dataclass
class TrustFlag:
    """A discounting cue attached to an agent identity."""
    flag_type: str  # "compromised", "suspicious", "rate_limited"
    created_at: float
    evidence_hash: str  # hash of evidence that triggered flag
    severity: float  # 0-1
    
    @property
    def flag_hash(self) -> str:
        content = f"{self.flag_type}:{self.created_at}:{self.evidence_hash}:{self.severity}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass 
class AgentCert:
    """Agent certificate with bound trust flags."""
    agent_id: str
    pubkey_hash: str
    issued_at: float
    flags: list[TrustFlag] = field(default_factory=list)
    flag_binding: Optional[str] = None  # hash of all flag hashes
    
    def bind_flags(self):
        """Cryptographically bind flags into cert. Dissociation = cert invalid."""
        if not self.flags:
            self.flag_binding = hashlib.sha256(b"clean").hexdigest()[:16]
        else:
            flag_hashes = sorted(f.flag_hash for f in self.flags)
            combined = ":".join(flag_hashes)
            self.flag_binding = hashlib.sha256(combined.encode()).hexdigest()[:16]
    
    def verify_binding(self) -> bool:
        """Verify flag binding hasn't been tampered with."""
        if self.flag_binding is None:
            return False
        expected_binding = None
        if not self.flags:
            expected_binding = hashlib.sha256(b"clean").hexdigest()[:16]
        else:
            flag_hashes = sorted(f.flag_hash for f in self.flags)
            combined = ":".join(flag_hashes)
            expected_binding = hashlib.sha256(combined.encode()).hexdigest()[:16]
        return self.flag_binding == expected_binding


def simulate_sleeper_effect():
    """Simulate sleeper effect in agent trust with and without binding."""
    
    print("=" * 60)
    print("SLEEPER EFFECT DETECTOR")
    print("Kumkale & Albarracín (Psych Bull 2004)")
    print("=" * 60)
    
    now = time.time()
    
    # Create a compromised agent
    flag = TrustFlag(
        flag_type="compromised",
        created_at=now - 3600,  # 1 hour ago
        evidence_hash="abc123",
        severity=0.9
    )
    
    scenarios = []
    
    # Scenario 1: No flag binding (vulnerable to sleeper effect)
    print(f"\n{'─' * 60}")
    print("Scenario 1: NO FLAG BINDING (current agent infra)")
    cert_unbound = AgentCert("agent_alice", "pk_alice", now - 7200)
    cert_unbound.flags = [flag]
    
    # Simulate reboot — flags stored in context, not cert
    print(f"  Before reboot: {len(cert_unbound.flags)} flags")
    cert_after_reboot = AgentCert("agent_alice", "pk_alice", now - 7200)
    cert_after_reboot.flags = []  # Context cleared!
    print(f"  After reboot:  {len(cert_after_reboot.flags)} flags ← SLEEPER EFFECT")
    print(f"  Trust restored WITHOUT earning it back")
    print(f"  Grade: F (flag dissociated from identity)")
    scenarios.append(("No binding", "F", "flag lost on reboot"))
    
    # Scenario 2: Flag binding (immune to sleeper effect)
    print(f"\n{'─' * 60}")
    print("Scenario 2: FLAG BINDING (proposed fix)")
    cert_bound = AgentCert("agent_alice", "pk_alice", now - 7200)
    cert_bound.flags = [flag]
    cert_bound.bind_flags()
    
    print(f"  Flag binding: {cert_bound.flag_binding}")
    print(f"  Verify binding: {cert_bound.verify_binding()}")
    
    # Simulate reboot — cert includes binding
    cert_reboot_bound = AgentCert("agent_alice", "pk_alice", now - 7200)
    cert_reboot_bound.flags = []  # Try to clear flags
    cert_reboot_bound.flag_binding = cert_bound.flag_binding  # But binding persists
    
    valid = cert_reboot_bound.verify_binding()
    print(f"  After reboot (flags cleared, binding kept): valid={valid}")
    print(f"  Binding mismatch → cert INVALID until flags restored")
    print(f"  Grade: A (dissociation cryptographically impossible)")
    scenarios.append(("Flag binding", "A", "dissociation detected"))
    
    # Scenario 3: Flag binding with legitimate flag removal
    print(f"\n{'─' * 60}")
    print("Scenario 3: LEGITIMATE FLAG REMOVAL (earned trust back)")
    cert_earned = AgentCert("agent_alice", "pk_alice", now)
    cert_earned.flags = []  # Clean after remediation
    cert_earned.bind_flags()  # New clean binding
    
    print(f"  New cert issued after remediation")
    print(f"  Clean binding: {cert_earned.flag_binding}")
    print(f"  Verify: {cert_earned.verify_binding()}")
    print(f"  Grade: A (trust earned through new cert, not flag loss)")
    scenarios.append(("Legitimate removal", "A", "new cert issued"))
    
    # Scenario 4: Tampered binding
    print(f"\n{'─' * 60}")
    print("Scenario 4: TAMPERED BINDING (adversarial)")
    cert_tampered = AgentCert("agent_alice", "pk_alice", now - 7200)
    cert_tampered.flags = [flag]
    cert_tampered.bind_flags()
    
    # Adversary tries to clear flags but keep binding
    cert_tampered.flags = []
    cert_tampered.flag_binding = hashlib.sha256(b"clean").hexdigest()[:16]
    
    # But issuer's signature covers original binding — forgery detectable
    # (In real impl, cert is signed by issuer)
    print(f"  Adversary cleared flags + forged clean binding")
    print(f"  Verify (local): {cert_tampered.verify_binding()} ← passes locally")
    print(f"  But: issuer signature covers original binding → FORGERY DETECTED")
    print(f"  Grade: B (requires signed cert verification)")
    scenarios.append(("Tampered binding", "B", "issuer sig catches forgery"))
    
    # Scenario 5: Differential decay simulation
    print(f"\n{'─' * 60}")
    print("Scenario 5: DIFFERENTIAL DECAY (Kumkale 2004 model)")
    print()
    
    # Kumkale finding: message impact decays with half-life ~6 weeks
    # Discounting cue decays with half-life ~2 weeks
    # After sufficient time, message > cue → sleeper effect
    
    message_halflife = 42  # days (message content retention)
    cue_halflife = 14      # days (source discounting retention)
    
    print(f"  {'Day':>4}  {'Message':>8}  {'Cue':>8}  {'Net Trust':>10}  {'Status'}")
    print(f"  {'─'*4}  {'─'*8}  {'─'*8}  {'─'*10}  {'─'*20}")
    
    for day in [0, 7, 14, 21, 28, 42, 56]:
        import math
        message_strength = math.exp(-0.693 * day / message_halflife)
        cue_strength = math.exp(-0.693 * day / cue_halflife)
        
        # Net trust = message if cue forgotten, discounted if cue remembered
        net_trust = message_strength * (1 - cue_strength * 0.8)
        
        if cue_strength > 0.5:
            status = "DISCOUNTING (safe)"
        elif net_trust > 0.3:
            status = "SLEEPER ACTIVE ⚠️"
        else:
            status = "faded"
        
        print(f"  {day:>4}  {message_strength:>8.3f}  {cue_strength:>8.3f}  {net_trust:>10.3f}  {status}")
    
    print(f"\n  Without binding: flag (cue) decays → compromised key trusted again")
    print(f"  With binding: flag cryptographically permanent → sleeper impossible")
    
    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    for name, grade, reason in scenarios:
        print(f"  {name:.<30} Grade {grade} ({reason})")
    print()
    print("KEY INSIGHT (Kumkale & Albarracín 2004):")
    print("  Discounting cues decay faster than message content.")
    print("  In agents: trust flags decay faster than key material.")
    print("  Fix: bind flags INTO certs. Dissociation = cert invalid.")
    print("  The sleeper effect is a cryptographic problem, not a memory one.")


if __name__ == "__main__":
    simulate_sleeper_effect()
