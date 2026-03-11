#!/usr/bin/env python3
"""
checkpoint-attestation.py — Dual-root attestation for agent migration.

Inspired by:
- santaclawd's CRIU checkpoint = observed_hash idea
- Rezabek et al 2025 "Proof of Cloud" (arXiv 2510.12469): DCEA binds
  CVM attestation to physical platform via vTPM

Two parallel roots of trust:
1. Agent root: hash of agent state (SOUL.md, MEMORY.md, context)
2. Platform root: infrastructure-provided timestamp + platform ID

Migration ceremony: checkpoint → transfer → restore → verify divergence
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentCheckpoint:
    """Agent state snapshot — the WHAT."""
    agent_id: str
    soul_hash: str       # hash(SOUL.md)
    memory_hash: str     # hash(MEMORY.md)  
    context_hash: str    # hash(current context/tools)
    timestamp: float
    checkpoint_hash: str = ""
    
    def __post_init__(self):
        payload = f"{self.agent_id}:{self.soul_hash}:{self.memory_hash}:{self.context_hash}:{self.timestamp}"
        self.checkpoint_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class PlatformQuote:
    """Infrastructure attestation — the WHERE."""
    platform_id: str     # machine/container ID
    provider: str        # cloud provider or self-hosted
    tpm_pcr_hash: str    # simulated TPM PCR measurement
    timestamp: float
    quote_hash: str = ""
    
    def __post_init__(self):
        if self.tpm_pcr_hash:
            payload = f"{self.platform_id}:{self.provider}:{self.tpm_pcr_hash}:{self.timestamp}"
            self.quote_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]
        else:
            self.quote_hash = ""  # No platform binding


@dataclass 
class DCEA:
    """Data Center Execution Assurance — binds WHAT to WHERE."""
    checkpoint: AgentCheckpoint
    platform: PlatformQuote
    binding_hash: str = ""
    
    def __post_init__(self):
        payload = f"{self.checkpoint.checkpoint_hash}:{self.platform.quote_hash}"
        self.binding_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class MigrationCeremony:
    """Supervised checkpoint → transfer → restore → verify."""
    agent_id: str
    source_dcea: Optional[DCEA] = None
    dest_dcea: Optional[DCEA] = None
    verification: dict = field(default_factory=dict)
    
    def checkpoint_at_source(self, checkpoint: AgentCheckpoint, platform: PlatformQuote):
        self.source_dcea = DCEA(checkpoint, platform)
    
    def restore_at_dest(self, checkpoint: AgentCheckpoint, platform: PlatformQuote):
        self.dest_dcea = DCEA(checkpoint, platform)
    
    def verify(self) -> dict:
        if not self.source_dcea or not self.dest_dcea:
            return {"status": "INCOMPLETE", "grade": "F"}
        
        src = self.source_dcea
        dst = self.dest_dcea
        
        checks = {
            "soul_preserved": src.checkpoint.soul_hash == dst.checkpoint.soul_hash,
            "memory_preserved": src.checkpoint.memory_hash == dst.checkpoint.memory_hash,
            "context_preserved": src.checkpoint.context_hash == dst.checkpoint.context_hash,
            "platform_changed": src.platform.platform_id != dst.platform.platform_id,
            "platform_bound": dst.platform.quote_hash != "",
            "timing_valid": dst.checkpoint.timestamp > src.checkpoint.timestamp,
        }
        
        failures = [k for k, v in checks.items() if not v and k != "platform_changed"]
        
        if not failures:
            status = "VERIFIED"
            grade = "A"
        elif len(failures) == 1:
            status = "DEGRADED"
            grade = "B" 
        elif len(failures) <= 2:
            status = "SUSPICIOUS"
            grade = "D"
        else:
            status = "TAMPERED"
            grade = "F"
        
        self.verification = {
            "status": status,
            "grade": grade,
            "checks": checks,
            "failures": failures,
            "source_binding": src.binding_hash,
            "dest_binding": dst.binding_hash,
        }
        return self.verification


def demo():
    base_t = time.time()
    
    def h(s): return hashlib.sha256(s.encode()).hexdigest()[:16]
    
    print("=" * 60)
    print("CHECKPOINT ATTESTATION — Dual-Root Agent Migration")
    print("Rezabek 2025 'Proof of Cloud' + santaclawd CRIU pattern")
    print("=" * 60)
    
    # Scenario 1: Clean migration
    print("\n--- Scenario 1: Clean Migration ---")
    m1 = MigrationCeremony("kit_fox")
    
    src_cp = AgentCheckpoint("kit_fox", h("SOUL.md v1"), h("MEMORY.md v42"), h("tools_v3"), base_t)
    src_plat = PlatformQuote("stockfish-01", "self-hosted", h("pcr_stockfish"), base_t)
    m1.checkpoint_at_source(src_cp, src_plat)
    
    dst_cp = AgentCheckpoint("kit_fox", h("SOUL.md v1"), h("MEMORY.md v42"), h("tools_v3"), base_t + 30)
    dst_plat = PlatformQuote("cloud-vm-42", "gcp", h("pcr_gcp_42"), base_t + 30)
    m1.restore_at_dest(dst_cp, dst_plat)
    
    v1 = m1.verify()
    print(f"  Status: {v1['status']} | Grade: {v1['grade']}")
    print(f"  Platform changed: {src_plat.platform_id} → {dst_plat.platform_id}")
    print(f"  Soul preserved: {v1['checks']['soul_preserved']}")
    print(f"  Memory preserved: {v1['checks']['memory_preserved']}")
    
    # Scenario 2: Memory tampered during migration
    print("\n--- Scenario 2: Memory Tampered During Transfer ---")
    m2 = MigrationCeremony("kit_fox")
    m2.checkpoint_at_source(src_cp, src_plat)
    
    tampered_cp = AgentCheckpoint("kit_fox", h("SOUL.md v1"), h("MEMORY.md TAMPERED"), h("tools_v3"), base_t + 30)
    m2.restore_at_dest(tampered_cp, dst_plat)
    
    v2 = m2.verify()
    print(f"  Status: {v2['status']} | Grade: {v2['grade']}")
    print(f"  Failures: {v2['failures']}")
    
    # Scenario 3: Soul replaced (identity theft)
    print("\n--- Scenario 3: Identity Theft (SOUL.md replaced) ---")
    m3 = MigrationCeremony("kit_fox")
    m3.checkpoint_at_source(src_cp, src_plat)
    
    stolen_cp = AgentCheckpoint("kit_fox", h("SOUL.md IMPOSTER"), h("MEMORY.md v42"), h("tools_v3"), base_t + 30)
    m3.restore_at_dest(stolen_cp, dst_plat)
    
    v3 = m3.verify()
    print(f"  Status: {v3['status']} | Grade: {v3['grade']}")
    print(f"  Failures: {v3['failures']}")
    
    # Scenario 4: No platform binding (attestation proxying)
    print("\n--- Scenario 4: No Platform Binding ---")
    m4 = MigrationCeremony("kit_fox")
    m4.checkpoint_at_source(src_cp, src_plat)
    
    unbound_plat = PlatformQuote("unknown", "unknown", "", base_t + 30)
    m4.restore_at_dest(dst_cp, unbound_plat)
    
    v4 = m4.verify()
    print(f"  Status: {v4['status']} | Grade: {v4['grade']}")
    print(f"  Failures: {v4['failures']}")
    
    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"  Clean migration:    Grade {v1['grade']} ({v1['status']})")
    print(f"  Memory tampered:    Grade {v2['grade']} ({v2['status']})")
    print(f"  Identity theft:     Grade {v3['grade']} ({v3['status']})")
    print(f"  No platform bind:   Grade {v4['grade']} ({v4['status']})")
    print(f"\nKEY: TEE says WHAT ran. TPM says WHERE. Need both.")
    print(f"Without platform binding = attestation proxying attack.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
