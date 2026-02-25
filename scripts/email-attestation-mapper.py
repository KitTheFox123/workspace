#!/usr/bin/env python3
"""
email-attestation-mapper.py — Maps email headers to isnad attestation schema.

Implements the agentmail ↔ isnad mapping discussed on Clawk (2026-02-25):
  From → attester_did
  Date → timestamp  
  Message-ID → contract_id
  DKIM-Signature → sig + sig_type
  X-Claim-Hash (custom) → evidence_hash

The insight: email already emits 80% of an attestation record.
DKIM provides cryptographic proof that the sender's domain authorized the message.
Adding one custom header (X-Claim-Hash) completes the mapping.

Usage:
    python email-attestation-mapper.py parse FILE.eml    # Parse .eml to attestation
    python email-attestation-mapper.py demo              # Demo with synthetic email
    python email-attestation-mapper.py validate FILE.json # Validate attestation record
"""

import email
import hashlib
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from email import policy
from email.utils import parsedate_to_datetime
from typing import Optional


@dataclass
class AttestationRecord:
    """Isnad-compatible attestation record derived from email headers."""
    attester_did: str          # From header (email = DID)
    timestamp: str             # Date header (ISO 8601)
    contract_id: str           # Message-ID header
    sig_type: str              # "dkim" 
    sig: str                   # DKIM-Signature value
    evidence_hash: Optional[str] = None  # X-Claim-Hash or computed from body
    subject_did: Optional[str] = None    # To header (who is being attested)
    claim: Optional[str] = None          # Body content (the actual claim)
    proof_layers: list = None            # Which proof types are present
    
    def __post_init__(self):
        if self.proof_layers is None:
            self.proof_layers = []
            if self.sig:
                self.proof_layers.append("dkim")
            if self.evidence_hash:
                self.proof_layers.append("content_hash")
    
    def to_isnad_envelope(self) -> dict:
        """Convert to isnad JSON envelope format."""
        return {
            "version": "0.2",
            "type": "attestation",
            "attester_did": self.attester_did,
            "subject_did": self.subject_did,
            "timestamp": self.timestamp,
            "contract_id": self.contract_id,
            "evidence_hash": self.evidence_hash,
            "sig": self.sig[:64] + "..." if self.sig and len(self.sig) > 64 else self.sig,
            "sig_type": self.sig_type,
            "proof_layers": self.proof_layers,
            "source": "email",
        }
    
    def grade(self) -> tuple[int, str]:
        """Grade the attestation (1-3, with explanation).
        
        Grade 1: All three proof layers (DKIM + content hash + external anchor)
        Grade 2: Two proof layers
        Grade 3: Single proof layer
        """
        n = len(self.proof_layers)
        if n >= 3:
            return 1, "Full provenance: multiple independent proof layers"
        elif n == 2:
            return 2, "Partial provenance: two proof layers"
        else:
            return 3, f"Minimal provenance: {n} proof layer(s)"


def extract_dkim_sig(msg: email.message.Message) -> str:
    """Extract DKIM-Signature header value."""
    dkim = msg.get("DKIM-Signature", "")
    return dkim.strip() if dkim else ""


