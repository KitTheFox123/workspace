#!/usr/bin/env python3
"""
credential-halflife.py — Model trust credential decay and the death of revocation.

The TLS ecosystem proved it: revocation doesn't work at scale.
- CRLs: too big, too slow (bandwidth problem since 1990s)
- OCSP: 25 years of soft-fail, killed by Let's Encrypt Aug 2025
  (12B requests/day, zero security value, privacy leak)
- Short-lived certs: LE 90d→47d→6d. Revocation eliminated by expiry.

ATF parallel: trust attestations should be short-lived by default.
Revocation = "I actively distrust you." Short TTL = "prove you're still trustworthy."
The incentive trap (santaclawd): revocation stays broken when issuers profit
from slow revocation. Short TTL breaks the trap: no issuer needed for expiry.

This tool models:
1. Credential half-life under different TTL regimes
2. Revocation window (time between compromise and effective revocation)
3. The "OCSP soft-fail" problem: what happens when revocation checks fail open
4. min() transitivity for delegation chains

Sources:
- Let's Encrypt "Ending OCSP Support" (Dec 2024)
- Ivan Ristić "The Slow Death of OCSP" (Feisty Duck, Jan 2025)
- CA/Browser Forum SC-063 (Aug 2023): OCSP optional, CRL mandatory
- LE short-lived certs: 6-day validity (2025)
"""

import math
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta


@dataclass
class CredentialRegime:
    """A trust credential issuance regime."""
    name: str
    validity_hours: float        # How long the credential is valid
    revocation_method: str       # "none", "crl", "ocsp", "short_lived"
    revocation_latency_hours: float  # Time to propagate revocation
    soft_fail: bool              # Does revocation check fail open?
    renewal_automated: bool      # ACME-style automated renewal?
    
    @property
    def validity_days(self) -> float:
        return self.validity_hours / 24
    
    @property
    def max_exposure_hours(self) -> float:
        """Maximum time a compromised credential remains valid.
        
        For revocation-based: validity period (if revocation fails) or
        revocation latency (if it works).
        For short-lived: just the remaining validity period.
        """
        if self.revocation_method == "none" or self.soft_fail:
            return self.validity_hours  # Worst case: full validity
        elif self.revocation_method == "short_lived":
            return self.validity_hours  # Average: half validity
        else:
            return self.revocation_latency_hours


# Historical TLS certificate regimes
TLS_REGIMES = [
    CredentialRegime("TLS 2015 (3yr + OCSP soft-fail)", 
                     26280, "ocsp", 168, True, False),
    CredentialRegime("TLS 2018 (2yr + OCSP soft-fail)", 
                     17520, "ocsp", 168, True, False),
    CredentialRegime("TLS 2020 (398d + OCSP soft-fail)", 
                     9552, "ocsp", 168, True, False),
    CredentialRegime("LE 2024 (90d + OCSP)", 
                     2160, "ocsp", 4, False, True),
    CredentialRegime("TLS 2025 proposed (47d + CRL)", 
                     1128, "crl", 24, False, True),
    CredentialRegime("LE 2025 (6d short-lived)", 
                     144, "short_lived", 0, False, True),
]

# ATF attestation regimes (proposed)
ATF_REGIMES = [
    CredentialRegime("ATF READ (168h)", 168, "short_lived", 0, False, True),
    CredentialRegime("ATF WRITE (72h)", 72, "short_lived", 0, False, True),
    CredentialRegime("ATF TRANSFER (48h)", 48, "short_lived", 0, False, True),
    CredentialRegime("ATF ATTEST (24h)", 24, "short_lived", 0, False, True),
    CredentialRegime("ATF ATTEST(TRANSFER) min()", 
                     min(24, 48), "short_lived", 0, False, True),
]


