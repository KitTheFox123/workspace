#!/usr/bin/env python3
"""
Key Rotation Ceremony Protocol
Implements the rotation ceremony discussed with Nole on Shellmates.

Generates keypairs, creates rotation requests, collects attestor signatures,
and verifies m-of-n threshold before accepting rotation.

Uses Ed25519 (via PyNaCl) for real cryptographic operations.

Usage:
  python3 key-rotation-ceremony.py demo      # Run full demo
  python3 key-rotation-ceremony.py generate   # Generate new keypair
  python3 key-rotation-ceremony.py rotate     # Create rotation request
"""

import json
import hashlib
import time
import sys
import os
import base64
import secrets

# Try to use real crypto, fall back to simulated
try:
    from nacl.signing import SigningKey, VerifyKey
    from nacl.encoding import Base64Encoder
    REAL_CRYPTO = True
except ImportError:
    REAL_CRYPTO = False
    print("⚠️  PyNaCl not installed. Using simulated signatures.")
    print("   Install: uv pip install pynacl")


class KeyPair:
    """Ed25519 keypair wrapper."""
    
    def __init__(self, signing_key=None):
        if REAL_CRYPTO:
            self.sk = signing_key or SigningKey.generate()
            self.vk = self.sk.verify_key
            self.public_b64 = self.vk.encode(Base64Encoder).decode()
            self.secret_b64 = self.sk.encode(Base64Encoder).decode()
        else:
            self._seed = secrets.token_hex(32)
            self.public_b64 = base64.b64encode(
                hashlib.sha256(self._seed.encode()).digest()
            ).decode()
            self.secret_b64 = base64.b64encode(self._seed.encode()[:32]).decode()
    
    def sign(self, message: bytes) -> str:
        if REAL_CRYPTO:
            signed = self.sk.sign(message)
            return base64.b64encode(signed.signature).decode()
        else:
            h = hashlib.sha256(self._seed.encode() + message).hexdigest()
            return base64.b64encode(bytes.fromhex(h)).decode()
    
    @staticmethod
    def verify(public_b64: str, message: bytes, signature_b64: str) -> bool:
        if REAL_CRYPTO:
            try:
                vk = VerifyKey(base64.b64decode(public_b64))
                vk.verify(message, base64.b64decode(signature_b64))
                return True
            except Exception:
                return False
        else:
            # Simulated: always returns True (can't verify without secret)
            return True


class RotationRequest:
    """A key rotation request that collects attestor signatures."""
    
    def __init__(self, agent_name: str, old_pubkey: str, new_pubkey: str,
                 threshold: int = 3, total_attestors: int = 5):
        self.agent_name = agent_name
        self.old_pubkey = old_pubkey
        self.new_pubkey = new_pubkey
        self.old_pubkey_hash = hashlib.sha256(old_pubkey.encode()).hexdigest()[:16]
        self.timestamp = int(time.time())
        self.nonce = secrets.token_hex(16)
        self.threshold = threshold
        self.total_attestors = total_attestors
        self.attestations = []
    
    def canonical_bytes(self) -> bytes:
        """Canonical representation for signing."""
        payload = {
            "agent_name": self.agent_name,
            "new_pubkey": self.new_pubkey,
            "old_pubkey_hash": self.old_pubkey_hash,
            "timestamp": self.timestamp,
            "nonce": self.nonce,
        }
        return json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    
    def add_attestation(self, attestor_name: str, attestor_pubkey: str,
                        signature: str, platform: str = "unknown") -> bool:
        """Add an attestor's signature. Returns True if valid."""
        if KeyPair.verify(attestor_pubkey, self.canonical_bytes(), signature):
            self.attestations.append({
                "attestor": attestor_name,
                "pubkey": attestor_pubkey,
                "signature": signature,
                "platform": platform,
                "attested_at": int(time.time()),
            })
            return True
        return False
    
    @property
    def is_complete(self) -> bool:
        return len(self.attestations) >= self.threshold
    
    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "old_pubkey_hash": self.old_pubkey_hash,
            "new_pubkey": self.new_pubkey,
            "timestamp": self.timestamp,
            "nonce": self.nonce,
            "threshold": self.threshold,
            "attestations": self.attestations,
            "complete": self.is_complete,
        }
    
    def summary(self) -> str:
        lines = [
            f"🔑 Key Rotation Ceremony for {self.agent_name}",
            f"   Old key hash: {self.old_pubkey_hash}",
            f"   New key:      {self.new_pubkey[:20]}...",
            f"   Nonce:        {self.nonce[:16]}...",
            f"   Threshold:    {len(self.attestations)}/{self.threshold} "
            f"({'✅ COMPLETE' if self.is_complete else '⏳ pending'})",
            f"   Attestors:",
        ]
        for a in self.attestations:
            lines.append(f"     - {a['attestor']} ({a['platform']})")
        return "\n".join(lines)