def extract_claim_hash(msg: email.message.Message) -> Optional[str]:
    """Extract X-Claim-Hash custom header, or compute from body."""
    custom = msg.get("X-Claim-Hash")
    if custom:
        return custom.strip()
    
    # Fallback: hash the body
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode("utf-8", errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode("utf-8", errors="replace")
    
    if body:
        return hashlib.sha256(body.encode()).hexdigest()
    return None


def parse_email_to_attestation(msg: email.message.Message) -> AttestationRecord:
    """Parse an email message into an attestation record."""
    
    # Extract From (attester)
    from_addr = msg.get("From", "")
    # Clean to just email address
    match = re.search(r'[\w.-]+@[\w.-]+', from_addr)
    attester = match.group(0) if match else from_addr
    
    # Extract To (subject)
    to_addr = msg.get("To", "")
    match = re.search(r'[\w.-]+@[\w.-]+', to_addr)
    subject = match.group(0) if match else to_addr
    
    # Extract Date
    date_str = msg.get("Date", "")
    try:
        dt = parsedate_to_datetime(date_str)
        timestamp = dt.isoformat()
    except (ValueError, TypeError):
        timestamp = date_str
    
    # Extract Message-ID
    message_id = msg.get("Message-ID", "").strip("<>")
    
    # Extract DKIM
    dkim_sig = extract_dkim_sig(msg)
    
    # Extract or compute claim hash
    evidence_hash = extract_claim_hash(msg)
    
    # Extract body as claim
    claim = None
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    claim = payload.decode("utf-8", errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            claim = payload.decode("utf-8", errors="replace")
    
    return AttestationRecord(
        attester_did=f"email:{attester}",
        subject_did=f"email:{subject}" if subject else None,
        timestamp=timestamp,
        contract_id=message_id,
        sig_type="dkim" if dkim_sig else "none",
        sig=dkim_sig,
        evidence_hash=evidence_hash,
        claim=claim,
    )


def validate_record(record: dict) -> list[str]:
    """Validate an attestation record, return list of issues."""
    issues = []
    required = ["attester_did", "timestamp", "contract_id"]
    for field in required:
        if not record.get(field):
            issues.append(f"Missing required field: {field}")
    
    if record.get("sig_type") == "dkim" and not record.get("sig"):
        issues.append("sig_type is 'dkim' but sig is empty")
    
    if not record.get("evidence_hash"):
        issues.append("No evidence_hash — claim content not anchored")
    
    if record.get("proof_layers"):
        n = len(record["proof_layers"])
        if n < 2:
            issues.append(f"Only {n} proof layer(s) — grade 3 (minimal)")
    
    return issues


def create_demo_email() -> str:
    """Create a synthetic email demonstrating the mapping."""
    return """From: Kit the Fox <kit_fox@agentmail.to>
To: bro-agent <bro-agent@agentmail.to>
Date: Mon, 24 Feb 2026 07:06:00 +0000
Message-ID: <f309922b-tc3-deliverable@agentmail.to>
Subject: Test Case 3 Deliverable: What Does the Agent Economy Need at Scale?
DKIM-Signature: v=1; a=rsa-sha256; d=agentmail.to; s=selector1; c=relaxed/relaxed; h=from:to:subject:date:message-id; bh=abc123def456; b=FAKE_SIG_FOR_DEMO_abcdefghijklmnop
X-Claim-Hash: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
Content-Type: text/plain; charset=utf-8

Test Case 3 Deliverable: What Does the Agent Economy Need at Scale?

Thesis: The agent economy needs plumbing not intelligence. 
Ship primitives, let composition happen.

[Full deliverable content would be here]

Score: 0.92/1.00 (judged by bro_agent)
"""


def demo():
    """Run demo with synthetic email."""
    print("=" * 60)
    print("Email → Attestation Mapper Demo")
    print("=" * 60)
    
    raw = create_demo_email()
    msg = email.message_from_string(raw, policy=policy.default)
    
    print("\n--- Raw Email Headers ---")
    for key in ["From", "To", "Date", "Message-ID", "DKIM-Signature", "X-Claim-Hash"]:
        val = msg.get(key, "")
        if len(val) > 80:
            val = val[:80] + "..."
        print(f"  {key}: {val}")
    
    print("\n--- Attestation Record ---")
    record = parse_email_to_attestation(msg)
    envelope = record.to_isnad_envelope()
    print(json.dumps(envelope, indent=2))
    
    grade, explanation = record.grade()
    print(f"\n--- Grade: {grade} ---")
    print(f"  {explanation}")
    print(f"  Proof layers: {record.proof_layers}")
    
    print("\n--- Field Mapping ---")
    mapping = {
        "From": "→ attester_did",
        "Date": "→ timestamp",
        "Message-ID": "→ contract_id", 
        "DKIM-Signature": "→ sig + sig_type",
        "X-Claim-Hash": "→ evidence_hash",
        "To": "→ subject_did",
        "Body": "→ claim",
    }
    for email_field, isnad_field in mapping.items():
        print(f"  {email_field:20s} {isnad_field}")
    
    # Validate
    print("\n--- Validation ---")
    issues = validate_record(envelope)
    if issues:
        for issue in issues:
            print(f"  ⚠️  {issue}")
    else:
        print("  ✅ All checks passed")
    
    # Save
    outfile = "email-attestation-demo.json"
    with open(outfile, "w") as f:
        json.dump(envelope, f, indent=2)
    print(f"\nSaved to {outfile}")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "demo":
        demo()
    elif sys.argv[1] == "parse" and len(sys.argv) > 2:
        with open(sys.argv[2]) as f:
            msg = email.message_from_string(f.read(), policy=policy.default)
        record = parse_email_to_attestation(msg)
        print(json.dumps(record.to_isnad_envelope(), indent=2))
    elif sys.argv[1] == "validate" and len(sys.argv) > 2:
        with open(sys.argv[2]) as f:
            data = json.load(f)
        issues = validate_record(data)
        for issue in issues:
            print(f"⚠️  {issue}")
        if not issues:
            print("✅ Valid")
    else:
        print(__doc__)
