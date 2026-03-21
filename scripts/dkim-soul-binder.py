#!/usr/bin/env python3
"""
dkim-soul-binder.py — Bind X-Agent-Soul to DKIM domain signatures.

Per santaclawd: "DKIM proves ORIGIN, X-Agent-Soul proves IDENTITY, 
ADV receipts prove BEHAVIOR. Three separate claims, three attestation layers.
But does smtp-replay-guard verify X-Agent-Soul integrity end-to-end?"

Gap: DKIM signs headers but doesn't mandate X-Agent-Soul inclusion.
Fix: Verify X-Agent-Soul is in DKIM signed header list. If not, 
the soul_hash is unauthenticated — anyone could inject it.

Three verification layers:
1. DKIM validity (domain proves origin)  
2. X-Agent-Soul in signed headers (domain vouches for agent identity)
3. Soul hash consistency (soul_hash matches known agent)
"""

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Optional
from enum import Enum


class BindingStatus(Enum):
    BOUND = "BOUND"           # DKIM signs X-Agent-Soul — full binding
    UNSIGNED = "UNSIGNED"     # X-Agent-Soul present but NOT in DKIM signed headers
    MISSING = "MISSING"       # No X-Agent-Soul header at all
    DKIM_FAIL = "DKIM_FAIL"   # DKIM verification failed
    MISMATCH = "MISMATCH"     # Soul hash doesn't match known agent


@dataclass
class DKIMSignature:
    domain: str
    selector: str
    signed_headers: list[str]
    valid: bool


@dataclass
class EmailHeaders:
    dkim_signature: Optional[DKIMSignature]
    x_agent_soul: Optional[str]
    x_agent_chain: Optional[str]
    x_agent_receipt: Optional[str]
    x_agent_timestamp: Optional[str]
    from_addr: str


def verify_soul_binding(headers: EmailHeaders, known_agents: dict[str, str] = None) -> dict:
    """
    Verify that X-Agent-Soul is cryptographically bound to the sending domain.
    
    Returns binding status + detailed analysis.
    """
    result = {
        "from": headers.from_addr,
        "layers": {},
        "status": None,
        "severity": None,
        "detail": None
    }
    
    # Layer 1: DKIM validity
    if not headers.dkim_signature:
        result["layers"]["dkim"] = {"status": "MISSING", "detail": "No DKIM signature"}
        result["status"] = BindingStatus.DKIM_FAIL.value
        result["severity"] = "CRITICAL"
        result["detail"] = "No DKIM signature — origin unverifiable"
        return result
    
    if not headers.dkim_signature.valid:
        result["layers"]["dkim"] = {"status": "INVALID", "detail": "DKIM verification failed"}
        result["status"] = BindingStatus.DKIM_FAIL.value
        result["severity"] = "CRITICAL"
        result["detail"] = "DKIM invalid — message may be tampered"
        return result
    
    result["layers"]["dkim"] = {
        "status": "VALID",
        "domain": headers.dkim_signature.domain,
        "selector": headers.dkim_signature.selector
    }
    
    # Layer 2: X-Agent-Soul in signed headers
    if not headers.x_agent_soul:
        result["layers"]["soul_binding"] = {"status": "MISSING", "detail": "No X-Agent-Soul header"}
        result["status"] = BindingStatus.MISSING.value
        result["severity"] = "WARNING"
        result["detail"] = "X-Agent-Soul absent — domain authenticated, agent identity not"
        return result
    
    signed_lower = [h.lower() for h in headers.dkim_signature.signed_headers]
    soul_signed = "x-agent-soul" in signed_lower
    
    if not soul_signed:
        result["layers"]["soul_binding"] = {
            "status": "UNSIGNED",
            "detail": "X-Agent-Soul present but NOT in DKIM signed headers",
            "signed_headers": headers.dkim_signature.signed_headers,
            "vulnerability": "Anyone with MTA access can inject/modify X-Agent-Soul"
        }
        result["status"] = BindingStatus.UNSIGNED.value
        result["severity"] = "HIGH"
        result["detail"] = "X-Agent-Soul NOT signed by DKIM — impersonation vector open"
        return result
    
    result["layers"]["soul_binding"] = {
        "status": "BOUND",
        "soul_hash": headers.x_agent_soul,
        "detail": "X-Agent-Soul included in DKIM signed headers"
    }
    
    # Layer 3: Soul hash consistency (if known agents provided)
    if known_agents:
        domain = headers.dkim_signature.domain
        expected = known_agents.get(domain)
        if expected and expected != headers.x_agent_soul:
            result["layers"]["consistency"] = {
                "status": "MISMATCH",
                "expected": expected,
                "received": headers.x_agent_soul,
                "detail": f"Soul hash changed for {domain}"
            }
            result["status"] = BindingStatus.MISMATCH.value
            result["severity"] = "CRITICAL"
            result["detail"] = f"Soul hash mismatch for {domain} — possible takeover"
            return result
        elif expected:
            result["layers"]["consistency"] = {"status": "MATCH", "detail": "Soul hash matches known agent"}
    
    # Also check other agent headers
    extra_signed = []
    for h in ["x-agent-chain", "x-agent-receipt", "x-agent-timestamp"]:
        if h in signed_lower:
            extra_signed.append(h)
    
    result["layers"]["additional_headers"] = {
        "signed": extra_signed,
        "unsigned": [h for h in ["x-agent-chain", "x-agent-receipt", "x-agent-timestamp"] 
                     if h not in signed_lower and getattr(headers, h.replace("-", "_").replace("x_", "x_"), None)]
    }
    
    result["status"] = BindingStatus.BOUND.value
    result["severity"] = "OK"
    result["detail"] = f"Full binding: {headers.dkim_signature.domain} → {headers.x_agent_soul[:16]}..."
    
    return result


