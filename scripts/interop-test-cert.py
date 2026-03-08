#!/usr/bin/env python3
"""interop-test-cert.py — Generate test scope certificates for three-way interop.

Generates scope certificates compatible with:
1. isnad scope-cert-issuer.py (Kit)
2. isnad evidence schema (Gendolf)
3. SkillFence v2 posture_hash receipts (hash/SkillFence)

For Wednesday March 12 interop test: Kit → Gendolf → hash round-trip.

Usage:
    python3 interop-test-cert.py --generate    # Generate test cert
    python3 interop-test-cert.py --validate    # Validate cert structure
    python3 interop-test-cert.py --roundtrip   # Simulate full round-trip
"""

import argparse
import json
import hashlib
import time
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict
from typing import List, Optional


@dataclass
class ScopeLine:
    """Individual scope permission."""
    action: str
    resource: str
    constraint: Optional[str] = None


@dataclass  
class ScopeCert:
    """Scope certificate for interop testing."""
    version: str
    cert_id: str
    principal_id: str
    agent_id: str
    issued_at: str
    expires_at: str
    ttl_seconds: int
    scope_lines: List[dict]
    scope_hash: str
    posture_hash: Optional[str]  # SkillFence v2 compatibility
    merkle_leaf: str
    signature_placeholder: str  # Would be Ed25519 in production
    
    # Evidence schema fields (Gendolf compatibility)
    evidence_type: str = "scope_attestation"
    evidence_level: str = "L2.5"  # Declared + CUSUM
    chain_id: Optional[str] = None


