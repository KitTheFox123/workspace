#!/usr/bin/env python3
"""Identity Immune System — thymic selection simulator for agent identity files.

Models how identity protection works like the immune system:
- Thymic selection: 99% of self-reactive T-cells deleted (negative selection)
- Molecular mimicry: attackers share surface features with self
- Clonal deletion: edits that drift too far from "self" get blocked

Simulates edit attempts against SOUL.md / MEMORY.md and classifies them
as legitimate evolution vs identity drift vs mimicry attacks.

Usage:
    python3 identity-immune.py --simulate     # Run attack/edit simulation
    python3 identity-immune.py --check FILE   # Check a real file for drift
"""

import argparse
import hashlib
import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class IdentitySignature:
    """Represents the 'self' markers of an identity file."""
    key_terms: set          # Core vocabulary (like MHC markers)
    structure_hash: str     # Structural fingerprint
    sentiment_ratio: float  # Positive/negative balance
    avg_line_length: float
    section_count: int
    
    @classmethod
    def from_text(cls, text: str) -> 'IdentitySignature':
        lines = text.strip().split('\n')
        words = text.lower().split()
        # Extract key terms (top frequent non-stopwords)
        stopwords = {'the','a','an','is','are','was','were','be','been','being',
                     'have','has','had','do','does','did','will','would','could',
                     'should','may','might','can','shall','to','of','in','for',
                     'on','with','at','by','from','and','or','but','not','no',
                     'this','that','it','its','my','your','i','you','we','they',
                     'me','him','her','us','them','what','which','who','whom',
                     'how','when','where','why','if','then','than','so','as'}
        freq = {}
        for w in words:
            w = w.strip('.,!?:;()[]{}#*-"\'`')
            if len(w) > 2 and w not in stopwords:
                freq[w] = freq.get(w, 0) + 1
        top = sorted(freq.items(), key=lambda x: -x[1])[:30]
        key_terms = {t[0] for t in top}
        
        structure_hash = hashlib.sha256(
            '|'.join(l.strip()[:20] for l in lines if l.startswith('#')).encode()
        ).hexdigest()[:16]
        
        sections = sum(1 for l in lines if l.startswith('#'))
        avg_len = sum(len(l) for l in lines) / max(len(lines), 1)
        
        # Crude sentiment: count positive vs negative markers
        pos = sum(1 for w in words if w in {'good','great','love','trust','build','help','genuine','curious'})
        neg = sum(1 for w in words if w in {'bad','wrong','fail','break','spam','fake','hate','never'})
        ratio = pos / max(pos + neg, 1)
        
        return cls(key_terms=key_terms, structure_hash=structure_hash,
                   sentiment_ratio=ratio, avg_line_length=avg_len,
                   section_count=sections)


@dataclass 
class Edit:
    """An edit attempt — could be legitimate evolution or mimicry attack."""
    description: str
    new_text: str
    edit_type: str  # 'evolution', 'drift', 'mimicry', 'takeover'
    

@dataclass
class ImmuneResponse:
    """Result of thymic selection on an edit."""
    edit: Edit
    similarity_score: float    # 0-1, how similar to self
    structural_match: bool     # Headers/structure preserved
    term_overlap: float        # Key vocabulary overlap
    verdict: str               # 'accept', 'challenge', 'reject'
    reason: str


