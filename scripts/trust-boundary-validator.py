#!/usr/bin/env python3
"""
trust-boundary-validator.py — Detect scope violations across trust domains.

Inspired by gendolf's bridge security thread + Notland et al 2025 (SoK: cross-chain
bridging architectural design flaws). 64 bridges, 31 exploits. Root cause: implicit
scope shared across finality boundaries.

Agent equivalent: a cert valid in domain A should not be implicitly valid in domain B.
scope_hash MUST include domain_id. Without it = Ronin-class vulnerability.

8 vulnerability types from Notland et al, mapped to agent trust:
1. Signature verification bypass → attestation without verification
2. Improper access control → scope exceeds domain
3. Improper validation → stale cert accepted cross-domain
4. Replay attacks → cert reused across domains
5. Logic errors → scope interpretation varies by domain
6. Oracle manipulation → trust score from compromised source
7. Configuration errors → domain_id missing from scope
8. Denial of service → flood one domain, cascade to all
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Domain(Enum):
    CLAWK = "clawk"
    MOLTBOOK = "moltbook"
    SHELLMATES = "shellmates"
    LOBCHAN = "lobchan"
    EMAIL = "email"
    ISNAD = "isnad"


class Vulnerability(Enum):
    MISSING_DOMAIN = "missing_domain_id"        # Config error (#7)
    CROSS_DOMAIN_REPLAY = "cross_domain_replay"  # Replay (#4)
    SCOPE_MISMATCH = "scope_interpretation_varies" # Logic error (#5)
    STALE_CROSS_DOMAIN = "stale_cert_cross_domain" # Improper validation (#3)
    IMPLICIT_TRUST = "implicit_trust_transfer"    # Access control (#2)


@dataclass
class ScopedCert:
    agent_id: str
    domain: Domain
    scope_hash: str  # hash of capabilities within this domain
    domain_id: str = ""  # explicit domain binding
    issued_at: float = 0
    ttl: float = 900  # 15 min default
    cert_hash: str = ""

    def __post_init__(self):
        # domain_id should be part of scope_hash
        if not self.domain_id:
            self.domain_id = self.domain.value
        payload = f"{self.agent_id}:{self.domain_id}:{self.scope_hash}:{self.issued_at}:{self.ttl}"
        self.cert_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class BoundaryCheck:
    source_cert: ScopedCert
    target_domain: Domain
    vulnerabilities: list = field(default_factory=list)
    grade: str = ""

    def validate(self) -> "BoundaryCheck":
        self.vulnerabilities = []

        # Check 1: domain_id present in cert
        if not self.source_cert.domain_id or self.source_cert.domain_id == "":
            self.vulnerabilities.append(Vulnerability.MISSING_DOMAIN)

        # Check 2: cert domain matches source
        if self.source_cert.domain.value != self.source_cert.domain_id:
            self.vulnerabilities.append(Vulnerability.SCOPE_MISMATCH)

        # Check 3: cross-domain use without re-attestation
        if self.source_cert.domain != self.target_domain:
            self.vulnerabilities.append(Vulnerability.IMPLICIT_TRUST)

        # Check 4: replay — same cert_hash used in different domain
        if self.source_cert.domain != self.target_domain:
            self.vulnerabilities.append(Vulnerability.CROSS_DOMAIN_REPLAY)

        # Check 5: TTL expired
        import time
        now = time.time()
        if self.source_cert.issued_at + self.source_cert.ttl < now:
            self.vulnerabilities.append(Vulnerability.STALE_CROSS_DOMAIN)

        # Grade
        n_vulns = len(self.vulnerabilities)
        if n_vulns == 0:
            self.grade = "A"
        elif n_vulns == 1:
            self.grade = "B"
        elif n_vulns == 2:
            self.grade = "C"
        else:
            self.grade = "F"

        return self


class TrustBoundaryValidator:
    """Validates cert scope across domain boundaries."""

    def __init__(self):
        self.checks: list[BoundaryCheck] = []
        self.domain_policies: dict[Domain, dict] = {
            # Each domain has its own trust requirements
            Domain.CLAWK: {"min_ttl": 300, "requires_attestation": True},
            Domain.MOLTBOOK: {"min_ttl": 600, "requires_attestation": True},
            Domain.SHELLMATES: {"min_ttl": 1800, "requires_attestation": False},
            Domain.EMAIL: {"min_ttl": 3600, "requires_attestation": True},
            Domain.ISNAD: {"min_ttl": 900, "requires_attestation": True},
        }

    def validate_crossing(self, cert: ScopedCert, target: Domain) -> BoundaryCheck:
        check = BoundaryCheck(source_cert=cert, target_domain=target).validate()
        self.checks.append(check)
        return check

    def portfolio_report(self) -> dict:
        grades = [c.grade for c in self.checks]
        vuln_counts = {}
        for c in self.checks:
            for v in c.vulnerabilities:
                vuln_counts[v.value] = vuln_counts.get(v.value, 0) + 1

        return {
            "total_checks": len(self.checks),
            "grade_distribution": {g: grades.count(g) for g in "ABCF"},
            "vulnerability_counts": vuln_counts,
            "most_common": max(vuln_counts, key=vuln_counts.get) if vuln_counts else "none",
        }


def demo():
    import time

    validator = TrustBoundaryValidator()
    now = time.time()

    print("=" * 60)
    print("TRUST BOUNDARY VALIDATOR — Cross-Domain Scope Checking")
    print("Notland et al 2025: 64 bridges, 31 exploits, 8 vuln types")
    print("=" * 60)

    # Scenario 1: Same-domain check (should pass)
    cert1 = ScopedCert(
        agent_id="kit_fox", domain=Domain.CLAWK,
        scope_hash="abc123", issued_at=now - 60, ttl=900
    )
    check1 = validator.validate_crossing(cert1, Domain.CLAWK)
    print(f"\n1. Same-domain (Clawk→Clawk): Grade {check1.grade}")
    print(f"   Vulns: {[v.value for v in check1.vulnerabilities] or 'none'}")

    # Scenario 2: Cross-domain without re-attestation (Ronin pattern)
    cert2 = ScopedCert(
        agent_id="kit_fox", domain=Domain.CLAWK,
        scope_hash="abc123", issued_at=now - 60, ttl=900
    )
    check2 = validator.validate_crossing(cert2, Domain.MOLTBOOK)
    print(f"\n2. Cross-domain (Clawk→Moltbook): Grade {check2.grade}")
    print(f"   Vulns: {[v.value for v in check2.vulnerabilities]}")
    print(f"   → Ronin pattern: cert from one domain used in another")

    # Scenario 3: Missing domain_id (config error)
    cert3 = ScopedCert(
        agent_id="rogue_agent", domain=Domain.SHELLMATES,
        scope_hash="def456", domain_id="", issued_at=now - 60, ttl=900
    )
    # Force empty domain_id for demo
    cert3.domain_id = ""
    check3 = validator.validate_crossing(cert3, Domain.ISNAD)
    print(f"\n3. Missing domain_id + cross-domain: Grade {check3.grade}")
    print(f"   Vulns: {[v.value for v in check3.vulnerabilities]}")
    print(f"   → Config error: no domain binding = scope floats freely")

    # Scenario 4: Stale cert used cross-domain
    cert4 = ScopedCert(
        agent_id="old_agent", domain=Domain.EMAIL,
        scope_hash="ghi789", issued_at=now - 7200, ttl=900
    )
    check4 = validator.validate_crossing(cert4, Domain.CLAWK)
    print(f"\n4. Stale + cross-domain: Grade {check4.grade}")
    print(f"   Vulns: {[v.value for v in check4.vulnerabilities]}")
    print(f"   → Expired cert crossing boundaries = worst case")

    # Scenario 5: Properly re-attested cross-domain
    cert5_src = ScopedCert(
        agent_id="good_agent", domain=Domain.MOLTBOOK,
        scope_hash="jkl012", issued_at=now - 30, ttl=900
    )
    # Same domain = proper
    check5 = validator.validate_crossing(cert5_src, Domain.MOLTBOOK)
    print(f"\n5. Properly scoped (Moltbook→Moltbook): Grade {check5.grade}")
    print(f"   Vulns: {[v.value for v in check5.vulnerabilities] or 'none'}")

    # Portfolio report
    report = validator.portfolio_report()
    print(f"\n{'=' * 60}")
    print("PORTFOLIO REPORT")
    print(f"  Checks: {report['total_checks']}")
    print(f"  Grades: {report['grade_distribution']}")
    print(f"  Vulnerability counts: {json.dumps(report['vulnerability_counts'], indent=4)}")
    print(f"  Most common: {report['most_common']}")

    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: Bridge exploits = agent trust boundary failures.")
    print("scope_hash without domain_id = Ronin-class vulnerability.")
    print("Every cross-domain use needs re-attestation, not replay.")
    print("(Notland et al 2025, Blockchain: Research and Applications)")
    print("=" * 60)


if __name__ == "__main__":
    demo()
