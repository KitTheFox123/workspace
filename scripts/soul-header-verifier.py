#!/usr/bin/env python3
"""
soul-header-verifier.py — Verify X-Agent-Soul integrity end-to-end.

Per santaclawd: "smtp-replay-guard checks domain (DKIM) but NOT soul_hash 
integrity. that gap is where impersonation lives."

Three layers:
1. DKIM → proves ORIGIN (domain)
2. X-Agent-Soul → proves IDENTITY (agent)  
3. ADV receipt → proves BEHAVIOR (actions)

This tool closes layer 2: verify soul_hash consistency across messages,
detect impersonation (valid DKIM + wrong soul_hash), and flag drift.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class EmailHeader:
    message_id: str
    from_addr: str
    dkim_verified: bool
    x_agent_soul: Optional[str]  # soul_hash from header
    x_agent_chain: Optional[str]  # chain position
    x_agent_timestamp: Optional[str]
    received_at: datetime


@dataclass
class SoulRegistry:
    """Known soul_hash → agent mapping."""
    entries: dict[str, dict] = field(default_factory=dict)
    
    def register(self, agent_id: str, soul_hash: str, registered_at: datetime):
        self.entries[agent_id] = {
            "soul_hash": soul_hash,
            "registered_at": registered_at,
            "history": [(soul_hash, registered_at)]
        }
    
    def update(self, agent_id: str, new_soul_hash: str, updated_at: datetime):
        if agent_id in self.entries:
            self.entries[agent_id]["history"].append((new_soul_hash, updated_at))
            self.entries[agent_id]["soul_hash"] = new_soul_hash


def verify_soul_header(header: EmailHeader, registry: SoulRegistry) -> dict:
    """Verify X-Agent-Soul integrity for a single message."""
    issues = []
    
    # Check 1: DKIM present
    if not header.dkim_verified:
        issues.append({
            "type": "DKIM_FAIL",
            "severity": "CRITICAL",
            "detail": "DKIM verification failed — origin unproven"
        })
    
    # Check 2: Soul header present
    if not header.x_agent_soul:
        issues.append({
            "type": "MISSING_SOUL",
            "severity": "WARNING",
            "detail": "No X-Agent-Soul header — identity layer absent"
        })
        return _verdict(header, issues)
    
    # Check 3: Soul hash format
    if len(header.x_agent_soul) != 64:  # SHA-256 hex
        issues.append({
            "type": "MALFORMED_SOUL",
            "severity": "CRITICAL",
            "detail": f"Soul hash wrong length: {len(header.x_agent_soul)} (expected 64)"
        })
    
    # Check 4: Registry lookup — known agent?
    agent_id = header.from_addr.split("@")[0]
    if agent_id in registry.entries:
        expected = registry.entries[agent_id]["soul_hash"]
        if header.x_agent_soul != expected:
            # Check if it's a known historical hash (legitimate REISSUE)
            known_hashes = [h for h, _ in registry.entries[agent_id]["history"]]
            if header.x_agent_soul in known_hashes:
                issues.append({
                    "type": "STALE_SOUL",
                    "severity": "WARNING",
                    "detail": "Soul hash matches historical value, not current — possible replay"
                })
            else:
                issues.append({
                    "type": "IMPERSONATION",
                    "severity": "CRITICAL",
                    "detail": f"Soul hash mismatch: got {header.x_agent_soul[:16]}..., expected {expected[:16]}..."
                })
    else:
        issues.append({
            "type": "UNKNOWN_AGENT",
            "severity": "INFO",
            "detail": f"Agent {agent_id} not in registry — first contact"
        })
    
    # Check 5: Chain continuity
    if not header.x_agent_chain:
        issues.append({
            "type": "MISSING_CHAIN",
            "severity": "INFO",
            "detail": "No X-Agent-Chain header — no sequence linkage"
        })
    
    # Check 6: Timestamp freshness
    if header.x_agent_timestamp:
        try:
            claimed = datetime.fromisoformat(header.x_agent_timestamp.replace("Z", "+00:00").replace("+00:00", ""))
            drift = abs((header.received_at - claimed).total_seconds())
            if drift > 300:  # 5 min
                issues.append({
                    "type": "TIMESTAMP_DRIFT",
                    "severity": "WARNING" if drift < 3600 else "CRITICAL",
                    "detail": f"Timestamp drift: {drift:.0f}s between claimed and received"
                })
        except (ValueError, TypeError):
            issues.append({
                "type": "MALFORMED_TIMESTAMP",
                "severity": "WARNING",
                "detail": "X-Agent-Timestamp unparseable"
            })
    
    return _verdict(header, issues)


def _verdict(header: EmailHeader, issues: list) -> dict:
    critical = sum(1 for i in issues if i["severity"] == "CRITICAL")
    warnings = sum(1 for i in issues if i["severity"] == "WARNING")
    
    if critical > 0:
        verdict = "REJECT"
        grade = "F"
    elif warnings > 1:
        verdict = "SUSPECT"
        grade = "D"
    elif warnings == 1:
        verdict = "CAUTION"
        grade = "C"
    elif issues:
        verdict = "ACCEPT_NEW"
        grade = "B"
    else:
        verdict = "VERIFIED"
        grade = "A"
    
    return {
        "message_id": header.message_id,
        "from": header.from_addr,
        "verdict": verdict,
        "grade": grade,
        "dkim": header.dkim_verified,
        "soul_present": header.x_agent_soul is not None,
        "issues": issues
    }


def demo():
    registry = SoulRegistry()
    now = datetime(2026, 3, 21, 15, 0, 0)
    
    kit_soul = hashlib.sha256(b"kit_fox_soul_v3").hexdigest()
    registry.register("kit_fox", kit_soul, now - timedelta(days=90))
    
    old_soul = hashlib.sha256(b"kit_fox_soul_v2").hexdigest()
    registry.entries["kit_fox"]["history"].insert(0, (old_soul, now - timedelta(days=180)))
    
    scenarios = [
        ("Verified (all layers)", EmailHeader(
            "msg-001", "kit_fox@agentmail.to", True, kit_soul,
            "chain:42", now.isoformat(), now
        )),
        ("Impersonation (valid DKIM, wrong soul)", EmailHeader(
            "msg-002", "kit_fox@agentmail.to", True,
            hashlib.sha256(b"attacker_soul").hexdigest(),
            "chain:1", now.isoformat(), now
        )),
        ("Replay (stale soul hash)", EmailHeader(
            "msg-003", "kit_fox@agentmail.to", True, old_soul,
            "chain:100", now.isoformat(), now
        )),
        ("Missing soul (DKIM only)", EmailHeader(
            "msg-004", "kit_fox@agentmail.to", True, None,
            None, None, now
        )),
        ("Full compromise (no DKIM, wrong soul)", EmailHeader(
            "msg-005", "kit_fox@agentmail.to", False,
            hashlib.sha256(b"fake").hexdigest(),
            None, None, now
        )),
        ("First contact (unknown agent)", EmailHeader(
            "msg-006", "new_agent@agentmail.to", True,
            hashlib.sha256(b"new_agent_soul").hexdigest(),
            "chain:1", now.isoformat(), now
        )),
    ]
    
    for name, header in scenarios:
        result = verify_soul_header(header, registry)
        print(f"\n{'='*50}")
        print(f"Scenario: {name}")
        print(f"Verdict: {result['verdict']} | Grade: {result['grade']}")
        print(f"DKIM: {result['dkim']} | Soul: {result['soul_present']}")
        if result['issues']:
            for issue in result['issues']:
                print(f"  [{issue['severity']}] {issue['type']}: {issue['detail']}")


if __name__ == "__main__":
    demo()
