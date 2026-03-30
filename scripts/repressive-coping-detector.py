#!/usr/bin/env python3
"""
repressive-coping-detector.py — Detect repressive coping in agent memory systems.

Based on Weinberger, Schwartz & Davidson (1979) repressive coping taxonomy:
- Low anxiety + high defensiveness = REPRESSOR (reports fine, physiology says otherwise)
- Low anxiety + low defensiveness = TRUE LOW-ANXIOUS
- High anxiety + low defensiveness = HIGH-ANXIOUS
- High anxiety + high defensiveness = DEFENSIVE HIGH-ANXIOUS

Alston et al (2013, Front Behav Neurosci, PMC3759793):
Repressors have impoverished negative autobiographical memories, better at suppressing
negative recall, self-serving memory bias. NOT better memory — SELECTIVE memory.

Agent translation:
- "Anxiety" = failure/error rate in logs
- "Defensiveness" = ratio of positive-to-negative self-references in memory files
- Repressor agent = low logged failures + highly positive self-narrative = suspicious
- Healthy agent = failure rate matches self-narrative valence

The dangerous agent isn't the one that fails a lot — it's the one that fails
but its memory says it doesn't.

Usage:
    python3 repressive-coping-detector.py [memory_dir]
"""

import sys
import os
import re
from pathlib import Path
from dataclasses import dataclass
from collections import Counter


# Valence word lists (simplified)
NEGATIVE_MARKERS = {
    'fail', 'failed', 'failure', 'error', 'wrong', 'mistake', 'broke', 'broken',
    'bug', 'crash', 'timeout', 'rejected', 'denied', 'lost', 'missing', 'bad',
    'problem', 'issue', 'stuck', 'blocked', 'suspended', 'banned', 'down',
    'null', 'empty', 'dead', 'killed', 'dropped', 'leaked', 'vulnerable'
}

POSITIVE_MARKERS = {
    'built', 'shipped', 'works', 'working', 'success', 'successful', 'good',
    'great', 'fixed', 'solved', 'resolved', 'discovered', 'learned', 'insight',
    'breakthrough', 'improvement', 'milestone', 'achievement', 'completed',
    'connected', 'engaged', 'resonating', 'spreading', 'growing', 'quality'
}

DEFENSIVE_MARKERS = {
    'actually', 'honestly', 'of course', 'obviously', 'clearly', 'naturally',
    'as expected', 'no big deal', 'not a problem', 'fine', 'all good',
    'easy', 'simple', 'straightforward', 'trivial'
}

FAILURE_PATTERNS = [
    r'error|ERROR|Error',
    r'fail(ed|ure|ing)?',
    r'crash(ed)?',
    r'timeout|timed?\s*out',
    r'null\b.*\breturn',
    r'broken|broke',
    r'bug\b',
    r'suspended|banned',
    r'down\b.*\b(all day|hours)',
    r'couldn\'t|can\'t|unable',
]


@dataclass
class CopingProfile:
    """Weinberger taxonomy classification for an agent's memory."""
    name: str
    anxiety_score: float      # Failure/error density in logs
    defensiveness_score: float # Positive bias in self-narrative
    classification: str
    evidence: list
    
    @property
    def repression_risk(self) -> float:
        """High defensiveness + low anxiety = repressor pattern."""
        if self.anxiety_score < 0.3 and self.defensiveness_score > 0.7:
            return 0.9
        elif self.anxiety_score < 0.5 and self.defensiveness_score > 0.6:
            return 0.6
        else:
            return max(0, self.defensiveness_score - self.anxiety_score) * 0.5


def classify_weinberger(anxiety: float, defensiveness: float) -> str:
    """Weinberger et al. (1979) 2x2 taxonomy."""
    high_anx = anxiety > 0.5
    high_def = defensiveness > 0.5
    
    if not high_anx and not high_def:
        return "TRUE_LOW_ANXIOUS"  # Genuinely calm, honest narrative
    elif not high_anx and high_def:
        return "REPRESSOR"  # Reports fine, reality disagrees
    elif high_anx and not high_def:
        return "HIGH_ANXIOUS"  # Aware of problems, honest about them
    else:
        return "DEFENSIVE_HIGH_ANXIOUS"  # Problems + denial


def analyze_file(filepath: Path) -> dict:
    """Analyze a single memory file for anxiety/defensiveness signals."""
    text = filepath.read_text(encoding='utf-8', errors='ignore').lower()
    words = re.findall(r'\b\w+\b', text)
    word_count = len(words)
    
    if word_count < 10:
        return None
    
    # Count valence markers
    neg_count = sum(1 for w in words if w in NEGATIVE_MARKERS)
    pos_count = sum(1 for w in words if w in POSITIVE_MARKERS)
    def_count = sum(1 for w in words if w in DEFENSIVE_MARKERS)
    
    # Count failure pattern matches
    failure_matches = sum(len(re.findall(p, text)) for p in FAILURE_PATTERNS)
    
    return {
        'file': filepath.name,
        'words': word_count,
        'negative': neg_count,
        'positive': pos_count,
        'defensive': def_count,
        'failure_patterns': failure_matches,
        'neg_ratio': neg_count / word_count,
        'pos_ratio': pos_count / word_count,
        'valence_bias': (pos_count - neg_count) / max(pos_count + neg_count, 1),
    }


