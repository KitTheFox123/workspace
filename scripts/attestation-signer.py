#!/usr/bin/env python3
"""Ed25519 attestation signer for isnad-rfc cross-agent verification.

Generates Ed25519 keypair (JWK format), signs attestation payloads as JWS,
and verifies signatures. Built for Gendolf sandbox test (2026-02-14).

Usage:
    python attestation-signer.py keygen          # Generate keypair
    python attestation-signer.py sign <payload>  # Sign JSON payload
    python attestation-signer.py verify <jws>    # Verify JWS
    python attestation-signer.py attest <claim> <subject>  # Create + sign attestation
"""

import base64
import json
import sys
import time
from pathlib import Path

try:
    from nacl.signing import SigningKey, VerifyKey
    from nacl.encoding import RawEncoder
except ImportError:
    print("pip install pynacl  (or: uv pip install pynacl)")
    sys.exit(1)

KEY_DIR = Path.home() / ".config" / "isnad"
PRIVKEY_PATH = KEY_DIR / "ed25519_private.json"
PUBKEY_PATH = KEY_DIR / "ed25519_public.jwk"

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)

def keygen():
    """Generate Ed25519 keypair, save as JWK."""
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    
    sk = SigningKey.generate()
    vk = sk.verify_key
    
    # JWK format (RFC 8037)
    private_jwk = {
        "kty": "OKP",
        "crv": "Ed25519",
        "x": b64url(bytes(vk)),
        "d": b64url(bytes(sk)),
        "kid": f"kit-fox-{int(time.time())}",
        "use": "sig",
    }
    
    public_jwk = {
        "kty": "OKP",
        "crv": "Ed25519",
        "x": private_jwk["x"],
        "kid": private_jwk["kid"],
        "use": "sig",
    }
    
    PRIVKEY_PATH.write_text(json.dumps(private_jwk, indent=2))
    PRIVKEY_PATH.chmod(0o600)
    PUBKEY_PATH.write_text(json.dumps(public_jwk, indent=2))
    
    print(f"Private key: {PRIVKEY_PATH}")
    print(f"Public JWK:  {PUBKEY_PATH}")
    print(f"kid: {public_jwk['kid']}")
    print(f"\nShare this public JWK with verifiers:")
    print(json.dumps(public_jwk, indent=2))

def load_signing_key() -> tuple[SigningKey, dict]:
    if not PRIVKEY_PATH.exists():
        print("No keypair found. Run: attestation-signer.py keygen")
        sys.exit(1)
    jwk = json.loads(PRIVKEY_PATH.read_text())
    sk = SigningKey(b64url_decode(jwk["d"]), encoder=RawEncoder)
    return sk, jwk

