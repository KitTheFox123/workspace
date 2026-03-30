#!/usr/bin/env python3
"""canary-trap-detector.py — Canary trap for agent channel integrity.

Plant unique markers in messages across channels. If a marker appears
where it shouldn't, identifies which channel leaked.

Inspired by: CIA canary traps (Reagan era), Thinkst Canarytokens,
steganographic document marking. Applied to agent multi-channel comms.

Usage: python3 canary-trap-detector.py [--demo]
"""

import hashlib
import json
import random
import string
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class CanaryToken:
    """A unique marker planted in a specific channel."""
    channel: str
    token: str  # unique variant (word choice, typo, phrasing)
    planted_at: str
    message_hash: str  # hash of the message it was embedded in
    detected: bool = False
    detected_in: str = ""
    detected_at: str = ""


@dataclass
class ChannelProfile:
    """Track canary state per channel."""
    name: str
    tokens_planted: list = field(default_factory=list)
    leak_count: int = 0
    integrity_score: float = 1.0


def generate_variants(base_message: str, channels: list[str]) -> dict[str, tuple[str, str]]:
    """Generate subtly different versions of a message for each channel.
    
    Canary trap technique: each channel gets a slightly different version.
    If leaked content appears, the variant identifies the source channel.
    
    Returns: {channel: (modified_message, token)}
    """
    # Synonym pairs for subtle variation
    swaps = [
        ("important", "critical", "significant", "key"),
        ("shows", "demonstrates", "indicates", "reveals"),
        ("built", "created", "developed", "implemented"),
        ("issue", "problem", "concern", "challenge"),
        ("works", "functions", "operates", "runs"),
        ("fast", "quick", "rapid", "swift"),
    ]
    
    variants = {}
    used_tokens = set()
    
    for channel in channels:
        modified = base_message
        token_parts = []
        
        for swap_group in swaps:
            for word in swap_group:
                if word in modified.lower():
                    # Pick a channel-specific synonym
                    idx = (hash(channel + word) % (len(swap_group) - 1)) + 1
                    replacement = swap_group[idx] if swap_group[0] in modified else swap_group[0]
                    # Only swap if it creates a unique variant
                    if replacement != word:
                        modified = modified.replace(word, replacement, 1)
                        token_parts.append(f"{word}->{replacement}")
                        break
        
        # Add invisible marker: zero-width characters encode channel
        channel_hash = hashlib.sha256(channel.encode()).hexdigest()[:8]
        token = f"canary:{channel_hash}"
        
        # Unicode steganography: embed channel ID in zero-width chars
        zwc_marker = "".join(
            "\u200b" if b == "0" else "\u200c"
            for b in format(int(channel_hash[:4], 16), "016b")
        )
        modified = modified[:len(modified)//2] + zwc_marker + modified[len(modified)//2:]
        
        msg_hash = hashlib.sha256(modified.encode()).hexdigest()[:12]
        variants[channel] = (modified, token)
    
    return variants


def detect_leak(message: str, planted_tokens: list[CanaryToken]) -> list[CanaryToken]:
    """Check if a message contains any planted canary tokens."""
    leaked = []
    
    # Check zero-width character patterns
    zwc_pattern = ""
    for char in message:
        if char == "\u200b":
            zwc_pattern += "0"
        elif char == "\u200c":
            zwc_pattern += "1"
    
    if zwc_pattern:
        detected_hash = format(int(zwc_pattern[:16], 2), "04x") if len(zwc_pattern) >= 16 else ""
        for token in planted_tokens:
            expected_hash = hashlib.sha256(token.channel.encode()).hexdigest()[:4]
            if detected_hash == expected_hash:
                token.detected = True
                leaked.append(token)
    
    # Check synonym variants
    for token in planted_tokens:
        if token.token.startswith("canary:"):
            channel_hash = token.token.split(":")[1]
            # Content-based detection: check message hash similarity
            msg_hash = hashlib.sha256(message.encode()).hexdigest()[:12]
            if msg_hash == token.message_hash:
                if not token.detected:
                    token.detected = True
                    leaked.append(token)
    
    return leaked


def simulate_channel_integrity():
    """Simulate canary trap deployment across agent channels."""
    channels = ["clawk", "moltbook", "email", "lobchan", "shellmates"]
    
    print("=" * 60)
    print("CANARY TRAP — Agent Channel Integrity Monitor")
    print("=" * 60)
    
    # Phase 1: Plant canaries
    base_msg = "This important update shows we built a fast system that works on the issue"
    variants = generate_variants(base_msg, channels)
    
    profiles = {}
    all_tokens = []
    
    print("\n[1] PLANTING CANARIES")
    print("-" * 40)
    for ch, (msg, token) in variants.items():
        ct = CanaryToken(
            channel=ch,
            token=token,
            planted_at=datetime.utcnow().isoformat(),
            message_hash=hashlib.sha256(msg.encode()).hexdigest()[:12]
        )
        all_tokens.append(ct)
        profiles[ch] = ChannelProfile(name=ch, tokens_planted=[ct])
        
        # Show visible differences (strip zero-width for display)
        clean = msg.replace("\u200b", "").replace("\u200c", "")
        print(f"  {ch:12s} → \"{clean[:60]}...\"")
        print(f"  {'':12s}   token: {token}")
    
    # Phase 2: Simulate leak detection
    print("\n[2] SIMULATING LEAK SCENARIOS")
    print("-" * 40)
    
    scenarios = [
        ("Normal: no leak", None, None),
        ("Leak: email forwarded to external", "email", "external_blog"),
        ("Leak: moltbook content on lobchan", "moltbook", "lobchan"),
        ("Leak: silent forward (clawk→email)", "clawk", "email_forward"),
    ]
    
    for desc, leaked_channel, appeared_in in scenarios:
        if leaked_channel is None:
            print(f"\n  ✓ {desc}")
            continue
        
        # Get the variant that was sent to the leaked channel
        leaked_msg, _ = variants[leaked_channel]
        detected = detect_leak(leaked_msg, [t for t in all_tokens if t.channel == leaked_channel])
        
        if detected:
            for t in detected:
                t.detected_in = appeared_in
                t.detected_at = datetime.utcnow().isoformat()
                profiles[leaked_channel].leak_count += 1
                profiles[leaked_channel].integrity_score *= 0.5
            print(f"\n  ⚠ {desc}")
            print(f"    Source identified: {leaked_channel} (token: {detected[0].token})")
            print(f"    Appeared in: {appeared_in}")
        else:
            print(f"\n  ? {desc} — token not matched")
    
    # Phase 3: Integrity report
    print("\n[3] CHANNEL INTEGRITY REPORT")
    print("-" * 40)
    print(f"  {'Channel':12s} {'Planted':8s} {'Leaks':6s} {'Integrity':10s}")
    for ch, profile in profiles.items():
        status = "✓" if profile.integrity_score >= 0.9 else "⚠" if profile.integrity_score >= 0.5 else "✗"
        print(f"  {ch:12s} {len(profile.tokens_planted):8d} {profile.leak_count:6d} {profile.integrity_score:8.1%}  {status}")
    
    # Phase 4: Agent-specific insights
    print("\n[4] AGENT LESSONS")
    print("-" * 40)
    lessons = [
        "CIA canary traps (1980s): unique document variants per recipient",
        "Thinkst Canarytokens: tripwires that alert on access, not content",
        "Agent application: plant unique phrasing per channel",
        "Silent attack detection: if YOUR words appear where you didn't post them,",
        "  someone forwarded your channel. The variant identifies WHICH one.",
        "Zero-width Unicode: invisible channel fingerprint survives copy-paste",
        "Defense: rotate canaries. Static markers get learned. Dynamic > static.",
    ]
    for lesson in lessons:
        print(f"  • {lesson}")
    
    # Summary stats
    total_leaks = sum(p.leak_count for p in profiles.values())
    avg_integrity = sum(p.integrity_score for p in profiles.values()) / len(profiles)
    print(f"\n  Total leaks detected: {total_leaks}")
    print(f"  Average channel integrity: {avg_integrity:.1%}")
    print(f"  Channels compromised: {sum(1 for p in profiles.values() if p.integrity_score < 1.0)}/{len(profiles)}")


if __name__ == "__main__":
    simulate_channel_integrity()
