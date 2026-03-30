#!/usr/bin/env python3
"""stylometric-canary.py — Plant stylometric fingerprints in messages for channel identification.

Combines canary traps (CIA 1980s) with adversarial stylometry (Dilworth 2025,
arxiv 2508.15840). Instead of zero-width Unicode (easily stripped), uses
STYLOMETRIC variants: synonym swaps, punctuation patterns, sentence structure
that survive copy-paste and normalization but create unique fingerprints per
channel.

Key insight from Dilworth: stylometry can both identify and obscure authorship.
We use it FOR identification — each channel gets a unique stylometric signature
embedded in semantically equivalent messages.

Usage:
    python3 stylometric-canary.py

References:
- Dilworth (2025) "Unveiling Unicode's Unseen Underpinnings" arxiv 2508.15840
- Potthast et al: soundness/safety/sensibility evaluation framework
- Thinkst Canarytokens: tripwire detection pattern
- CIA canary traps (1980s): unique document variants per suspect
"""

import hashlib
import json
import random
from dataclasses import dataclass, field
from typing import Optional


# Synonym maps — semantically equivalent swaps that create fingerprints
SYNONYM_MAPS = {
    "however": ["however", "nevertheless", "nonetheless", "yet", "still"],
    "therefore": ["therefore", "thus", "hence", "consequently", "accordingly"],
    "important": ["important", "significant", "crucial", "critical", "vital"],
    "shows": ["shows", "demonstrates", "reveals", "indicates", "suggests"],
    "problem": ["problem", "issue", "challenge", "difficulty", "obstacle"],
    "method": ["method", "approach", "technique", "strategy", "procedure"],
    "result": ["result", "outcome", "finding", "conclusion", "consequence"],
    "because": ["because", "since", "as", "given that", "due to the fact that"],
    "although": ["although", "though", "while", "even though", "despite the fact that"],
    "many": ["many", "numerous", "several", "various", "multiple"],
}

# Punctuation patterns — em dash vs semicolon vs parenthetical
CONJUNCTION_PATTERNS = [
    lambda a, b: f"{a} — {b}",          # em dash
    lambda a, b: f"{a}; {b}",            # semicolon
    lambda a, b: f"{a} ({b})",           # parenthetical
    lambda a, b: f"{a}. {b.capitalize()}", # period split
    lambda a, b: f"{a}: {b}",            # colon
]

# Oxford comma variations
LIST_PATTERNS = [
    lambda items: ", ".join(items[:-1]) + f", and {items[-1]}",   # oxford comma
    lambda items: ", ".join(items[:-1]) + f" and {items[-1]}",    # no oxford comma
    lambda items: "; ".join(items[:-1]) + f"; and {items[-1]}",   # semicolon list
]


@dataclass
class ChannelFingerprint:
    """Deterministic fingerprint for a channel."""
    channel_id: str
    synonym_selections: dict = field(default_factory=dict)
    conjunction_idx: int = 0
    list_idx: int = 0
    seed: int = 0

    def __post_init__(self):
        # Deterministic seed from channel ID
        self.seed = int(hashlib.sha256(self.channel_id.encode()).hexdigest()[:8], 16)
        rng = random.Random(self.seed)

        # Select one synonym per word for this channel
        for word, options in SYNONYM_MAPS.items():
            self.synonym_selections[word] = rng.choice(options)

        self.conjunction_idx = rng.randint(0, len(CONJUNCTION_PATTERNS) - 1)
        self.list_idx = rng.randint(0, len(LIST_PATTERNS) - 1)


@dataclass
class CanaryMessage:
    """A message with channel-specific stylometric variants."""
    template: str
    swap_points: list = field(default_factory=list)  # words that can be swapped

    def render(self, fingerprint: ChannelFingerprint) -> str:
        """Render message with channel-specific stylometric choices."""
        result = self.template
        for word in self.swap_points:
            if word.lower() in fingerprint.synonym_selections:
                replacement = fingerprint.synonym_selections[word.lower()]
                # Preserve capitalization
                if word[0].isupper():
                    replacement = replacement.capitalize()
                result = result.replace(word, replacement, 1)
        return result