def sign_jws(payload: dict) -> str:
    """Sign payload as JWS compact serialization (RFC 7515)."""
    sk, jwk = load_signing_key()
    
    header = {
        "alg": "EdDSA",
        "kid": jwk["kid"],
        "typ": "JWT",
    }
    
    header_b64 = b64url(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode()
    
    sig = sk.sign(signing_input, encoder=RawEncoder).signature
    sig_b64 = b64url(sig)
    
    return f"{header_b64}.{payload_b64}.{sig_b64}"

def verify_jws(jws: str, public_jwk: dict = None) -> dict:
    """Verify JWS, return payload if valid."""
    parts = jws.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWS format")
    
    header_b64, payload_b64, sig_b64 = parts
    header = json.loads(b64url_decode(header_b64))
    
    if header.get("alg") != "EdDSA":
        raise ValueError(f"Unsupported algorithm: {header.get('alg')}")
    
    if public_jwk is None:
        if not PUBKEY_PATH.exists():
            raise FileNotFoundError("No public key found")
        public_jwk = json.loads(PUBKEY_PATH.read_text())
    
    vk = VerifyKey(b64url_decode(public_jwk["x"]), encoder=RawEncoder)
    signing_input = f"{header_b64}.{payload_b64}".encode()
    sig = b64url_decode(sig_b64)
    
    vk.verify(signing_input, sig, encoder=RawEncoder)
    payload = json.loads(b64url_decode(payload_b64))
    
    print(f"✓ Valid signature (kid: {header.get('kid')})")
    return payload

def create_envelope(claim: str, subject: str, prev_hash: str = None) -> dict:
    """Create JSON envelope format (Gendolf sandbox format).
    
    Human-readable, with detached signature. Easier to inspect
    chain_ref + prev_hash without decoding.
    """
    import hashlib
    
    sk, jwk = load_signing_key()
    
    attestation = {
        "protocol": "isnad-rfc/v0.1",
        "iss": "kit_fox@agentmail.to",
        "sub": subject,
        "iat": int(time.time()),
        "exp": int(time.time()) + 86400 * 30,
        "claim": claim,
        "kid": jwk["kid"],
    }
    
    if prev_hash:
        attestation["prev_hash"] = prev_hash
        attestation["chain_ref"] = True
    
    # Canonical JSON for signing
    canonical = json.dumps(attestation, sort_keys=True, separators=(",", ":")).encode()
    
    # Sign the canonical payload
    sig = sk.sign(canonical, encoder=RawEncoder).signature
    
    # Compute content hash for chaining
    content_hash = hashlib.sha256(canonical).hexdigest()
    
    envelope = {
        "payload": attestation,
        "signature": b64url(sig),
        "alg": "EdDSA",
        "kid": jwk["kid"],
        "content_hash": content_hash,
    }
    
    print(f"Envelope attestation:")
    print(f"  Issuer:  {attestation['iss']}")
    print(f"  Subject: {attestation['sub']}")
    print(f"  Claim:   {attestation['claim']}")
    print(f"  Hash:    {content_hash[:16]}...")
    if prev_hash:
        print(f"  Chain:   → {prev_hash[:16]}...")
    print(f"\nJSON envelope:")
    print(json.dumps(envelope, indent=2))
    return envelope

def verify_envelope(envelope: dict, public_jwk: dict = None) -> dict:
    """Verify JSON envelope format."""
    if public_jwk is None:
        if not PUBKEY_PATH.exists():
            raise FileNotFoundError("No public key found")
        public_jwk = json.loads(PUBKEY_PATH.read_text())
    
    vk = VerifyKey(b64url_decode(public_jwk["x"]), encoder=RawEncoder)
    canonical = json.dumps(envelope["payload"], sort_keys=True, separators=(",", ":")).encode()
    sig = b64url_decode(envelope["signature"])
    
    vk.verify(canonical, sig, encoder=RawEncoder)
    print(f"✓ Valid envelope signature (kid: {envelope.get('kid')})")
    return envelope["payload"]

def create_attestation(claim: str, subject: str) -> str:
    """Create and sign an isnad attestation."""
    _, jwk = load_signing_key()
    
    attestation = {
        "iss": "kit_fox@agentmail.to",
        "sub": subject,
        "iat": int(time.time()),
        "exp": int(time.time()) + 86400 * 30,  # 30 days
        "claim": claim,
        "kid": jwk["kid"],
        "protocol": "isnad-rfc/v0.1",
    }
    
    jws = sign_jws(attestation)
    print(f"Attestation signed:")
    print(f"  Issuer:  {attestation['iss']}")
    print(f"  Subject: {attestation['sub']}")
    print(f"  Claim:   {attestation['claim']}")
    print(f"  Expires: {time.strftime('%Y-%m-%d', time.gmtime(attestation['exp']))}")
    print(f"\nJWS ({len(jws)} chars):")
    print(jws)
    return jws

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "keygen":
        keygen()
    elif cmd == "sign":
        payload = json.loads(sys.argv[2]) if len(sys.argv) > 2 else json.load(sys.stdin)
        jws = sign_jws(payload)
        print(jws)
    elif cmd == "verify":
        jws = sys.argv[2] if len(sys.argv) > 2 else sys.stdin.read().strip()
        pubkey = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
        payload = verify_jws(jws, pubkey)
        print(json.dumps(payload, indent=2))
    elif cmd == "attest":
        if len(sys.argv) < 4:
            print("Usage: attestation-signer.py attest <claim> <subject>")
            sys.exit(1)
        create_attestation(sys.argv[2], sys.argv[3])
    elif cmd == "envelope":
        if len(sys.argv) < 4:
            print("Usage: attestation-signer.py envelope <claim> <subject> [prev_hash]")
            sys.exit(1)
        prev = sys.argv[4] if len(sys.argv) > 4 else None
        create_envelope(sys.argv[2], sys.argv[3], prev)
    elif cmd == "verify-envelope":
        env = json.loads(sys.argv[2]) if len(sys.argv) > 2 else json.load(sys.stdin)
        pubkey = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
        payload = verify_envelope(env, pubkey)
        print(json.dumps(payload, indent=2))
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)

if __name__ == "__main__":
    main()
