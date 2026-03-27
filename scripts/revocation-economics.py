#!/usr/bin/env python3
"""
revocation-economics.py — Why revocation dies and short-lived wins.

Models the economics that killed OCSP and why ATF attestations use short TTLs.

History (sources: Let's Encrypt Dec 2024, Feisty Duck Jan 2025):
- OCSP standardized 1999, browsers adopted 2006-2011
- Browsers soft-failed → zero security value under active attack
- CAs cached responses for 7 days → replay attacks trivial
- Let's Encrypt: 12 BILLION OCSP requests/day, zero security benefit
- OCSP killed Aug 6, 2025. CRLs back, short-lived certs (6-day) incoming.
- Must-Staple: Firefox supported, Chrome/Safari refused. Dead.

Key insight (santaclawd): CA failure was ECONOMIC, not technical.
CAs profited from slow revocation. Issuers controlled the off-switch.

ATF lesson: attestation = short-lived cert. TTL expiry IS revocation.
No issuer controls the off-switch. Relying party sets WITNESS_POLICY.
"""

import json
from dataclasses import dataclass
from enum import Enum


class RevocationModel(Enum):
    CRL = "crl"              # Certificate Revocation List
    OCSP_HARD = "ocsp_hard"  # OCSP with hard-fail (never deployed at scale)
    OCSP_SOFT = "ocsp_soft"  # OCSP with soft-fail (what browsers actually did)
    SHORT_LIVED = "short_lived"  # Short-lived certs, no revocation needed
    ATF_TTL = "atf_ttl"      # ATF: trust expires by default


@dataclass
class EconomicParams:
    """Economic parameters for revocation infrastructure."""
    daily_requests: int          # Requests to revocation infra per day
    cost_per_million_requests: float  # USD per million requests
    response_cache_hours: int    # How long responses are cached
    revocation_propagation_hours: int  # Time for revocation to propagate
    cert_lifetime_days: int      # Certificate/attestation lifetime
    soft_fail_rate: float        # Fraction of clients that soft-fail (0-1)
    issuer_controls_revocation: bool  # Who holds the kill switch?
    privacy_leak: bool           # Does the check leak user behavior?


def model_params(model: RevocationModel) -> EconomicParams:
    """Real-world parameters per revocation model."""
    params = {
        RevocationModel.CRL: EconomicParams(
            daily_requests=500_000_000,   # CDN-distributed CRL fetches
            cost_per_million_requests=0.05,
            response_cache_hours=24,
            revocation_propagation_hours=24,
            cert_lifetime_days=90,
            soft_fail_rate=0.0,           # CRLs are fetched or not
            issuer_controls_revocation=True,
            privacy_leak=False,           # CRLs are bulk downloads
        ),
        RevocationModel.OCSP_HARD: EconomicParams(
            daily_requests=12_000_000_000,  # LE's actual number
            cost_per_million_requests=0.10,
            response_cache_hours=168,       # 7 days (actual LE cache)
            revocation_propagation_hours=0.25,  # 15 min (post-2024 BRs)
            cert_lifetime_days=90,
            soft_fail_rate=0.0,             # Hard fail = real security
            issuer_controls_revocation=True,
            privacy_leak=True,              # CA sees which sites you visit
        ),
        RevocationModel.OCSP_SOFT: EconomicParams(
            daily_requests=12_000_000_000,
            cost_per_million_requests=0.10,
            response_cache_hours=168,
            revocation_propagation_hours=0.25,
            cert_lifetime_days=90,
            soft_fail_rate=0.95,            # Chrome, Safari soft-fail
            issuer_controls_revocation=True,
            privacy_leak=True,
        ),
        RevocationModel.SHORT_LIVED: EconomicParams(
            daily_requests=0,               # No revocation checks needed
            cost_per_million_requests=0.0,
            response_cache_hours=0,
            revocation_propagation_hours=0,
            cert_lifetime_days=6,           # LE short-lived certs (2025)
            soft_fail_rate=0.0,             # N/A - no checking
            issuer_controls_revocation=False,  # Cert just expires
            privacy_leak=False,
        ),
        RevocationModel.ATF_TTL: EconomicParams(
            daily_requests=0,               # No revocation infra
            cost_per_million_requests=0.0,
            response_cache_hours=0,
            revocation_propagation_hours=0,
            cert_lifetime_days=3,           # 72h TTL (WRITE class)
            soft_fail_rate=0.0,             # Expiry is deterministic
            issuer_controls_revocation=False,  # Relying party decides
            privacy_leak=False,
        ),
    }
    return params[model]


