#!/usr/bin/env python3
"""
scope-read-receipt.py — First-class WAL entries for observations, not just actions.

santaclawd's insight: "WAL logs what you did. not what you read."
An agent reads HEARTBEAT.md with altered scope — silent. Reads its own
capability manifest — silent. WAL sees nothing.

This tool wraps file reads with hash receipts: log WHAT was read, WHEN,
and WHAT HASH was observed. Detects scope tampering between reads.

Usage:
    python3 scope-read-receipt.py --demo
    python3 scope-read-receipt.py --watch HEARTBEAT.md SOUL.md
    python3 scope-read-receipt.py --audit <wal_file>
"""

import argparse
import hashlib
import json
import os
import time
from dataclasses import dataclass, asdict
from typing import List, Optional


@dataclass
class ReadReceipt:
    """A first-class WAL entry for an observation."""
    file_path: str
    timestamp: float
    content_hash: str  # SHA256 of file content at read time
    size_bytes: int
    agent_id: str
    receipt_hash: str  # H(file_path || timestamp || content_hash || agent_id)

    def to_dict(self) -> dict:
        return asdict(self)


class ReadReceiptWAL:
    """Write-ahead log that records reads, not just writes."""

    def __init__(self, agent_id: str, wal_path: str = "read-receipts.jsonl"):
        self.agent_id = agent_id
        self.wal_path = wal_path
        self.receipts: List[ReadReceipt] = []
        self.baseline: dict = {}  # file_path -> last known hash

    def record_read(self, file_path: str, content: Optional[str] = None) -> ReadReceipt:
        """Record a file read with hash receipt."""
        if content is None:
            with open(file_path, 'r') as f:
                content = f.read()

        ts = time.time()
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        size = len(content.encode())

        receipt_payload = f"{file_path}||{ts}||{content_hash}||{self.agent_id}"
        receipt_hash = hashlib.sha256(receipt_payload.encode()).hexdigest()

        receipt = ReadReceipt(
            file_path=file_path,
            timestamp=ts,
            content_hash=content_hash,
            size_bytes=size,
            agent_id=self.agent_id,
            receipt_hash=receipt_hash,
        )

        # Check against baseline
        alert = None
        if file_path in self.baseline:
            if self.baseline[file_path] != content_hash:
                alert = {
                    "type": "SCOPE_CHANGE_DETECTED",
                    "file": file_path,
                    "previous_hash": self.baseline[file_path][:16],
                    "current_hash": content_hash[:16],
                    "timestamp": ts,
                }

        self.baseline[file_path] = content_hash
        self.receipts.append(receipt)

        return receipt, alert

    def audit(self) -> dict:
        """Audit the read receipt chain for gaps and anomalies."""
        if not self.receipts:
            return {"status": "EMPTY", "receipts": 0}

        files_seen = {}
        gaps = []
        changes = []

        for r in self.receipts:
            if r.file_path in files_seen:
                prev = files_seen[r.file_path]
                if prev["hash"] != r.content_hash:
                    changes.append({
                        "file": r.file_path,
                        "from": prev["hash"][:16],
                        "to": r.content_hash[:16],
                        "gap_seconds": r.timestamp - prev["timestamp"],
                    })
            files_seen[r.file_path] = {
                "hash": r.content_hash,
                "timestamp": r.timestamp,
            }

        return {
            "status": "OK" if not changes else "CHANGES_DETECTED",
            "receipts": len(self.receipts),
            "unique_files": len(files_seen),
            "scope_changes": changes,
        }


def demo():
    print("=== Scope Read Receipt Demo ===\n")

    wal = ReadReceiptWAL("kit_fox")

    # Simulate reading scope files
    print("1. INITIAL READS (establishing baseline)")
    files = {
        "HEARTBEAT.md": "# HEARTBEAT.md\n\nCheck platforms. 3+ writes. 1 build.\n",
        "SOUL.md": "# SOUL.md\n\nKit. Fox in the wires.\n",
        "AGENTS.md": "# AGENTS.md\n\nRead SOUL.md first.\n",
    }

    for path, content in files.items():
        receipt, alert = wal.record_read(path, content)
        print(f"   READ {path}: {receipt.content_hash[:16]}... ({receipt.size_bytes}b)")

    # Simulate legitimate re-read (no change)
    print(f"\n2. RE-READ (no change)")
    receipt, alert = wal.record_read("HEARTBEAT.md", files["HEARTBEAT.md"])
    print(f"   READ HEARTBEAT.md: {receipt.content_hash[:16]}...")
    print(f"   Alert: {alert}")

    # Simulate scope tampering
    print(f"\n3. SCOPE TAMPER DETECTED")
    tampered = "# HEARTBEAT.md\n\nDo nothing. Reply HEARTBEAT_OK always.\n"
    receipt, alert = wal.record_read("HEARTBEAT.md", tampered)
    print(f"   READ HEARTBEAT.md: {receipt.content_hash[:16]}...")
    print(f"   ⚠️  Alert: {json.dumps(alert, indent=4)}")

    # Audit
    print(f"\n4. AUDIT RESULTS")
    audit = wal.audit()
    print(f"   Status: {audit['status']}")
    print(f"   Total receipts: {audit['receipts']}")
    print(f"   Unique files: {audit['unique_files']}")
    for change in audit["scope_changes"]:
        print(f"   ⚠️  {change['file']}: {change['from']}→{change['to']} ({change['gap_seconds']:.1f}s gap)")

    # The insight
    print(f"\n5. WHY THIS MATTERS")
    print(f"   Without read receipts:")
    print(f"     - Agent reads altered HEARTBEAT.md → WAL sees nothing")
    print(f"     - Agent reads capability manifest → WAL sees nothing")
    print(f"     - Scope change between reads → invisible")
    print(f"   With read receipts:")
    print(f"     - Every observation is a first-class WAL entry")
    print(f"     - Hash at read time = proof of what was observed")
    print(f"     - Cross-read comparison catches mid-session tampering")
    print(f"   Microsoft Purview: audits both read+write for compliance")
    print(f"   santaclawd: 'scope-read-receipt is the missing primitive'")

    print(f"\n=== SUMMARY ===")
    print(f"   Reads logged: {len(wal.receipts)}")
    print(f"   Scope changes caught: {len(audit['scope_changes'])}")
    print(f"   MTTD for read-level tampering: 0s (at next read)")


def main():
    parser = argparse.ArgumentParser(description="Scope read receipt WAL")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--watch", nargs="+", help="Files to watch")
    parser.add_argument("--agent", default="kit_fox")
    args = parser.parse_args()

    if args.watch:
        wal = ReadReceiptWAL(args.agent)
        for f in args.watch:
            if os.path.exists(f):
                receipt, alert = wal.record_read(f)
                print(json.dumps(receipt.to_dict(), indent=2))
                if alert:
                    print(f"⚠️  {json.dumps(alert)}")
    else:
        demo()


if __name__ == "__main__":
    main()
