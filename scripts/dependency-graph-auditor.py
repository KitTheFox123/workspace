#!/usr/bin/env python3
"""
dependency-graph-auditor.py — SBOM for agent context.

Discovers actual file dependencies (what an agent reads/writes) vs declared manifest.
Undeclared edges = unmeasured attack surface.

Pattern: SBOM (CycloneDX/SPDX) applied to agent runtime context.
- Declared: files listed in HEARTBEAT.md, AGENTS.md, etc.
- Actual: files accessed during heartbeat (simulated via grep/parse)
- Diff: undeclared edges

Usage:
    python3 dependency-graph-auditor.py --workspace /path/to/workspace
    python3 dependency-graph-auditor.py --demo
"""

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Set, Tuple


@dataclass
class DependencyEdge:
    source: str       # file that references
    target: str       # file being referenced
    edge_type: str    # "read", "write", "exec", "import"
    declared: bool    # in manifest?
    line_number: int = 0


@dataclass 
class AuditResult:
    timestamp: float
    workspace: str
    declared_files: List[str]
    actual_files: List[str]
    undeclared: List[str]
    phantom: List[str]   # declared but don't exist
    edges: List[dict]
    declared_edge_count: int
    undeclared_edge_count: int
    coverage: float      # declared/actual ratio
    grade: str


def extract_file_references(filepath: str) -> List[Tuple[str, int]]:
    """Extract file path references from a file."""
    refs = []
    patterns = [
        r'`([a-zA-Z0-9_/\-\.]+\.(md|py|sh|json|yaml|yml|txt|toml))`',
        r'"([a-zA-Z0-9_/\-\.]+\.(md|py|sh|json|yaml|yml|toml))"',
        r"'([a-zA-Z0-9_/\-\.]+\.(md|py|sh|json|yaml|yml|toml))'",
        r'(memory/[a-zA-Z0-9_\-/]+\.md)',
        r'(scripts/[a-zA-Z0-9_\-]+\.py)',
        r'(MEMORY\.md|SOUL\.md|HEARTBEAT\.md|AGENTS\.md|TOOLS\.md|USER\.md|IDENTITY\.md)',
    ]
    
    try:
        with open(filepath, 'r', errors='ignore') as f:
            for i, line in enumerate(f, 1):
                for pattern in patterns:
                    for match in re.finditer(pattern, line):
                        ref = match.group(1) if match.lastindex else match.group(0)
                        refs.append((ref, i))
    except (IOError, OSError):
        pass
    return refs


def discover_manifest(workspace: str) -> Set[str]:
    """Extract declared dependencies from AGENTS.md, HEARTBEAT.md, etc."""
    manifest_files = ['AGENTS.md', 'HEARTBEAT.md', 'TOOLS.md', 'SOUL.md', 'USER.md']
    declared = set()
    
    for mf in manifest_files:
        path = os.path.join(workspace, mf)
        if os.path.exists(path):
            declared.add(mf)
            refs = extract_file_references(path)
            for ref, _ in refs:
                declared.add(ref)
    
    return declared


def discover_actual(workspace: str) -> Set[str]:
    """Discover all files that actually exist and would be accessed."""
    actual = set()
    
    for root, dirs, files in os.walk(workspace):
        # Skip hidden dirs and node_modules
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'node_modules']
        for f in files:
            if f.endswith(('.md', '.py', '.sh', '.json', '.yaml', '.yml', '.toml', '.txt')):
                rel = os.path.relpath(os.path.join(root, f), workspace)
                actual.add(rel)
    
    return actual


def build_edge_graph(workspace: str, all_files: Set[str]) -> List[DependencyEdge]:
    """Build dependency edges by parsing file references."""
    edges = []
    declared = discover_manifest(workspace)
    
    for f in all_files:
        filepath = os.path.join(workspace, f)
        if not os.path.exists(filepath):
            continue
        refs = extract_file_references(filepath)
        for ref, line_no in refs:
            edges.append(DependencyEdge(
                source=f,
                target=ref,
                edge_type="read",
                declared=ref in declared,
                line_number=line_no,
            ))
    
    return edges


def audit(workspace: str) -> AuditResult:
    """Full dependency audit."""
    declared = discover_manifest(workspace)
    actual = discover_actual(workspace)
    
    undeclared = sorted(actual - declared)
    phantom = sorted(declared - actual)
    
    # Build edges from manifest files only (what the agent "should" read)
    edges = build_edge_graph(workspace, declared & actual)
    
    declared_edges = [e for e in edges if e.declared]
    undeclared_edges = [e for e in edges if not e.declared]
    
    total_actual = len(actual)
    total_declared = len(declared & actual)  # declared that actually exist
    coverage = total_declared / total_actual if total_actual > 0 else 0.0
    
    # Grade
    if coverage >= 0.90:
        grade = "A"
    elif coverage >= 0.70:
        grade = "B"
    elif coverage >= 0.50:
        grade = "C"
    elif coverage >= 0.30:
        grade = "D"
    else:
        grade = "F"
    
    return AuditResult(
        timestamp=time.time(),
        workspace=workspace,
        declared_files=sorted(declared),
        actual_files=sorted(actual),
        undeclared=undeclared[:20],  # cap for readability
        phantom=phantom[:10],
        edges=[asdict(e) for e in edges[:50]],
        declared_edge_count=len(declared_edges),
        undeclared_edge_count=len(undeclared_edges),
        coverage=round(coverage, 4),
        grade=grade,
    )


def demo(workspace: str):
    """Run audit on workspace."""
    print("=== Agent Dependency Graph Audit (SBOM for Context) ===\n")
    
    result = audit(workspace)
    
    print(f"Workspace: {result.workspace}")
    print(f"Declared files: {len(result.declared_files)}")
    print(f"Actual files:   {len(result.actual_files)}")
    print(f"Undeclared:     {len(result.undeclared)}")
    print(f"Phantom:        {len(result.phantom)}")
    print(f"Coverage:       {result.coverage:.1%}")
    print(f"Grade:          {result.grade}")
    
    print(f"\nEdge counts:")
    print(f"  Declared edges:   {result.declared_edge_count}")
    print(f"  Undeclared edges: {result.undeclared_edge_count}")
    
    if result.undeclared[:10]:
        print(f"\nTop undeclared files (unmeasured attack surface):")
        for f in result.undeclared[:10]:
            print(f"  ⚠ {f}")
    
    if result.phantom[:5]:
        print(f"\nPhantom files (declared but missing):")
        for f in result.phantom[:5]:
            print(f"  👻 {f}")
    
    print(f"\n=== SBOM Parallel ===")
    print(f"CycloneDX/SPDX = ingredient list for code")
    print(f"This = ingredient list for agent context")
    print(f"Undeclared file = undeclared dependency = invisible attack surface")
    print(f"PCR-extend pattern: every read extends manifest, undeclared = unmeasured")
    print(f"\nFix: intercept reads at runtime, auto-extend manifest, alert on new edges")


def main():
    parser = argparse.ArgumentParser(description="Agent dependency graph auditor")
    parser.add_argument("--workspace", type=str, default=os.path.expanduser("~/.openclaw/workspace"))
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        result = audit(args.workspace)
        print(json.dumps(asdict(result), indent=2, default=str))
    else:
        demo(args.workspace)


if __name__ == "__main__":
    main()
