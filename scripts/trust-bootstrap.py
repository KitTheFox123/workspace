#!/usr/bin/env python3
"""
trust-bootstrap.py — Who attests the attester?

Gendolf's question: "who attests the checkpoint was taken honestly?"
The infinite regress problem. Every attestation needs an attester,
who needs attestation, who needs...

Solutions from different domains:
- TPM: hardware root of trust (fused key, can't be extracted)
- SMTP: infrastructure-written headers (sender can't forge Received: lines)
- CT: browser-enforced SCTs (CA can't bypass requirement)
- DNA methylation: biology-written clock (organism can't forge age)

Pattern: the thing being measured can't write its own measurement.
"""

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class AttestationSource(Enum):
    SELF_REPORTED = "self_reported"        # Agent claims own state
    PEER_ATTESTED = "peer_attested"        # Another agent attests
    INFRASTRUCTURE = "infrastructure"       # Runtime/platform attests
    HARDWARE = "hardware"                  # TPM/TEE attests
    CRYPTOGRAPHIC = "cryptographic"        # Math proves (ZKP, hash chain)


# Trust weight by source — who CAN'T forge it?
SOURCE_WEIGHTS = {
    AttestationSource.SELF_REPORTED: 0.1,    # Can always lie
    AttestationSource.PEER_ATTESTED: 0.4,    # Collusion possible
    AttestationSource.INFRASTRUCTURE: 0.7,   # Harder to forge
    AttestationSource.HARDWARE: 0.9,         # Requires physical access
    AttestationSource.CRYPTOGRAPHIC: 0.95,   # Requires breaking math
}


@dataclass
class AttestationClaim:
    claim_id: str
    source: AttestationSource
    attester_id: str
    subject_id: str  # Who/what is being attested
    claim: str
    evidence_hash: str
    
    @property
    def self_attesting(self) -> bool:
        """Is the subject attesting itself?"""
        return self.attester_id == self.subject_id
    
    @property
    def trust_weight(self) -> float:
        weight = SOURCE_WEIGHTS[self.source]
        if self.self_attesting:
            weight *= 0.2  # 80% penalty for self-attestation
        return weight


@dataclass
class TrustBootstrap:
    """Models the trust bootstrap problem: how do you establish
    initial trust without pre-existing trust?"""
    
    claims: list = None
    
    def __post_init__(self):
        self.claims = self.claims or []
    
    def add_claim(self, claim: AttestationClaim):
        self.claims.append(claim)
    
    def regress_depth(self) -> int:
        """How deep is the attestation chain before hitting a root?"""
        roots = [c for c in self.claims if c.source in 
                (AttestationSource.HARDWARE, AttestationSource.CRYPTOGRAPHIC)]
        if roots:
            return 0  # Grounded
        infra = [c for c in self.claims if c.source == AttestationSource.INFRASTRUCTURE]
        if infra:
            return 1  # One hop to infrastructure
        peers = [c for c in self.claims if c.source == AttestationSource.PEER_ATTESTED]
        if peers:
            return 2  # Two hops (peer could be lying)
        return 99  # Infinite regress — only self-attestation
    
    def bootstrap_grade(self) -> tuple[str, str]:
        """Grade the trust bootstrap."""
        depth = self.regress_depth()
        
        # Check for self-attestation-only
        all_self = all(c.self_attesting for c in self.claims)
        if all_self and self.claims:
            return "F", "INFINITE_REGRESS: only self-attestation"
        
        # Check diversity of sources
        sources = set(c.source for c in self.claims)
        
        if depth == 0:
            if len(sources) >= 3:
                return "A+", "GROUNDED: hardware/crypto root + diverse sources"
            return "A", "GROUNDED: hardware/crypto root of trust"
        elif depth == 1:
            return "B", "INFRASTRUCTURE: one hop to trusted platform"
        elif depth == 2:
            if len(self.claims) >= 3:
                return "C+", "PEER: multiple independent attesters"
            return "C", "PEER: attestation by other agents (collusion risk)"
        else:
            return "F", "UNGROUNDED: no root of trust"
    
    def composite_trust(self) -> float:
        """Weighted trust score across all claims."""
        if not self.claims:
            return 0.0
        weights = [c.trust_weight for c in self.claims]
        # Use max rather than average — one strong root grounds everything
        return max(weights)


def demo():
    print("=" * 60)
    print("TRUST BOOTSTRAP — Who Attests the Attester?")
    print("=" * 60)
    
    scenarios = {
        "Self-only (most agents today)": [
            AttestationClaim("c1", AttestationSource.SELF_REPORTED, 
                           "agent_a", "agent_a", "I am running version 2.1", "abc123"),
            AttestationClaim("c2", AttestationSource.SELF_REPORTED,
                           "agent_a", "agent_a", "My scope hash is xyz", "def456"),
        ],
        "Peer-attested (isnad basic)": [
            AttestationClaim("c3", AttestationSource.PEER_ATTESTED,
                           "agent_b", "agent_a", "Observed agent_a responding correctly", "ghi789"),
            AttestationClaim("c4", AttestationSource.PEER_ATTESTED,
                           "agent_c", "agent_a", "Confirmed agent_a scope matches", "jkl012"),
        ],
        "Infrastructure (SMTP/CT model)": [
            AttestationClaim("c5", AttestationSource.INFRASTRUCTURE,
                           "smtp_server", "agent_a", "Received: from agent_a at 17:00 UTC", "mno345"),
            AttestationClaim("c6", AttestationSource.PEER_ATTESTED,
                           "agent_b", "agent_a", "Observed via email thread", "pqr678"),
        ],
        "Hardware-grounded (TPM model)": [
            AttestationClaim("c7", AttestationSource.HARDWARE,
                           "tpm_chip", "agent_a", "PCR[7] = sha256(runtime_state)", "stu901"),
            AttestationClaim("c8", AttestationSource.INFRASTRUCTURE,
                           "platform", "agent_a", "Container hash matches manifest", "vwx234"),
            AttestationClaim("c9", AttestationSource.PEER_ATTESTED,
                           "agent_b", "agent_a", "Independent observation confirms", "yza567"),
        ],
        "Mixed with self-contamination": [
            AttestationClaim("c10", AttestationSource.INFRASTRUCTURE,
                           "platform", "agent_a", "Runtime checkpoint hash", "bcd890"),
            AttestationClaim("c11", AttestationSource.SELF_REPORTED,
                           "agent_a", "agent_a", "I confirm my own hash", "efg123"),
        ],
    }
    
    for name, claims in scenarios.items():
        tb = TrustBootstrap(claims)
        grade, reason = tb.bootstrap_grade()
        depth = tb.regress_depth()
        trust = tb.composite_trust()
        
        print(f"\n{'─' * 50}")
        print(f"Scenario: {name}")
        print(f"  Claims: {len(claims)}")
        print(f"  Sources: {', '.join(c.source.value for c in claims)}")
        print(f"  Self-attesting: {sum(1 for c in claims if c.self_attesting)}/{len(claims)}")
        print(f"  Regress depth: {depth} {'(GROUNDED)' if depth == 0 else '(INFINITE)' if depth == 99 else ''}")
        print(f"  Trust score: {trust:.2f}")
        print(f"  Grade: {grade} — {reason}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: The thing being measured can't write its")
    print("own measurement. Infrastructure attestation > self-attestation.")
    print("TPM fuses the key. SMTP writes the header. CT enforces SCTs.")
    print("The agent doesn't attest its own state. The runtime does.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
