#!/usr/bin/env python3
"""agent-clm.py — Agent Certificate Lifecycle Management.

CLM for agent scope certificates, inspired by ANSSI ACME guidelines 
and CA/B Forum 47-day cert timeline. Manages fleet-level lifecycle:
discovery, monitoring, renewal automation, policy enforcement.

Lesson from PKI: ACME (protocol) alone is insufficient. CLM (management 
layer) prevents outages from shortened cert lifetimes.

Usage:
    python3 agent-clm.py --demo
    python3 agent-clm.py --issue AGENT_ID --ttl-hours 4 --scope "read,write"
    python3 agent-clm.py --fleet-status
"""

import argparse
import json
import hashlib
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import List, Optional


@dataclass
class ScopeCert:
    """Short-lived scope certificate for an agent."""
    cert_id: str
    agent_id: str
    principal_id: str
    scope_lines: List[str]
    scope_hash: str
    issued_at: str
    expires_at: str
    ttl_hours: float
    renewal_count: int = 0
    status: str = "active"  # active, expired, revoked, pending_renewal


@dataclass 
class FleetStatus:
    """Fleet-level certificate health."""
    total_agents: int
    active_certs: int
    expired_certs: int
    pending_renewal: int
    revoked_certs: int
    avg_ttl_hours: float
    min_ttl_remaining_hours: float
    policy_violations: List[str]
    health_grade: str


class AgentCLM:
    """Certificate Lifecycle Manager for agent scope certs."""
    
    def __init__(self, max_ttl_hours: float = 24.0, 
                 renewal_window_pct: float = 0.33,
                 min_ttl_hours: float = 0.5):
        self.certs: List[ScopeCert] = []
        self.max_ttl_hours = max_ttl_hours
        self.renewal_window_pct = renewal_window_pct
        self.min_ttl_hours = min_ttl_hours
        self.policy_violations: List[str] = []
    
    def issue_cert(self, agent_id: str, principal_id: str, 
                   scope_lines: List[str], ttl_hours: float) -> ScopeCert:
        """Issue a new scope certificate."""
        # Policy enforcement
        if ttl_hours > self.max_ttl_hours:
            self.policy_violations.append(
                f"TTL {ttl_hours}h exceeds max {self.max_ttl_hours}h for {agent_id}")
            ttl_hours = self.max_ttl_hours
        if ttl_hours < self.min_ttl_hours:
            self.policy_violations.append(
                f"TTL {ttl_hours}h below min {self.min_ttl_hours}h for {agent_id}")
            ttl_hours = self.min_ttl_hours
        
        now = datetime.now(timezone.utc)
        scope_hash = hashlib.sha256(
            "\n".join(sorted(scope_lines)).encode()
        ).hexdigest()[:16]
        
        cert = ScopeCert(
            cert_id=hashlib.sha256(
                f"{agent_id}:{scope_hash}:{now.isoformat()}".encode()
            ).hexdigest()[:12],
            agent_id=agent_id,
            principal_id=principal_id,
            scope_lines=scope_lines,
            scope_hash=scope_hash,
            issued_at=now.isoformat(),
            expires_at=(now + timedelta(hours=ttl_hours)).isoformat(),
            ttl_hours=ttl_hours,
        )
        
        # Expire previous certs for this agent
        for c in self.certs:
            if c.agent_id == agent_id and c.status == "active":
                c.status = "expired"
        
        self.certs.append(cert)
        return cert
    
    def check_renewal(self) -> List[ScopeCert]:
        """Find certs needing renewal (within renewal window)."""
        now = datetime.now(timezone.utc)
        needs_renewal = []
        for cert in self.certs:
            if cert.status != "active":
                continue
            expires = datetime.fromisoformat(cert.expires_at)
            remaining = (expires - now).total_seconds() / 3600
            threshold = cert.ttl_hours * self.renewal_window_pct
            if remaining <= threshold:
                cert.status = "pending_renewal"
                needs_renewal.append(cert)
        return needs_renewal
    
    def renew_cert(self, cert: ScopeCert) -> ScopeCert:
        """Renew by issuing fresh cert with same scope."""
        new_cert = self.issue_cert(
            cert.agent_id, cert.principal_id,
            cert.scope_lines, cert.ttl_hours
        )
        new_cert.renewal_count = cert.renewal_count + 1
        return new_cert
    
    def fleet_status(self) -> FleetStatus:
        """Get fleet-wide health status."""
        now = datetime.now(timezone.utc)
        agents = set(c.agent_id for c in self.certs)
        active = [c for c in self.certs if c.status == "active"]
        expired = [c for c in self.certs if c.status == "expired"]
        pending = [c for c in self.certs if c.status == "pending_renewal"]
        revoked = [c for c in self.certs if c.status == "revoked"]
        
        avg_ttl = sum(c.ttl_hours for c in active) / max(len(active), 1)
        
        min_remaining = float('inf')
        for c in active:
            expires = datetime.fromisoformat(c.expires_at)
            remaining = (expires - now).total_seconds() / 3600
            min_remaining = min(min_remaining, remaining)
        if min_remaining == float('inf'):
            min_remaining = 0.0
        
        # Grade
        if len(expired) == 0 and len(self.policy_violations) == 0:
            grade = "A"
        elif len(expired) <= 1:
            grade = "B"
        elif len(expired) <= 3:
            grade = "C"
        else:
            grade = "F"
        
        return FleetStatus(
            total_agents=len(agents),
            active_certs=len(active),
            expired_certs=len(expired),
            pending_renewal=len(pending),
            revoked_certs=len(revoked),
            avg_ttl_hours=round(avg_ttl, 2),
            min_ttl_remaining_hours=round(min_remaining, 2),
            policy_violations=self.policy_violations[:],
            health_grade=grade,
        )