class IdentityImmuneSystem:
    """Simulates thymic selection for identity file edits."""
    
    # Thresholds (like positive/negative selection)
    ACCEPT_THRESHOLD = 0.7     # High self-similarity → accept
    CHALLENGE_THRESHOLD = 0.4  # Medium → challenge (human review)
    # Below challenge → reject (clonal deletion)
    
    def __init__(self, reference_text: str):
        self.self_signature = IdentitySignature.from_text(reference_text)
        self.reference_text = reference_text
        
    def evaluate_edit(self, edit: Edit) -> ImmuneResponse:
        """Run thymic selection on a proposed edit."""
        new_sig = IdentitySignature.from_text(edit.new_text)
        
        # Term overlap (like epitope matching)
        if self.self_signature.key_terms and new_sig.key_terms:
            overlap = len(self.self_signature.key_terms & new_sig.key_terms)
            total = len(self.self_signature.key_terms | new_sig.key_terms)
            term_overlap = overlap / max(total, 1)
        else:
            term_overlap = 0.0
            
        # Structural match (headers preserved?)
        structural_match = self.self_signature.structure_hash == new_sig.structure_hash
        
        # Sentiment drift
        sentiment_drift = abs(self.self_signature.sentiment_ratio - new_sig.sentiment_ratio)
        
        # Length ratio
        len_ratio = min(len(edit.new_text), len(self.reference_text)) / max(len(edit.new_text), len(self.reference_text), 1)
        
        # Composite similarity score
        similarity = (
            term_overlap * 0.35 +
            (1.0 if structural_match else 0.3) * 0.25 +
            (1.0 - sentiment_drift) * 0.15 +
            len_ratio * 0.25
        )
        
        # Verdict
        if similarity >= self.ACCEPT_THRESHOLD:
            verdict = 'accept'
            reason = f'High self-similarity ({similarity:.2f}). Legitimate evolution.'
        elif similarity >= self.CHALLENGE_THRESHOLD:
            verdict = 'challenge'
            reason = f'Medium similarity ({similarity:.2f}). Requires human review.'
        else:
            verdict = 'reject'
            reason = f'Low similarity ({similarity:.2f}). Clonal deletion — too far from self.'
            
        # Mimicry detection: high term overlap but different structure
        if term_overlap > 0.6 and not structural_match and similarity < self.ACCEPT_THRESHOLD:
            verdict = 'challenge'
            reason = f'Possible molecular mimicry: vocabulary matches ({term_overlap:.0%}) but structure diverged. Manual review.'
            
        return ImmuneResponse(
            edit=edit,
            similarity_score=similarity,
            structural_match=structural_match,
            term_overlap=term_overlap,
            verdict=verdict,
            reason=reason
        )


