#!/usr/bin/env python3
"""install-runtime-linker.py — Links install-time integrity to runtime receipts.

Bridges the gap between static artifact verification (SkillFence model)
and dynamic runtime monitoring (three-signal verdict). Every runtime
action receipt embeds the install-time cert ID, making behavior
traceable to a verified artifact.

Inspired by hash's SkillFence + action receipts integration proposal.

Usage:
    python3 install-runtime-linker.py --demo
"""

import argparse
import json
import hashlib
import time
from dataclasses import dataclass, asdict, field
from typing import List, Optional
from datetime import datetime, timezone


@dataclass
class InstallCert:
    """Install-time integrity certificate."""
    cert_id: str
    skill_hash: str
    skill_name: str
    operator_id: str
    operator_sig: str  # placeholder
    issued_at: str
    ttl_hours: int = 24
    
    @staticmethod
    def create(skill_name: str, skill_content: str, operator_id: str) -> 'InstallCert':
        skill_hash = hashlib.sha256(skill_content.encode()).hexdigest()[:16]
        cert_id = hashlib.sha256(f"{skill_hash}:{operator_id}:{time.time()}".encode()).hexdigest()[:12]
        return InstallCert(
            cert_id=cert_id,
            skill_hash=skill_hash,
            skill_name=skill_name,
            operator_id=operator_id,
            operator_sig=hashlib.sha256(f"sig:{cert_id}".encode()).hexdigest()[:16],
            issued_at=datetime.now(timezone.utc).isoformat(),
        )
    
    def is_expired(self) -> bool:
        issued = datetime.fromisoformat(self.issued_at)
        elapsed = (datetime.now(timezone.utc) - issued).total_seconds() / 3600
        return elapsed > self.ttl_hours


@dataclass
class ActionReceipt:
    """Runtime action receipt linked to install cert."""
    receipt_id: str
    cert_id: str  # Link to install-time cert
    action: str
    timestamp: str
    input_hash: str
    output_hash: str
    scope_hash: str
    chain_hash: str  # Hash chain link
    
    @staticmethod
    def create(cert_id: str, action: str, input_data: str, output_data: str, 
               scope_hash: str, prev_hash: str = "genesis") -> 'ActionReceipt':
        ts = datetime.now(timezone.utc).isoformat()
        input_hash = hashlib.sha256(input_data.encode()).hexdigest()[:12]
        output_hash = hashlib.sha256(output_data.encode()).hexdigest()[:12]
        receipt_id = hashlib.sha256(f"{cert_id}:{action}:{ts}".encode()).hexdigest()[:12]
        chain_hash = hashlib.sha256(f"{prev_hash}:{receipt_id}:{input_hash}:{output_hash}".encode()).hexdigest()[:16]
        return ActionReceipt(
            receipt_id=receipt_id,
            cert_id=cert_id,
            action=action,
            timestamp=ts,
            input_hash=input_hash,
            output_hash=output_hash,
            scope_hash=scope_hash,
            chain_hash=chain_hash,
        )


@dataclass
class LinkedTrace:
    """Full trace linking install cert to runtime receipts."""
    cert: InstallCert
    receipts: List[ActionReceipt] = field(default_factory=list)
    
    def add_action(self, action: str, input_data: str, output_data: str, scope_hash: str):
        prev = self.receipts[-1].chain_hash if self.receipts else "genesis"
        receipt = ActionReceipt.create(self.cert.cert_id, action, input_data, output_data, scope_hash, prev)
        self.receipts.append(receipt)
        return receipt
    
    def verify_chain(self) -> dict:
        """Verify receipt chain integrity."""
        if not self.receipts:
            return {"valid": True, "length": 0}
        
        breaks = []
        prev_hash = "genesis"
        for i, r in enumerate(self.receipts):
            expected = hashlib.sha256(
                f"{prev_hash}:{r.receipt_id}:{r.input_hash}:{r.output_hash}".encode()
            ).hexdigest()[:16]
            if expected != r.chain_hash:
                breaks.append(i)
            if r.cert_id != self.cert.cert_id:
                breaks.append(i)
            prev_hash = r.chain_hash
        
        return {
            "valid": len(breaks) == 0,
            "length": len(self.receipts),
            "breaks": breaks,
            "cert_expired": self.cert.is_expired(),
            "cert_id": self.cert.cert_id,
        }
    
    def drift_score(self) -> float:
        """Measure scope drift across receipts."""
        if len(self.receipts) < 2:
            return 0.0
        scope_hashes = [r.scope_hash for r in self.receipts]
        changes = sum(1 for i in range(1, len(scope_hashes)) if scope_hashes[i] != scope_hashes[i-1])
        return changes / (len(scope_hashes) - 1)


def demo():
    print("=" * 60)
    print("INSTALL-RUNTIME LINKER DEMO")
    print("=" * 60)
    
    # Create install cert
    cert = InstallCert.create("web-search", "def search(q): return fetch(q)", "operator_ilya")
    print(f"\n[INSTALL] Cert {cert.cert_id} for '{cert.skill_name}'")
    print(f"  Skill hash: {cert.skill_hash}")
    print(f"  Operator: {cert.operator_id}")
    print(f"  TTL: {cert.ttl_hours}h")
    
    # Create linked trace
    trace = LinkedTrace(cert=cert)
    scope = hashlib.sha256(b"search:fetch:report").hexdigest()[:12]
    
    actions = [
        ("search", "query: trust systems", "3 results found", scope),
        ("fetch", "url: arxiv.org/123", "paper content", scope),
        ("report", "summarize findings", "Trust requires...", scope),
        ("search", "query: BCI implants", "5 results", scope),
        # Scope drift — new scope hash
        ("exec", "run script", "output data", hashlib.sha256(b"exec:admin").hexdigest()[:12]),
    ]
    
    print(f"\n[RUNTIME] Recording {len(actions)} actions:")
    for action, inp, out, sc in actions:
        receipt = trace.add_action(action, inp, out, sc)
        drift_marker = " ⚠️ SCOPE DRIFT" if sc != scope else ""
        print(f"  [{receipt.receipt_id}] {action} → cert:{receipt.cert_id[:8]}{drift_marker}")
    
    # Verify
    result = trace.verify_chain()
    drift = trace.drift_score()
    
    print(f"\n[VERIFY]")
    print(f"  Chain valid: {result['valid']}")
    print(f"  Chain length: {result['length']}")
    print(f"  Cert expired: {result['cert_expired']}")
    print(f"  Scope drift: {drift:.1%}")
    print(f"  Breaks: {result['breaks'] if result['breaks'] else 'none'}")
    
    grade = "A" if result['valid'] and drift < 0.1 else "B" if result['valid'] else "F"
    print(f"\n  GRADE: {grade}")
    print(f"  {'✅ All actions traceable to verified artifact' if grade != 'F' else '❌ Chain integrity compromised'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Install-runtime linker")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    demo()
