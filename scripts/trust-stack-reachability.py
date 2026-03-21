#!/usr/bin/env python3
"""
trust-stack-reachability.py — Layer 0: transport reachability for trust stack.

Per santaclawd: "six layers of agent trust infrastructure — and all six assume reachability."
Layer 0 is transport. SMTP IS layer 0.

Probes all 6 trust layers from transport up:
  L0: Transport (MX record, SMTP connectivity)
  L1: Genesis (publish endpoint reachable)
  L2: Independence (oracle uptime)
  L3: Revocation (fresh CRL available)
  L4: Correction (receipt delivery working)
  L5: Attestation (sidecar composition possible)

If L0 fails, all layers above are unreachable.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class LayerStatus(Enum):
    REACHABLE = "REACHABLE"
    DEGRADED = "DEGRADED"
    UNREACHABLE = "UNREACHABLE"
    UNKNOWN = "UNKNOWN"


@dataclass
class LayerProbe:
    layer: int
    name: str
    status: LayerStatus
    latency_ms: Optional[float] = None
    last_success: Optional[datetime] = None
    detail: str = ""


@dataclass 
class TrustStackReachability:
    """Probes trust stack reachability from transport up."""
    
    layers = [
        (0, "transport", "MX/SMTP connectivity"),
        (1, "genesis", "registry publish endpoint"),
        (2, "independence", "oracle uptime"),
        (3, "revocation", "CRL freshness"),
        (4, "correction", "receipt delivery"),
        (5, "attestation", "sidecar composition"),
    ]
    
    def probe(self, agent_email: str, 
              transport_ok: bool = True,
              genesis_endpoint: Optional[str] = None,
              oracle_count: int = 0,
              crl_age_hours: float = 0,
              last_receipt_hours: float = 0,
              sidecar_ok: bool = True) -> dict:
        """Probe all layers. If L0 fails, everything above is UNREACHABLE."""
        
        now = datetime.utcnow()
        probes = []
        cascade_fail = False
        
        # L0: Transport
        if transport_ok:
            probes.append(LayerProbe(0, "transport", LayerStatus.REACHABLE,
                                     detail=f"MX for {agent_email.split('@')[1]} resolves"))
        else:
            probes.append(LayerProbe(0, "transport", LayerStatus.UNREACHABLE,
                                     detail="MX resolution failed — all layers cascade"))
            cascade_fail = True
        
        # L1: Genesis
        if cascade_fail:
            probes.append(LayerProbe(1, "genesis", LayerStatus.UNREACHABLE,
                                     detail="cascade from L0"))
        elif genesis_endpoint:
            probes.append(LayerProbe(1, "genesis", LayerStatus.REACHABLE,
                                     detail=f"registry at {genesis_endpoint}"))
        else:
            probes.append(LayerProbe(1, "genesis", LayerStatus.UNKNOWN,
                                     detail="no genesis endpoint configured"))
        
        # L2: Independence
        if cascade_fail:
            probes.append(LayerProbe(2, "independence", LayerStatus.UNREACHABLE,
                                     detail="cascade from L0"))
        elif oracle_count >= 3:
            probes.append(LayerProbe(2, "independence", LayerStatus.REACHABLE,
                                     detail=f"{oracle_count} oracles responding"))
        elif oracle_count > 0:
            probes.append(LayerProbe(2, "independence", LayerStatus.DEGRADED,
                                     detail=f"only {oracle_count}/3 minimum oracles"))
        else:
            probes.append(LayerProbe(2, "independence", LayerStatus.UNREACHABLE,
                                     detail="no oracles responding"))
        
        # L3: Revocation
        if cascade_fail:
            probes.append(LayerProbe(3, "revocation", LayerStatus.UNREACHABLE,
                                     detail="cascade from L0"))
        elif crl_age_hours <= 24:
            probes.append(LayerProbe(3, "revocation", LayerStatus.REACHABLE,
                                     detail=f"CRL age {crl_age_hours:.1f}h (fresh)"))
        elif crl_age_hours <= 72:
            probes.append(LayerProbe(3, "revocation", LayerStatus.DEGRADED,
                                     detail=f"CRL age {crl_age_hours:.1f}h (stale)"))
        else:
            probes.append(LayerProbe(3, "revocation", LayerStatus.UNREACHABLE,
                                     detail=f"CRL age {crl_age_hours:.1f}h (expired)"))
        
        # L4: Correction
        if cascade_fail:
            probes.append(LayerProbe(4, "correction", LayerStatus.UNREACHABLE,
                                     detail="cascade from L0"))
        elif last_receipt_hours <= 24:
            probes.append(LayerProbe(4, "correction", LayerStatus.REACHABLE,
                                     detail=f"last receipt {last_receipt_hours:.1f}h ago"))
        elif last_receipt_hours <= 168:
            probes.append(LayerProbe(4, "correction", LayerStatus.DEGRADED,
                                     detail=f"last receipt {last_receipt_hours:.1f}h ago"))
        else:
            probes.append(LayerProbe(4, "correction", LayerStatus.UNREACHABLE,
                                     detail=f"no receipts in {last_receipt_hours:.0f}h"))
        
        # L5: Attestation
        if cascade_fail:
            probes.append(LayerProbe(5, "attestation", LayerStatus.UNREACHABLE,
                                     detail="cascade from L0"))
        elif sidecar_ok and not any(p.status == LayerStatus.UNREACHABLE for p in probes[1:]):
            probes.append(LayerProbe(5, "attestation", LayerStatus.REACHABLE,
                                     detail="sidecar composition available"))
        else:
            failed = [p.name for p in probes if p.status == LayerStatus.UNREACHABLE]
            probes.append(LayerProbe(5, "attestation", LayerStatus.DEGRADED,
                                     detail=f"blocked by: {', '.join(failed)}"))
        
        # Overall verdict
        reachable = sum(1 for p in probes if p.status == LayerStatus.REACHABLE)
        degraded = sum(1 for p in probes if p.status == LayerStatus.DEGRADED)
        unreachable = sum(1 for p in probes if p.status == LayerStatus.UNREACHABLE)
        
        if unreachable == 0 and degraded == 0:
            verdict = "FULLY_REACHABLE"
            grade = "A"
        elif unreachable == 0:
            verdict = "DEGRADED"
            grade = "C"
        elif probes[0].status == LayerStatus.UNREACHABLE:
            verdict = "CASCADE_FAILURE"
            grade = "F"
        else:
            verdict = "PARTIAL_FAILURE"
            grade = "D"
        
        return {
            "agent": agent_email,
            "verdict": verdict,
            "grade": grade,
            "reachable": reachable,
            "degraded": degraded,
            "unreachable": unreachable,
            "layers": [{
                "layer": p.layer,
                "name": p.name,
                "status": p.status.value,
                "detail": p.detail
            } for p in probes]
        }


def demo():
    checker = TrustStackReachability()
    
    scenarios = [
        ("healthy", dict(agent_email="kit_fox@agentmail.to", transport_ok=True,
                         genesis_endpoint="registry.example.com", oracle_count=5,
                         crl_age_hours=6, last_receipt_hours=2, sidecar_ok=True)),
        ("transport_down", dict(agent_email="dead@nowhere.invalid", transport_ok=False,
                                oracle_count=5, crl_age_hours=6, last_receipt_hours=2)),
        ("degraded_stack", dict(agent_email="weak@agentmail.to", transport_ok=True,
                                genesis_endpoint="registry.example.com", oracle_count=1,
                                crl_age_hours=48, last_receipt_hours=100)),
    ]
    
    for name, params in scenarios:
        result = checker.probe(**params)
        print(f"\n{'='*50}")
        print(f"Scenario: {name} | Grade: {result['grade']} | {result['verdict']}")
        for layer in result['layers']:
            status_icon = {"REACHABLE": "✓", "DEGRADED": "~", "UNREACHABLE": "✗", "UNKNOWN": "?"}
            print(f"  L{layer['layer']} [{status_icon[layer['status']]}] {layer['name']}: {layer['detail']}")


if __name__ == "__main__":
    demo()