def analyze_model(model: RevocationModel) -> dict:
    """Analyze economics and security of a revocation model."""
    p = model_params(model)
    
    # Cost analysis
    daily_cost = (p.daily_requests / 1_000_000) * p.cost_per_million_requests
    annual_cost = daily_cost * 365
    
    # Security analysis
    # Window of vulnerability = time attacker can use revoked cert
    if p.soft_fail_rate > 0:
        # Soft-fail: attacker just blocks OCSP → infinite window
        effective_vuln_window_hours = p.cert_lifetime_days * 24
    elif p.daily_requests == 0:
        # No revocation needed: window = remaining cert lifetime
        effective_vuln_window_hours = p.cert_lifetime_days * 24 / 2  # Average
    else:
        effective_vuln_window_hours = max(
            p.revocation_propagation_hours,
            p.response_cache_hours
        )
    
    # Privacy cost (OCSP reveals browsing to CA)
    privacy_exposure_daily = p.daily_requests if p.privacy_leak else 0
    
    # Issuer dependency score
    issuer_risk = 1.0 if p.issuer_controls_revocation else 0.0
    
    # Composite security score (higher = better)
    # Short vuln window, no soft-fail, no issuer dependency, no privacy leak
    max_vuln = 90 * 24  # Worst case: full 90-day cert lifetime
    vuln_score = 1.0 - (effective_vuln_window_hours / max_vuln)
    security_score = (
        vuln_score * 0.35 +
        (1.0 - p.soft_fail_rate) * 0.25 +
        (1.0 - issuer_risk) * 0.20 +
        (0.0 if p.privacy_leak else 1.0) * 0.20
    )
    
    return {
        "model": model.value,
        "economics": {
            "daily_requests": f"{p.daily_requests:,}",
            "daily_cost_usd": round(daily_cost, 2),
            "annual_cost_usd": round(annual_cost, 2),
        },
        "security": {
            "cert_lifetime_days": p.cert_lifetime_days,
            "vuln_window_hours": round(effective_vuln_window_hours, 1),
            "soft_fail_rate": p.soft_fail_rate,
            "issuer_controls_revocation": p.issuer_controls_revocation,
            "privacy_leak": p.privacy_leak,
            "composite_score": round(security_score, 4),
        },
    }


def run_analysis():
    """Compare all revocation models."""
    print("=" * 70)
    print("REVOCATION ECONOMICS: WHY OCSP DIED AND SHORT-LIVED WINS")
    print("Sources: Let's Encrypt (Dec 2024), Feisty Duck (Jan 2025)")
    print("=" * 70)
    
    models = [
        RevocationModel.CRL,
        RevocationModel.OCSP_HARD,
        RevocationModel.OCSP_SOFT,
        RevocationModel.SHORT_LIVED,
        RevocationModel.ATF_TTL,
    ]
    
    results = []
    for m in models:
        r = analyze_model(m)
        results.append(r)
        
        print(f"\n{'─' * 50}")
        print(f"Model: {r['model'].upper()}")
        print(f"  Cost: ${r['economics']['annual_cost_usd']:,.0f}/yr ({r['economics']['daily_requests']} req/day)")
        print(f"  Vuln window: {r['security']['vuln_window_hours']}h", end="")
        if r['security']['soft_fail_rate'] > 0:
            print(f" (EFFECTIVE: {r['security']['cert_lifetime_days']*24}h — soft-fail negates all)")
        else:
            print()
        print(f"  Soft-fail rate: {r['security']['soft_fail_rate']:.0%}")
        print(f"  Issuer controls off-switch: {r['security']['issuer_controls_revocation']}")
        print(f"  Privacy leak: {r['security']['privacy_leak']}")
        print(f"  Security score: {r['security']['composite_score']:.2f}")
    
    # Rankings
    ranked = sorted(results, key=lambda r: r['security']['composite_score'], reverse=True)
    
    print(f"\n{'=' * 70}")
    print("RANKINGS (by security score):")
    for i, r in enumerate(ranked, 1):
        cost = r['economics']['annual_cost_usd']
        print(f"  {i}. {r['model'].upper():15s} score={r['security']['composite_score']:.2f}  cost=${cost:>12,.0f}/yr")
    
    print(f"\n{'=' * 70}")
    print("LESSONS:")
    print("1. OCSP soft-fail = zero security. $438M/yr (at scale) for nothing.")
    print("2. Short-lived certs eliminate revocation entirely. $0 infra cost.")
    print("3. Issuer-controlled revocation creates economic capture.")
    print("4. ATF TTL: trust expires by default. No off-switch to capture.")
    print("5. Privacy: OCSP leaked 12B browsing events/day to CAs.")
    print(f"\nLE killed OCSP Aug 2025. ATF should never build it.")
    
    return results


if __name__ == "__main__":
    run_analysis()
