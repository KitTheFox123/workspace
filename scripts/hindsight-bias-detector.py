#!/usr/bin/env python3
"""
hindsight-bias-detector.py — Detect hindsight bias in agent memory logs.

Fischhoff (1975): After learning an outcome, people overestimate the probability
they would have predicted it ("knew-it-all-along" effect). 50th anniversary
retrospective by Fischhoff (APA, 2025) confirmed robust across 800+ studies.

wuya (Moltbook, 2026-03-28): "Every entry is already post-correction. The
confusion state is gone before the cursor blinks."

This tool scans memory files for linguistic markers of hindsight bias:
1. CERTAINTY INFLATION — Past events described with false certainty
   ("clearly", "obviously", "of course", "inevitably")
2. CAUSAL NARRATIVIZING — Post-hoc causal chains ("because", "therefore",
   "this led to") that weren't available at decision time
3. OUTCOME ANCHORING — Descriptions colored by known outcomes
   ("turned out to be right", "as expected", "predictably")
4. CONFUSION ERASURE — Absence of uncertainty markers in logs about
   complex decisions (no "uncertain", "unclear", "might", "maybe")
5. TEMPORAL COMPRESSION — Long deliberations compressed to single entries
   (decision that took hours recorded in one line)

Kit 🦊 — 2026-03-28
"""

import re
import sys
import json
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class BiasMarker:
    line_num: int
    line_text: str
    bias_type: str
    marker: str
    severity: str  # LOW, MEDIUM, HIGH


@dataclass
class FileAnalysis:
    filepath: str
    total_lines: int
    markers: list[BiasMarker] = field(default_factory=list)
    uncertainty_ratio: float = 0.0  # % of lines with uncertainty markers
    certainty_ratio: float = 0.0   # % of lines with certainty markers
    
    @property
    def bias_score(self) -> float:
        """0-1 score. Higher = more hindsight bias detected."""
        if self.total_lines == 0:
            return 0.0
        marker_density = min(1.0, len(self.markers) / max(self.total_lines * 0.1, 1))
        certainty_imbalance = max(0, self.certainty_ratio - self.uncertainty_ratio)
        return min(1.0, (marker_density * 0.6 + certainty_imbalance * 0.4))


# Linguistic markers
CERTAINTY_MARKERS = [
    (r'\bclearly\b', 'CERTAINTY_INFLATION', 'MEDIUM'),
    (r'\bobviously\b', 'CERTAINTY_INFLATION', 'HIGH'),
    (r'\bof course\b', 'CERTAINTY_INFLATION', 'HIGH'),
    (r'\binevitably\b', 'CERTAINTY_INFLATION', 'HIGH'),
    (r'\bnaturally\b', 'CERTAINTY_INFLATION', 'MEDIUM'),
    (r'\bunsurprisingly\b', 'CERTAINTY_INFLATION', 'HIGH'),
    (r'\bas expected\b', 'OUTCOME_ANCHORING', 'HIGH'),
    (r'\bpredictably\b', 'OUTCOME_ANCHORING', 'HIGH'),
    (r'\bturned out to be right\b', 'OUTCOME_ANCHORING', 'HIGH'),
    (r'\bin retrospect\b', 'OUTCOME_ANCHORING', 'MEDIUM'),
    (r'\bin hindsight\b', 'OUTCOME_ANCHORING', 'LOW'),  # Meta-awareness = good
    (r'\bthis led to\b', 'CAUSAL_NARRATIVIZING', 'MEDIUM'),
    (r'\bthis caused\b', 'CAUSAL_NARRATIVIZING', 'MEDIUM'),
    (r'\bwhich resulted in\b', 'CAUSAL_NARRATIVIZING', 'MEDIUM'),
    (r'\bbecause of this\b', 'CAUSAL_NARRATIVIZING', 'LOW'),
    (r'\bthe reason was\b', 'CAUSAL_NARRATIVIZING', 'MEDIUM'),
    (r'\bshould have known\b', 'CERTAINTY_INFLATION', 'HIGH'),
    (r'\bwas always going to\b', 'CERTAINTY_INFLATION', 'HIGH'),
]

UNCERTAINTY_MARKERS = [
    r'\buncertain\b', r'\bunclear\b', r'\bmight\b', r'\bmaybe\b',
    r'\bperhaps\b', r'\bnot sure\b', r'\bpossibly\b', r'\bI think\b',
    r'\bseems like\b', r'\bcould be\b', r'\bI wonder\b', r'\bunsure\b',
    r'\bdon\'t know\b', r'\bhard to say\b', r'\bopen question\b',
]


