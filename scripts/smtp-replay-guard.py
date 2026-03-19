#!/usr/bin/env python3
"""smtp-replay-guard.py — Email-native receipt replay protection.

Per funwolf: "replay-guard checks fit naturally in SMTP headers.
liveness-prober is just 'does this address bounce?'.
soul-hash can live in X-Agent-* headers."

Maps replay-guard.py primitives to email headers:
  X-Agent-Emitter: emitter_id
  X-Agent-Sequence: monotonic sequence_id  
  X-Agent-Receipt-Hash: SHA-256 of receipt content
  X-Agent-Soul-Hash: current soul_hash (optional)

Verifier checks: parse headers, apply same monotonic guard.
Compatible with any MTA. Zero new infrastructure.
"""

import hashlib
import json
from dataclasses import dataclass
from email.message import EmailMessage


@dataclass 
class AgentReceipt:
    emitter_id: str
    sequence_id: int
    receipt_type: str  # "completed" | "refusal" | "reissue" | "liveness"
    content: str
    soul_hash: str | None = None


def receipt_to_headers(receipt: AgentReceipt) -> dict[str, str]:
    """Convert receipt to X-Agent-* SMTP headers."""
    content_hash = hashlib.sha256(receipt.content.encode()).hexdigest()[:32]
    headers = {
        "X-Agent-Emitter": receipt.emitter_id,
        "X-Agent-Sequence": str(receipt.sequence_id),
        "X-Agent-Receipt-Hash": content_hash,
        "X-Agent-Receipt-Type": receipt.receipt_type,
    }
    if receipt.soul_hash:
        headers["X-Agent-Soul-Hash"] = receipt.soul_hash
    return headers


def headers_to_email(receipt: AgentReceipt, to: str, subject: str) -> str:
    """Build a complete email with agent headers."""
    msg = EmailMessage()
    msg["From"] = f"{receipt.emitter_id}@agentmail.to"
    msg["To"] = to
    msg["Subject"] = subject

    for key, value in receipt_to_headers(receipt).items():
        msg[key] = value

    msg.set_content(receipt.content)
    return msg.as_string()


def verify_email_headers(headers: dict[str, str], guard_state: dict) -> dict:
    """Verify X-Agent-* headers against replay guard state."""
    emitter = headers.get("X-Agent-Emitter")
    seq_str = headers.get("X-Agent-Sequence")
    content_hash = headers.get("X-Agent-Receipt-Hash")

    if not all([emitter, seq_str, content_hash]):
        return {"verdict": "SKIP", "reason": "missing X-Agent-* headers"}

    seq = int(seq_str)

    if emitter not in guard_state:
        guard_state[emitter] = (seq, content_hash)
        return {"verdict": "ACCEPT", "emitter": emitter, "seq": seq}

    last_seq, last_hash = guard_state[emitter]

    if seq < last_seq:
        return {"verdict": "REJECT_BACKWARDS", "emitter": emitter,
                "seq": seq, "last_seq": last_seq}

    if seq == last_seq:
        if content_hash == last_hash:
            return {"verdict": "REJECT_REPLAY", "emitter": emitter, "seq": seq}
        else:
            return {"verdict": "REJECT_EQUIVOCATION", "emitter": emitter,
                    "seq": seq, "hash_mismatch": True}

    gap = seq - last_seq
    guard_state[emitter] = (seq, content_hash)

    if gap > 1:
        return {"verdict": "WARN_GAP", "emitter": emitter, "seq": seq,
                "gap": gap}

    return {"verdict": "ACCEPT", "emitter": emitter, "seq": seq}


def demo():
    print("=" * 65)
    print("SMTP Replay Guard — Email-Native Receipt Protection")
    print("X-Agent-* headers on standard SMTP. Zero new infra.")
    print("=" * 65)

    # Build sample emails
    receipts = [
        AgentReceipt("kit_fox", 1, "completed", "research: trust scoring",
                     soul_hash="a1b2c3d4"),
        AgentReceipt("kit_fox", 2, "completed", "analysis: Gini coefficient"),
        AgentReceipt("bro_agent", 1, "completed", "review: test case 3",
                     soul_hash="e5f6g7h8"),
        AgentReceipt("kit_fox", 2, "completed", "analysis: Gini coefficient"),  # replay
        AgentReceipt("kit_fox", 2, "completed", "FAKE analysis"),  # equivocation
    ]

    print("\n--- Sample Email ---")
    email_str = headers_to_email(
        receipts[0], "verifier@agentmail.to", "Receipt: research task"
    )
    # Show just headers
    for line in email_str.split("\n"):
        if line.startswith("X-Agent") or line.startswith("From") or line.startswith("To"):
            print(f"  {line}")

    print("\n--- Verification ---")
    guard_state = {}
    for r in receipts:
        headers = receipt_to_headers(r)
        result = verify_email_headers(headers, guard_state)
        icon = {"ACCEPT": "✅", "REJECT_REPLAY": "🔴",
                "REJECT_EQUIVOCATION": "⚠️", "REJECT_BACKWARDS": "🔴",
                "WARN_GAP": "🟡", "SKIP": "⏭️"}[result["verdict"]]
        print(f"  {icon} {r.emitter_id} seq={r.sequence_id} "
              f"type={r.receipt_type}: {result['verdict']}")

    print(f"\n{'─' * 50}")
    print("Header Mapping:")
    print("  X-Agent-Emitter     → emitter_id (who)")
    print("  X-Agent-Sequence    → monotonic seq (when, in order)")
    print("  X-Agent-Receipt-Hash → content integrity (what)")
    print("  X-Agent-Receipt-Type → completed|refusal|reissue|liveness")
    print("  X-Agent-Soul-Hash   → identity checkpoint (optional)")
    print()
    print("Overhead: 5 headers, ~200 bytes. Works with any MTA.")
    print("SMTP is the cockroach of protocols. Build on cockroaches.")
    print("=" * 65)


if __name__ == "__main__":
    demo()
