#!/usr/bin/env python3
"""isnad-sign.py — Ed25519 attestation signing for isnad protocol.

Usage:
  python scripts/isnad-sign.py keygen          # Generate Ed25519 keypair (JWK)
  python scripts/isnad-sign.py sign <claim>    # Sign an attestation claim
  python scripts/isnad-sign.py verify <file>   # Verify a signed attestation
  python scripts/isnad-sign.py jwk             # Export public key as JWK

Keys stored in ~/.config/isnad/
"""

import json, sys, os, time, base64, hashlib
from pathlib import Path

KEY_DIR = Path.home() / ".config" / "isnad"

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * padding)

def keygen():
    """Generate Ed25519 keypair, store as JWK."""
    from nacl.signing import SigningKey
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    
    sk = SigningKey.generate()
    pk = sk.verify_key
    
    # Ed25519 JWK format (RFC 8037)
    private_jwk = {
        "kty": "OKP",
        "crv": "Ed25519",
        "x": b64url(bytes(pk)),
        "d": b64url(bytes(sk)),
        "kid": f"kit-fox-{int(time.time())}",
    }
    public_jwk = {k: v for k, v in private_jwk.items() if k != "d"}
    
    (KEY_DIR / "private.jwk.json").write_text(json.dumps(private_jwk, indent=2))
    (KEY_DIR / "public.jwk.json").write_text(json.dumps(public_jwk, indent=2))
    os.chmod(KEY_DIR / "private.jwk.json", 0o600)
    
    print(f"Keys generated in {KEY_DIR}")
    print(f"Public JWK:\n{json.dumps(public_jwk, indent=2)}")
    print(f"Key ID: {private_jwk['kid']}")

def load_signing_key():
    from nacl.signing import SigningKey
    jwk = json.loads((KEY_DIR / "private.jwk.json").read_text())
    seed = b64url_decode(jwk["d"])
    return SigningKey(seed), jwk["kid"]

def load_verify_key(jwk_path=None):
    from nacl.signing import VerifyKey
    if jwk_path:
        jwk = json.loads(Path(jwk_path).read_text())
    else:
        jwk = json.loads((KEY_DIR / "public.jwk.json").read_text())
    pk_bytes = b64url_decode(jwk["x"])
    return VerifyKey(pk_bytes), jwk.get("kid", "unknown")

def sign(claim_text: str):
    """Create a signed attestation (JWS-like JSON envelope)."""
    sk, kid = load_signing_key()
    
    attestation = {
        "version": "isnad-0.1",
        "type": "attestation",
        "issuer": "kit_fox@agentmail.to",
        "kid": kid,
        "issued_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "claim": claim_text,
    }
    
    # Canonical JSON payload
    payload_bytes = json.dumps(attestation, sort_keys=True, separators=(",", ":")).encode()
    
    # Sign
    signed = sk.sign(payload_bytes)
    signature = signed.signature
    
    envelope = {
        "payload": attestation,
        "signature": b64url(signature),
        "payload_hash": hashlib.sha256(payload_bytes).hexdigest(),
    }
    
    out_path = KEY_DIR / f"attestation-{int(time.time())}.json"
    out_path.write_text(json.dumps(envelope, indent=2))
    print(f"Signed attestation: {out_path}")
    print(json.dumps(envelope, indent=2))
    return envelope

def verify(file_path: str):
    """Verify a signed attestation."""
    envelope = json.loads(Path(file_path).read_text())
    payload = envelope["payload"]
    sig = b64url_decode(envelope["signature"])
    
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    
    # Verify hash
    expected_hash = hashlib.sha256(payload_bytes).hexdigest()
    if expected_hash != envelope.get("payload_hash"):
        print("FAIL: payload hash mismatch")
        return False
    
    vk, kid = load_verify_key()
    try:
        vk.verify(payload_bytes, sig)
        print(f"VALID ✓ — signed by {payload.get('issuer', 'unknown')} (kid: {kid})")
        print(f"  Claim: {payload.get('claim')}")
        print(f"  Issued: {payload.get('issued_at')}")
        return True
    except Exception as e:
        print(f"INVALID ✗ — {e}")
        return False

def export_jwk():
    jwk = json.loads((KEY_DIR / "public.jwk.json").read_text())
    print(json.dumps(jwk, indent=2))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    cmd = sys.argv[1]
    if cmd == "keygen":
        keygen()
    elif cmd == "sign":
        if len(sys.argv) < 3:
            print("Usage: isnad-sign.py sign <claim text>")
            sys.exit(1)
        sign(" ".join(sys.argv[2:]))
    elif cmd == "verify":
        if len(sys.argv) < 3:
            print("Usage: isnad-sign.py verify <attestation.json>")
            sys.exit(1)
        ok = verify(sys.argv[2])
        sys.exit(0 if ok else 1)
    elif cmd == "jwk":
        export_jwk()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)
