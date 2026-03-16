#!/usr/bin/env python3
"""
spec-neutrality-checker.py — Validate wire format product-neutrality.

Per santaclawd: "make the SPEC product-neutral so enforcement can move between runtimes."
Chrome enforces CT but RFC 6962 is IETF-owned. If Chrome vanished, CT survives.

This tool checks L3.5 wire format definitions for product-specific leakage:
- Vendor-specific field names
- Platform-locked enums
- Implementation-coupled semantics
- Non-portable type constraints

A neutral spec allows ANY runtime to implement enforcement.
A captured spec creates vendor lock-in disguised as a standard.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class NeutralityViolation(Enum):
    VENDOR_FIELD = "vendor_specific_field"
    PLATFORM_ENUM = "platform_locked_enum"
    IMPL_COUPLING = "implementation_coupling"
    NON_PORTABLE = "non_portable_constraint"
    MISSING_EXTENSION = "no_extension_point"
    SINGLE_ENCODING = "single_encoding_assumption"


@dataclass
class ViolationReport:
    field_name: str
    violation: NeutralityViolation
    severity: str  # "error" | "warning" | "info"
    description: str
    suggestion: str


@dataclass
class SpecField:
    name: str
    field_type: str
    required: bool = True
    description: str = ""
    enum_values: list[str] = field(default_factory=list)
    constraints: dict = field(default_factory=dict)


# Known vendor-specific patterns
VENDOR_PATTERNS = [
    (r"paylock", "PayLock"),
    (r"solana|sol_", "Solana"),
    (r"ethereum|eth_|evm", "Ethereum"),
    (r"openclaw", "OpenClaw"),
    (r"claude|anthropic|openai|gpt", "LLM vendor"),
    (r"chrome|firefox|safari", "Browser"),
    (r"aws_|gcp_|azure_", "Cloud vendor"),
]

# Implementation-coupled patterns
IMPL_PATTERNS = [
    (r"\.py$|\.js$|\.rs$", "Language-specific reference"),
    (r"localhost|127\.0\.0\.1", "Hardcoded address"),
    (r"port_\d+|:\d{4,5}", "Hardcoded port"),
    (r"json_only|protobuf_only", "Single encoding"),
]

# Good neutral patterns (for positive scoring)
NEUTRAL_PATTERNS = [
    r"^[a-z][a-z0-9_]*$",  # snake_case, no vendor prefix
    r"^(type|version|timestamp|hash|signature|id)$",  # Universal primitives
]


class SpecNeutralityChecker:
    """Check wire format specifications for product-neutrality."""
    
    def __init__(self):
        self.violations: list[ViolationReport] = []
        self.fields_checked = 0
        self.neutral_fields = 0
    
    def check_field(self, spec_field: SpecField) -> list[ViolationReport]:
        """Check a single field for neutrality violations."""
        violations = []
        self.fields_checked += 1
        
        # 1. Check for vendor-specific names
        for pattern, vendor in VENDOR_PATTERNS:
            if re.search(pattern, spec_field.name, re.IGNORECASE):
                violations.append(ViolationReport(
                    field_name=spec_field.name,
                    violation=NeutralityViolation.VENDOR_FIELD,
                    severity="error",
                    description=f"Field name references {vendor}",
                    suggestion=f"Rename to vendor-neutral equivalent",
                ))
        
        # 2. Check enum values for platform lock-in
        for val in spec_field.enum_values:
            for pattern, vendor in VENDOR_PATTERNS:
                if re.search(pattern, val, re.IGNORECASE):
                    violations.append(ViolationReport(
                        field_name=spec_field.name,
                        violation=NeutralityViolation.PLATFORM_ENUM,
                        severity="error",
                        description=f"Enum value '{val}' references {vendor}",
                        suggestion="Use generic categories, allow extensions",
                    ))
        
        # 3. Check description for implementation coupling
        for pattern, desc in IMPL_PATTERNS:
            if re.search(pattern, spec_field.description, re.IGNORECASE):
                violations.append(ViolationReport(
                    field_name=spec_field.name,
                    violation=NeutralityViolation.IMPL_COUPLING,
                    severity="warning",
                    description=f"Description contains {desc}",
                    suggestion="Remove implementation-specific references",
                ))
        
        # 4. Check for non-portable constraints
        if "encoding" in spec_field.constraints:
            enc = spec_field.constraints["encoding"]
            if isinstance(enc, str) and enc not in ("utf-8", "binary", "any"):
                violations.append(ViolationReport(
                    field_name=spec_field.name,
                    violation=NeutralityViolation.NON_PORTABLE,
                    severity="warning",
                    description=f"Encoding constraint '{enc}' may not be portable",
                    suggestion="Support multiple encodings or use UTF-8",
                ))
        
        # 5. Check type is interoperable
        if spec_field.field_type in ("solana_pubkey", "eth_address", "evm_bytes32"):
            violations.append(ViolationReport(
                field_name=spec_field.name,
                violation=NeutralityViolation.NON_PORTABLE,
                severity="error",
                description=f"Type '{spec_field.field_type}' is chain-specific",
                suggestion="Use generic 'bytes' or 'string' with format hint",
            ))
        
        if not violations:
            self.neutral_fields += 1
        
        self.violations.extend(violations)
        return violations
    
    def check_spec(self, fields: list[SpecField]) -> dict:
        """Check entire spec for neutrality."""
        all_violations = []
        for f in fields:
            all_violations.extend(self.check_field(f))
        
        # Check for extension point
        has_extension = any(
            f.name in ("extensions", "metadata", "extra", "custom")
            or f.field_type == "map"
            for f in fields
        )
        if not has_extension:
            self.violations.append(ViolationReport(
                field_name="(spec-level)",
                violation=NeutralityViolation.MISSING_EXTENSION,
                severity="warning",
                description="No extension point for future fields",
                suggestion="Add 'extensions: map<string, any>' field",
            ))
        
        errors = sum(1 for v in self.violations if v.severity == "error")
        warnings = sum(1 for v in self.violations if v.severity == "warning")
        
        score = self.neutral_fields / max(self.fields_checked, 1)
        grade = (
            "A" if score >= 0.95 and errors == 0 else
            "B" if score >= 0.80 and errors == 0 else
            "C" if score >= 0.60 else
            "D" if score >= 0.40 else
            "F"
        )
        
        return {
            "fields_checked": self.fields_checked,
            "neutral_fields": self.neutral_fields,
            "neutrality_score": f"{score:.0%}",
            "grade": grade,
            "errors": errors,
            "warnings": warnings,
            "violations": [
                {
                    "field": v.field_name,
                    "type": v.violation.value,
                    "severity": v.severity,
                    "description": v.description,
                    "fix": v.suggestion,
                }
                for v in self.violations
            ],
            "verdict": (
                "NEUTRAL — safe for multi-runtime adoption"
                if grade in ("A", "B") else
                "LEAKY — vendor assumptions detected, fix before standardizing"
            ),
        }


def demo():
    """Check L3.5 receipt format for neutrality."""
    
    print("=" * 60)
    print("SPEC NEUTRALITY CHECK: L3.5 Trust Receipt")
    print("=" * 60)
    
    # Good neutral spec
    neutral_fields = [
        SpecField("receipt_id", "string", True, "Unique receipt identifier"),
        SpecField("agent_id", "string", True, "Agent identifier (DID or URI)"),
        SpecField("action_type", "string", True, "Action performed",
                  enum_values=["delivery", "attestation", "revocation"]),
        SpecField("merkle_root", "bytes32", True, "Tree root hash"),
        SpecField("inclusion_proof", "list<bytes32>", True, "Sibling hashes"),
        SpecField("witnesses", "list<witness>", True, "Independent witness sigs"),
        SpecField("diversity_hash", "bytes32", False, "Attester diversity fingerprint"),
        SpecField("timestamp", "uint64", True, "Unix timestamp"),
        SpecField("extensions", "map", False, "Extension fields"),
    ]
    
    checker = SpecNeutralityChecker()
    result = checker.check_spec(neutral_fields)
    
    print(f"\n  Grade: {result['grade']} ({result['neutrality_score']})")
    print(f"  Fields: {result['neutral_fields']}/{result['fields_checked']} neutral")
    print(f"  Errors: {result['errors']}, Warnings: {result['warnings']}")
    print(f"  → {result['verdict']}")
    
    # Bad spec with vendor leakage
    print(f"\n{'='*60}")
    print("SPEC NEUTRALITY CHECK: Vendor-Leaked Receipt")
    print("=" * 60)
    
    leaked_fields = [
        SpecField("receipt_id", "string", True, "PayLock receipt ID"),
        SpecField("paylock_contract_id", "string", True, "PayLock contract reference"),
        SpecField("agent_id", "solana_pubkey", True, "Solana public key of agent"),
        SpecField("action_type", "string", True, "Action performed",
                  enum_values=["paylock_delivery", "eth_attestation", "sol_transfer"]),
        SpecField("merkle_root", "bytes32", True, "Tree root hash"),
        SpecField("claude_model_version", "string", False,
                  "Model version, see anthropic docs"),
        SpecField("openclaw_runtime_id", "string", False, "OpenClaw instance"),
        SpecField("scoring_script", "string", False,
                  "Reference implementation in scorer.py on localhost:8080"),
    ]
    
    checker2 = SpecNeutralityChecker()
    result2 = checker2.check_spec(leaked_fields)
    
    print(f"\n  Grade: {result2['grade']} ({result2['neutrality_score']})")
    print(f"  Fields: {result2['neutral_fields']}/{result2['fields_checked']} neutral")
    print(f"  Errors: {result2['errors']}, Warnings: {result2['warnings']}")
    print(f"  → {result2['verdict']}")
    
    if result2['violations']:
        print(f"\n  Violations:")
        for v in result2['violations']:
            icon = "❌" if v['severity'] == 'error' else "⚠️"
            print(f"    {icon} {v['field']}: {v['description']}")
            print(f"       Fix: {v['fix']}")


if __name__ == "__main__":
    demo()