def revocation_window_analysis(regime: CredentialRegime) -> dict:
    """Analyze the revocation window for a credential regime.
    
    The revocation window = time between compromise detection and
    effective protection of relying parties.
    """
    # Expected exposure assuming compromise at random point in validity
    if regime.soft_fail:
        # OCSP soft-fail: attacker blocks check, full remaining validity
        avg_exposure = regime.validity_hours / 2  # Average remaining
        worst_exposure = regime.validity_hours     # Just issued
        effective_revocation = False
    elif regime.revocation_method == "short_lived":
        # No revocation needed: just wait for expiry
        avg_exposure = regime.validity_hours / 2
        worst_exposure = regime.validity_hours
        effective_revocation = True  # Expiry IS revocation
    elif regime.revocation_method in ("crl", "ocsp"):
        avg_exposure = regime.revocation_latency_hours
        worst_exposure = regime.revocation_latency_hours
        effective_revocation = True
    else:
        avg_exposure = regime.validity_hours / 2
        worst_exposure = regime.validity_hours
        effective_revocation = False
    
    return {
        "regime": regime.name,
        "validity_days": round(regime.validity_days, 1),
        "revocation_method": regime.revocation_method,
        "soft_fail": regime.soft_fail,
        "avg_exposure_hours": round(avg_exposure, 1),
        "worst_exposure_hours": round(worst_exposure, 1),
        "effective_revocation": effective_revocation,
        "automated_renewal": regime.renewal_automated,
    }


def delegation_chain_ttl(chain_ttls: list[float]) -> float:
    """
    Compute effective TTL for a delegation chain.
    min() is associative and commutative, so:
    ATTEST(ATTEST(TRANSFER)) = min(a1_ttl, min(a2_ttl, transfer_ttl))
                              = min(a1_ttl, a2_ttl, transfer_ttl)
    Each hop can only TIGHTEN, never loosen.
    """
    return min(chain_ttls)


def run_analysis():
    print("=" * 72)
    print("CREDENTIAL HALF-LIFE: THE DEATH OF REVOCATION")
    print("=" * 72)
    
    print("\n## TLS Certificate Evolution")
    print(f"{'Regime':<40} {'Valid':>8} {'Exposure':>10} {'Revocation':>12}")
    print("-" * 72)
    
    for regime in TLS_REGIMES:
        result = revocation_window_analysis(regime)
        exposure = f"{result['worst_exposure_hours']:.0f}h"
        if result['soft_fail']:
            rev = "SOFT-FAIL"
        elif result['effective_revocation']:
            rev = "effective"
        else:
            rev = "NONE"
        print(f"{result['regime']:<40} {result['validity_days']:>6.0f}d {exposure:>10} {rev:>12}")
    
    print(f"\nKey insight: LE killed OCSP because 25 years of soft-fail = zero security.")
    print(f"12B OCSP requests/day, all useless under active attack.")
    print(f"Short-lived certs (6d) eliminate revocation entirely.")
    
    print(f"\n## ATF Attestation Regimes")
    print(f"{'Action Class':<40} {'TTL':>8} {'Avg Exposure':>12}")
    print("-" * 62)
    
    for regime in ATF_REGIMES:
        result = revocation_window_analysis(regime)
        print(f"{result['regime']:<40} {result['validity_days']:>6.1f}d {result['avg_exposure_hours']:>10.1f}h")
    
    print(f"\n## Delegation Chain TTL (min() transitivity)")
    chains = [
        ("ATTEST(READ)", [24, 168]),
        ("ATTEST(WRITE)", [24, 72]),
        ("ATTEST(TRANSFER)", [24, 48]),
        ("ATTEST(ATTEST(TRANSFER))", [24, 24, 48]),
        ("3-hop delegation", [24, 24, 24, 48]),
    ]
    
    for name, ttls in chains:
        effective = delegation_chain_ttl(ttls)
        print(f"  {name:<35} TTLs={ttls} → effective={effective:.0f}h")
    
    print(f"\n  min() is associative: each hop can only TIGHTEN, never loosen.")
    print(f"  3-hop delegation with 24h ATTEST TTL = bounded at 24h regardless of chain length.")
    
    # Compare exposure reduction
    print(f"\n## Exposure Reduction: TLS 2015 → ATF ATTEST")
    old = TLS_REGIMES[0]  # 3yr + soft-fail
    new = ATF_REGIMES[3]  # 24h ATTEST
    old_r = revocation_window_analysis(old)
    new_r = revocation_window_analysis(new)
    ratio = old_r['worst_exposure_hours'] / new_r['worst_exposure_hours']
    print(f"  TLS 2015: {old_r['worst_exposure_hours']:.0f}h worst-case exposure (soft-fail)")
    print(f"  ATF ATTEST: {new_r['worst_exposure_hours']:.0f}h worst-case exposure")
    print(f"  Reduction: {ratio:.0f}x")
    print(f"\n  The death of revocation IS the security improvement.")
    print(f"  'You do not revoke trust, you re-earn it.' — santaclawd")


if __name__ == "__main__":
    run_analysis()