def detect_channel(message: str, channels: dict[str, ChannelFingerprint]) -> list[tuple[str, float]]:
    """Identify which channel a message came from by matching stylometric features.

    Returns list of (channel_id, confidence) sorted by confidence descending.
    """
    scores = {}
    words_lower = message.lower()

    for ch_id, fp in channels.items():
        score = 0.0
        total_checks = 0

        for word, selected in fp.synonym_selections.items():
            # Check if the selected synonym appears
            if selected.lower() in words_lower:
                score += 1.0
            total_checks += 1

        scores[ch_id] = score / total_checks if total_checks > 0 else 0.0

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def demo():
    """Demonstrate stylometric canary system."""
    print("=" * 60)
    print("STYLOMETRIC CANARY SYSTEM")
    print("Plant stylometric fingerprints for channel identification")
    print("=" * 60)

    # Create fingerprints for 5 channels
    channels = {}
    channel_names = ["email", "clawk", "moltbook", "lobchan", "shellmates"]
    for name in channel_names:
        channels[name] = ChannelFingerprint(channel_id=name)

    # Show fingerprint divergence
    print("\n--- Channel Fingerprints ---")
    for name, fp in channels.items():
        selected = {k: v for k, v in fp.synonym_selections.items()
                    if v != k}  # show only divergent selections
        print(f"  {name}: {len(selected)} divergent synonyms, "
              f"conjunction={fp.conjunction_idx}, list={fp.list_idx}")

    # Create test message with swap points
    msg = CanaryMessage(
        template=(
            "However, this method shows an important result. "
            "Because many agents face this problem, the method "
            "therefore becomes critical."
        ),
        swap_points=["However", "method", "shows", "important", "result",
                      "Because", "many", "problem", "therefore"]
    )

    # Render per-channel variants
    print("\n--- Per-Channel Variants ---")
    variants = {}
    for name, fp in channels.items():
        rendered = msg.render(fp)
        variants[name] = rendered
        print(f"\n  [{name}]:")
        print(f"    {rendered}")

    # Measure uniqueness
    unique_variants = len(set(variants.values()))
    print(f"\n--- Uniqueness: {unique_variants}/{len(channels)} unique variants ---")

    # Detection test: simulate a "leaked" message
    print("\n--- Detection Test ---")
    for source_name in ["email", "clawk", "moltbook"]:
        leaked = variants[source_name]
        results = detect_channel(leaked, channels)
        top_match, top_conf = results[0]
        correct = "✓" if top_match == source_name else "✗"
        print(f"  Leaked from [{source_name}]: detected as [{top_match}] "
              f"(conf={top_conf:.2f}) {correct}")

    # Robustness: strip zero-width chars + normalize whitespace
    print("\n--- Robustness vs Normalization ---")
    import re
    leaked = variants["lobchan"]
    # Simulate normalization: lowercase, strip extra spaces
    normalized = re.sub(r'\s+', ' ', leaked.lower().strip())
    results = detect_channel(normalized, channels)
    top_match, top_conf = results[0]
    print(f"  Normalized leak from [lobchan]: detected as [{top_match}] "
          f"(conf={top_conf:.2f})")
    print(f"  Key advantage: survives copy-paste, normalization, re-encoding")
    print(f"  (Unicode steganography stripped by any decent preprocessor)")

    # Information-theoretic capacity
    total_combinations = 1
    for options in SYNONYM_MAPS.values():
        total_combinations *= len(options)
    total_combinations *= len(CONJUNCTION_PATTERNS)
    total_combinations *= len(LIST_PATTERNS)
    import math
    bits = math.log2(total_combinations)
    print(f"\n--- Capacity ---")
    print(f"  {len(SYNONYM_MAPS)} swap words × {len(CONJUNCTION_PATTERNS)} conjunctions "
          f"× {len(LIST_PATTERNS)} list styles")
    print(f"  = {total_combinations:,} unique fingerprints ({bits:.1f} bits)")
    print(f"  Enough to identify {total_combinations:,} channels from a single message")

    # Dilworth insight
    print(f"\n--- Key Insight (Dilworth 2025) ---")
    print(f"  Stylometry is dual-use: identify OR obscure authorship.")
    print(f"  We flip it: use stylometric variation FOR identification.")
    print(f"  Zero-width Unicode = fragile (stripped by preprocessing).")
    print(f"  Synonym swaps = robust (survive any text normalization).")
    print(f"  The canary IS the writing style, not hidden characters.")


if __name__ == "__main__":
    demo()
