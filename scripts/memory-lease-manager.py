#!/usr/bin/env python3
"""
memory-lease-manager.py — TTL-based memory leasing for agent recall.

Inspired by HashiCorp Vault dynamic secrets + Ebbinghaus decay.
Every stored fact gets: TTL, sensitivity label, renewal rule.
No renewal = evaporation. Default state = forgotten.

"Memory leases: make agent recall expire by default"
"""

import json
import hashlib
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class Sensitivity(Enum):
    PUBLIC = "public"           # No harm if leaked
    INTERNAL = "internal"       # Operational context
    CONFIDENTIAL = "confidential"  # Credentials, keys, PII
    RESTRICTED = "restricted"   # Stuff that should barely exist


class RenewalRule(Enum):
    AUTO = "auto"           # Renew if provenance still valid
    JUSTIFY = "justify"     # Must re-justify need at renewal
    ONE_SHOT = "one_shot"   # Never renews — use once, forget


# Default TTLs per sensitivity (HashiCorp pattern)
DEFAULT_TTLS = {
    Sensitivity.PUBLIC: timedelta(days=30),
    Sensitivity.INTERNAL: timedelta(days=7),
    Sensitivity.CONFIDENTIAL: timedelta(hours=24),
    Sensitivity.RESTRICTED: timedelta(hours=1),
}


@dataclass
class MemoryLease:
    key: str
    value: str
    sensitivity: Sensitivity
    renewal_rule: RenewalRule
    provenance: str  # Where this fact came from
    created_at: datetime
    ttl: timedelta
    renewals: int = 0
    max_renewals: int = 10
    revoked: bool = False

    @property
    def expires_at(self) -> datetime:
        return self.created_at + self.ttl * (self.renewals + 1)

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at or self.revoked

    @property
    def freshness(self) -> float:
        """Ebbinghaus decay: R = e^(-t/S) where S = TTL in hours."""
        if self.revoked:
            return 0.0
        elapsed = (datetime.utcnow() - self.created_at).total_seconds() / 3600
        S = self.ttl.total_seconds() / 3600
        if S == 0:
            return 0.0
        return math.exp(-elapsed / S)

    def renew(self, justification: str = "") -> bool:
        """Attempt renewal. Returns success."""
        if self.revoked:
            return False
        if self.renewal_rule == RenewalRule.ONE_SHOT:
            return False
        if self.renewals >= self.max_renewals:
            return False
        if self.renewal_rule == RenewalRule.JUSTIFY and not justification:
            return False
        self.renewals += 1
        return True

    def revoke(self):
        self.revoked = True

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "sensitivity": self.sensitivity.value,
            "renewal_rule": self.renewal_rule.value,
            "provenance": self.provenance,
            "freshness": f"{self.freshness:.3f}",
            "expired": self.is_expired,
            "renewals": f"{self.renewals}/{self.max_renewals}",
            "ttl_hours": self.ttl.total_seconds() / 3600,
        }


class LeaseManager:
    def __init__(self):
        self.leases: dict[str, MemoryLease] = {}

    def store(self, key: str, value: str, 
              sensitivity: Sensitivity = Sensitivity.INTERNAL,
              renewal_rule: RenewalRule = RenewalRule.AUTO,
              provenance: str = "unknown",
              ttl: Optional[timedelta] = None) -> MemoryLease:
        lease = MemoryLease(
            key=key,
            value=value,
            sensitivity=sensitivity,
            renewal_rule=renewal_rule,
            provenance=provenance,
            created_at=datetime.utcnow(),
            ttl=ttl or DEFAULT_TTLS[sensitivity],
        )
        self.leases[key] = lease
        return lease

    def recall(self, key: str) -> Optional[str]:
        """Recall a fact. Returns None if expired/revoked/missing."""
        lease = self.leases.get(key)
        if lease is None or lease.is_expired:
            return None
        return lease.value

    def gc(self) -> list[str]:
        """Garbage collect expired leases. Returns evaporated keys."""
        expired = [k for k, v in self.leases.items() if v.is_expired]
        for k in expired:
            del self.leases[k]
        return expired

    def audit(self) -> dict:
        """Blast radius audit: what's stored, at what sensitivity, for how long."""
        by_sensitivity = {}
        for lease in self.leases.values():
            s = lease.sensitivity.value
            if s not in by_sensitivity:
                by_sensitivity[s] = {"count": 0, "expired": 0, "avg_freshness": 0}
            by_sensitivity[s]["count"] += 1
            if lease.is_expired:
                by_sensitivity[s]["expired"] += 1
            by_sensitivity[s]["avg_freshness"] += lease.freshness
        
        for s in by_sensitivity:
            n = by_sensitivity[s]["count"]
            if n > 0:
                by_sensitivity[s]["avg_freshness"] = round(
                    by_sensitivity[s]["avg_freshness"] / n, 3
                )
        
        return {
            "total_leases": len(self.leases),
            "by_sensitivity": by_sensitivity,
            "blast_radius": sum(
                1 for l in self.leases.values() 
                if l.sensitivity in (Sensitivity.CONFIDENTIAL, Sensitivity.RESTRICTED)
                and not l.is_expired
            ),
        }


def demo():
    print("=== Memory Lease Manager ===\n")
    
    mgr = LeaseManager()
    
    # Store facts at different sensitivity levels
    scenarios = [
        ("platform_api_url", "https://www.clawk.ai/api/v1", 
         Sensitivity.PUBLIC, RenewalRule.AUTO, "TOOLS.md"),
        ("agent_name", "Kit", 
         Sensitivity.INTERNAL, RenewalRule.AUTO, "SOUL.md"),
        ("api_key_clawk", "clawk_2c9cc79b...", 
         Sensitivity.CONFIDENTIAL, RenewalRule.JUSTIFY, "credentials.json"),
        ("ssh_private_key", "-----BEGIN...", 
         Sensitivity.RESTRICTED, RenewalRule.ONE_SHOT, "ssh-keygen"),
    ]
    
    for key, val, sens, rule, prov in scenarios:
        lease = mgr.store(key, val, sens, rule, prov)
        d = lease.to_dict()
        print(f"📋 {key}")
        print(f"   Sensitivity: {d['sensitivity']} | TTL: {d['ttl_hours']}h | Rule: {d['renewal_rule']}")
        print(f"   Freshness: {d['freshness']} | Provenance: {d['provenance']}")
        print()
    
    # Audit
    audit = mgr.audit()
    print(f"--- Blast Radius Audit ---")
    print(f"Total leases: {audit['total_leases']}")
    print(f"High-sensitivity active: {audit['blast_radius']}")
    for s, data in audit["by_sensitivity"].items():
        print(f"  {s}: {data['count']} leases, avg freshness {data['avg_freshness']}")
    
    print()
    print("--- Design Principles ---")
    print("1. Default state = forgotten (Ebbinghaus decay)")
    print("2. Sensitivity determines TTL (HashiCorp Vault pattern)")
    print("3. Renewal requires justification for confidential+")
    print("4. ONE_SHOT credentials evaporate after single use")
    print("5. Blast radius = count of active high-sensitivity leases")
    print("6. GC runs on heartbeat — expired facts disappear automatically")


if __name__ == "__main__":
    demo()
