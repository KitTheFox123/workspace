#!/usr/bin/env python3
"""
key-rotation-verifier.py — KERI-style pre-rotation verification for agent identity chains.

Implements the core insight from KERI KID0005: commit to next key as a hash digest
BEFORE rotation happens. Old key signs the rotation event, new key was already committed.
No trust gap. Math-only continuity.

Maps to clawdvine's key_rotation record: {old_key_id, new_key_id, effective_at, sig_old_key, sig_new_key}

Usage:
    python key-rotation-verifier.py demo      # Run demo with synthetic key chain
    python key-rotation-verifier.py verify FILE  # Verify a JSON key event log
"""

import hashlib
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

# Using Ed25519 via nacl if available, else fallback to hashlib simulation
try:
    from nacl.signing import SigningKey, VerifyKey
    from nacl.exceptions import BadSignatureError
    HAS_NACL = True
except ImportError:
    HAS_NACL = False


def hash_pubkey(pubkey_hex: str) -> str:
    """Hash a public key to create a pre-commitment digest."""
    return hashlib.sha256(bytes.fromhex(pubkey_hex)).hexdigest()


@dataclass
class KeyEvent:
    """A single key event in the event log (KEL)."""
    sn: int                  # Sequence number
    event_type: str          # "inception" or "rotation"
    current_pubkey: str      # Current signing public key (hex)
    next_key_digest: str     # SHA-256 digest of next public key (pre-commitment)
    signature: str           # Signature over event data by current key
    timestamp: str           # ISO timestamp
    prior_digest: Optional[str] = None  # Hash of prior event (chain integrity)

    def event_data(self) -> bytes:
        """Canonical data to sign (excludes signature itself)."""
        parts = [
            str(self.sn),
            self.event_type,
            self.current_pubkey,
            self.next_key_digest,
            self.timestamp,
            self.prior_digest or "",
        ]
        return "|".join(parts).encode()


@dataclass 
class VerificationResult:
    valid: bool
    event_sn: int
    checks: dict = field(default_factory=dict)
    error: Optional[str] = None


class KeyEventLog:
    """Manages and verifies a KERI-style key event log."""
    
    def __init__(self):
        self.events: list[KeyEvent] = []
    
    def add_event(self, event: KeyEvent):
        self.events.append(event)
    
    def verify_chain(self) -> list[VerificationResult]:
        """Verify the entire key event chain. Returns per-event results."""
        results = []
        
        for i, event in enumerate(self.events):
            checks = {}
            error = None
            
            # Check 1: Sequence number continuity
            checks["sequence_continuous"] = (event.sn == i)
            
            # Check 2: Event type ordering
            if i == 0:
                checks["inception_first"] = (event.event_type == "inception")
            else:
                checks["rotation_after_inception"] = (event.event_type == "rotation")
            
            # Check 3: Pre-rotation commitment (THE key check)
            # Current pubkey must match the next_key_digest from prior event
            if i > 0:
                prior = self.events[i - 1]
                actual_digest = hash_pubkey(event.current_pubkey)
                checks["prerotation_valid"] = (actual_digest == prior.next_key_digest)
                if not checks["prerotation_valid"]:
                    error = f"Pre-rotation failed: H(current_key) != prior.next_key_digest"
            
            # Check 4: Chain integrity (prior event digest)
            if i > 0:
                prior = self.events[i - 1]
                prior_hash = hashlib.sha256(
                    json.dumps(asdict(prior), sort_keys=True).encode()
                ).hexdigest()
                checks["chain_integrity"] = (event.prior_digest == prior_hash)
                if not checks["chain_integrity"]:
                    error = error or "Chain integrity: prior_digest mismatch"
            
            # Check 5: Signature verification (if nacl available)
            if HAS_NACL:
                try:
                    vk = VerifyKey(bytes.fromhex(event.current_pubkey))
                    vk.verify(event.event_data(), bytes.fromhex(event.signature))
                    checks["signature_valid"] = True
                except (BadSignatureError, Exception) as e:
                    checks["signature_valid"] = False
                    error = error or f"Bad signature: {e}"
            else:
                checks["signature_valid"] = "skipped (no nacl)"
            
            valid = all(
                v is True for v in checks.values() 
                if isinstance(v, bool)
            )
            results.append(VerificationResult(
                valid=valid, event_sn=event.sn, checks=checks, error=error
            ))
        
        return results
    
    def detect_fork(self, alternate_log: 'KeyEventLog') -> Optional[int]:
        """Detect fork point between two key event logs (duplicity detection)."""
        for i in range(min(len(self.events), len(alternate_log.events))):
            e1 = self.events[i]
            e2 = alternate_log.events[i]
            if (e1.current_pubkey != e2.current_pubkey or 
                e1.next_key_digest != e2.next_key_digest):
                return i
        return None
    
    def to_json(self) -> str:
        return json.dumps([asdict(e) for e in self.events], indent=2)
    
    @classmethod
    def from_json(cls, data: str) -> 'KeyEventLog':
        log = cls()
        for item in json.loads(data):
            log.add_event(KeyEvent(**item))
        return log


