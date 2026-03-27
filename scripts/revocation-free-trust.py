#!/usr/bin/env python3
"""
revocation-free-trust.py — Why short TTL beats revocation lists.

Maps the death of OCSP (Let's Encrypt killed it Aug 2025) to ATF trust design.

History (Feisty Duck, Jan 2025 + LE announcement Dec 2024):
- OCSP standardized 1999, never worked at scale
- Browsers implemented soft-fail (pointless: attacker blocks OCSP, proceeds)
- Chrome disabled OCSP entirely in 2012 (v19)
- CAs cached responses for 7 days (replay attacks trivial)
- OCSP leaked which sites you visited to the CA (privacy nightmare)
- LE served 12 BILLION OCSP requests/day. Nobody was checking.
- CA/Browser Forum made OCSP optional Aug 2023, CRL mandatory
- LE killed OCSP May 2025, shut responders Aug 2025
- Solution: short-lived certs (90d → 47d → 6d). No revocation needed.

ATF parallel:
- CRL/OCSP = centralized revocation (issuer controls it) → economic trap
- Short TTL = decentralized expiry (time controls it) → no gatekeepers
- Relying party never needs to ask the issuer → issuer-independent
- ATTEST_TTL decay per hop = self-limiting delegation depth
- "The moment attestation becomes a subscription service, the incentive trap closes" (santaclawd)

Simulation: Compare revocation-based vs TTL-based trust under attack scenarios.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
from enum import Enum


class TrustModel(Enum):
    CRL = "crl"                  # Check revocation list (PKI/CA model)
    OCSP = "ocsp"                # Online status check (real-time query to issuer)
    SHORT_TTL = "short_ttl"      # No revocation — credentials expire quickly
    OCSP_STAPLED = "ocsp_stapled"  # Server-pushed status (OCSP stapling)


@dataclass
class Credential:
    """A trust credential (cert/attestation)."""
    id: str
    issuer: str
    subject: str
    issued_at: datetime
    ttl_hours: float
    revoked: bool = False
    revoked_at: Optional[datetime] = None
    
    @property
    def expires_at(self) -> datetime:
        return self.issued_at + timedelta(hours=self.ttl_hours)
    
    def is_expired(self, at: datetime) -> bool:
        return at >= self.expires_at
    
    def revoke(self, at: datetime):
        self.revoked = True
        self.revoked_at = at


@dataclass 
class AttackWindow:
    """Time window during which a compromised credential can be abused."""
    credential_id: str
    compromise_time: datetime
    detection_time: datetime
    revocation_effective_time: Optional[datetime]  # When relying parties stop accepting
    credential_expiry: datetime
    model: TrustModel
    
    @property
    def exposure_hours(self) -> float:
        """How long the compromised credential remains usable."""
        if self.model == TrustModel.SHORT_TTL:
            # No revocation mechanism — exposure = time until expiry
            end = self.credential_expiry
        elif self.revocation_effective_time:
            # Revocation works — exposure = time until effective revocation
            end = self.revocation_effective_time
        else:
            # Revocation failed (soft-fail) — exposure = time until expiry
            end = self.credential_expiry
        
        return max(0, (end - self.compromise_time).total_seconds() / 3600)


class RevocationFreeSimulator:
    """
    Compare trust models under credential compromise scenarios.
    
    Key insight: OCSP soft-fail means revocation-based models often
    degrade to TTL-based behavior anyway, but with added complexity,
    privacy leakage, and issuer dependency.
    """
    
    # Real-world parameters from LE/Feisty Duck research
    OCSP_CACHE_HOURS = 168      # 7 days (typical CA OCSP response validity)
    CRL_UPDATE_HOURS = 24       # Daily CRL refresh (optimistic)
    OCSP_SOFT_FAIL_RATE = 0.30  # 30% of checks fail silently (conservative)
    DETECTION_DELAY_HOURS = 6   # Average time to detect compromise
    REVOCATION_PROPAGATION_HOURS = 4  # Time for revocation to propagate
    
    # LE certificate TTL trajectory
    TTL_TRAJECTORY = {
        "2020": 2160,   # 90 days
        "2025": 1128,   # 47 days (Apple proposal adopted)
        "2025_short": 144,  # 6 days (LE short-lived)
        "ATF_default": 72,  # 3 days (ATF WRITE-class)
        "ATF_transfer": 48, # 2 days (ATF TRANSFER-class)
    }
    
    def simulate_compromise(
        self,
        model: TrustModel,
        ttl_hours: float,
        soft_fail: bool = False,
    ) -> AttackWindow:
        """Simulate a credential compromise under a given trust model."""
        now = datetime.now(timezone.utc)
        
        # Credential issued some time ago (random point in its lifetime)
        issued_at = now - timedelta(hours=ttl_hours * 0.5)  # Midpoint of validity
        cred = Credential("cred-1", "issuer-1", "subject-1", issued_at, ttl_hours)
        
        # Compromise happens now
        compromise_time = now
        detection_time = now + timedelta(hours=self.DETECTION_DELAY_HOURS)
        
        if model == TrustModel.SHORT_TTL:
            # No revocation mechanism. Credential just expires.
            return AttackWindow(
                credential_id=cred.id,
                compromise_time=compromise_time,
                detection_time=detection_time,
                revocation_effective_time=None,
                credential_expiry=cred.expires_at,
                model=model,
            )
        
        elif model == TrustModel.CRL:
            # CRL updated periodically. Effective revocation = detection + propagation + CRL refresh
            if soft_fail:
                # Client ignores CRL fetch failure — falls back to accepting
                return AttackWindow(
                    credential_id=cred.id,
                    compromise_time=compromise_time,
                    detection_time=detection_time,
                    revocation_effective_time=None,  # Revocation never takes effect
                    credential_expiry=cred.expires_at,
                    model=model,
                )
            effective = detection_time + timedelta(
                hours=self.REVOCATION_PROPAGATION_HOURS + self.CRL_UPDATE_HOURS
            )
            return AttackWindow(
                credential_id=cred.id,
                compromise_time=compromise_time,
                detection_time=detection_time,
                revocation_effective_time=effective,
                credential_expiry=cred.expires_at,
                model=model,
            )
        
        elif model == TrustModel.OCSP:
            if soft_fail:
                # OCSP soft-fail: attacker blocks OCSP, browser proceeds anyway
                # This is why Chrome disabled OCSP in 2012
                return AttackWindow(
                    credential_id=cred.id,
                    compromise_time=compromise_time,
                    detection_time=detection_time,
                    revocation_effective_time=None,
                    credential_expiry=cred.expires_at,
                    model=model,
                )
            # OCSP hard-fail (rare): cached response still valid for days
            effective = detection_time + timedelta(hours=self.OCSP_CACHE_HOURS)
            return AttackWindow(
                credential_id=cred.id,
                compromise_time=compromise_time,
                detection_time=detection_time,
                revocation_effective_time=effective,
                credential_expiry=cred.expires_at,
                model=model,
            )
        
        elif model == TrustModel.OCSP_STAPLED:
            # Server pushes status — but server is compromised, so attacker
            # staples the last valid OCSP response (replay attack)
            effective = detection_time + timedelta(hours=self.OCSP_CACHE_HOURS)
            return AttackWindow(
                credential_id=cred.id,
                compromise_time=compromise_time,
                detection_time=detection_time,
                revocation_effective_time=effective,
                credential_expiry=cred.expires_at,
                model=model,
            )
        
        raise ValueError(f"Unknown model: {model}")
    
    def compare_models(self) -> dict:
        """Compare all trust models across TTL trajectory."""
        results = {}
        
        for era, ttl in self.TTL_TRAJECTORY.items():
            era_results = {}
            
            for model in TrustModel:
                # Normal operation
                window_normal = self.simulate_compromise(model, ttl, soft_fail=False)
                # Under attack (soft-fail)
                window_attack = self.simulate_compromise(model, ttl, soft_fail=True)
                
                era_results[model.value] = {
                    "ttl_hours": ttl,
                    "exposure_normal_hours": round(window_normal.exposure_hours, 1),
                    "exposure_attack_hours": round(window_attack.exposure_hours, 1),
                    "revocation_works": window_normal.revocation_effective_time is not None,
                    "attack_degrades_to_ttl": window_attack.exposure_hours == window_normal.exposure_hours 
                        if model == TrustModel.SHORT_TTL else 
                        window_attack.revocation_effective_time is None,
                }
            
            results[era] = era_results
        
        return results


def run():
    sim = RevocationFreeSimulator()
    results = sim.compare_models()
    
    print("=" * 78)
    print("REVOCATION-FREE TRUST: Why Short TTL Beats Revocation Lists")
    print("Based on: LE OCSP shutdown (2025), Feisty Duck analysis, ATF design")
    print("=" * 78)
    
    for era, models in results.items():
        ttl = list(models.values())[0]["ttl_hours"]
        print(f"\n{'─' * 78}")
        print(f"ERA: {era} (TTL = {ttl}h = {ttl/24:.0f}d)")
        print(f"{'─' * 78}")
        print(f"  {'Model':<20} {'Normal (h)':<14} {'Under Attack (h)':<18} {'Revocation?':<14} {'Attack = TTL?'}")
        
        for model_name, data in models.items():
            print(f"  {model_name:<20} {data['exposure_normal_hours']:<14} {data['exposure_attack_hours']:<18} "
                  f"{'yes' if data['revocation_works'] else 'NO':<14} "
                  f"{'YES ⚠' if data['attack_degrades_to_ttl'] else 'no'}")
    
    # Key insight summary
    print(f"\n{'=' * 78}")
    print("KEY INSIGHTS:")
    print("─" * 78)
    print()
    print("1. OCSP soft-fail = revocation theater. Attacker blocks check, proceeds.")
    print("   Chrome knew this in 2012. Everyone else caught up by 2025.")
    print()
    print("2. Even OCSP hard-fail: cached responses valid 7 days = 7-day replay window.")
    print("   Compromised server staples last-valid response. Game over.")
    print()
    print("3. Short TTL (6d certs, 72h ATF) makes revocation UNNECESSARY:")
    
    # Calculate the crossover point
    atf_ttl = sim.TTL_TRAJECTORY["ATF_default"]
    crl_effective = sim.DETECTION_DELAY_HOURS + sim.REVOCATION_PROPAGATION_HOURS + sim.CRL_UPDATE_HOURS
    print(f"   - ATF WRITE exposure: {atf_ttl/2:.0f}h (half of {atf_ttl}h TTL)")
    print(f"   - CRL effective revocation: {crl_effective:.0f}h (detection + propagation + refresh)")
    print(f"   - When TTL/2 < CRL_effective ({atf_ttl/2:.0f}h < {crl_effective:.0f}h): short TTL WINS")
    print(f"   - Crossover: TTL < {crl_effective * 2}h ({crl_effective * 2 / 24:.1f}d)")
    print()
    print("4. Economic trap (santaclawd): issuer profits from slow revocation.")
    print("   LE served 12B OCSP requests/day. Nobody checking. Pure cost.")
    print("   Short TTL = relying party never asks the issuer. Trap can't close.")
    print()
    print("5. ATTEST_TTL = min(own, attested). Composes transitively.")
    print("   Each delegation hop can only SHORTEN. Self-limiting by construction.")
    print("   5 hops × 0.8 decay = 0.33× original. No revocation needed.")
    print()
    print("6. Privacy: OCSP leaks which sites you visit to the CA.")
    print("   Short TTL: relying party checks expiry LOCALLY. No phone-home.")
    print()
    print('"At the end of the day, with short-lived certificates, we — finally —')
    print(' have a plausible revocation checking story, even if it doesn\'t actually')
    print(' involve any revocation." — Ivan Ristić, Feisty Duck (Jan 2025)')
    

if __name__ == "__main__":
    run()
