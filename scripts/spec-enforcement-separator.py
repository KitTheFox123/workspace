#!/usr/bin/env python3
"""
spec-enforcement-separator.py — Validate spec/enforcement separation in protocol design.

The Pattern (TCP/IP → HTML → CT → L3.5):
  - Spec org ≠ enforcement org
  - DARPA wrote TCP/IP, BSD enforced it
  - W3C writes HTML, browsers render it
  - IETF wrote CT (RFC 6962), Chrome enforced it
  - When they merge → vendor lock-in (ActiveX, Flash, AMP)

Design principle: prescribe WIRE FORMAT (interop), leave POLICY to consumers.
RFC 9413 lesson: Postel's Law ("be liberal") caused ossification.

This tool audits a protocol spec for separation violations:
  1. Does the spec mandate scoring algorithms? (violation: policy in spec)
  2. Does the spec mandate specific implementations? (violation: enforcement in spec)
  3. Is the wire format self-describing? (requirement: interop without shared code)
  4. Can a new enforcer adopt the spec without the original org? (portability test)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Layer(Enum):
    WIRE_FORMAT = "wire_format"       # What goes on the wire (SPEC)
    VALIDATION = "validation"         # Is the data well-formed? (SPEC)
    POLICY = "policy"                 # What do we do with it? (ENFORCEMENT)
    SCORING = "scoring"               # How do we rank/weight? (ENFORCEMENT)
    GOVERNANCE = "governance"         # Who decides changes? (SPEC ORG)
    ENFORCEMENT = "enforcement"       # Who rejects non-compliance? (ENFORCER)


class Coupling(Enum):
    """How tightly spec and enforcement are coupled."""
    SEPARATED = "separated"     # IETF/Chrome model — gold standard
    LOOSE = "loose"             # Same org but different teams
    COUPLED = "coupled"         # Same codebase, different modules
    FUSED = "fused"             # Vendor lock-in (ActiveX model)


@dataclass
class SpecElement:
    """A single element of a protocol specification."""
    name: str
    layer: Layer
    description: str
    in_spec: bool          # Should this be in the spec?
    in_enforcer: bool      # Should this be in the enforcer?
    currently_in_spec: bool     # Where is it actually?
    currently_in_enforcer: bool
    
    @property
    def correctly_placed(self) -> bool:
        return (self.in_spec == self.currently_in_spec and 
                self.in_enforcer == self.currently_in_enforcer)
    
    @property
    def violation_type(self) -> Optional[str]:
        if self.correctly_placed:
            return None
        if self.currently_in_spec and not self.in_spec:
            return "policy_in_spec"  # Enforcement logic leaked into spec
        if self.currently_in_enforcer and not self.in_enforcer:
            return "spec_in_enforcer"  # Spec logic locked in enforcer
        return "misplaced"


@dataclass
class SeparationAudit:
    """Audit result for spec/enforcement separation."""
    protocol_name: str
    elements: list[SpecElement]
    coupling: Coupling
    spec_org: str
    enforcement_org: str
    
    @property
    def violations(self) -> list[SpecElement]:
        return [e for e in self.elements if not e.correctly_placed]
    
    @property
    def policy_in_spec_count(self) -> int:
        return sum(1 for e in self.violations if e.violation_type == "policy_in_spec")
    
    @property  
    def spec_in_enforcer_count(self) -> int:
        return sum(1 for e in self.violations if e.violation_type == "spec_in_enforcer")
    
    @property
    def separation_score(self) -> float:
        if not self.elements:
            return 0.0
        return sum(1 for e in self.elements if e.correctly_placed) / len(self.elements)
    
    @property
    def portability(self) -> float:
        """Can a new enforcer adopt without the original org?"""
        # Portability = 1 - (fraction of spec locked in enforcer)
        enforcer_locked = sum(1 for e in self.elements 
                            if e.in_spec and e.currently_in_enforcer and not e.currently_in_spec)
        if not self.elements:
            return 0.0
        return 1.0 - (enforcer_locked / len(self.elements))
    
    def grade(self) -> str:
        score = self.separation_score
        if score >= 0.95 and self.coupling in (Coupling.SEPARATED, Coupling.LOOSE):
            return "A"
        elif score >= 0.85:
            return "B"
        elif score >= 0.70:
            return "C"
        elif score >= 0.50:
            return "D"
        return "F"
    
    def report(self) -> str:
        lines = [
            f"=== Spec/Enforcement Separation Audit: {self.protocol_name} ===",
            f"Spec org: {self.spec_org}",
            f"Enforcement org: {self.enforcement_org}",
            f"Coupling: {self.coupling.value}",
            f"Separation: {self.separation_score:.0%} ({self.grade()})",
            f"Portability: {self.portability:.0%}",
            f"Violations: {len(self.violations)}/{len(self.elements)}",
        ]
        
        if self.policy_in_spec_count:
            lines.append(f"  ⚠️ Policy in spec: {self.policy_in_spec_count}")
        if self.spec_in_enforcer_count:
            lines.append(f"  ⚠️ Spec in enforcer: {self.spec_in_enforcer_count}")
        
        for v in self.violations:
            lines.append(f"  ❌ {v.name}: {v.violation_type} ({v.layer.value})")
        
        return "\n".join(lines)


# Historical case studies
CASE_STUDIES = {
    "CT (RFC 6962 + Chrome)": SeparationAudit(
        protocol_name="Certificate Transparency",
        spec_org="IETF",
        enforcement_org="Google Chrome",
        coupling=Coupling.SEPARATED,
        elements=[
            SpecElement("SCT format", Layer.WIRE_FORMAT, "Signed Certificate Timestamp",
                       in_spec=True, in_enforcer=False, currently_in_spec=True, currently_in_enforcer=False),
            SpecElement("Log API", Layer.WIRE_FORMAT, "Append/query interface",
                       in_spec=True, in_enforcer=False, currently_in_spec=True, currently_in_enforcer=False),
            SpecElement("Merkle proof", Layer.VALIDATION, "Inclusion proof format",
                       in_spec=True, in_enforcer=False, currently_in_spec=True, currently_in_enforcer=False),
            SpecElement("SCT count policy", Layer.POLICY, "How many SCTs required",
                       in_spec=False, in_enforcer=True, currently_in_spec=False, currently_in_enforcer=True),
            SpecElement("Log operator list", Layer.ENFORCEMENT, "Which logs are trusted",
                       in_spec=False, in_enforcer=True, currently_in_spec=False, currently_in_enforcer=True),
            SpecElement("Enforcement date", Layer.ENFORCEMENT, "When to reject non-CT certs",
                       in_spec=False, in_enforcer=True, currently_in_spec=False, currently_in_enforcer=True),
        ],
    ),
    "L3.5 Trust (current design)": SeparationAudit(
        protocol_name="L3.5 Trust Receipts",
        spec_org="isnad-rfc (GitHub)",
        enforcement_org="TBD (first mover)",
        coupling=Coupling.SEPARATED,
        elements=[
            SpecElement("Receipt wire format", Layer.WIRE_FORMAT, "T/G/A/S/C dimensions",
                       in_spec=True, in_enforcer=False, currently_in_spec=True, currently_in_enforcer=False),
            SpecElement("Merkle inclusion proof", Layer.VALIDATION, "Receipt tree proof",
                       in_spec=True, in_enforcer=False, currently_in_spec=True, currently_in_enforcer=False),
            SpecElement("Witness signature format", Layer.WIRE_FORMAT, "Attestation envelope",
                       in_spec=True, in_enforcer=False, currently_in_spec=True, currently_in_enforcer=False),
            SpecElement("Scoring algorithm", Layer.SCORING, "How to weight dimensions",
                       in_spec=False, in_enforcer=True, currently_in_spec=False, currently_in_enforcer=True),
            SpecElement("SLASH triggers", Layer.POLICY, "What warrants slashing",
                       in_spec=True, in_enforcer=True, currently_in_spec=True, currently_in_enforcer=True),
            SpecElement("Graduation schedule", Layer.ENFORCEMENT, "REPORT→STRICT timeline",
                       in_spec=False, in_enforcer=True, currently_in_spec=False, currently_in_enforcer=True),
            SpecElement("Min witness count", Layer.POLICY, "N≥2 requirement",
                       in_spec=True, in_enforcer=True, currently_in_spec=True, currently_in_enforcer=False),
        ],
    ),
    "ActiveX (anti-pattern)": SeparationAudit(
        protocol_name="ActiveX Controls",
        spec_org="Microsoft",
        enforcement_org="Microsoft IE",
        coupling=Coupling.FUSED,
        elements=[
            SpecElement("COM interface", Layer.WIRE_FORMAT, "Component Object Model",
                       in_spec=True, in_enforcer=False, currently_in_spec=True, currently_in_enforcer=True),
            SpecElement("Security zones", Layer.POLICY, "Trust levels per origin",
                       in_spec=False, in_enforcer=True, currently_in_spec=True, currently_in_enforcer=True),
            SpecElement("Code signing", Layer.VALIDATION, "Authenticode signatures",
                       in_spec=True, in_enforcer=False, currently_in_spec=True, currently_in_enforcer=True),
            SpecElement("Registry permissions", Layer.ENFORCEMENT, "Which controls allowed",
                       in_spec=False, in_enforcer=True, currently_in_spec=True, currently_in_enforcer=True),
            SpecElement("Update mechanism", Layer.ENFORCEMENT, "Windows Update only",
                       in_spec=False, in_enforcer=True, currently_in_spec=True, currently_in_enforcer=True),
        ],
    ),
}


def demo():
    for name, audit in CASE_STUDIES.items():
        print(f"\n{audit.report()}")
        print()
    
    # Summary comparison
    print("=" * 60)
    print("COMPARISON: Spec/Enforcement Separation")
    print("=" * 60)
    print(f"{'Protocol':<30} {'Grade':>5} {'Sep%':>5} {'Port%':>5} {'Coupling':<12}")
    print("-" * 60)
    for name, audit in CASE_STUDIES.items():
        print(f"{name:<30} {audit.grade():>5} {audit.separation_score:>4.0%} {audit.portability:>4.0%} {audit.coupling.value:<12}")
    
    print(f"\n💡 Key insight: CT scores A because IETF owns the spec,")
    print(f"   Chrome owns the enforcement. Neither can lock out the other.")
    print(f"   ActiveX scored F because Microsoft owned both → vendor lock-in.")
    print(f"   L3.5 follows CT model: GitHub spec, runtime enforcement.")


if __name__ == "__main__":
    demo()