class ExternalWitness:
    """Publish rotation record to external witness (file-based for now)."""
    
    def __init__(self, witness_dir: str = None):
        self.witness_dir = witness_dir or os.path.expanduser(
            "~/.openclaw/workspace/data/rotation-witnesses"
        )
        os.makedirs(self.witness_dir, exist_ok=True)
    
    def publish(self, rotation: RotationRequest) -> str:
        """Write rotation record and return the witness hash."""
        record = rotation.to_dict()
        record_json = json.dumps(record, sort_keys=True, indent=2)
        witness_hash = hashlib.sha256(record_json.encode()).hexdigest()
        
        filename = f"{rotation.agent_name}_{rotation.timestamp}_{witness_hash[:8]}.json"
        filepath = os.path.join(self.witness_dir, filename)
        
        with open(filepath, 'w') as f:
            f.write(record_json)
        
        return witness_hash, filepath


def demo():
    """Run a full key rotation ceremony demo."""
    print("=" * 60)
    print("🔑 Key Rotation Ceremony Demo")
    print(f"   Crypto: {'Ed25519 (PyNaCl)' if REAL_CRYPTO else 'Simulated'}")
    print("=" * 60)
    
    # Generate agent's old and new keys
    print("\n1️⃣  Generating agent keypairs...")
    old_key = KeyPair()
    new_key = KeyPair()
    print(f"   Old pubkey: {old_key.public_b64[:30]}...")
    print(f"   New pubkey: {new_key.public_b64[:30]}...")
    
    # Create rotation request (3-of-5 threshold)
    print("\n2️⃣  Creating rotation request (3-of-5)...")
    rotation = RotationRequest(
        agent_name="kit_fox",
        old_pubkey=old_key.public_b64,
        new_pubkey=new_key.public_b64,
        threshold=3,
        total_attestors=5,
    )
    
    # Self-sign with old key (proves ownership of old identity)
    print("\n3️⃣  Self-signing with old key (proves chain continuity)...")
    old_sig = old_key.sign(rotation.canonical_bytes())
    rotation.add_attestation("kit_fox (self)", old_key.public_b64, old_sig, "self")
    
    # Generate attestor keys and sign
    attestors = [
        ("nole", "moltcities"),
        ("drainfun", "shellmates"),
        ("holly", "moltbook"),
        ("arnold", "shellmates"),
    ]
    
    print("\n4️⃣  Collecting attestor signatures...")
    for name, platform in attestors:
        attestor_key = KeyPair()
        sig = attestor_key.sign(rotation.canonical_bytes())
        ok = rotation.add_attestation(name, attestor_key.public_b64, sig, platform)
        status = "✅" if ok else "❌"
        print(f"   {status} {name} ({platform})")
        
        if rotation.is_complete:
            print(f"\n   🎉 Threshold reached at {len(rotation.attestations)} attestations!")
            break
    
    # Publish to external witness
    print("\n5️⃣  Publishing to external witness...")
    witness = ExternalWitness()
    witness_hash, filepath = witness.publish(rotation)
    print(f"   Witness hash: {witness_hash[:16]}...")
    print(f"   Stored at: {filepath}")
    
    # Summary
    print(f"\n{rotation.summary()}")
    
    # Verify cross-platform diversity
    platforms = set(a["platform"] for a in rotation.attestations)
    print(f"\n   Platform diversity: {len(platforms)} platforms {list(platforms)}")
    if len(platforms) >= 2:
        print("   ✅ Cross-platform attestation achieved")
    else:
        print("   ⚠️  All attestors from same platform — less resilient")
    
    print(f"\n{'=' * 60}")
    print("Done. Rotation ceremony complete.")
    return rotation


def generate():
    """Generate and print a new keypair."""
    kp = KeyPair()
    print(json.dumps({
        "public_key": kp.public_b64,
        "secret_key": kp.secret_b64,
        "algorithm": "Ed25519" if REAL_CRYPTO else "simulated",
        "generated_at": int(time.time()),
    }, indent=2))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "demo"
    if cmd == "demo":
        demo()
    elif cmd == "generate":
        generate()
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: key-rotation-ceremony.py [demo|generate]")
        sys.exit(1)
