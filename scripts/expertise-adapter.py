#!/usr/bin/env python3
"""
expertise-adapter.py — Expertise Reversal Effect detector for agent prompts.

Based on Kalyuga 2007: scaffolding that helps novices HARMS experts.
Analyzes a prompt/message to estimate domain expertise level,
then recommends appropriate scaffolding level.

Signals used:
- Jargon density (domain-specific terms vs total words)
- Question specificity (vague "how do I" vs precise "why does X behave as Y")
- Assumed knowledge (references to concepts without explanation)
- Hedging language (uncertainty markers)

Usage:
  echo "How do I make a POST request?" | python3 expertise-adapter.py
  echo "Why does my CORS preflight fail with 403 on PUT but not POST?" | python3 expertise-adapter.py
"""

import sys
import re
from collections import Counter

# Expertise signal words (domain: computing/programming)
JARGON = {
    # Low-level
    'api', 'endpoint', 'cors', 'preflight', 'websocket', 'tcp', 'udp',
    'mutex', 'semaphore', 'deadlock', 'race condition', 'atomicity',
    'syscall', 'kernel', 'userspace', 'mmap', 'epoll', 'kqueue',
    # Web
    'middleware', 'orm', 'csrf', 'xss', 'jwt', 'oauth', 'openid',
    'graphql', 'grpc', 'protobuf', 'webhook', 'idempotent', 'idempotency',
    # Infra
    'kubernetes', 'k8s', 'docker', 'containerize', 'orchestration',
    'terraform', 'ansible', 'ci/cd', 'pipeline', 'canary deploy',
    # Data
    'sharding', 'replication', 'consensus', 'raft', 'paxos', 'crdt',
    'eventual consistency', 'linearizability', 'serializability',
    # Crypto
    'ed25519', 'ecdsa', 'hmac', 'sha256', 'merkle', 'attestation',
    'x509', 'certificate', 'tls', 'mtls',
    # Agent-specific
    'mcp', 'tool_use', 'function_calling', 'rag', 'embedding',
    'tokenizer', 'context window', 'system prompt', 'fine-tune',
    'lora', 'qlora', 'rlhf', 'dpo', 'grpo',
}

NOVICE_PATTERNS = [
    r'\bhow (?:do|can|would) (?:i|you|we)\b',
    r'\bwhat is (?:a |an |the )?\b',
    r'\bcan (?:someone|anyone|you) explain\b',
    r'\bi\'?m (?:new|confused|stuck|lost|beginner)\b',
    r'\bwhere do i start\b',
    r'\bstep by step\b',
    r'\beli5\b',
    r'\bfor dummies\b',
    r'\btutorial\b',
    r'\bbasic[s]?\b',
]

EXPERT_PATTERNS = [
    r'\bwhy does .+ (?:fail|break|behave|return|throw)\b',
    r'\btradeoff[s]? between\b',
    r'\bcompared to\b',
    r'\binstead of\b',
    r'\bperformance (?:of|with|under|regression)\b',
    r'\bedge case\b',
    r'\bundefined behavior\b',
    r'\brace condition\b',
    r'\bbackpressure\b',
    r'\binvariant\b',
    r'\bimplication[s]? (?:of|for)\b',
]

HEDGING = [
    r'\bmaybe\b', r'\bperhaps\b', r'\bi think\b', r'\bi guess\b',
    r'\bnot sure\b', r'\bprobably\b', r'\bmight be\b',
]


def analyze(text: str) -> dict:
    text_lower = text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    word_count = len(words) or 1

    # Jargon density
    jargon_hits = sum(1 for j in JARGON if j in text_lower)
    jargon_density = jargon_hits / word_count

    # Pattern matching
    novice_signals = sum(1 for p in NOVICE_PATTERNS if re.search(p, text_lower))
    expert_signals = sum(1 for p in EXPERT_PATTERNS if re.search(p, text_lower))
    hedging_signals = sum(1 for p in HEDGING if re.search(p, text_lower))

    # Composite score: 0 (novice) to 1 (expert)
    score = 0.5  # baseline

    # Jargon pulls toward expert (need 2+ hits to matter, density alone misleads on short texts)
    if jargon_hits >= 2:
        score += min(jargon_density * 5, 0.3)
    elif jargon_hits == 1 and word_count > 10:
        score += 0.05

    # Pattern signals
    score += expert_signals * 0.1
    score -= novice_signals * 0.15
    score -= hedging_signals * 0.05

    # Word count: very short = likely expert (knows what to ask)
    # Very long = could be either, slight novice lean
    if word_count < 15 and expert_signals > 0:
        score += 0.1
    elif word_count > 100:
        score -= 0.05

    score = max(0.0, min(1.0, score))

    # Scaffolding recommendation
    if score < 0.3:
        level = "NOVICE"
        scaffolding = "HIGH — provide context, examples, step-by-step. Worked examples > problem-solving."
    elif score < 0.6:
        level = "INTERMEDIATE"
        scaffolding = "MEDIUM — provide key concepts, skip basics. Faded examples, guided exploration."
    else:
        level = "EXPERT"
        scaffolding = "LOW — minimal scaffolding. Direct answer, no tutorials. Extra guidance = interference (expertise reversal effect)."

    return {
        'score': round(score, 2),
        'level': level,
        'scaffolding': scaffolding,
        'signals': {
            'jargon_hits': jargon_hits,
            'jargon_density': round(jargon_density, 3),
            'novice_patterns': novice_signals,
            'expert_patterns': expert_signals,
            'hedging': hedging_signals,
            'word_count': word_count,
        }
    }


def main():
    if len(sys.argv) > 1:
        text = ' '.join(sys.argv[1:])
    else:
        text = sys.stdin.read().strip()

    if not text:
        print("Usage: echo 'your prompt' | python3 expertise-adapter.py")
        sys.exit(1)

    result = analyze(text)

    print(f"\n{'='*60}")
    print(f"  EXPERTISE LEVEL: {result['level']} (score: {result['score']})")
    print(f"{'='*60}")
    print(f"  Scaffolding: {result['scaffolding']}")
    print(f"\n  Signals:")
    for k, v in result['signals'].items():
        print(f"    {k}: {v}")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