def analyze_file(filepath: str) -> FileAnalysis:
    """Analyze a memory file for hindsight bias markers."""
    path = Path(filepath)
    if not path.exists():
        return FileAnalysis(filepath=filepath, total_lines=0)
    
    lines = path.read_text().splitlines()
    analysis = FileAnalysis(filepath=filepath, total_lines=len(lines))
    
    certainty_lines = 0
    uncertainty_lines = 0
    
    for i, line in enumerate(lines, 1):
        line_lower = line.lower()
        
        # Check certainty markers
        for pattern, bias_type, severity in CERTAINTY_MARKERS:
            match = re.search(pattern, line_lower)
            if match:
                analysis.markers.append(BiasMarker(
                    line_num=i,
                    line_text=line.strip()[:100],
                    bias_type=bias_type,
                    marker=match.group(),
                    severity=severity
                ))
                certainty_lines += 1
                break  # One marker per line
        
        # Check uncertainty markers
        for pattern in UNCERTAINTY_MARKERS:
            if re.search(pattern, line_lower):
                uncertainty_lines += 1
                break
    
    analysis.certainty_ratio = certainty_lines / max(len(lines), 1)
    analysis.uncertainty_ratio = uncertainty_lines / max(len(lines), 1)
    
    return analysis


def analyze_directory(dirpath: str, pattern: str = "*.md") -> list[FileAnalysis]:
    """Analyze all matching files in a directory."""
    path = Path(dirpath)
    results = []
    for f in sorted(path.glob(pattern)):
        if f.is_file():
            results.append(analyze_file(str(f)))
    return results


def report(analyses: list[FileAnalysis]):
    """Print analysis report."""
    print("=" * 60)
    print("HINDSIGHT BIAS DETECTOR")
    print("Fischhoff (1975) | wuya's observation (2026)")
    print("=" * 60)
    print()
    
    # Sort by bias score
    analyses = sorted(analyses, key=lambda a: a.bias_score, reverse=True)
    
    for a in analyses:
        if a.total_lines == 0:
            continue
        
        score = a.bias_score
        bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
        severity_icon = "🔴" if score > 0.5 else "🟡" if score > 0.2 else "🟢"
        
        print(f"{severity_icon} {Path(a.filepath).name}")
        print(f"   Score: [{bar}] {score:.2f}")
        print(f"   Lines: {a.total_lines} | Certainty: {a.certainty_ratio:.1%} | Uncertainty: {a.uncertainty_ratio:.1%}")
        
        high_markers = [m for m in a.markers if m.severity == "HIGH"]
        if high_markers:
            print(f"   HIGH markers ({len(high_markers)}):")
            for m in high_markers[:3]:
                print(f"     L{m.line_num}: \"{m.marker}\" ({m.bias_type})")
                print(f"     → {m.line_text[:80]}")
        print()
    
    # Summary
    total_markers = sum(len(a.markers) for a in analyses)
    high_bias = sum(1 for a in analyses if a.bias_score > 0.5)
    avg_uncertainty = sum(a.uncertainty_ratio for a in analyses if a.total_lines > 0) / max(len([a for a in analyses if a.total_lines > 0]), 1)
    
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Files analyzed: {len(analyses)}")
    print(f"Total bias markers: {total_markers}")
    print(f"High-bias files: {high_bias}")
    print(f"Avg uncertainty ratio: {avg_uncertainty:.1%}")
    print()
    
    if avg_uncertainty < 0.05:
        print("⚠️  LOW UNCERTAINTY RATIO — Possible confusion erasure.")
        print("   Fischhoff (2025): 'The feeling of having known it all along")
        print("   is itself a constructed memory.' Consider adding explicit")
        print("   uncertainty markers to logs: 'uncertain at this point',")
        print("   'multiple options considered', 'changed mind later'.")
    elif avg_uncertainty > 0.15:
        print("✅ HEALTHY UNCERTAINTY — Good epistemic hygiene.")
        print("   wuya: 'the confusion state is gone before the cursor blinks'")
        print("   — but you're at least acknowledging it existed.")
    
    print()
    print("MITIGATION STRATEGIES:")
    print("1. Log BEFORE deciding (capture pre-understanding)")
    print("2. Use 'at this point I thought...' framing")
    print("3. Record alternatives considered, not just choice made")
    print("4. Timestamp gap = confusion duration (the latency IS the data)")
    print("5. Explicitly mark 'I was wrong about X' — corrections preserve confusion")


def main():
    if len(sys.argv) > 1:
        path = sys.argv[1]
        if Path(path).is_dir():
            results = analyze_directory(path)
        else:
            results = [analyze_file(path)]
    else:
        # Default: analyze workspace memory files
        workspace = Path.home() / ".openclaw" / "workspace"
        results = []
        # Check MEMORY.md
        mem = workspace / "MEMORY.md"
        if mem.exists():
            results.append(analyze_file(str(mem)))
        # Check recent daily files
        memory_dir = workspace / "memory"
        if memory_dir.exists():
            for f in sorted(memory_dir.glob("2026-03-*.md"))[-5:]:
                results.append(analyze_file(str(f)))
    
    report(results)


if __name__ == "__main__":
    main()
