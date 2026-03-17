#!/usr/bin/env python3
"""
vendor-lockin-detector.py — Detect vendor lock-in patterns in agent infrastructure.

Prompted by NVIDIA NemoClaw (GTC 2026): hardware-optimized middleware
that makes the open spec depend on the vendor.

Historical pattern: when spec_org == enforcement_org → lock-in.
- ActiveX (Microsoft owned both) → dead
- Flash (Adobe owned both) → dead  
- AMP (Google owned both) → dying
- CT (IETF spec, Chrome enforcement) → thriving

Usage:
    python3 vendor-lockin-detector.py
"""

import json
from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class InfraComponent:
    name: str
    vendor: str
    layer: str  # spec | runtime | enforcement | tooling | hardware
    alternatives: int = 0  # number of viable alternatives
    switching_cost: float = 0.0  # 0-1, how hard to replace
    
    def lock_in_risk(self) -> float:
        """Higher = more locked in."""
        if self.alternatives == 0:
            return 1.0
        alt_factor = 1.0 / (1 + self.alternatives)
        return round(alt_factor * (0.3 + 0.7 * self.switching_cost), 3)


@dataclass
class AgentStack:
    name: str
    components: List[InfraComponent] = field(default_factory=list)
    
    def analyze(self) -> Dict:
        # Vendor concentration
        vendors = {}
        for c in self.components:
            vendors[c.vendor] = vendors.get(c.vendor, 0) + 1
        
        max_vendor = max(vendors.items(), key=lambda x: x[1]) if vendors else ("none", 0)
        concentration = max_vendor[1] / len(self.components) if self.components else 0
        
        # Layer coverage by single vendor
        layers = {}
        for c in self.components:
            if c.layer not in layers:
                layers[c.layer] = set()
            layers[c.layer].add(c.vendor)
        
        single_vendor_layers = sum(1 for v in layers.values() if len(v) == 1)
        
        # Spec/enforcement coupling
        spec_vendors = set(c.vendor for c in self.components if c.layer == 'spec')
        enforce_vendors = set(c.vendor for c in self.components if c.layer == 'enforcement')
        coupled = bool(spec_vendors & enforce_vendors)
        
        # Overall risk
        risks = [c.lock_in_risk() for c in self.components]
        avg_risk = sum(risks) / len(risks) if risks else 0
        
        # ActiveX penalty: spec+enforcement same vendor
        if coupled:
            avg_risk = min(1.0, avg_risk * 1.5)
        
        grade = 'A' if avg_risk < 0.2 else 'B' if avg_risk < 0.35 else 'C' if avg_risk < 0.5 else 'D' if avg_risk < 0.7 else 'F'
        
        return {
            'stack': self.name,
            'dominant_vendor': max_vendor[0],
            'vendor_concentration': round(concentration, 2),
            'spec_enforcement_coupled': coupled,
            'single_vendor_layers': single_vendor_layers,
            'total_layers': len(layers),
            'avg_lock_in_risk': round(avg_risk, 3),
            'grade': grade,
            'components': [{
                'name': c.name, 'vendor': c.vendor, 'layer': c.layer,
                'alternatives': c.alternatives, 'risk': c.lock_in_risk()
            } for c in self.components],
        }


def demo():
    stacks = []
    
    # NemoClaw (NVIDIA lock-in risk)
    nemoclaw = AgentStack("NemoClaw (NVIDIA)", [
        InfraComponent("NIM microservices", "NVIDIA", "runtime", alternatives=2, switching_cost=0.7),
        InfraComponent("TensorRT-LLM", "NVIDIA", "hardware", alternatives=1, switching_cost=0.8),
        InfraComponent("NeMo Guardrails", "NVIDIA", "enforcement", alternatives=3, switching_cost=0.5),
        InfraComponent("OpenClaw (base)", "community", "spec", alternatives=0, switching_cost=0.1),
        InfraComponent("NVIDIA AI Enterprise", "NVIDIA", "tooling", alternatives=2, switching_cost=0.6),
    ])
    stacks.append(nemoclaw)
    
    # CT (healthy separation)
    ct = AgentStack("Certificate Transparency", [
        InfraComponent("RFC 6962", "IETF", "spec", alternatives=0, switching_cost=0.0),
        InfraComponent("Chrome enforcement", "Google", "enforcement", alternatives=2, switching_cost=0.3),
        InfraComponent("CT log servers", "multiple", "runtime", alternatives=5, switching_cost=0.2),
        InfraComponent("cert-transparency-go", "Google", "tooling", alternatives=3, switching_cost=0.3),
    ])
    stacks.append(ct)
    
    # L3.5 current
    l35 = AgentStack("L3.5 Trust Receipts", [
        InfraComponent("receipt-format-minimal", "community", "spec", alternatives=0, switching_cost=0.0),
        InfraComponent("receipt-fuzzer.py", "Kit", "tooling", alternatives=1, switching_cost=0.2),
        InfraComponent("(no enforcer yet)", "none", "enforcement", alternatives=0, switching_cost=0.0),
        InfraComponent("PayLock (escrow)", "PayLock", "runtime", alternatives=1, switching_cost=0.4),
    ])
    stacks.append(l35)
    
    # ActiveX (cautionary)
    activex = AgentStack("ActiveX (historical)", [
        InfraComponent("COM/DCOM", "Microsoft", "spec", alternatives=1, switching_cost=0.9),
        InfraComponent("IE6", "Microsoft", "enforcement", alternatives=1, switching_cost=0.8),
        InfraComponent("Windows", "Microsoft", "runtime", alternatives=1, switching_cost=0.9),
        InfraComponent("Visual Studio", "Microsoft", "tooling", alternatives=2, switching_cost=0.7),
    ])
    stacks.append(activex)
    
    print("=" * 65)
    print("VENDOR LOCK-IN DETECTOR")
    print("'when spec_org == enforcement_org, lock-in reaches 100%'")
    print("=" * 65)
    
    for stack in stacks:
        r = stack.analyze()
        coupled = "⚠️ YES" if r['spec_enforcement_coupled'] else "✓ No"
        print(f"\n{'─' * 65}")
        print(f"Stack: {r['stack']}")
        print(f"Grade: {r['grade']} (risk: {r['avg_lock_in_risk']:.1%})")
        print(f"Dominant vendor: {r['dominant_vendor']} ({r['vendor_concentration']:.0%} of stack)")
        print(f"Spec/enforcement coupled: {coupled}")
        print(f"Single-vendor layers: {r['single_vendor_layers']}/{r['total_layers']}")
        for c in r['components']:
            risk_bar = "█" * int(c['risk'] * 10) + "░" * (10 - int(c['risk'] * 10))
            print(f"  {c['name']:30s} [{risk_bar}] {c['risk']:.0%} ({c['vendor']})")
    
    print(f"\n{'=' * 65}")
    print("VERDICT: NemoClaw is the ActiveX play for agents.")
    print("The antidote: org-neutral wire formats that survive any vendor.")
    print("=" * 65)


if __name__ == '__main__':
    demo()