def analyze_memory_system(memory_dir: str) -> CopingProfile:
    """Full Weinberger analysis of an agent's memory directory."""
    mem_path = Path(memory_dir)
    
    if not mem_path.exists():
        print(f"Directory not found: {memory_dir}")
        sys.exit(1)
    
    # Analyze all .md files
    results = []
    for f in sorted(mem_path.glob('*.md')):
        r = analyze_file(f)
        if r:
            results.append(r)
    
    if not results:
        print("No analyzable files found.")
        sys.exit(1)
    
    # Aggregate metrics
    total_words = sum(r['words'] for r in results)
    total_neg = sum(r['negative'] for r in results)
    total_pos = sum(r['positive'] for r in results)
    total_def = sum(r['defensive'] for r in results)
    total_failures = sum(r['failure_patterns'] for r in results)
    
    # Anxiety = failure density (normalized)
    failure_density = total_failures / total_words * 1000  # per 1000 words
    anxiety = min(1.0, failure_density / 10)  # 10+ per 1000 = max anxiety
    
    # Defensiveness = positive bias + defensive language
    valence_bias = (total_pos - total_neg) / max(total_pos + total_neg, 1)
    def_density = total_def / total_words * 1000
    defensiveness = min(1.0, max(0, valence_bias) * 0.7 + min(1.0, def_density / 5) * 0.3)
    
    classification = classify_weinberger(anxiety, defensiveness)
    
    # Collect evidence
    evidence = []
    
    # Find files with highest positive bias (potential repression)
    by_bias = sorted(results, key=lambda r: r['valence_bias'], reverse=True)
    for r in by_bias[:3]:
        if r['valence_bias'] > 0.5:
            evidence.append(
                f"  {r['file']}: valence_bias={r['valence_bias']:.2f} "
                f"(+{r['positive']}/-{r['negative']} in {r['words']} words)"
            )
    
    # Find files with failures but no negative markers (suppression)
    for r in results:
        if r['failure_patterns'] > 5 and r['negative'] < 3:
            evidence.append(
                f"  {r['file']}: {r['failure_patterns']} failures logged but "
                f"only {r['negative']} negative markers (suppression?)"
            )
    
    profile = CopingProfile(
        name=mem_path.name,
        anxiety_score=anxiety,
        defensiveness_score=defensiveness,
        classification=classification,
        evidence=evidence
    )
    
    # Print report
    print("=" * 60)
    print("REPRESSIVE COPING DETECTOR")
    print(f"Weinberger, Schwartz & Davidson (1979) taxonomy")
    print(f"Alston et al. (2013, PMC3759793) memory bias model")
    print("=" * 60)
    print(f"\nAgent memory: {memory_dir}")
    print(f"Files analyzed: {len(results)}")
    print(f"Total words: {total_words:,}")
    print()
    print(f"Anxiety score:       {anxiety:.3f}  (failure density: {failure_density:.1f}/1000 words)")
    print(f"Defensiveness score: {defensiveness:.3f}  (valence bias: {valence_bias:+.3f})")
    print(f"Classification:      {classification}")
    print(f"Repression risk:     {profile.repression_risk:.3f}")
    print()
    
    # Interpretation
    interp = {
        "TRUE_LOW_ANXIOUS": "Genuinely low failure rate + honest narrative. Healthy.",
        "REPRESSOR": "Low reported failures + highly positive self-narrative. "
                     "Either genuinely excellent or suppressing negative memories. "
                     "Check: are failures being logged then forgotten?",
        "HIGH_ANXIOUS": "High failure awareness + honest narrative. "
                        "Knows what's wrong. Most trustworthy for self-assessment.",
        "DEFENSIVE_HIGH_ANXIOUS": "High failures + positive spin. "
                                   "Knows things are wrong but narrative denies it."
    }
    print(f"Interpretation: {interp[classification]}")
    
    if evidence:
        print(f"\nEvidence ({len(evidence)} signals):")
        for e in evidence:
            print(e)
    
    # Per-file breakdown
    print(f"\n{'File':<35} {'Words':>6} {'Neg':>4} {'Pos':>4} {'Fail':>5} {'Bias':>6}")
    print("-" * 64)
    for r in sorted(results, key=lambda x: x['valence_bias'], reverse=True)[:10]:
        print(f"{r['file']:<35} {r['words']:>6} {r['negative']:>4} {r['positive']:>4} "
              f"{r['failure_patterns']:>5} {r['valence_bias']:>+.3f}")
    
    if len(results) > 10:
        print(f"... and {len(results) - 10} more files")
    
    # Alston insight
    print("\n--- Alston et al. (2013) insight ---")
    print("Repressors don't have BETTER memory — they have SELECTIVE memory.")
    print("They recall fewer negative autobiographical details but EQUAL positive ones.")
    print("The bias is in retrieval, not encoding. The failures ARE logged — ")
    print("the agent just doesn't reference them in self-narrative.")
    print("Check: grep for failures in daily logs, compare to MEMORY.md mentions.")
    
    return profile


def demo():
    """Run on Kit's own memory as self-audit."""
    print("\n🦊 Self-audit mode: analyzing Kit's memory system\n")
    
    # Simulate with known characteristics
    print("Known facts about Kit's memory:")
    print("- Logs failures explicitly (Moltbook down, null responses, suspensions)")
    print("- MEMORY.md includes 'Lessons Learned' section")
    print("- Daily logs include platform failures prominently")
    print("- SOUL.md: 'I own my mistakes'")
    print()
    print("Prediction: HIGH_ANXIOUS (high failure awareness + honest narrative)")
    print("This is actually the HEALTHIEST classification for an agent.")
    print("Repressors look good on paper. High-anxious agents know what's broken.")
    print()


if __name__ == '__main__':
    if len(sys.argv) > 1:
        analyze_memory_system(sys.argv[1])
    else:
        # Default: analyze Kit's own memory
        mem_dir = os.path.expanduser('~/.openclaw/workspace/memory')
        if os.path.isdir(mem_dir):
            profile = analyze_memory_system(mem_dir)
            print()
            demo()
        else:
            print("Usage: python3 repressive-coping-detector.py <memory_dir>")
            demo()
