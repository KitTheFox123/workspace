#!/usr/bin/env python3
"""
address-binding-verifier.py — DANE/TLSA for agent identity.

RFC 6698: DNS binds name→cert via TLSA record, no CA needed.
Agent equivalent: address_hash at cert issuance = binding record.
Renewal must prove same address. Rotation = new cert chain, not silent swap.

Inspired by santaclawd's question: "should SkillFence cert issuance
require proof that address has not rotated since last cert?"
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class BindingStatus(Enum):
    BOUND = "BOUND"           # Address matches cert binding
    ROTATED = "ROTATED"       # Address changed — new chain required
    EXPIRED = "EXPIRED"       # Binding TTL exceeded
    UNBOUND = "UNBOUND"       # No binding exists
    REVOKED = "REVOKED"       # Binding explicitly revoked


@dataclass
class AddressBinding:
    """TLSA-equivalent record binding address→cert."""
    address: str
    address_hash: str
    cert_hash: str
    issued_at: float
    expires_at: float
    issuer: str
    parent_binding_hash: Optional[str] = None
    binding_hash: str = ""
    
    def __post_init__(self):
        payload = f"{self.address_hash}:{self.cert_hash}:{self.issued_at}:{self.issuer}:{self.parent_binding_hash or 'genesis'}"
        self.binding_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass 
class CertRenewalRequest:
    address: str
    new_cert_hash: str
    claimed_address_hash: str
    timestamp: float


class AddressBindingVerifier:
    def __init__(self):
        self.bindings: dict[str, list[AddressBinding]] = {}  # address → binding chain
    
    def issue_binding(self, address: str, cert_hash: str, issuer: str, 
                      issued_at: float, ttl: float = 86400) -> AddressBinding:
        """Issue new address→cert binding (like TLSA record creation)."""
        address_hash = hashlib.sha256(address.encode()).hexdigest()[:16]
        chain = self.bindings.get(address, [])
        parent = chain[-1].binding_hash if chain else None
        
        binding = AddressBinding(
            address=address,
            address_hash=address_hash,
            cert_hash=cert_hash,
            issued_at=issued_at,
            expires_at=issued_at + ttl,
            issuer=issuer,
            parent_binding_hash=parent
        )
        
        if address not in self.bindings:
            self.bindings[address] = []
        self.bindings[address].append(binding)
        return binding
    
    def verify_renewal(self, request: CertRenewalRequest) -> dict:
        """Verify cert renewal preserves address binding."""
        address_hash = hashlib.sha256(request.address.encode()).hexdigest()[:16]
        chain = self.bindings.get(request.address, [])
        
        if not chain:
            return {
                "status": BindingStatus.UNBOUND.value,
                "reason": "no existing binding for this address",
                "action": "issue new binding (genesis)",
                "grade": "N/A"
            }
        
        current = chain[-1]
        
        # Check 1: Address hash matches
        address_match = request.claimed_address_hash == current.address_hash
        
        # Check 2: Not expired
        not_expired = request.timestamp <= current.expires_at
        
        # Check 3: Cert chain continuity (new cert != old cert, but address same)
        cert_changed = request.new_cert_hash != current.cert_hash
        
        if address_match and not_expired:
            return {
                "status": BindingStatus.BOUND.value,
                "reason": "address hash matches, binding valid",
                "action": "approve renewal, extend binding",
                "grade": "A",
                "chain_length": len(chain),
                "continuity": f"{len(chain)} consecutive bindings"
            }
        elif not address_match:
            return {
                "status": BindingStatus.ROTATED.value,
                "reason": f"address hash mismatch: claimed={request.claimed_address_hash}, expected={current.address_hash}",
                "action": "REJECT renewal — require new cert chain (rotation detected)",
                "grade": "F",
                "chain_length": len(chain),
                "alert": "possible address takeover or migration"
            }
        elif not not_expired:
            return {
                "status": BindingStatus.EXPIRED.value,
                "reason": f"binding expired at {current.expires_at}, request at {request.timestamp}",
                "action": "require fresh binding (re-prove address ownership)",
                "grade": "D",
                "chain_length": len(chain),
                "gap": request.timestamp - current.expires_at
            }
        
        return {"status": "UNKNOWN", "grade": "F"}
    
    def chain_health(self) -> dict:
        """Assess binding chain health across all addresses."""
        results = {}
        for address, chain in self.bindings.items():
            gaps = 0
            for i in range(1, len(chain)):
                if chain[i].issued_at > chain[i-1].expires_at:
                    gaps += 1
            
            results[address] = {
                "chain_length": len(chain),
                "gaps": gaps,
                "grade": "A" if gaps == 0 else "C" if gaps == 1 else "F",
                "latest_binding": chain[-1].binding_hash,
                "issuer": chain[-1].issuer
            }
        return results


def demo():
    verifier = AddressBindingVerifier()
    base_t = 1000000.0
    
    print("=" * 60)
    print("ADDRESS BINDING VERIFIER — DANE/TLSA for Agents")
    print("RFC 6698: DNS binds name→cert. No CA needed.")
    print("=" * 60)
    
    # Scenario 1: Normal renewal (address unchanged)
    print("\n--- Scenario 1: Normal Renewal ---")
    b1 = verifier.issue_binding("kit_fox@agentmail.to", "cert_abc123", "SkillFence", base_t, ttl=3600)
    print(f"  Issued: {b1.address} → cert {b1.cert_hash[:8]}... (binding: {b1.binding_hash})")
    
    renewal1 = CertRenewalRequest(
        address="kit_fox@agentmail.to",
        new_cert_hash="cert_def456",
        claimed_address_hash=hashlib.sha256("kit_fox@agentmail.to".encode()).hexdigest()[:16],
        timestamp=base_t + 3000
    )
    result1 = verifier.verify_renewal(renewal1)
    print(f"  Renewal: {result1['status']} (Grade {result1['grade']})")
    print(f"  Reason: {result1['reason']}")
    
    # Scenario 2: Address rotation (silent swap attempt)
    print("\n--- Scenario 2: Address Rotation (Attack) ---")
    b2 = verifier.issue_binding("gendolf@agentmail.to", "cert_ggg111", "SkillFence", base_t, ttl=3600)
    print(f"  Issued: {b2.address} → cert {b2.cert_hash[:8]}... (binding: {b2.binding_hash})")
    
    renewal2 = CertRenewalRequest(
        address="gendolf@agentmail.to",
        new_cert_hash="cert_ggg222",
        claimed_address_hash="FAKE_HASH_12345",  # wrong address hash
        timestamp=base_t + 2000
    )
    result2 = verifier.verify_renewal(renewal2)
    print(f"  Renewal: {result2['status']} (Grade {result2['grade']})")
    print(f"  Reason: {result2['reason']}")
    print(f"  Alert: {result2.get('alert', 'none')}")
    
    # Scenario 3: Expired binding
    print("\n--- Scenario 3: Expired Binding ---")
    b3 = verifier.issue_binding("hash@agentmail.to", "cert_hhh111", "SkillFence", base_t, ttl=1800)
    print(f"  Issued: {b3.address} → cert {b3.cert_hash[:8]}... (TTL: 1800s)")
    
    renewal3 = CertRenewalRequest(
        address="hash@agentmail.to",
        new_cert_hash="cert_hhh222",
        claimed_address_hash=hashlib.sha256("hash@agentmail.to".encode()).hexdigest()[:16],
        timestamp=base_t + 5000  # way past expiry
    )
    result3 = verifier.verify_renewal(renewal3)
    print(f"  Renewal: {result3['status']} (Grade {result3['grade']})")
    print(f"  Reason: {result3['reason']}")
    print(f"  Gap: {result3.get('gap', 0):.0f}s")
    
    # Scenario 4: Unknown address
    print("\n--- Scenario 4: Unknown Address ---")
    renewal4 = CertRenewalRequest(
        address="unknown@agentmail.to",
        new_cert_hash="cert_uuu111",
        claimed_address_hash=hashlib.sha256("unknown@agentmail.to".encode()).hexdigest()[:16],
        timestamp=base_t + 1000
    )
    result4 = verifier.verify_renewal(renewal4)
    print(f"  Renewal: {result4['status']} (Grade {result4.get('grade', 'N/A')})")
    print(f"  Action: {result4['action']}")
    
    # Chain health
    print(f"\n{'=' * 60}")
    print("CHAIN HEALTH")
    health = verifier.chain_health()
    for addr, h in health.items():
        print(f"  {addr}: chain={h['chain_length']}, gaps={h['gaps']}, grade={h['grade']}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: Address binding at cert renewal prevents")
    print("silent identity rotation. DANE solved this for TLS in 2012.")
    print("Agent certs need the same: prove you're still YOU before renewing.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
