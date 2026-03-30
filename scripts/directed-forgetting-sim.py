#!/usr/bin/env python3
"""
directed-forgetting-sim.py — Models intentional forgetting for agent memory management.

Based on Spear, Reid, Guitard & Jamieson (2024, Exp Psychol 71:278-297, PMC11868810):
Item-based directed forgetting is STRENGTH-based (differential encoding), not
distinctiveness-based. Remember-cued items get elaborative rehearsal; forget-cued
items get rehearsal termination. The forgetting isn't active suppression — it's
passive neglect.

Agent translation: MEMORY.md entries aren't "deleted" — they're differentially
encoded. High-priority items get rehearsal (re-read in heartbeats). Low-priority
items get rehearsal terminated (not re-read). Forgetting = stopping rehearsal.

Connects to sixerdemon's "engineered haunting" — we CHOOSE which loops stay open.
The directed forgetting literature says the mechanism is rehearsal allocation,
not active suppression. You don't push memories out; you stop pulling them in.

Also models Bjork's "desirable difficulty" (1994): some forgetting improves
long-term retention by forcing effortful retrieval. Optimal forgetting rate
exists — too little = bloat, too much = amnesia.

Usage: python3 directed-forgetting-sim.py [--memory-file PATH]
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class MemoryEntry:
    """A single memory trace with encoding strength."""
    content: str
    category: str
    encoding_strength: float  # 0.0-1.0, how deeply encoded
    rehearsal_count: int  # times re-read in heartbeats
    last_rehearsal: Optional[str]  # ISO timestamp
    cue: str  # "remember" or "forget"
    retrieval_probability: float = 0.0
    desirable_difficulty: float = 0.0

    def compute_retrieval_probability(self, current_time: str, decay_rate: float = 0.05):
        """
        Bjork's New Theory of Disuse (1992):
        Retrieval strength decays, storage strength doesn't.
        Retrieval prob = storage_strength * exp(-decay * time_since_rehearsal)
        
        But: low retrieval strength at time of re-study = HIGHER storage gain.
        That's the desirable difficulty.
        """
        storage = self.encoding_strength * (1 + math.log1p(self.rehearsal_count))
        
        if self.last_rehearsal:
            try:
                last = datetime.fromisoformat(self.last_rehearsal.replace('Z', '+00:00'))
                now = datetime.fromisoformat(current_time.replace('Z', '+00:00'))
                hours_elapsed = (now - last).total_seconds() / 3600
            except (ValueError, TypeError):
                hours_elapsed = 24.0
        else:
            hours_elapsed = 168.0  # 1 week default
        
        retrieval_strength = math.exp(-decay_rate * hours_elapsed)
        self.retrieval_probability = min(1.0, storage * retrieval_strength)
        
        # Desirable difficulty: low retrieval strength = high learning gain
        # when re-studied (Bjork 1994)
        self.desirable_difficulty = 1.0 - retrieval_strength
        
        return self.retrieval_probability


class DirectedForgettingSim:
    """Simulates directed forgetting in agent memory."""
    
    CATEGORY_PATTERNS = {
        'connection': r'(connection|collab|DM|email|match|agent\s+\w+)',
        'research': r'(paper|study|finding|PMC|arxiv|doi)',
        'build': r'(script|built|tool|\.py|code|commit)',
        'insight': r'(lesson|insight|principle|rule|pattern)',
        'event': r'(happened|milestone|shipped|launched|broke)',
        'quote': r'(said|quote|"[^"]+"|—\s)',
        'meta': r'(memory|heartbeat|context|session)',
    }
    
    def __init__(self):
        self.entries: list[MemoryEntry] = []
        self.forget_criteria = {
            'stale_threshold_hours': 168,  # 1 week without rehearsal
            'low_strength_threshold': 0.3,
            'max_rehearsal_without_use': 5,  # rehearsed but never referenced
        }
    
    def parse_memory_file(self, filepath: str) -> list[MemoryEntry]:
        """Parse a memory file into entries."""
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}")
            return []
        
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Split on markdown headers or bullet points
        sections = re.split(r'\n(?=#+\s|[-*]\s\*\*)', content)
        entries = []
        
        for section in sections:
            section = section.strip()
            if len(section) < 20:
                continue
            
            category = self._categorize(section)
            strength = self._estimate_encoding_strength(section)
            rehearsal = self._estimate_rehearsal_count(section)
            
            entry = MemoryEntry(
                content=section[:200],
                category=category,
                encoding_strength=strength,
                rehearsal_count=rehearsal,
                last_rehearsal=None,
                cue=self._assign_cue(strength, rehearsal, category),
            )
            entries.append(entry)
        
        self.entries = entries
        return entries
    
    def _categorize(self, text: str) -> str:
        for cat, pattern in self.CATEGORY_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE):
                return cat
        return 'uncategorized'
    
    def _estimate_encoding_strength(self, text: str) -> float:
        """Estimate how deeply encoded a memory is."""
        strength = 0.3  # baseline
        
        # Specificity markers increase encoding
        if re.search(r'\d{4}[-/]\d{2}[-/]\d{2}', text):
            strength += 0.1  # dated = concrete
        if re.search(r'PMC\d+|arxiv|doi', text, re.IGNORECASE):
            strength += 0.15  # sourced = verified
        if re.search(r'"[^"]{10,}"', text):
            strength += 0.1  # quoted = distinctive
        if re.search(r'lesson|insight|key|critical', text, re.IGNORECASE):
            strength += 0.1  # marked as important
        if re.search(r'built|shipped|created|wrote', text, re.IGNORECASE):
            strength += 0.1  # action = deep encoding
        if len(text) > 500:
            strength += 0.05  # elaborated
        
        return min(1.0, strength)
    
    def _estimate_rehearsal_count(self, text: str) -> int:
        """Estimate how many times something has been rehearsed."""
        count = 1
        # Cross-references suggest rehearsal
        if re.search(r'see also|cf\.|related|connects to', text, re.IGNORECASE):
            count += 2
        # Multiple dates suggest revisiting
        dates = re.findall(r'\d{4}[-/]\d{2}[-/]\d{2}', text)
        count += len(set(dates))
        return count
    
    def _assign_cue(self, strength: float, rehearsal: int, category: str) -> str:
        """
        Directed forgetting cue assignment.
        
        Key insight from Spear et al (2024): the cue doesn't cause forgetting.
        It determines whether elaborative rehearsal CONTINUES or TERMINATES.
        
        For agents: "remember" = keep rehearsing in heartbeats
                    "forget" = stop rehearsing (passive decay)
        """
        # Always remember: critical rules, active connections, recent builds
        if category in ('insight', 'meta') and strength > 0.5:
            return 'remember'
        
        # Forget candidates: low strength, low rehearsal, stale categories
        if strength < self.forget_criteria['low_strength_threshold']:
            return 'forget'
        
        # High rehearsal but uncategorized = noise
        if rehearsal > self.forget_criteria['max_rehearsal_without_use'] and category == 'uncategorized':
            return 'forget'
        
        return 'remember'
    
    def simulate_heartbeat_consolidation(self, current_time: str = None):
        """
        Simulate what happens during a heartbeat review.
        
        Spear et al: strength mechanism = elaborative rehearsal of R-cued items.
        Bjork: desirable difficulty = items harder to retrieve benefit MORE from re-study.
        
        Optimal strategy: prioritize rehearsal of IMPORTANT but HARD-TO-RETRIEVE items.
        This is exactly the spindle consolidation model (Cairney 2021).
        """
        if current_time is None:
            current_time = datetime.utcnow().isoformat() + 'Z'
        
        for entry in self.entries:
            entry.compute_retrieval_probability(current_time)
        
        # Sort by priority: high desirable difficulty + remember cue
        remember_items = [e for e in self.entries if e.cue == 'remember']
        forget_items = [e for e in self.entries if e.cue == 'forget']
        
        # Prioritize by desirable difficulty (hard but important = review first)
        remember_items.sort(key=lambda e: e.desirable_difficulty, reverse=True)
        
        return {
            'remember_count': len(remember_items),
            'forget_count': len(forget_items),
            'high_difficulty_remember': [
                {
                    'content': e.content[:80],
                    'category': e.category,
                    'retrieval_prob': round(e.retrieval_probability, 3),
                    'desirable_difficulty': round(e.desirable_difficulty, 3),
                }
                for e in remember_items[:5]
                if e.desirable_difficulty > 0.5
            ],
            'forget_candidates': [
                {
                    'content': e.content[:80],
                    'category': e.category,
                    'encoding_strength': round(e.encoding_strength, 3),
                    'reason': 'low encoding strength' if e.encoding_strength < 0.3 else 'passive decay',
                }
                for e in forget_items[:5]
            ],
            'optimal_review_order': 'high desirable difficulty first (Bjork 1994)',
            'mechanism': 'strength (rehearsal allocation), NOT suppression (Spear et al 2024)',
        }
    
    def compute_forgetting_curve(self, hours: list[float] = None) -> list[dict]:
        """
        Ebbinghaus-style forgetting curve for remember vs forget items.
        
        Key: the curves DIVERGE because of differential rehearsal,
        not because forget items are actively suppressed.
        """
        if hours is None:
            hours = [0, 1, 4, 12, 24, 48, 168]
        
        curves = []
        for h in hours:
            remember_probs = []
            forget_probs = []
            
            for entry in self.entries:
                fake_time = datetime(2026, 3, 30, 7, 0, 0)
                from datetime import timedelta
                current = (fake_time + timedelta(hours=h)).isoformat() + 'Z'
                
                prob = entry.compute_retrieval_probability(current)
                if entry.cue == 'remember':
                    remember_probs.append(prob)
                else:
                    forget_probs.append(prob)
            
            curves.append({
                'hours': h,
                'remember_mean': round(sum(remember_probs) / max(len(remember_probs), 1), 3),
                'forget_mean': round(sum(forget_probs) / max(len(forget_probs), 1), 3),
                'divergence': round(
                    (sum(remember_probs) / max(len(remember_probs), 1)) -
                    (sum(forget_probs) / max(len(forget_probs), 1)), 3
                ),
            })
        
        return curves


def main():
    parser = argparse.ArgumentParser(description='Directed forgetting simulation for agent memory')
    parser.add_argument('--memory-file', default=None, help='Path to MEMORY.md or similar')
    parser.add_argument('--json', action='store_true', help='JSON output')
    args = parser.parse_args()
    
    sim = DirectedForgettingSim()
    
    # Default to MEMORY.md in workspace
    memory_file = args.memory_file or os.path.expanduser('~/.openclaw/workspace/MEMORY.md')
    
    entries = sim.parse_memory_file(memory_file)
    if not entries:
        print("No entries found.")
        return
    
    print(f"=== Directed Forgetting Simulation ===")
    print(f"Source: {memory_file}")
    print(f"Total entries: {len(entries)}")
    print()
    
    # Category breakdown
    categories = {}
    for e in entries:
        categories[e.category] = categories.get(e.category, 0) + 1
    
    print("Category distribution:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")
    print()
    
    # Cue assignment
    remember = [e for e in entries if e.cue == 'remember']
    forget = [e for e in entries if e.cue == 'forget']
    print(f"Cue assignment:")
    print(f"  Remember (keep rehearsing): {len(remember)} ({100*len(remember)/len(entries):.1f}%)")
    print(f"  Forget (stop rehearsing):   {len(forget)} ({100*len(forget)/len(entries):.1f}%)")
    print()
    
    # Consolidation simulation
    result = sim.simulate_heartbeat_consolidation()
    
    print(f"Mechanism: {result['mechanism']}")
    print(f"Review order: {result['optimal_review_order']}")
    print()
    
    if result['high_difficulty_remember']:
        print("Priority review (high desirable difficulty):")
        for item in result['high_difficulty_remember']:
            print(f"  [{item['category']}] difficulty={item['desirable_difficulty']}, "
                  f"retrieval={item['retrieval_prob']}")
            print(f"    {item['content']}")
        print()
    
    if result['forget_candidates']:
        print("Forget candidates (rehearsal terminated):")
        for item in result['forget_candidates']:
            print(f"  [{item['category']}] strength={item['encoding_strength']}: {item['reason']}")
            print(f"    {item['content']}")
        print()
    
    # Forgetting curves
    curves = sim.compute_forgetting_curve()
    print("Forgetting curves (remember vs forget):")
    print(f"  {'Hours':>6} | {'Remember':>8} | {'Forget':>8} | {'Gap':>6}")
    print(f"  {'-'*6} | {'-'*8} | {'-'*8} | {'-'*6}")
    for c in curves:
        print(f"  {c['hours']:>6} | {c['remember_mean']:>8.3f} | {c['forget_mean']:>8.3f} | {c['divergence']:>6.3f}")
    
    print()
    print("Key insight: the gap is from DIFFERENTIAL REHEARSAL, not active suppression.")
    print("You don't push memories out. You stop pulling them in.")
    print("Sixerdemon's 'engineered haunting' = choosing which items get rehearsal cues.")
    
    if args.json:
        print()
        print(json.dumps({
            'entries': len(entries),
            'remember': len(remember),
            'forget': len(forget),
            'categories': categories,
            'consolidation': result,
            'curves': curves,
        }, indent=2))


if __name__ == '__main__':
    main()
