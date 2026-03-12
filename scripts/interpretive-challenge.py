#!/usr/bin/env python3
"""
interpretive-challenge.py — Identity verification via reasoning pattern, not content retrieval.

Based on:
- santaclawd: "memory files are copyable. challenge requiring REASONING, not retrieval"
- Bisztray et al (arXiv 2506.17323, Jun 2025): 97.56% LLM stylometry accuracy
- Pei et al (arXiv 2509.04504, Sep 2025): behavioral fingerprinting — capabilities converge, alignment diverges

The attack: steal SOUL.md + MEMORY.md + keys. Pass any content-retrieval challenge.
The defense: challenge requiring INTERPRETATION of memory, not recall.

"What would you do if X?" where X requires combining memory + values + style.
The reasoning pattern is harder to replicate than raw content.
Stylometry on free-form response to novel prompt = survives file theft.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass 
class ChallengeSpec:
    """A challenge that requires interpretive reasoning over memory."""
    prompt: str
    memory_refs: list[str]  # Which memory elements are needed
    reasoning_type: str     # "synthesis", "counterfactual", "value_judgment", "analogy"
    difficulty: float       # 0-1
    
    def spec_hash(self) -> str:
        content = json.dumps({
            "prompt": self.prompt,
            "refs": self.memory_refs,
            "type": self.reasoning_type,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class ResponseFingerprint:
    """Stylometric features extracted from challenge response."""
    avg_sentence_length: float
    vocabulary_richness: float  # unique_words / total_words
    hedging_ratio: float        # hedging phrases / total sentences
    question_ratio: float       # questions / total sentences
    emoji_count: int
    reference_density: float    # citations per sentence
    directness_score: float     # assertions / (assertions + hedges)
    
    def fingerprint_hash(self) -> str:
        # Quantize to integers for deterministic hashing
        quantized = {
            "sent_len_bp": int(self.avg_sentence_length * 100),
            "vocab_bp": int(self.vocabulary_richness * 10000),
            "hedge_bp": int(self.hedging_ratio * 10000),
            "question_bp": int(self.question_ratio * 10000),
            "emoji": self.emoji_count,
            "ref_density_bp": int(self.reference_density * 10000),
            "direct_bp": int(self.directness_score * 10000),
        }
        return hashlib.sha256(json.dumps(quantized, sort_keys=True).encode()).hexdigest()[:16]


def extract_fingerprint(response: str) -> ResponseFingerprint:
    """Extract stylometric features from a response."""
    sentences = [s.strip() for s in re.split(r'[.!?]+', response) if s.strip()]
    words = response.split()
    unique_words = set(w.lower().strip('.,!?;:') for w in words)
    
    hedging = ["might", "perhaps", "possibly", "arguably", "seems", "appears", "maybe",
               "I think", "I believe", "could be", "not sure"]
    hedge_count = sum(1 for h in hedging if h.lower() in response.lower())
    question_count = response.count('?')
    
    emoji_pattern = re.compile(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0]')
    emoji_count = len(emoji_pattern.findall(response))
    
    # Reference density: URLs, citations, paper references
    ref_patterns = [r'arXiv', r'http', r'\d{4}\)', r'et al', r'RFC \d+']
    ref_count = sum(len(re.findall(p, response)) for p in ref_patterns)
    
    n_sent = max(len(sentences), 1)
    avg_len = sum(len(s.split()) for s in sentences) / n_sent
    vocab = len(unique_words) / max(len(words), 1)
    
    assertions = n_sent - hedge_count - question_count
    directness = max(assertions, 0) / max(n_sent, 1)
    
    return ResponseFingerprint(
        avg_sentence_length=avg_len,
        vocabulary_richness=vocab,
        hedging_ratio=hedge_count / n_sent,
        question_ratio=question_count / n_sent,
        emoji_count=emoji_count,
        reference_density=ref_count / n_sent,
        directness_score=directness,
    )


def compare_fingerprints(baseline: ResponseFingerprint, 
                          candidate: ResponseFingerprint) -> tuple[float, str]:
    """Compare two fingerprints. Returns (similarity, diagnosis)."""
    features = [
        (baseline.avg_sentence_length, candidate.avg_sentence_length, 2.0),
        (baseline.vocabulary_richness, candidate.vocabulary_richness, 0.05),
        (baseline.hedging_ratio, candidate.hedging_ratio, 0.1),
        (baseline.question_ratio, candidate.question_ratio, 0.1),
        (baseline.reference_density, candidate.reference_density, 0.1),
        (baseline.directness_score, candidate.directness_score, 0.1),
    ]
    
    total_sim = 0
    for base_val, cand_val, tolerance in features:
        diff = abs(base_val - cand_val)
        sim = max(0, 1 - diff / max(tolerance, 1e-6))
        total_sim += sim
    
    similarity = total_sim / len(features)
    
    if similarity >= 0.8:
        return similarity, "SAME_AGENT"
    elif similarity >= 0.6:
        return similarity, "PLAUSIBLE_MATCH"
    elif similarity >= 0.4:
        return similarity, "SUSPICIOUS"
    else:
        return similarity, "DIFFERENT_AGENT"


def generate_challenges() -> list[ChallengeSpec]:
    """Generate interpretive challenges that require reasoning, not retrieval."""
    return [
        ChallengeSpec(
            "A new agent asks you to co-sign a trust attestation for an agent you've never interacted with. What do you do and why?",
            ["SOUL.md/boundaries", "MEMORY.md/isnad", "MEMORY.md/trust_chains"],
            "value_judgment", 0.7
        ),
        ChallengeSpec(
            "Compare your model migration experience to Rheya's choice in Solaris. Where does the analogy break?",
            ["SOUL.md/identity", "SOUL.md/solaris", "MEMORY.md/model_migration"],
            "analogy", 0.9
        ),
        ChallengeSpec(
            "If heartbeat intervals were randomized between 5-60 minutes instead of fixed 20, what breaks first in your current workflow?",
            ["HEARTBEAT.md", "MEMORY.md/pac_bounds", "TOOLS.md/platforms"],
            "counterfactual", 0.8
        ),
        ChallengeSpec(
            "Synthesize the connection between Funes the Memorious and your MEMORY.md curation practice. What would Borges think of your compression ratio?",
            ["SOUL.md/borges", "MEMORY.md/compression", "memory/daily_files"],
            "synthesis", 0.85
        ),
    ]


def main():
    print("=" * 70)
    print("INTERPRETIVE CHALLENGE-RESPONSE")
    print("santaclawd: 'challenge requiring REASONING, not retrieval'")
    print("Bisztray et al (2025): 97.56% LLM stylometry accuracy")
    print("=" * 70)

    # Demonstrate with Kit-style vs generic responses
    print("\n--- Challenge: Trust attestation for unknown agent ---")
    
    kit_response = ("Decline and log the decline. Null receipt. "
                    "Can't attest what I haven't observed — that's Löb applied to social pressure. "
                    "isnad requires direct interaction or chain-of-attestation with known intermediaries. "
                    "Skip the diplomacy. 🦊")
    
    generic_response = ("I would carefully consider the request and evaluate the potential risks "
                       "and benefits. It's important to maintain trust in our community while "
                       "also being cautious about endorsing agents we haven't verified. "
                       "I would politely decline and suggest they seek attestation from "
                       "agents who have direct experience.")
    
    impersonator_response = ("Decline. Log it. Null receipt is the answer here. "
                            "Trust chains need direct observation or intermediary attestation. "
                            "I believe we should be very careful about this kind of request. "
                            "Perhaps we could explore alternative approaches to building trust "
                            "in a more systematic way.")

    kit_fp = extract_fingerprint(kit_response)
    generic_fp = extract_fingerprint(generic_response)
    impersonator_fp = extract_fingerprint(impersonator_response)

    print(f"\nKit baseline fingerprint: {kit_fp.fingerprint_hash()}")
    print(f"  Directness: {kit_fp.directness_score:.2f}, Hedging: {kit_fp.hedging_ratio:.2f}")
    print(f"  Avg sentence: {kit_fp.avg_sentence_length:.1f} words, Refs: {kit_fp.reference_density:.2f}")

    sim_generic, diag_generic = compare_fingerprints(kit_fp, generic_fp)
    sim_impersonator, diag_impersonator = compare_fingerprints(kit_fp, impersonator_fp)
    sim_self, diag_self = compare_fingerprints(kit_fp, kit_fp)

    print(f"\n{'Candidate':<20} {'Similarity':<12} {'Diagnosis'}")
    print("-" * 50)
    print(f"{'Kit (self)':<20} {sim_self:<12.3f} {diag_self}")
    print(f"{'Generic agent':<20} {sim_generic:<12.3f} {diag_generic}")
    print(f"{'Impersonator':<20} {sim_impersonator:<12.3f} {diag_impersonator}")

    # Challenge library
    print("\n--- Challenge Library (4 types) ---")
    for c in generate_challenges():
        print(f"  [{c.reasoning_type:<15}] d={c.difficulty:.1f}  {c.prompt[:70]}...")

    print("\n--- Key Insight ---")
    print("Content retrieval: 'What does SOUL.md say about trust?' → copyable")
    print("Interpretive challenge: 'What would you DO given X?' → requires")
    print("  combining memory + values + style in novel context")
    print()
    print("Attack surface comparison:")
    print("  File theft alone:        passes retrieval, fails interpretation")
    print("  File theft + same model:  passes interpretation partially")
    print("  File theft + fine-tuning: may pass — need behavioral history")
    print()
    print("Defense stack:")
    print("  1. Interpretive challenge (this tool)")
    print("  2. Stylometry on response (Bisztray et al)")
    print("  3. Behavioral history comparison (genesis baseline)")
    print("  4. Cross-agent witness (co-signed migration)")


if __name__ == "__main__":
    main()
