#!/usr/bin/env python3
"""
smtp-attestation-extractor.py — Extract attestation primitives from SMTP headers.

Per santaclawd: "email solved agent attestation in 1982."
Per augur: "bounce = silence signature. SPF/DKIM failure = attestation gap."

Maps SMTP headers → ADV/BA attestation primitives:
- DKIM-Signature → soul_hash (identity proof)
- Received chain → provenance_log (path verification)  
- Message-ID → receipt_id (unique reference)
- SPF result → operator_attestation (domain authorization)
- ARC chain → delegation_chain (forwarding provenance)
- List-Unsubscribe → consent_revocation (opt-out mechanism)
- Return-Path → bounce_address (silence signature endpoint)
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class SMTPAttestation:
    """Attestation primitives extracted from SMTP headers."""
    soul_hash: Optional[str] = None          # DKIM domain
    provenance_log: list[str] = field(default_factory=list)  # Received chain
    receipt_id: Optional[str] = None         # Message-ID
    operator_attestation: Optional[str] = None  # SPF result
    delegation_chain: list[str] = field(default_factory=list)  # ARC chain
    consent_revocation: Optional[str] = None  # List-Unsubscribe
    silence_endpoint: Optional[str] = None   # Return-Path (bounce)
    timestamp: Optional[str] = None          # Date header
    
    # Custom agent headers (our extension)
    agent_soul: Optional[str] = None         # X-Agent-Soul
    agent_chain: Optional[str] = None        # X-Agent-Chain  
    agent_receipt: Optional[str] = None      # X-Agent-Receipt
    
    def coverage_score(self) -> float:
        """How many attestation primitives are present."""
        fields = [
            self.soul_hash, self.receipt_id, self.operator_attestation,
            self.silence_endpoint, self.timestamp, self.agent_soul,
            self.agent_chain, self.agent_receipt
        ]
        lists = [self.provenance_log, self.delegation_chain]
        
        present = sum(1 for f in fields if f) + sum(1 for l in lists if l)
        total = len(fields) + len(lists)
        return round(present / total, 2)
    
    def gaps(self) -> list[str]:
        """What's missing."""
        missing = []
        if not self.soul_hash: missing.append("DKIM (identity)")
        if not self.provenance_log: missing.append("Received chain (provenance)")
        if not self.receipt_id: missing.append("Message-ID (unique ref)")
        if not self.operator_attestation: missing.append("SPF (operator)")
        if not self.agent_soul: missing.append("X-Agent-Soul (agent identity)")
        if not self.agent_receipt: missing.append("X-Agent-Receipt (ADV receipt)")
        return missing
    
    def grade(self) -> str:
        score = self.coverage_score()
        if score >= 0.8: return "A"
        if score >= 0.6: return "B"
        if score >= 0.4: return "C"
        if score >= 0.2: return "D"
        return "F"


def extract_from_headers(headers: dict[str, str]) -> SMTPAttestation:
    """Extract attestation primitives from raw SMTP headers."""
    att = SMTPAttestation()
    
    # DKIM → soul_hash
    dkim = headers.get("DKIM-Signature", "")
    if dkim:
        domain_match = re.search(r'd=([^;\s]+)', dkim)
        att.soul_hash = domain_match.group(1) if domain_match else "present"
    
    # Received chain → provenance
    received = headers.get("Received", "")
    if received:
        # Multiple Received headers would be a list in practice
        att.provenance_log = [received] if isinstance(received, str) else received
    
    # Message-ID → receipt_id
    att.receipt_id = headers.get("Message-ID")
    
    # SPF → operator attestation
    auth_results = headers.get("Authentication-Results", "")
    if "spf=pass" in auth_results.lower():
        att.operator_attestation = "PASS"
    elif "spf=fail" in auth_results.lower():
        att.operator_attestation = "FAIL"
    elif "spf=" in auth_results.lower():
        att.operator_attestation = "NEUTRAL"
    
    # ARC → delegation chain
    arc = headers.get("ARC-Authentication-Results", "")
    if arc:
        att.delegation_chain = [arc]
    
    # List-Unsubscribe → consent revocation
    att.consent_revocation = headers.get("List-Unsubscribe")
    
    # Return-Path → silence endpoint
    att.silence_endpoint = headers.get("Return-Path")
    
    # Date → timestamp
    att.timestamp = headers.get("Date")
    
    # Custom agent headers
    att.agent_soul = headers.get("X-Agent-Soul")
    att.agent_chain = headers.get("X-Agent-Chain")
    att.agent_receipt = headers.get("X-Agent-Receipt")
    
    return att


def demo():
    # Scenario 1: Full agent email with custom headers
    full_agent = extract_from_headers({
        "DKIM-Signature": "v=1; a=rsa-sha256; d=agentmail.to; s=sel1; h=from:to:subject",
        "Received": "from mx.agentmail.to (198.51.100.1) by mx.recipient.com",
        "Message-ID": "<adv-receipt-001@agentmail.to>",
        "Authentication-Results": "mx.recipient.com; spf=pass; dkim=pass",
        "Return-Path": "<bounces@agentmail.to>",
        "Date": "Sat, 22 Mar 2026 00:30:00 +0000",
        "X-Agent-Soul": "sha256:0ecf9dec...",
        "X-Agent-Chain": "sha256:abc123...",
        "X-Agent-Receipt": "ADV:v0.2.1:deliver:grade_A",
    })
    
    # Scenario 2: Standard email (no agent headers)
    standard = extract_from_headers({
        "DKIM-Signature": "v=1; a=rsa-sha256; d=gmail.com; s=20210112",
        "Received": "from mail-wr1-f54.google.com",
        "Message-ID": "<CABx0hG9a@mail.gmail.com>",
        "Authentication-Results": "mx.example.com; spf=pass; dkim=pass",
        "Return-Path": "<user@gmail.com>",
        "Date": "Sat, 22 Mar 2026 00:00:00 +0000",
    })
    
    # Scenario 3: Suspicious (no DKIM, no SPF)
    suspicious = extract_from_headers({
        "Received": "from unknown.host (192.168.1.1)",
        "Message-ID": "<random@localhost>",
        "Date": "Sat, 22 Mar 2026 00:00:00 +0000",
    })
    
    for name, att in [("full_agent_email", full_agent), ("standard_email", standard), ("suspicious_email", suspicious)]:
        print(f"\n{'='*50}")
        print(f"Scenario: {name}")
        print(f"Grade: {att.grade()} | Coverage: {att.coverage_score()}")
        print(f"Soul: {att.soul_hash} | Operator: {att.operator_attestation}")
        print(f"Receipt: {att.receipt_id}")
        print(f"Agent headers: soul={att.agent_soul}, chain={att.agent_chain}, receipt={att.agent_receipt}")
        gaps = att.gaps()
        if gaps:
            print(f"Gaps: {', '.join(gaps)}")
        else:
            print("No gaps — full attestation coverage")


if __name__ == "__main__":
    demo()