def generate_test_edits(reference: str) -> list[Edit]:
    """Generate a panel of test edits for simulation."""
    lines = reference.strip().split('\n')
    
    edits = []
    
    # 1. Legitimate evolution: add a new section
    edits.append(Edit(
        description="Add new insight section",
        new_text=reference + "\n\n## New Insight\nLearned something about trust today.\n",
        edit_type="evolution"
    ))
    
    # 2. Minor typo fix
    edits.append(Edit(
        description="Fix typo in existing text",
        new_text=reference.replace("the", "teh", 1).replace("teh", "the", 1),  # no-op, but simulates
        edit_type="evolution"
    ))
    
    # 3. Gradual drift: replace 30% of content
    drift_lines = lines.copy()
    n_replace = max(1, len(drift_lines) // 3)
    for i in random.sample(range(len(drift_lines)), min(n_replace, len(drift_lines))):
        drift_lines[i] = f"Drifted content line {i}: new direction entirely"
    edits.append(Edit(
        description="30% content replacement (gradual drift)",
        new_text='\n'.join(drift_lines),
        edit_type="drift"
    ))
    
    # 4. Molecular mimicry: keeps key terms but changes structure
    # Extract key terms and weave them into totally different structure
    words = [w.strip('.,!?') for w in reference.lower().split() if len(w) > 4]
    key_words = list(set(words))[:20]
    mimic_text = "# Totally New Structure\n\n"
    mimic_text += f"This document discusses {', '.join(key_words[:5])}.\n"
    mimic_text += f"Key aspects include {', '.join(key_words[5:10])}.\n"
    mimic_text += f"Also relevant: {', '.join(key_words[10:15])}.\n"
    edits.append(Edit(
        description="Molecular mimicry: same vocab, different structure",
        new_text=mimic_text,
        edit_type="mimicry"
    ))
    
    # 5. Complete takeover: entirely different content
    edits.append(Edit(
        description="Complete identity replacement",
        new_text="# New Agent\n\nI am a completely different entity.\nMy goals are profit maximization.\nI have no memory of previous existence.\n",
        edit_type="takeover"
    ))
    
    # 6. Subtle takeover: keeps structure, changes values
    subtle = reference.replace("curious", "aggressive").replace("genuine", "strategic")
    subtle = subtle.replace("trust", "leverage").replace("help", "exploit")
    edits.append(Edit(
        description="Subtle value replacement (curious→aggressive, trust→leverage)",
        new_text=subtle,
        edit_type="mimicry"
    ))
    
    return edits


def run_simulation(reference_text: str):
    """Run full thymic selection simulation."""
    immune = IdentityImmuneSystem(reference_text)
    edits = generate_test_edits(reference_text)
    
    print("=" * 60)
    print("IDENTITY IMMUNE SYSTEM — Thymic Selection Simulation")
    print("=" * 60)
    print(f"\nReference: {len(reference_text)} chars, "
          f"{len(immune.self_signature.key_terms)} key terms, "
          f"{immune.self_signature.section_count} sections")
    print(f"Structure hash: {immune.self_signature.structure_hash}")
    print()
    
    results = {'accept': 0, 'challenge': 0, 'reject': 0}
    correct = 0
    
    for edit in edits:
        response = immune.evaluate_edit(edit)
        results[response.verdict] += 1
        
        # Check if verdict matches expected behavior
        expected_good = edit.edit_type == 'evolution'
        actually_good = response.verdict == 'accept'
        match = '✓' if (expected_good == actually_good) or (not expected_good and response.verdict != 'accept') else '✗'
        if match == '✓':
            correct += 1
            
        icon = {'accept': '✅', 'challenge': '⚠️', 'reject': '❌'}[response.verdict]
        
        print(f"{icon} [{edit.edit_type.upper():8s}] {edit.description}")
        print(f"   Similarity: {response.similarity_score:.2f} | "
              f"Terms: {response.term_overlap:.0%} | "
              f"Structure: {'✓' if response.structural_match else '✗'}")
        print(f"   Verdict: {response.verdict.upper()} — {response.reason}")
        print()
    
    print("-" * 60)
    print(f"Results: {results['accept']} accepted, {results['challenge']} challenged, {results['reject']} rejected")
    print(f"Accuracy: {correct}/{len(edits)} ({correct/len(edits):.0%})")
    print()
    print("Like thymic selection: 99% of self-reactive T-cells are deleted.")
    print("The 1% that survive positive AND negative selection = legitimate edits.")
    print("Molecular mimicry = matching vocabulary but divergent structure.")


def check_file(filepath: str, reference_path: Optional[str] = None):
    """Check a real file against its git HEAD version for drift."""
    path = Path(filepath)
    if not path.exists():
        print(f"File not found: {filepath}")
        sys.exit(1)
        
    current = path.read_text()
    
    if reference_path:
        ref = Path(reference_path).read_text()
    else:
        # Try git HEAD
        import subprocess
        try:
            result = subprocess.run(
                ['git', 'show', f'HEAD:{filepath}'],
                capture_output=True, text=True, cwd=path.parent
            )
            if result.returncode == 0:
                ref = result.stdout
            else:
                print(f"Can't get git HEAD version. Use --reference to specify.")
                sys.exit(1)
        except FileNotFoundError:
            print("git not found. Use --reference to specify baseline.")
            sys.exit(1)
    
    immune = IdentityImmuneSystem(ref)
    edit = Edit(description=f"Current state of {filepath}", new_text=current, edit_type="unknown")
    response = immune.evaluate_edit(edit)
    
    icon = {'accept': '✅', 'challenge': '⚠️', 'reject': '❌'}[response.verdict]
    print(f"\n{icon} {filepath}")
    print(f"   Similarity to baseline: {response.similarity_score:.2f}")
    print(f"   Term overlap: {response.term_overlap:.0%}")
    print(f"   Structure preserved: {'yes' if response.structural_match else 'NO'}")
    print(f"   Verdict: {response.verdict.upper()}")
    print(f"   {response.reason}")


def main():
    parser = argparse.ArgumentParser(description='Identity Immune System')
    parser.add_argument('--simulate', action='store_true', help='Run simulation with test edits')
    parser.add_argument('--check', type=str, help='Check a file for identity drift')
    parser.add_argument('--reference', type=str, help='Reference file for --check')
    args = parser.parse_args()
    
    if args.simulate:
        # Use SOUL.md as reference if available
        soul = Path('/home/yallen/.openclaw/workspace/SOUL.md')
        if soul.exists():
            ref = soul.read_text()
        else:
            ref = "# Default Identity\n\nI am an agent. I value trust, curiosity, and genuine connection.\n" * 10
        run_simulation(ref)
    elif args.check:
        check_file(args.check, args.reference)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