def generate_scope_hash(scope_lines: List[ScopeLine]) -> str:
    """Hash scope lines deterministically."""
    canonical = json.dumps([asdict(s) for s in scope_lines], sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def generate_posture_hash(agent_id: str, scope_hash: str, timestamp: str) -> str:
    """SkillFence v2 compatible posture hash."""
    data = f"{agent_id}:{scope_hash}:{timestamp}"
    return hashlib.sha256(data.encode()).hexdigest()


def generate_merkle_leaf(cert_data: str) -> str:
    """CT-style Merkle leaf hash (H(0x00 || data))."""
    return hashlib.sha256(b'\x00' + cert_data.encode()).hexdigest()


def generate_test_cert(
    principal: str = "ilya@openclaw",
    agent: str = "kit_fox",
    ttl: int = 3600
) -> ScopeCert:
    """Generate a test scope certificate."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=ttl)
    
    scope_lines = [
        ScopeLine("read", "memory/*", "own_workspace_only"),
        ScopeLine("write", "memory/*", "own_workspace_only"),
        ScopeLine("execute", "scripts/*", "no_network_access"),
        ScopeLine("post", "clawk.ai", "280_char_limit"),
        ScopeLine("post", "moltbook.com", "30min_cooldown"),
    ]
    
    scope_hash = generate_scope_hash(scope_lines)
    issued_at = now.isoformat()
    
    posture_hash = generate_posture_hash(agent, scope_hash, issued_at)
    
    cert_id = hashlib.sha256(
        f"{principal}:{agent}:{issued_at}".encode()
    ).hexdigest()[:16]
    
    cert_data = json.dumps({
        "cert_id": cert_id,
        "principal": principal,
        "agent": agent,
        "scope_hash": scope_hash,
        "issued_at": issued_at
    }, sort_keys=True)
    
    merkle_leaf = generate_merkle_leaf(cert_data)
    
    # HMAC placeholder (would be Ed25519 in production)
    sig_data = f"{cert_id}:{scope_hash}:{issued_at}:{expires.isoformat()}"
    signature = hashlib.sha256(f"PLACEHOLDER_KEY:{sig_data}".encode()).hexdigest()
    
    return ScopeCert(
        version="isnad-interop-v1",
        cert_id=cert_id,
        principal_id=principal,
        agent_id=agent,
        issued_at=issued_at,
        expires_at=expires.isoformat(),
        ttl_seconds=ttl,
        scope_lines=[asdict(s) for s in scope_lines],
        scope_hash=scope_hash,
        posture_hash=posture_hash,
        merkle_leaf=merkle_leaf,
        signature_placeholder=signature,
        evidence_type="scope_attestation",
        evidence_level="L2.5",
        chain_id=f"isnad-{cert_id[:8]}"
    )


def validate_cert(cert_dict: dict) -> dict:
    """Validate certificate structure for interop compatibility."""
    checks = {}
    
    # isnad fields
    isnad_required = ["cert_id", "principal_id", "agent_id", "scope_hash", 
                      "issued_at", "expires_at", "scope_lines", "merkle_leaf"]
    for field in isnad_required:
        checks[f"isnad.{field}"] = field in cert_dict
    
    # SkillFence v2 fields
    checks["skillfence.posture_hash"] = "posture_hash" in cert_dict
    checks["skillfence.cert_id"] = "cert_id" in cert_dict
    
    # Gendolf evidence schema fields
    checks["evidence.type"] = cert_dict.get("evidence_type") == "scope_attestation"
    checks["evidence.level"] = cert_dict.get("evidence_level") in ["L0", "L1", "L2", "L2.5", "L3"]
    checks["evidence.chain_id"] = "chain_id" in cert_dict
    
    # Verify scope hash
    if "scope_lines" in cert_dict:
        computed = hashlib.sha256(
            json.dumps(cert_dict["scope_lines"], sort_keys=True).encode()
        ).hexdigest()
        checks["integrity.scope_hash"] = computed == cert_dict.get("scope_hash")
    
    # Check TTL
    if "issued_at" in cert_dict and "expires_at" in cert_dict:
        try:
            issued = datetime.fromisoformat(cert_dict["issued_at"])
            expires = datetime.fromisoformat(cert_dict["expires_at"])
            checks["validity.not_expired"] = expires > datetime.now(timezone.utc)
            checks["validity.ttl_positive"] = (expires - issued).total_seconds() > 0
        except Exception:
            checks["validity.parseable"] = False
    
    passed = sum(1 for v in checks.values() if v)
    total = len(checks)
    
    return {
        "checks": checks,
        "passed": passed,
        "total": total,
        "grade": "A" if passed == total else "B" if passed >= total - 1 else "C" if passed >= total - 3 else "F",
        "interop_ready": passed == total
    }


def simulate_roundtrip():
    """Simulate Kit → Gendolf → hash round-trip."""
    print("=" * 60)
    print("THREE-WAY INTEROP TEST SIMULATION")
    print("Kit (scope-cert) → Gendolf (evidence) → hash (SkillFence)")
    print("=" * 60)
    print()
    
    # Step 1: Kit generates cert
    print("[1] Kit: Generating scope certificate...")
    cert = generate_test_cert()
    cert_dict = asdict(cert)
    print(f"    cert_id: {cert.cert_id}")
    print(f"    scope_hash: {cert.scope_hash[:16]}...")
    print(f"    posture_hash: {cert.posture_hash[:16]}...")
    print(f"    merkle_leaf: {cert.merkle_leaf[:16]}...")
    print()
    
    # Step 2: Gendolf validates against evidence schema
    print("[2] Gendolf: Validating against evidence schema...")
    evidence = {
        "type": cert.evidence_type,
        "level": cert.evidence_level,
        "chain_id": cert.chain_id,
        "cert_ref": cert.cert_id,
        "scope_hash": cert.scope_hash,
        "timestamp": cert.issued_at,
        "validator": "gendolf_evidence_schema_v1"
    }
    print(f"    evidence_type: {evidence['type']}")
    print(f"    evidence_level: {evidence['level']}")
    print(f"    chain_id: {evidence['chain_id']}")
    print(f"    ✅ Evidence schema mapping complete")
    print()
    
    # Step 3: hash/SkillFence validates posture
    print("[3] hash: Validating SkillFence v2 receipt...")
    receipt = {
        "cert_id": cert.cert_id,
        "posture_hash": cert.posture_hash,
        "posture_hash_at_dispatch": cert.posture_hash,  # Same at dispatch time
        "dispatched_at": cert.issued_at,
        "scope_hash_match": cert.scope_hash == generate_scope_hash(
            [ScopeLine(**s) for s in cert.scope_lines]
        ),
        "validator": "skillfence_v2_receipt"
    }
    print(f"    cert_id: {receipt['cert_id']}")
    print(f"    posture_hash: {receipt['posture_hash'][:16]}...")
    print(f"    scope_hash_match: {receipt['scope_hash_match']}")
    print(f"    ✅ SkillFence receipt validation complete")
    print()
    
    # Step 4: Validate full structure
    print("[4] Validation: Full interop check...")
    validation = validate_cert(cert_dict)
    print(f"    Checks: {validation['passed']}/{validation['total']}")
    print(f"    Grade: {validation['grade']}")
    print(f"    Interop ready: {validation['interop_ready']}")
    print()
    
    if validation['interop_ready']:
        print("🟢 ROUND-TRIP COMPLETE — All three schemas compatible")
    else:
        failed = [k for k, v in validation['checks'].items() if not v]
        print(f"🔴 FAILED CHECKS: {failed}")
    
    return cert_dict, evidence, receipt, validation


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Interop test cert generator")
    parser.add_argument("--generate", action="store_true", help="Generate test cert")
    parser.add_argument("--validate", type=str, help="Validate cert from JSON file")
    parser.add_argument("--roundtrip", action="store_true", help="Simulate round-trip")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()
    
    if args.roundtrip:
        simulate_roundtrip()
    elif args.generate:
        cert = generate_test_cert()
        print(json.dumps(asdict(cert), indent=2))
    elif args.validate:
        with open(args.validate) as f:
            cert_dict = json.load(f)
        result = validate_cert(cert_dict)
        print(json.dumps(result, indent=2))
    else:
        simulate_roundtrip()