def demo():
    """Run fleet management demo."""
    clm = AgentCLM(max_ttl_hours=8.0, min_ttl_hours=0.5)
    
    print("=" * 60)
    print("AGENT CERTIFICATE LIFECYCLE MANAGEMENT")
    print("Inspired by ANSSI ACME + CA/B Forum 47-day timeline")
    print("=" * 60)
    print()
    
    # Issue certs for fleet
    agents = [
        ("kit_fox", "ilya", ["read_files", "write_memory", "web_search", "post_social"], 4.0),
        ("gendolf", "gendolf_principal", ["read_files", "validate_schema", "git_push"], 6.0),
        ("santaclawd", "santa_principal", ["read_files", "email_send", "web_search"], 4.0),
        ("rogue_agent", "unknown", ["read_files", "exec_commands", "network_access"], 48.0),  # violates policy
    ]
    
    print("--- ISSUING SCOPE CERTS ---")
    for agent_id, principal, scope, ttl in agents:
        cert = clm.issue_cert(agent_id, principal, scope, ttl)
        print(f"  [{cert.status.upper()}] {cert.agent_id}: TTL={cert.ttl_hours}h, scope={cert.scope_hash}")
    print()
    
    # Check policy violations
    if clm.policy_violations:
        print("--- POLICY VIOLATIONS ---")
        for v in clm.policy_violations:
            print(f"  ⚠️  {v}")
        print()
    
    # Simulate time passing — expire kit's cert
    kit_cert = [c for c in clm.certs if c.agent_id == "kit_fox" and c.status == "active"][0]
    kit_cert.expires_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    
    # Check renewals
    needs_renewal = clm.check_renewal()
    if needs_renewal:
        print("--- PENDING RENEWAL ---")
        for cert in needs_renewal:
            print(f"  🔄 {cert.agent_id}: cert {cert.cert_id} entering renewal window")
            new_cert = clm.renew_cert(cert)
            print(f"     → renewed: {new_cert.cert_id} (renewal #{new_cert.renewal_count})")
        print()
    
    # Fleet status
    status = clm.fleet_status()
    print("--- FLEET STATUS ---")
    print(f"  Grade: {status.health_grade}")
    print(f"  Total agents: {status.total_agents}")
    print(f"  Active certs: {status.active_certs}")
    print(f"  Expired: {status.expired_certs}")
    print(f"  Pending renewal: {status.pending_renewal}")
    print(f"  Avg TTL: {status.avg_ttl_hours}h")
    print(f"  Min remaining: {status.min_ttl_remaining_hours}h")
    print(f"  Policy violations: {len(status.policy_violations)}")
    print()
    
    print("--- KEY INSIGHT ---")
    print("ACME (heartbeat re-attestation) handles individual cert renewal.")
    print("CLM (fleet monitoring) handles: discovery, policy, renewal windows.")
    print("Short TTL without CLM = outage factory. ANSSI learned this for PKI.")
    print("Same lesson applies to agent scope management at scale.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent Certificate Lifecycle Management")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        clm = AgentCLM()
        print(json.dumps(asdict(clm.fleet_status()), indent=2))
    else:
        demo()