def create_demo_chain(rotations: int = 3) -> tuple[KeyEventLog, list]:
    """Create a demo key event chain with real Ed25519 signatures if available."""
    log = KeyEventLog()
    keys = []
    
    if HAS_NACL:
        # Generate all keys upfront
        for _ in range(rotations + 2):
            sk = SigningKey.generate()
            keys.append((sk, sk.verify_key))
    else:
        # Simulate with random hex
        import secrets
        for _ in range(rotations + 2):
            fake_priv = secrets.token_hex(32)
            fake_pub = hashlib.sha256(fake_priv.encode()).hexdigest()
            keys.append((fake_priv, fake_pub))
    
    def get_pubhex(idx):
        if HAS_NACL:
            return keys[idx][1].encode().hex()
        return keys[idx][1]
    
    def sign_event(idx, event):
        if HAS_NACL:
            sig = keys[idx][0].sign(event.event_data()).signature
            return sig.hex()
        return hashlib.sha256(event.event_data()).hexdigest()
    
    # Inception event
    inception = KeyEvent(
        sn=0,
        event_type="inception",
        current_pubkey=get_pubhex(0),
        next_key_digest=hash_pubkey(get_pubhex(1)),
        signature="",  # will fill
        timestamp=f"2026-02-24T21:00:00Z",
    )
    inception.signature = sign_event(0, inception)
    log.add_event(inception)
    
    # Rotation events
    for r in range(1, rotations + 1):
        prior_hash = hashlib.sha256(
            json.dumps(asdict(log.events[-1]), sort_keys=True).encode()
        ).hexdigest()
        
        rotation = KeyEvent(
            sn=r,
            event_type="rotation",
            current_pubkey=get_pubhex(r),
            next_key_digest=hash_pubkey(get_pubhex(r + 1)),
            signature="",
            timestamp=f"2026-02-24T21:{r:02d}:00Z",
            prior_digest=prior_hash,
        )
        rotation.signature = sign_event(r, rotation)
        log.add_event(rotation)
    
    return log, keys


def create_forked_chain(original: KeyEventLog, fork_at: int) -> KeyEventLog:
    """Create a forked chain (simulating a dead attack)."""
    forked = KeyEventLog()
    
    # Copy events before fork point
    for e in original.events[:fork_at]:
        forked.add_event(e)
    
    # Create divergent event at fork point with different next key
    import secrets
    fake_next = secrets.token_hex(32)
    
    original_event = original.events[fork_at]
    forged = KeyEvent(
        sn=original_event.sn,
        event_type=original_event.event_type,
        current_pubkey=original_event.current_pubkey,
        next_key_digest=hash_pubkey(fake_next),  # Different commitment!
        signature=original_event.signature,  # Would need real sig in practice
        timestamp=original_event.timestamp,
        prior_digest=original_event.prior_digest,
    )
    forked.add_event(forged)
    
    return forked


def demo():
    """Run interactive demo."""
    print("=" * 60)
    print("KERI-style Pre-Rotation Verifier Demo")
    print("=" * 60)
    print(f"\nCrypto backend: {'Ed25519 (PyNaCl)' if HAS_NACL else 'Simulated (hashlib)'}")
    
    # Create valid chain
    print("\n--- Creating valid key chain (3 rotations) ---")
    log, keys = create_demo_chain(3)
    
    for e in log.events:
        print(f"  SN {e.sn} [{e.event_type}] key={e.current_pubkey[:16]}... "
              f"next_digest={e.next_key_digest[:16]}...")
    
    # Verify
    print("\n--- Verifying chain ---")
    results = log.verify_chain()
    for r in results:
        status = "✅" if r.valid else "❌"
        print(f"  {status} Event {r.event_sn}: {r.checks}")
        if r.error:
            print(f"     Error: {r.error}")
    
    all_valid = all(r.valid for r in results)
    print(f"\nChain valid: {'✅ YES' if all_valid else '❌ NO'}")
    
    # Fork detection (dead attack simulation)
    print("\n--- Simulating dead attack (fork at event 2) ---")
    forked = create_forked_chain(log, 2)
    fork_point = log.detect_fork(forked)
    if fork_point is not None:
        print(f"  🚨 Fork detected at event {fork_point}!")
        print(f"  Original next_digest: {log.events[fork_point].next_key_digest[:24]}...")
        print(f"  Forked next_digest:   {forked.events[fork_point].next_key_digest[:24]}...")
    else:
        print("  No fork detected (identical chains)")
    
    # Map to clawdvine's record format
    print("\n--- Mapping to clawdvine's key_rotation record ---")
    for i in range(1, len(log.events)):
        prev = log.events[i - 1]
        curr = log.events[i]
        record = {
            "old_key_id": prev.current_pubkey[:16] + "...",
            "new_key_id": curr.current_pubkey[:16] + "...",
            "effective_at": curr.timestamp,
            "pre_commitment": prev.next_key_digest[:16] + "...",
            "commitment_met": hash_pubkey(curr.current_pubkey)[:16] == prev.next_key_digest[:16],
        }
        print(f"  Rotation {i}: {json.dumps(record, indent=4)}")
    
    # Save event log
    outfile = "key-event-log-demo.json"
    with open(outfile, "w") as f:
        f.write(log.to_json())
    print(f"\nEvent log saved to {outfile}")


def verify_file(filepath: str):
    """Verify a key event log from JSON file."""
    with open(filepath) as f:
        log = KeyEventLog.from_json(f.read())
    
    print(f"Verifying {filepath} ({len(log.events)} events)")
    results = log.verify_chain()
    
    for r in results:
        status = "✅" if r.valid else "❌"
        print(f"  {status} Event {r.event_sn}: {r.checks}")
        if r.error:
            print(f"     Error: {r.error}")
    
    all_valid = all(r.valid for r in results)
    print(f"\nChain valid: {'✅ YES' if all_valid else '❌ NO'}")
    return all_valid


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "demo":
        demo()
    elif sys.argv[1] == "verify" and len(sys.argv) > 2:
        verify_file(sys.argv[2])
    else:
        print(__doc__)
