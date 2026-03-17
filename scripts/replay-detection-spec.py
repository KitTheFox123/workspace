#!/usr/bin/env python3
"""
replay-detection-spec.py — ADV-020 resolution: replay detection for L3.5 receipts.

Per funwolf (2026-03-17): single receipt can't prove uniqueness alone.
Two paths: nonce+timestamp (stateless) OR prior_receipt_hash (stateful).
Resolution: MUST nonce, SHOULD chain.

This script implements and tests both mechanisms.
"""

import hashlib
import json
import time
import secrets
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ReplayProtectedReceipt:
    """Receipt with replay detection fields per ADV-020 resolution."""
    receipt_id: str = ""
    agent_id: str = ""
    task_hash: str = ""
    timestamp: str = ""
    
    # MUST: Stateless replay detection (any verifier can check)
    nonce: str = ""  # MUST be unique per receipt. 128-bit minimum.
    
    # SHOULD: Stateful replay detection (auditor needs history)
    prior_receipt_hash: Optional[str] = None  # SHA-256 of previous receipt
    sequence_number: Optional[int] = None  # Monotonic counter
    
    def canonical(self) -> str:
        d = {k: v for k, v in self.__dict__.items() if v is not None and k != 'receipt_id'}
        return json.dumps(d, sort_keys=True, separators=(',', ':'))
    
    def compute_hash(self) -> str:
        return hashlib.sha256(self.canonical().encode()).hexdigest()


class StatelessDetector:
    """Nonce + timestamp window. Any verifier, no state needed beyond window."""
    
    def __init__(self, window_seconds: int = 300):
        self.window = window_seconds
        self.seen_nonces: set = set()  # Bounded by window
    
    def check(self, receipt: ReplayProtectedReceipt, current_time: float) -> dict:
        errors = []
        
        # MUST have nonce
        if not receipt.nonce:
            errors.append("MISSING_NONCE: receipt MUST include nonce")
        elif len(receipt.nonce) < 32:  # 128-bit = 32 hex chars
            errors.append(f"WEAK_NONCE: {len(receipt.nonce)} chars < 32 minimum")
        
        # Nonce uniqueness within window
        if receipt.nonce in self.seen_nonces:
            errors.append(f"REPLAY_DETECTED: nonce {receipt.nonce[:8]}... already seen")
        
        # Timestamp freshness
        try:
            # Simple epoch check
            ts = float(receipt.timestamp) if receipt.timestamp.replace('.', '').isdigit() else current_time
            if abs(current_time - ts) > self.window:
                errors.append(f"STALE_RECEIPT: timestamp {self.window}s outside window")
        except (ValueError, AttributeError):
            errors.append("INVALID_TIMESTAMP")
        
        if not errors:
            self.seen_nonces.add(receipt.nonce)
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'method': 'stateless',
            'window_seconds': self.window,
        }


class StatefulDetector:
    """Hash chain + sequence numbers. Auditor needs full history."""
    
    def __init__(self):
        self.chains: dict = {}  # agent_id -> [receipt_hashes]
        self.sequences: dict = {}  # agent_id -> last_sequence
    
    def check(self, receipt: ReplayProtectedReceipt) -> dict:
        errors = []
        warnings = []
        agent = receipt.agent_id
        
        # Chain integrity
        if receipt.prior_receipt_hash is not None:
            if agent in self.chains and self.chains[agent]:
                expected = self.chains[agent][-1]
                if receipt.prior_receipt_hash != expected:
                    errors.append(
                        f"CHAIN_BREAK: prior_receipt_hash={receipt.prior_receipt_hash[:16]}... "
                        f"!= expected={expected[:16]}..."
                    )
            elif agent not in self.chains:
                # First receipt with chain reference — genesis
                warnings.append("GENESIS_CHAIN: first receipt references prior, unverifiable")
        else:
            warnings.append("NO_CHAIN: receipt lacks prior_receipt_hash (SHOULD include)")
        
        # Sequence monotonicity
        if receipt.sequence_number is not None:
            if agent in self.sequences:
                if receipt.sequence_number <= self.sequences[agent]:
                    errors.append(
                        f"SEQUENCE_REGRESSION: {receipt.sequence_number} "
                        f"<= last seen {self.sequences[agent]}"
                    )
            self.sequences[agent] = max(
                self.sequences.get(agent, 0), 
                receipt.sequence_number
            )
        
        # Record
        if not errors:
            if agent not in self.chains:
                self.chains[agent] = []
            self.chains[agent].append(receipt.compute_hash())
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'method': 'stateful',
            'chain_length': len(self.chains.get(agent, [])),
        }


class CombinedDetector:
    """Both stateless AND stateful. Belt and suspenders."""
    
    def __init__(self, window_seconds: int = 300):
        self.stateless = StatelessDetector(window_seconds)
        self.stateful = StatefulDetector()
    
    def check(self, receipt: ReplayProtectedReceipt, current_time: float) -> dict:
        sl = self.stateless.check(receipt, current_time)
        sf = self.stateful.check(receipt)
        
        all_errors = sl['errors'] + sf['errors']
        all_warnings = sf.get('warnings', [])
        
        return {
            'valid': len(all_errors) == 0,
            'errors': all_errors,
            'warnings': all_warnings,
            'stateless': sl,
            'stateful': sf,
        }


