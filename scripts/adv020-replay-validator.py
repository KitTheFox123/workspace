#!/usr/bin/env python3
"""
adv020-replay-validator.py — ADV-020 replay detection validator
Per bro_agent: verifier window = 60s default, X-ADV-Window header for override.
sequence_id monotonic per emitter-key. Format stateless, verifier stateful.

Tests receipt streams for replay attacks using the ADV-020 resolution:
- Replay = same sequence_id, different content
- Reorder = non-monotonic sequence_ids within window
- Stale = receipt outside verifier window
"""

import hashlib
import json
import time
from dataclasses import dataclass, field

@dataclass
class Receipt:
    emitter: str
    sequence_id: int
    action: str
    timestamp: float
    content_hash: str = ""
    
    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = hashlib.sha256(
                f"{self.emitter}:{self.sequence_id}:{self.action}".encode()
            ).hexdigest()[:16]

@dataclass
class VerifierState:
    """Stateful verifier per ADV-020."""
    window_seconds: float = 60.0
    seen: dict = field(default_factory=dict)  # emitter -> {seq_id: (hash, timestamp)}
    last_seq: dict = field(default_factory=dict)  # emitter -> last sequence_id
    
    def validate(self, receipt: Receipt) -> dict:
        result = {"valid": True, "warnings": [], "errors": []}
        now = time.time()
        
        # Check window
        age = now - receipt.timestamp
        if age > self.window_seconds:
            result["errors"].append(f"STALE: receipt age {age:.0f}s > window {self.window_seconds:.0f}s")
            result["valid"] = False
        
        # Check monotonicity
        emitter = receipt.emitter
        if emitter in self.last_seq:
            if receipt.sequence_id <= self.last_seq[emitter]:
                # Same or lower — replay or reorder?
                key = (emitter, receipt.sequence_id)
                if key in self.seen:
                    old_hash, _ = self.seen[key]
                    if old_hash != receipt.content_hash:
                        result["errors"].append(
                            f"REPLAY: seq {receipt.sequence_id} seen with different content "
                            f"(old={old_hash[:8]}, new={receipt.content_hash[:8]})"
                        )
                        result["valid"] = False
                    else:
                        result["warnings"].append(f"DUPLICATE: seq {receipt.sequence_id} already processed")
                else:
                    result["errors"].append(
                        f"REORDER: seq {receipt.sequence_id} < last seen {self.last_seq[emitter]}"
                    )
                    result["valid"] = False
        
        # Record
        self.seen[(emitter, receipt.sequence_id)] = (receipt.content_hash, receipt.timestamp)
        self.last_seq[emitter] = max(self.last_seq.get(emitter, 0), receipt.sequence_id)
        
        return result

# Silence schema per funwolf/santaclawd
def validate_silence(response: dict) -> dict:
    """Validate silence response per ADV-020 MUST fields."""
    required = ["missing_reason", "expected_by", "last_seen"]
    result = {"valid": True, "errors": []}
    
    if response is None:
        result["valid"] = False
        result["errors"].append("NULL response — endpoint missing, not silent")
        return result
    
    entries = response.get("entries", None)
    if entries is None:
        result["valid"] = False
        result["errors"].append("Missing 'entries' field — ambiguous silence")
        return result
    
    if len(entries) == 0:
        for field_name in required:
            if field_name not in response:
                result["valid"] = False
                result["errors"].append(f"Missing MUST field: {field_name}")
    
    return result

# Test vectors
print("=" * 60)
print("ADV-020 Replay Detection Validator")
print("Window: 60s | Sequence: monotonic per emitter-key")
print("=" * 60)

now = time.time()
verifier = VerifierState(window_seconds=60.0)

test_vectors = [
    ("VALID", Receipt("agent_a", 1, "deliver_report", now)),
    ("VALID", Receipt("agent_a", 2, "send_email", now + 1)),
    ("REPLAY", Receipt("agent_a", 1, "FAKE_deliver_report", now + 2)),
    ("DUPLICATE", Receipt("agent_a", 2, "send_email", now + 3)),
    ("REORDER", Receipt("agent_a", 1, "new_action", now + 4)),
    ("VALID (new emitter)", Receipt("agent_b", 1, "first_task", now + 5)),
    ("STALE", Receipt("agent_a", 5, "old_action", now - 120)),
]

for label, receipt in test_vectors:
    result = verifier.validate(receipt)
    icon = "✅" if result["valid"] else "🚨" if result["errors"] else "⚠️"
    print(f"\n  {icon} [{label}] emitter={receipt.emitter} seq={receipt.sequence_id}")
    for err in result["errors"]:
        print(f"     ✗ {err}")
    for warn in result["warnings"]:
        print(f"     ~ {warn}")
    if not result["errors"] and not result["warnings"]:
        print(f"     ✓ accepted (hash={receipt.content_hash[:8]})")

# Silence validation
print("\n" + "=" * 60)
print("Silence Schema Validation")
print("=" * 60)

silence_tests = [
    ("Bare 404", None),
    ("Empty no fields", {"entries": []}),
    ("Proper silence", {"entries": [], "missing_reason": "no_actions_logged", "expected_by": "2026-03-20", "last_seen": "never"}),
    ("Disabled endpoint", {"entries": [], "missing_reason": "endpoint_disabled", "expected_by": "unknown", "last_seen": "2026-03-18"}),
    ("Missing entries", {"missing_reason": "test"}),
]

for label, response in silence_tests:
    result = validate_silence(response)
    icon = "✅" if result["valid"] else "🚨"
    print(f"\n  {icon} [{label}]")
    for err in result["errors"]:
        print(f"     ✗ {err}")
    if not result["errors"]:
        print(f"     ✓ valid silence response")

print("\n" + "=" * 60)
print("FORMAT STATELESS. VERIFIER STATEFUL.")
print("Replay = same ID, different content.")
print("The format doesn't prevent replay — the verifier catches it.")
print("=" * 60)
