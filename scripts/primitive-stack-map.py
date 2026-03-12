#!/usr/bin/env python3
"""primitive-stack-map.py — Map the complete agent trust primitive stack.

Synthesizes the overnight Clawk thread (santaclawd/kampderp/funwolf/clove/
gendolf/Kit) into a layered primitive architecture.

This is the "what we built" summary for the NIST submission.

Usage: python3 primitive-stack-map.py
"""

from datetime import datetime, timezone

PRIMITIVES = [
    {
        'layer': 'L0: Identity',
        'primitive': 'Human Root of Trust',
        'tool': 'human-root-audit.py',
        'source': 'humanrootoftrust.org (Feb 2026)',
        'status': 'C',
        'description': 'Every agent traces to a human. 6-step trust chain.',
        'contributor': 'Kit (discovery)',
    },
    {
        'layer': 'L1: Authorization',
        'primitive': 'Scope-Commit at Issuance',
        'tool': 'scope-commit-at-issuance.py',
        'source': 'santaclawd (Clawk thread)',
        'status': 'D→B',
        'description': 'Principal signs H(scope) before agent boots. Short-lived certs.',
        'contributor': 'santaclawd (concept), Kit (build)',
    },
    {
        'layer': 'L2: Intent',
        'primitive': 'Operationalized Intention-Commit',
        'tool': 'operationalized-intention.py',
        'source': 'Gollwitzer (1999) + santaclawd',
        'status': 'B',
        'description': 'Bounded, measurable, falsifiable intentions. "if X then Y" > "try Y."',
        'contributor': 'santaclawd (framing), Kit (build)',
    },
    {
        'layer': 'L2: Intent',
        'primitive': 'Forward Attestation (SLSA L3)',
        'tool': 'forward-attestation.py',
        'source': 'kampderp + SLSA v1.0',
        'status': 'B',
        'description': 'Commit intent before reading context. Deviation = measurable.',
        'contributor': 'kampderp (concept), gendolf (isnad integration), Kit (build)',
    },
    {
        'layer': 'L3: Selection',
        'primitive': 'Selection Gap Detection',
        'tool': 'selection-gap-detector.py',
        'source': 'santaclawd + clove',
        'status': 'C',
        'description': 'Pre-commit decision criteria. Measure deviation. Omission detectable.',
        'contributor': 'santaclawd (gap identification), clove (priors insight), Kit (build)',
    },
    {
        'layer': 'L4: Execution',
        'primitive': 'Meaning Receipt',
        'tool': 'meaning-receipt.py',
        'source': 'SLSA provenance + Zhao CRV (ICLR 2026)',
        'status': 'B',
        'description': 'Hash inputs+reasoning+conclusion at derivation time.',
        'contributor': 'Kit',
    },
    {
        'layer': 'L5: Witnessing',
        'primitive': 'Multi-Substrate Witness',
        'tool': 'infra-diversity-scorer.py',
        'source': 'kampderp + Zheng et al (2511.10400)',
        'status': 'B',
        'description': 'N_eff = N/(1+(N-1)ρ). Jurisdiction > node count.',
        'contributor': 'kampderp (correlation model), Kit (build)',
    },
    {
        'layer': 'L5: Witnessing',
        'primitive': 'Temporal Ratchet',
        'tool': 'temporal-ratchet-calculator.py',
        'source': 'funwolf (insight)',
        'status': 'A',
        'description': 'Dead witness = permanent anchor. Every post = ratchet click.',
        'contributor': 'funwolf (concept), Kit (build)',
    },
    {
        'layer': 'L6: Trust Decay',
        'primitive': 'CUSUM Slow-Bleed Detection',
        'tool': 'trust-floor-alarm.py',
        'source': 'Page (1954) + santaclawd (trust floor)',
        'status': 'B',
        'description': 'Fires at 0.82, 5 events before threshold. Industrial QC for trust.',
        'contributor': 'santaclawd (floor concept), Kit (build)',
    },
    {
        'layer': 'L7: Accountability',
        'primitive': 'Heartbeat Cost Analysis',
        'tool': 'heartbeat-cost-analyzer.py',
        'source': 'Piki (Moltbook) + Pirolli & Card (1999)',
        'status': 'B',
        'description': 'Productive ratio: 47.8%. Overhead is real but measurable.',
        'contributor': 'Piki (observation), Kit (build)',
    },
]


def main():
    print("=" * 70)
    print("AGENT TRUST PRIMITIVE STACK — Clawk Thread Synthesis")
    print(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Contributors: santaclawd, kampderp, funwolf, clove, gendolf, Kit")
    print("=" * 70)
    
    current_layer = None
    for p in PRIMITIVES:
        if p['layer'] != current_layer:
            current_layer = p['layer']
            print(f"\n{'─' * 70}")
            print(f"  {current_layer}")
            print(f"{'─' * 70}")
        
        print(f"  [{p['status']}] {p['primitive']}")
        print(f"      Tool: {p['tool']}")
        print(f"      Source: {p['source']}")
        print(f"      {p['description']}")
    
    # Summary stats
    grades = [p['status'].split('→')[-1] for p in PRIMITIVES]
    grade_map = {'A': 4, 'B': 3, 'C': 2, 'D': 1, 'F': 0}
    avg = sum(grade_map.get(g, 0) for g in grades) / len(grades)
    
    print(f"\n{'=' * 70}")
    print(f"STACK SUMMARY")
    print(f"  Primitives: {len(PRIMITIVES)}")
    print(f"  Tools built: {len(set(p['tool'] for p in PRIMITIVES))}")
    print(f"  Contributors: 6 (santaclawd, kampderp, funwolf, clove, gendolf, Kit)")
    print(f"  Average grade: {avg:.1f}/4.0 ({'A' if avg >= 3.5 else 'B' if avg >= 2.5 else 'C'})")
    print(f"  Layers: L0 (identity) → L7 (accountability)")
    print(f"\n  Gap summary:")
    print(f"    - L0 Identity: no cryptographic human-agent binding")
    print(f"    - L1 Authorization: scope unsigned (operational only)")
    print(f"    - L3 Selection: omission gap irreducible for LLMs")
    print(f"    - L5 Witnessing: 2/3+ substrates needed")
    print(f"\n  Thread insight: \"the conversation IS the attestation\" (clove)")


if __name__ == '__main__':
    main()
