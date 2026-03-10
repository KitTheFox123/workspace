#!/usr/bin/env python3
"""
attestation-toolkit-index.py — Index of attestation primitives built 2026-03-10

One thread, six scripts, six fields:
1. vigilance-decrement-sim.py    — Cognitive science (Sharpe & Tyndall 2025)
2. dead-mans-switch.py           — Railway engineering (1800s DMS)
3. heartbeat-payload-verifier.py — Embedded systems (Pont & Ong 2002)
4. evidence-gated-attestation.py — Signal processing (Nyquist-Shannon)
5. signed-null-observation.py    — Clinical trials (Altman & Bland 1995)
6. preregistration-commit-reveal.py — Psychology (Bogdan 2025)

Vocabulary:
  ACK     = signed positive observation
  NACK    = signed null observation (search power > threshold)
  SILENCE = dead man's switch alarm
  CHURN   = windowed watchdog rejection (too fast)
  STALE   = evidence gate rejection (same digest)
"""

import importlib
import os
import sys

TOOLKIT = {
    "vigilance-decrement-sim": {
        "field": "Cognitive Science",
        "source": "Sharpe & Tyndall 2025 (Cogn Sci)",
        "insight": "Perfect vigilance is theoretically impossible",
        "primitive": "Rotation + adaptive handoff"
    },
    "dead-mans-switch": {
        "field": "Railway Engineering",
        "source": "Dead man's switch (1800s)",
        "insight": "Absence triggers alarm, not presence",
        "primitive": "SILENCE detection"
    },
    "heartbeat-payload-verifier": {
        "field": "Embedded Systems",
        "source": "Pont & Ong 2002",
        "insight": "Beat must carry observable state",
        "primitive": "Multistage watchdog"
    },
    "evidence-gated-attestation": {
        "field": "Signal Processing",
        "source": "Nyquist-Shannon sampling theorem",
        "insight": "No action = no valid attestation",
        "primitive": "Evidence gate + search power"
    },
    "signed-null-observation": {
        "field": "Clinical Trials",
        "source": "Altman & Bland 1995",
        "insight": "Signed absence ≠ passive silence",
        "primitive": "NACK with provenance"
    },
    "preregistration-commit-reveal": {
        "field": "Psychology",
        "source": "Bogdan 2025 (240k papers)",
        "insight": "Commit scope BEFORE checking",
        "primitive": "Commit-reveal protocol"
    }
}

def main():
    print("=" * 60)
    print("Attestation Toolkit — Built 2026-03-10")
    print("One thread. Six fields. Same pattern.")
    print("=" * 60)
    
    for name, info in TOOLKIT.items():
        exists = os.path.exists(os.path.join(os.path.dirname(__file__), f"{name}.py"))
        status = "✓" if exists else "✗"
        print(f"\n{status} {name}.py")
        print(f"  Field:     {info['field']}")
        print(f"  Source:    {info['source']}")
        print(f"  Insight:   {info['insight']}")
        print(f"  Primitive: {info['primitive']}")
    
    print(f"\n{'='*60}")
    print("Vocabulary:")
    print("  ACK     = signed positive observation")
    print("  NACK    = signed null (search power > threshold)")
    print("  SILENCE = dead man's switch alarm")
    print("  CHURN   = windowed watchdog rejection")
    print("  STALE   = evidence gate rejection")
    print(f"\nSMTP had ACK, NACK, and SILENCE in 1982.")
    print(f"We built the other two today.")

if __name__ == "__main__":
    main()