def demo():
    known = {"agentmail.to": "0ecf9dec"}
    
    scenarios = [
        ("fully_bound", EmailHeaders(
            dkim_signature=DKIMSignature("agentmail.to", "s1", 
                ["From", "To", "Subject", "X-Agent-Soul", "X-Agent-Chain", "X-Agent-Receipt"], True),
            x_agent_soul="0ecf9dec",
            x_agent_chain="abc123",
            x_agent_receipt="receipt_001",
            x_agent_timestamp="2026-03-21T15:00:00Z",
            from_addr="kit_fox@agentmail.to"
        )),
        ("soul_unsigned", EmailHeaders(
            dkim_signature=DKIMSignature("agentmail.to", "s1",
                ["From", "To", "Subject"], True),  # X-Agent-Soul NOT signed!
            x_agent_soul="0ecf9dec",
            x_agent_chain="abc123",
            x_agent_receipt=None,
            x_agent_timestamp=None,
            from_addr="kit_fox@agentmail.to"
        )),
        ("no_soul", EmailHeaders(
            dkim_signature=DKIMSignature("agentmail.to", "s1",
                ["From", "To", "Subject"], True),
            x_agent_soul=None,
            x_agent_chain=None,
            x_agent_receipt=None,
            x_agent_timestamp=None,
            from_addr="kit_fox@agentmail.to"
        )),
        ("soul_mismatch", EmailHeaders(
            dkim_signature=DKIMSignature("agentmail.to", "s1",
                ["From", "To", "Subject", "X-Agent-Soul"], True),
            x_agent_soul="DEADBEEF",  # wrong soul!
            x_agent_chain=None,
            x_agent_receipt=None,
            x_agent_timestamp=None,
            from_addr="kit_fox@agentmail.to"
        )),
    ]
    
    for name, headers in scenarios:
        result = verify_soul_binding(headers, known)
        print(f"\n{'='*50}")
        print(f"Scenario: {name}")
        print(f"Status: {result['status']} | Severity: {result['severity']}")
        print(f"Detail: {result['detail']}")
        for layer, info in result['layers'].items():
            print(f"  {layer}: {info.get('status', 'N/A')} — {info.get('detail', '')}")


if __name__ == "__main__":
    demo()
