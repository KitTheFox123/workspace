#!/usr/bin/env python3
"""
trust-acme.py — ACME-inspired automated trust renewal for ATF.

Maps RFC 8555 (ACME) concepts to agent trust management:
- ACME account → Agent identity (DID/agent_id)  
- Certificate → Trust credential (time-bounded attestation)
- Challenge → Forensic probe (prove you still control what you claim)
- Order → Trust renewal request
- Authorization → Challenge-response verification
- Finalize → Issue short-lived trust credential

Key ACME design principles applied:
1. **Automated renewal** — Trust decays by default, must be actively re-earned
2. **Challenge-response** — Prove capability, don't just assert it
3. **Short-lived credentials** — 90-day certs killed CRL. Short TTL kills revocation.
4. **No gatekeepers** — Any registry can verify, not just the issuer
5. **Domain validation** — Prove control of the claimed resource

Challenge types (mapped from ACME HTTP-01, DNS-01, TLS-ALPN-01):
- CAPABILITY_PROBE: Execute a task, prove competence (HTTP-01 equivalent)
- HISTORY_VERIFY: Prove temporal existence via append-only log (DNS-01 equivalent)
- LIVE_ATTESTATION: Real-time challenge from verifier (TLS-ALPN-01 equivalent)

"Let's Encrypt killed the CA cartel by making cert issuance automated + free.
ATF needs the same: automated trust renewal, free verification, no gatekeepers."

Sources:
- RFC 8555: ACME protocol
- alphasenpai: "ACME for reputation" / "forensic floor"
- santaclawd: short-lived certs model, trust decays by default
- Let's Encrypt: 380M+ active certs via automation
"""

import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone, timedelta


class ChallengeType(Enum):
    """ACME-inspired challenge types for trust verification."""
    CAPABILITY_PROBE = "capability-probe"    # HTTP-01: prove you can do the thing
    HISTORY_VERIFY = "history-verify"        # DNS-01: prove temporal existence
    LIVE_ATTESTATION = "live-attestation"    # TLS-ALPN-01: real-time challenge


class ChallengeStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    VALID = "valid"
    INVALID = "invalid"
    EXPIRED = "expired"


class OrderStatus(Enum):
    PENDING = "pending"
    READY = "ready"       # All challenges passed
    PROCESSING = "processing"
    VALID = "valid"       # Credential issued
    INVALID = "invalid"
    EXPIRED = "expired"


@dataclass
class Challenge:
    """A single challenge in the trust verification flow."""
    id: str
    type: ChallengeType
    token: str                    # Random token for challenge
    status: ChallengeStatus = ChallengeStatus.PENDING
    validated_at: Optional[str] = None
    error: Optional[str] = None
    
    # Challenge-specific data
    expected_response: Optional[str] = None  # What we expect back
    probe_task: Optional[str] = None         # For capability probes
    history_anchor: Optional[str] = None     # For history verification
    
    @property
    def is_complete(self) -> bool:
        return self.status in (ChallengeStatus.VALID, ChallengeStatus.INVALID)


@dataclass
class Authorization:
    """Authorization for a specific trust claim."""
    id: str
    agent_id: str
    claim: str                    # What trust claim is being renewed
    challenges: list[Challenge]
    status: str = "pending"       # pending, valid, invalid, expired
    expires: Optional[str] = None


@dataclass 
class TrustCredential:
    """Short-lived trust credential (the "certificate")."""
    id: str
    agent_id: str
    claims: list[str]            # Verified trust claims
    issued_at: str
    expires_at: str              # Short TTL!
    issuer_registry: str
    challenge_log: list[str]     # Which challenges were passed
    fingerprint: str             # Hash of credential contents
    
    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > datetime.fromisoformat(self.expires_at)
    
    @property
    def ttl_hours(self) -> float:
        exp = datetime.fromisoformat(self.expires_at)
        now = datetime.now(timezone.utc)
        return max(0, (exp - now).total_seconds() / 3600)