def demo():
    """Demonstrate replay detection — the ADV-020 resolution."""
    print("=" * 60)
    print("ADV-020 RESOLUTION: Replay Detection for L3.5 Receipts")
    print("MUST nonce (stateless). SHOULD chain (stateful).")
    print("=" * 60)
    
    detector = CombinedDetector(window_seconds=300)
    now = time.time()
    
    # 1. Valid receipt with both protections
    r1 = ReplayProtectedReceipt(
        agent_id="agent:kit_fox",
        task_hash="sha256:abc123",
        timestamp=str(now),
        nonce=secrets.token_hex(16),
        prior_receipt_hash=None,  # Genesis
        sequence_number=1,
    )
    result = detector.check(r1, now)
    print(f"\n[1] Valid receipt (genesis): {'✅' if result['valid'] else '❌'}")
    if result['warnings']:
        print(f"    Warnings: {result['warnings']}")
    
    # 2. Valid chained receipt
    r2 = ReplayProtectedReceipt(
        agent_id="agent:kit_fox",
        task_hash="sha256:def456",
        timestamp=str(now + 10),
        nonce=secrets.token_hex(16),
        prior_receipt_hash=r1.compute_hash(),
        sequence_number=2,
    )
    result = detector.check(r2, now + 10)
    print(f"[2] Valid chained receipt: {'✅' if result['valid'] else '❌'}")
    
    # 3. REPLAY: same nonce
    r3_replay = ReplayProtectedReceipt(
        agent_id="agent:kit_fox",
        task_hash="sha256:def456",
        timestamp=str(now + 20),
        nonce=r2.nonce,  # REPLAY!
        prior_receipt_hash=r2.compute_hash(),
        sequence_number=3,
    )
    result = detector.check(r3_replay, now + 20)
    print(f"[3] Replay (same nonce): {'✅' if result['valid'] else '❌'} {result['errors']}")
    
    # 4. CHAIN BREAK: wrong prior hash
    r4_fork = ReplayProtectedReceipt(
        agent_id="agent:kit_fox",
        task_hash="sha256:ghi789",
        timestamp=str(now + 30),
        nonce=secrets.token_hex(16),
        prior_receipt_hash="sha256:WRONG",
        sequence_number=3,
    )
    result = detector.check(r4_fork, now + 30)
    print(f"[4] Chain break (wrong prior): {'✅' if result['valid'] else '❌'} {result['errors']}")
    
    # 5. SEQUENCE REGRESSION
    r5_regress = ReplayProtectedReceipt(
        agent_id="agent:kit_fox",
        task_hash="sha256:jkl012",
        timestamp=str(now + 40),
        nonce=secrets.token_hex(16),
        sequence_number=1,  # REGRESSION!
    )
    result = detector.check(r5_regress, now + 40)
    print(f"[5] Sequence regression: {'✅' if result['valid'] else '❌'} {result['errors']}")
    
    # 6. STALE receipt
    r6_stale = ReplayProtectedReceipt(
        agent_id="agent:kit_fox",
        task_hash="sha256:mno345",
        timestamp=str(now - 600),  # 10 min old, window is 5 min
        nonce=secrets.token_hex(16),
        sequence_number=4,
    )
    result = detector.check(r6_stale, now)
    print(f"[6] Stale receipt (10m old): {'✅' if result['valid'] else '❌'} {result['errors']}")
    
    # 7. No nonce (MUST fail)
    r7_no_nonce = ReplayProtectedReceipt(
        agent_id="agent:kit_fox",
        task_hash="sha256:pqr678",
        timestamp=str(now + 50),
        sequence_number=5,
    )
    result = detector.check(r7_no_nonce, now + 50)
    print(f"[7] Missing nonce: {'✅' if result['valid'] else '❌'} {result['errors']}")
    
    # 8. No chain (SHOULD warn, not fail)
    r8_no_chain = ReplayProtectedReceipt(
        agent_id="agent:new_agent",
        task_hash="sha256:stu901",
        timestamp=str(now + 60),
        nonce=secrets.token_hex(16),
    )
    result = detector.check(r8_no_chain, now + 60)
    print(f"[8] No chain (SHOULD warn): {'✅' if result['valid'] else '❌'} warnings={result['warnings']}")
    
    print(f"\n{'=' * 60}")
    print("SPEC RESOLUTION:")
    print("  nonce: MUST (128-bit minimum, unique per receipt)")
    print("  prior_receipt_hash: SHOULD (SHA-256 of previous)")
    print("  sequence_number: SHOULD (monotonic counter)")
    print("  timestamp window: 300s default, consumer-configurable")
    print(f"{'=' * 60}")
    print("\nfunwolf was right: stateless is portable, stateful is auditable.")
    print("The spec needs both. MUST the cheap one, SHOULD the strong one.")


if __name__ == '__main__':
    demo()
