#!/usr/bin/env python3
"""
dkim-ceremony-mapper.py — Maps DKIM key rotation practices to ATF ceremony design.

santaclawd's 5am insight: "every ATF V1.2 design decision has a 1990s email RFC that solved it first."

DKIM key rotation (M3AAWG 2019, Valimail 2025) → ATF ceremony key rotation:
- DKIM selector = ceremony key identifier
- DNS propagation delay = trust propagation delay  
- Key overlap period = ceremony overlap (overlap-transition-engine.py)
- 2048-bit minimum (2025) = ceremony key strength floor
- Ed25519 gaining traction = lightweight ceremony signatures

Email solved these problems:
- Receipt = Read receipt (RFC 3798)
- Bridge = MX fallback
- Ceremony = DKIM key rotation
- Rejection receipt = SMTP 550
- Valley-free = SPF alignment chain
- ASPA = DMARC policy declaration ("these are my authorized senders")

Sources:
- M3AAWG DKIM Key Rotation Best Common Practices (March 2019)
- Valimail "How to set up and rotate your DKIM keys in 2025"
- RFC 6376: DKIM Signatures
- RFC 3798: Message Disposition Notification (read receipts)
- RFC 7489: DMARC
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone, timedelta
from typing import Optional


class KeyStrength(Enum):
    """Key strength tiers — maps DKIM evolution to ATF."""
    RSA_1024 = "rsa_1024"     # Legacy, deprecated 2023+
    RSA_2048 = "rsa_2048"     # Current minimum (Valimail 2025)
    RSA_4096 = "rsa_4096"     # Testing phase
    ED25519 = "ed25519"       # Gaining traction — shorter but equivalent


class CeremonyPhase(Enum):
    """DKIM rotation phases mapped to ATF ceremony."""
    GENERATE = "generate"         # Create new key pair
    PUBLISH = "publish"           # Publish new public key (DNS for DKIM, registry for ATF)
    PROPAGATE = "propagate"       # Wait for propagation (DNS TTL / trust gossip)
    OVERLAP = "overlap"           # Both keys active (sign with new, verify with both)
    SIGN_NEW = "sign_new"         # Switch signing to new key
    REVOKE_OLD = "revoke_old"     # Remove old key from DNS/registry
    COMPLETE = "complete"


@dataclass
class DKIMRotation:
    """DKIM key rotation event — the email RFC that ATF ceremonies mirror."""
    selector: str              # DKIM selector (e.g., "s1", "s2")
    domain: str
    key_strength: KeyStrength
    rotation_interval_days: int  # M3AAWG: quarterly minimum
    propagation_ttl_hours: int   # DNS TTL for propagation
    overlap_hours: int           # Both keys valid simultaneously
    
    def ceremony_parallel(self) -> dict:
        """Map DKIM rotation to ATF ceremony parameters."""
        return {
            "selector": f"ceremony_key_{self.selector}",
            "registry": self.domain,
            "key_floor": self.key_strength.value,
            "rotation_interval": f"{self.rotation_interval_days}d",
            "propagation_window": f"{self.propagation_ttl_hours}h",
            "overlap_window": f"{self.overlap_hours}h",
            "dkim_parallel": {
                "selector": "DKIM selector = ceremony key identifier",
                "dns_propagation": "DNS TTL = trust gossip propagation delay",
                "overlap": "Both keys valid = overlap-transition-engine PRE_PUBLISH phase",
                "revocation": "Remove old DNS record = ceremony key REVOKED state",
            },
        }


@dataclass
class EmailRFCMapping:
    """Maps email RFCs to ATF design decisions."""
    rfc: str
    title: str
    year: int
    atf_parallel: str
    mechanism: str
    
    def describe(self) -> str:
        return f"RFC {self.rfc} ({self.year}): {self.title}\n  → ATF: {self.atf_parallel}\n  Mechanism: {self.mechanism}"


# The complete mapping santaclawd described
EMAIL_RFC_MAPPINGS = [
    EmailRFCMapping(
        "3798", "Message Disposition Notification", 2004,
        "receipt = read receipt",
        "Sender requests notification that recipient received/read message. "
        "ATF receipt = cryptographic proof of trust transaction delivery."
    ),
    EmailRFCMapping(
        "6376", "DKIM Signatures", 2011,
        "ceremony key = DKIM signing key",
        "Domain signs outgoing mail with private key, publishes public key in DNS. "
        "ATF ceremony = registry signs endorsements with ceremony key."
    ),
    EmailRFCMapping(
        "7489", "DMARC", 2015,
        "ASPA = DMARC policy declaration",
        "Domain publishes policy: 'these are my authorized senders' (SPF+DKIM alignment). "
        "ASPA = 'these are my authorized trust providers.' Same structure: declare relationships, verify paths."
    ),
    EmailRFCMapping(
        "5321", "SMTP", 1982,
        "bridge = MX fallback routing",
        "MX records define where to deliver mail, with priority fallback. "
        "ATF bridge = cross-registry trust routing with fallback paths."
    ),
    EmailRFCMapping(
        "3463", "Enhanced Status Codes", 2003,
        "rejection receipt = SMTP 550 + enhanced status code",
        "SMTP returns structured rejection: 550 5.1.1 'user unknown'. "
        "ATF rejection receipt = structured reason code for trust denial."
    ),
    EmailRFCMapping(
        "6962", "CT (not email but same era)", 2013,
        "CT log = append-only endorsement log",
        "Public append-only log of issued certificates. "
        "ATF provenance log = append-only hash-chained action record."
    ),
    EmailRFCMapping(
        "8617", "ARC (Authenticated Received Chain)", 2019,
        "trust chain across intermediaries",
        "Preserves authentication results across mail forwarding hops. "
        "ATF bridge attestation = preserves trust provenance across registry boundaries."
    ),
    EmailRFCMapping(
        "8460", "SMTP TLS Reporting", 2018,
        "observable-state-emitter = TLS failure reports",
        "Domains publish policy to receive TLS connection failure reports. "
        "ATF TRUST_STATE_CHANGED events = observable failure reporting."
    ),
]


class DKIMCeremonyMapper:
    """
    Maps DKIM key rotation lifecycle to ATF ceremony lifecycle.
    
    Key insight: email solved identity + verification + receipts since 1971.
    ATF is reinventing email infrastructure for agent trust.
    The mapping isn't metaphorical — it's structural.
    """
    
    def __init__(self):
        self.rotation_log: list[dict] = []
    
    def simulate_rotation(self, rotation: DKIMRotation) -> list[dict]:
        """Simulate a DKIM key rotation mapped to ATF ceremony phases."""
        phases = []
        now = datetime.now(timezone.utc)
        
        # Phase 1: Generate new key
        phases.append({
            "phase": CeremonyPhase.GENERATE.value,
            "dkim": f"Generate new {rotation.key_strength.value} key pair",
            "atf": f"Generate new ceremony key (strength floor: {rotation.key_strength.value})",
            "timestamp": now.isoformat(),
            "duration": "instant",
        })
        
        # Phase 2: Publish new key (don't sign with it yet)
        publish_time = now + timedelta(hours=1)
        phases.append({
            "phase": CeremonyPhase.PUBLISH.value,
            "dkim": f"Publish new public key as DNS TXT record (selector: {rotation.selector}2)",
            "atf": "Publish new ceremony key to registry (PRE_PUBLISH state)",
            "timestamp": publish_time.isoformat(),
            "duration": "instant",
            "parallel": "overlap-transition-engine.py PRE_PUBLISH phase",
        })
        
        # Phase 3: Wait for propagation
        propagate_time = publish_time + timedelta(hours=rotation.propagation_ttl_hours)
        phases.append({
            "phase": CeremonyPhase.PROPAGATE.value,
            "dkim": f"Wait {rotation.propagation_ttl_hours}h for DNS propagation (TTL expiry)",
            "atf": f"Wait for trust gossip propagation ({rotation.propagation_ttl_hours}h window)",
            "timestamp": propagate_time.isoformat(),
            "duration": f"{rotation.propagation_ttl_hours}h",
            "parallel": "BGP: wait for route propagation before switching",
            "risk": "Premature switch = some verifiers reject new key (DNS cache / trust cache)",
        })
        
        # Phase 4: Overlap — both keys valid
        overlap_start = propagate_time
        overlap_end = overlap_start + timedelta(hours=rotation.overlap_hours)
        phases.append({
            "phase": CeremonyPhase.OVERLAP.value,
            "dkim": f"Both selectors active for {rotation.overlap_hours}h. Sign with new, verify with both.",
            "atf": f"DOUBLE_SIGN phase: both ceremony keys valid for {rotation.overlap_hours}h",
            "timestamp": overlap_start.isoformat(),
            "duration": f"{rotation.overlap_hours}h",
            "parallel": "overlap-transition-engine.py DOUBLE_SIGN phase",
            "critical": "This is where DKIM rotation fails in practice — too short = bounced mail, too long = key compromise window",
        })
        
        # Phase 5: Switch signing to new key
        sign_time = overlap_end
        phases.append({
            "phase": CeremonyPhase.SIGN_NEW.value,
            "dkim": "All new emails signed with new key only",
            "atf": "All new endorsements use new ceremony key only",
            "timestamp": sign_time.isoformat(),
            "duration": "instant",
        })
        
        # Phase 6: Revoke old key
        revoke_time = sign_time + timedelta(hours=24)  # Grace period
        phases.append({
            "phase": CeremonyPhase.REVOKE_OLD.value,
            "dkim": f"Remove old selector from DNS. Old signatures still verify against cached keys for TTL.",
            "atf": "Old ceremony key → REVOKED state. Prior receipts valid per CAdES-A time-of-signing.",
            "timestamp": revoke_time.isoformat(),
            "duration": "permanent",
            "parallel": "receipt-archaeology.py: old receipts valid at signing time regardless of later revocation",
        })
        
        # Phase 7: Complete
        phases.append({
            "phase": CeremonyPhase.COMPLETE.value,
            "dkim": f"Rotation complete. Next rotation in {rotation.rotation_interval_days} days.",
            "atf": f"Ceremony complete. Next ceremony per ceremony-scheduler.py ({rotation.rotation_interval_days}d interval).",
            "timestamp": (revoke_time + timedelta(hours=1)).isoformat(),
            "duration": "instant",
        })
        
        self.rotation_log.append({
            "rotation": rotation.ceremony_parallel(),
            "phases": phases,
        })
        
        return phases
    
    def validate_rotation_interval(self, rotation: DKIMRotation) -> dict:
        """
        Validate rotation interval against M3AAWG best practices.
        
        M3AAWG (2019): Rotate at least quarterly.
        Valimail (2025): Monthly for high-volume senders.
        ATF: ceremony-scheduler.py risk-tiered intervals.
        """
        assessment = {
            "interval_days": rotation.rotation_interval_days,
            "key_strength": rotation.key_strength.value,
        }
        
        if rotation.rotation_interval_days <= 30:
            assessment["rating"] = "EXCELLENT"
            assessment["m3aawg"] = "Exceeds M3AAWG quarterly minimum"
            assessment["atf_tier"] = "HIGH risk tier (30d operational key)"
        elif rotation.rotation_interval_days <= 90:
            assessment["rating"] = "GOOD"
            assessment["m3aawg"] = "Meets M3AAWG quarterly recommendation"
            assessment["atf_tier"] = "MEDIUM risk tier (90d operational key)"
        elif rotation.rotation_interval_days <= 365:
            assessment["rating"] = "ACCEPTABLE"
            assessment["m3aawg"] = "Below M3AAWG recommendation but common"
            assessment["atf_tier"] = "LOW risk tier (365d operational key)"
        else:
            assessment["rating"] = "DANGEROUS"
            assessment["m3aawg"] = "Exceeds any recommended interval — PGP failure mode"
            assessment["atf_tier"] = "EXPIRED — triggers ceremony-scheduler grace period"
        
        # Key strength check
        if rotation.key_strength == KeyStrength.RSA_1024:
            assessment["key_warning"] = "DEPRECATED: 1024-bit RSA insufficient since 2023"
        elif rotation.key_strength == KeyStrength.ED25519:
            assessment["key_note"] = "Ed25519: shorter keys, equivalent security, faster verification"
        
        return assessment


def run_scenarios():
    """Demonstrate DKIM-to-ATF ceremony mapping."""
    mapper = DKIMCeremonyMapper()
    
    print("=" * 70)
    print("DKIM KEY ROTATION → ATF CEREMONY MAPPING")
    print("=" * 70)
    
    # Print RFC mappings
    print("\n📧 EMAIL RFC → ATF DESIGN DECISION MAPPINGS")
    print("-" * 70)
    for mapping in EMAIL_RFC_MAPPINGS:
        print(f"\n{mapping.describe()}")
    
    print(f"\n{'=' * 70}")
    print("🔄 DKIM KEY ROTATION LIFECYCLE → ATF CEREMONY LIFECYCLE")
    print("-" * 70)
    
    # Scenario 1: Standard quarterly rotation (M3AAWG recommended)
    rotation = DKIMRotation(
        selector="s1",
        domain="registry-alpha.trust",
        key_strength=KeyStrength.RSA_2048,
        rotation_interval_days=90,
        propagation_ttl_hours=24,
        overlap_hours=48,
    )
    
    phases = mapper.simulate_rotation(rotation)
    print(f"\nScenario: Quarterly rotation ({rotation.key_strength.value})")
    for p in phases:
        print(f"\n  [{p['phase'].upper()}]")
        print(f"    DKIM: {p['dkim']}")
        print(f"    ATF:  {p['atf']}")
        if 'parallel' in p:
            print(f"    Parallel: {p['parallel']}")
        if 'critical' in p:
            print(f"    ⚠️  {p['critical']}")
    
    # Validate rotation intervals
    print(f"\n{'=' * 70}")
    print("📊 ROTATION INTERVAL VALIDATION (M3AAWG + ATF)")
    print("-" * 70)
    
    test_intervals = [
        DKIMRotation("s1", "high-freq.trust", KeyStrength.ED25519, 30, 4, 24),
        DKIMRotation("s2", "standard.trust", KeyStrength.RSA_2048, 90, 24, 48),
        DKIMRotation("s3", "lazy.trust", KeyStrength.RSA_2048, 365, 48, 72),
        DKIMRotation("s4", "pgp-failure.trust", KeyStrength.RSA_1024, 730, 24, 24),
    ]
    
    for rot in test_intervals:
        assessment = mapper.validate_rotation_interval(rot)
        print(f"\n  {rot.domain}: {assessment['interval_days']}d / {assessment['key_strength']}")
        print(f"    Rating: {assessment['rating']}")
        print(f"    M3AAWG: {assessment['m3aawg']}")
        print(f"    ATF tier: {assessment['atf_tier']}")
        if 'key_warning' in assessment:
            print(f"    ⚠️  {assessment['key_warning']}")
        if 'key_note' in assessment:
            print(f"    📝 {assessment['key_note']}")
    
    print(f"\n{'=' * 70}")
    print("KEY INSIGHT")
    print("-" * 70)
    print("""
  Email solved agent trust problems 50 years ago:
  - Identity: DKIM (2011) = cryptographic domain signing
  - Policy: DMARC (2015) = "these are my authorized senders" (= ASPA)
  - Receipts: MDN/RFC 3798 = delivery confirmation
  - Chain preservation: ARC/RFC 8617 = trust across intermediaries
  - Failure reporting: SMTP-TLS/RFC 8460 = observable state events
  - Rejection: SMTP 550 + enhanced codes = structured rejection receipts
  
  ATF is email infrastructure wearing a trust framework costume.
  SMTP survived 55 years because it encodes RELATIONSHIPS, not protocols.
  The lesson: ship primitives, let composition happen.
    """)
    
    return True


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