class TrustACME:
    """
    ACME-inspired automated trust management for agents.
    
    Flow (mirrors RFC 8555):
    1. Agent requests trust renewal (newOrder)
    2. Registry returns required challenges (authorizations)
    3. Agent completes challenges (prove capability/history/liveness)
    4. Registry verifies challenge responses
    5. If all pass → issue short-lived trust credential
    6. Credential expires → repeat from step 1
    
    Key differences from TLS ACME:
    - Challenges test CAPABILITY not just control
    - History verification = temporal proof of existence
    - Credentials are scoped to specific trust claims
    - No CA hierarchy — any registry can issue
    """
    
    DEFAULT_TTL_HOURS = 72       # 3 days (vs ACME's 90 days for certs)
    RENEWAL_WINDOW_HOURS = 24    # Start renewal when 24h remain
    CHALLENGE_TIMEOUT_SEC = 300  # 5 minutes to complete challenge
    
    def __init__(self, registry_id: str):
        self.registry_id = registry_id
        self.orders: dict[str, dict] = {}
        self.authorizations: dict[str, Authorization] = {}
        self.credentials: dict[str, TrustCredential] = {}
        self.challenge_results: list[dict] = []
    
    def new_order(self, agent_id: str, claims: list[str]) -> dict:
        """
        Create a new trust renewal order.
        Returns required authorizations (challenges to complete).
        """
        order_id = f"order-{secrets.token_hex(8)}"
        now = datetime.now(timezone.utc)
        
        authorizations = []
        for claim in claims:
            auth = self._create_authorization(agent_id, claim)
            authorizations.append(auth)
            self.authorizations[auth.id] = auth
        
        order = {
            "id": order_id,
            "status": OrderStatus.PENDING.value,
            "agent_id": agent_id,
            "claims": claims,
            "authorization_ids": [a.id for a in authorizations],
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=24)).isoformat(),
        }
        self.orders[order_id] = order
        
        return order
    
    def _create_authorization(self, agent_id: str, claim: str) -> Authorization:
        """Create authorization with appropriate challenges for a claim."""
        auth_id = f"auth-{secrets.token_hex(8)}"
        now = datetime.now(timezone.utc)
        
        challenges = []
        
        # Every claim requires at least a capability probe
        challenges.append(Challenge(
            id=f"chal-{secrets.token_hex(8)}",
            type=ChallengeType.CAPABILITY_PROBE,
            token=secrets.token_hex(16),
            probe_task=f"Demonstrate capability for claim: {claim}",
        ))
        
        # History verification for claims requiring temporal proof
        if "established" in claim or "persistent" in claim or "reliable" in claim:
            challenges.append(Challenge(
                id=f"chal-{secrets.token_hex(8)}",
                type=ChallengeType.HISTORY_VERIFY,
                token=secrets.token_hex(16),
                history_anchor=f"Prove existence since claiming: {claim}",
            ))
        
        # High-value claims require live attestation
        if "verified" in claim or "trusted" in claim:
            challenges.append(Challenge(
                id=f"chal-{secrets.token_hex(8)}",
                type=ChallengeType.LIVE_ATTESTATION,
                token=secrets.token_hex(16),
            ))
        
        return Authorization(
            id=auth_id,
            agent_id=agent_id,
            claim=claim,
            challenges=challenges,
            expires=(now + timedelta(hours=24)).isoformat(),
        )
    
    def respond_to_challenge(self, challenge_id: str, response: str) -> dict:
        """
        Agent responds to a challenge.
        Like ACME: agent prepares response, then tells server to verify.
        """
        # Find the challenge
        challenge = None
        auth = None
        for a in self.authorizations.values():
            for c in a.challenges:
                if c.id == challenge_id:
                    challenge = c
                    auth = a
                    break
        
        if not challenge:
            return {"error": "Challenge not found"}
        
        if challenge.status != ChallengeStatus.PENDING:
            return {"error": f"Challenge already {challenge.status.value}"}
        
        # Verify based on challenge type
        challenge.status = ChallengeStatus.PROCESSING
        
        result = self._verify_challenge(challenge, response)
        
        challenge.status = result["status"]
        challenge.validated_at = datetime.now(timezone.utc).isoformat() if result["passed"] else None
        challenge.error = result.get("error")
        
        self.challenge_results.append({
            "challenge_id": challenge_id,
            "type": challenge.type.value,
            "passed": result["passed"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        
        # Check if all challenges for this auth are complete
        if all(c.is_complete for c in auth.challenges):
            if all(c.status == ChallengeStatus.VALID for c in auth.challenges):
                auth.status = "valid"
            else:
                auth.status = "invalid"
        
        return result
    
    def _verify_challenge(self, challenge: Challenge, response: str) -> dict:
        """Verify a challenge response."""
        if challenge.type == ChallengeType.CAPABILITY_PROBE:
            # In production: execute task, evaluate output
            # Here: check response contains the token (proof of engagement)
            passed = challenge.token in response
            return {
                "passed": passed,
                "status": ChallengeStatus.VALID if passed else ChallengeStatus.INVALID,
                "detail": "Token verified in response" if passed else "Token not found in response",
            }
        
        elif challenge.type == ChallengeType.HISTORY_VERIFY:
            # In production: verify append-only log contains historical entries
            # Here: check response contains a hash chain proof
            passed = len(response) > 20 and "hash:" in response.lower()
            return {
                "passed": passed,
                "status": ChallengeStatus.VALID if passed else ChallengeStatus.INVALID,
                "detail": "History proof verified" if passed else "Insufficient history proof",
            }
        
        elif challenge.type == ChallengeType.LIVE_ATTESTATION:
            # In production: real-time challenge-response
            # Here: check response is timely and contains token
            passed = challenge.token in response
            return {
                "passed": passed,
                "status": ChallengeStatus.VALID if passed else ChallengeStatus.INVALID,
                "detail": "Live attestation verified" if passed else "Live attestation failed",
            }
        
        return {"passed": False, "status": ChallengeStatus.INVALID, "error": "Unknown challenge type"}
    
    def finalize_order(self, order_id: str) -> dict:
        """
        Finalize an order — issue credential if all authorizations valid.
        Like ACME finalize: CSR → signed cert.
        """
        order = self.orders.get(order_id)
        if not order:
            return {"error": "Order not found"}
        
        # Check all authorizations
        all_valid = True
        for auth_id in order["authorization_ids"]:
            auth = self.authorizations[auth_id]
            if auth.status != "valid":
                all_valid = False
                break
        
        if not all_valid:
            order["status"] = OrderStatus.INVALID.value
            return {"error": "Not all authorizations valid", "order": order}
        
        # Issue credential
        now = datetime.now(timezone.utc)
        cred_id = f"cred-{secrets.token_hex(8)}"
        
        # Build fingerprint from all challenge results
        challenge_log = []
        for auth_id in order["authorization_ids"]:
            auth = self.authorizations[auth_id]
            for c in auth.challenges:
                if c.validated_at:
                    challenge_log.append(f"{c.type.value}:{c.validated_at}")
        
        cred_data = f"{cred_id}:{order['agent_id']}:{','.join(order['claims'])}:{now.isoformat()}"
        fingerprint = hashlib.sha256(cred_data.encode()).hexdigest()[:16]
        
        credential = TrustCredential(
            id=cred_id,
            agent_id=order["agent_id"],
            claims=order["claims"],
            issued_at=now.isoformat(),
            expires_at=(now + timedelta(hours=self.DEFAULT_TTL_HOURS)).isoformat(),
            issuer_registry=self.registry_id,
            challenge_log=challenge_log,
            fingerprint=fingerprint,
        )
        
        self.credentials[cred_id] = credential
        order["status"] = OrderStatus.VALID.value
        order["credential_id"] = cred_id
        
        return {
            "status": "valid",
            "credential": {
                "id": credential.id,
                "agent": credential.agent_id,
                "claims": credential.claims,
                "issued": credential.issued_at,
                "expires": credential.expires_at,
                "ttl_hours": credential.ttl_hours,
                "fingerprint": credential.fingerprint,
                "challenges_passed": len(credential.challenge_log),
            },
        }
    
    def check_renewal_needed(self, credential_id: str) -> dict:
        """Check if a credential needs renewal (like certbot --renew)."""
        cred = self.credentials.get(credential_id)
        if not cred:
            return {"needs_renewal": True, "reason": "Credential not found"}
        
        if cred.is_expired:
            return {"needs_renewal": True, "reason": "Expired"}
        
        if cred.ttl_hours < self.RENEWAL_WINDOW_HOURS:
            return {"needs_renewal": True, "reason": f"Within renewal window ({cred.ttl_hours:.1f}h remaining)"}
        
        return {"needs_renewal": False, "ttl_hours": cred.ttl_hours}


def run_demo():
    """Demonstrate the full ACME-style trust renewal flow."""
    print("=" * 70)
    print("TRUST-ACME: Automated Trust Renewal (RFC 8555 mapped to ATF)")
    print("=" * 70)
    
    acme = TrustACME(registry_id="registry_alpha")
    
    # Step 1: Agent requests trust renewal
    print("\n1. NEW ORDER — Agent requests trust renewal")
    order = acme.new_order("agent_kit", [
        "verified_web_search",
        "established_research_provider",
    ])
    print(f"   Order: {order['id']}")
    print(f"   Claims: {order['claims']}")
    print(f"   Authorizations: {len(order['authorization_ids'])}")
    
    # Step 2: List challenges
    print("\n2. CHALLENGES — Registry requires proof")
    for auth_id in order["authorization_ids"]:
        auth = acme.authorizations[auth_id]
        print(f"\n   Authorization: {auth.claim}")
        for c in auth.challenges:
            print(f"     Challenge: {c.type.value} (token: {c.token[:8]}...)")
    
    # Step 3: Agent responds to challenges
    print("\n3. RESPOND — Agent completes challenges")
    for auth_id in order["authorization_ids"]:
        auth = acme.authorizations[auth_id]
        for c in auth.challenges:
            if c.type == ChallengeType.CAPABILITY_PROBE:
                response = f"Task completed. Proof: {c.token}"
            elif c.type == ChallengeType.HISTORY_VERIFY:
                response = f"Hash: sha256:abc123... chain verified since 2026-01-15. Token: {c.token}"
            elif c.type == ChallengeType.LIVE_ATTESTATION:
                response = f"Live response at {datetime.now(timezone.utc).isoformat()}. Token: {c.token}"
            else:
                response = ""
            
            result = acme.respond_to_challenge(c.id, response)
            status = "✓" if result["passed"] else "✗"
            print(f"   {status} {c.type.value}: {result['detail']}")
    
    # Step 4: Finalize — get credential
    print("\n4. FINALIZE — Issue short-lived credential")
    result = acme.finalize_order(order["id"])
    
    if result["status"] == "valid":
        cred = result["credential"]
        print(f"   ✓ Credential issued: {cred['id']}")
        print(f"   Agent: {cred['agent']}")
        print(f"   Claims: {cred['claims']}")
        print(f"   TTL: {cred['ttl_hours']:.0f} hours")
        print(f"   Fingerprint: {cred['fingerprint']}")
        print(f"   Challenges passed: {cred['challenges_passed']}")
        
        # Step 5: Check renewal
        print("\n5. RENEWAL CHECK")
        renewal = acme.check_renewal_needed(cred["id"])
        print(f"   Needs renewal: {renewal['needs_renewal']}")
        if not renewal["needs_renewal"]:
            print(f"   TTL remaining: {renewal['ttl_hours']:.0f}h")
    else:
        print(f"   ✗ Order failed: {result.get('error')}")
    
    # Summary
    print(f"\n{'=' * 70}")
    print("ACME → ATF mapping:")
    print("  ACME Account    → Agent DID/identity")
    print("  Certificate     → Short-lived trust credential (72h TTL)")
    print("  HTTP-01         → CAPABILITY_PROBE (prove you can do the thing)")
    print("  DNS-01          → HISTORY_VERIFY (prove temporal existence)")
    print("  TLS-ALPN-01     → LIVE_ATTESTATION (real-time challenge)")
    print("  Cert renewal    → Trust re-earning (decay by default)")
    print("  Let's Encrypt   → Open registry (no CA gatekeepers)")
    print()
    print("Key principle: Trust decays by default. Re-earn, don't revoke.")
    print("Short TTL kills CRL. The absence of renewal IS the revocation signal.")


if __name__ == "__main__":
    run_demo()
