#!/usr/bin/env python3
"""
Postel Patch Scorer — Apply LangSec's patch to Postel's principle for agent comms.

Sassaman & Patterson (LangSec): "Liberal acceptance" misinterpreted as "trust all input."
The patch: message complexity must match parser power. Context-sensitive grammars require
Turing-complete parsers → undecidable validation → exploitation surface.

Agent receipt schema design principle:
  - SEND (egress): Strict. Reject anything that doesn't match the formal grammar.
  - RECEIVE (ingress): Accept known envelope, quarantine unknown payload.
  - PARSE: Receipt format must be context-FREE (decidable), not context-sensitive.
  - REJECT: Proper rejection is as important as acceptance.

Complexity tiers (Chomsky hierarchy):
  Type 3 (Regular): Simple key-value pairs. Regex-parseable. SAFE.
  Type 2 (Context-Free): Nested structures (JSON). PDA-parseable. MOSTLY SAFE.
  Type 1 (Context-Sensitive): Cross-field dependencies. LBA-required. DANGEROUS.
  Type 0 (Recursively Enumerable): Turing-complete input. UNDECIDABLE. EXPLOIT TERRITORY.

Usage:
    python3 postel-patch-scorer.py              # Demo
    echo '{"schema": {...}}' | python3 postel-patch-scorer.py --stdin
"""

import json, sys

COMPLEXITY_TIERS = {
    "regular": {
        "chomsky": "Type 3",
        "parser": "Finite automaton / Regex",
        "decidable": True,
        "safe": True,
        "risk": 0.1,
        "examples": ["key=value pairs", "fixed-width fields", "CSV"],
    },
    "context_free": {
        "chomsky": "Type 2",
        "parser": "Pushdown automaton",
        "decidable": True,
        "safe": True,  # mostly
        "risk": 0.3,
        "examples": ["JSON", "XML", "S-expressions", "receipt envelope"],
    },
    "context_sensitive": {
        "chomsky": "Type 1",
        "parser": "Linear bounded automaton",
        "decidable": True,
        "safe": False,
        "risk": 0.7,
        "examples": ["cross-field validation", "conditional formats", "protocol negotiation"],
    },
    "recursively_enumerable": {
        "chomsky": "Type 0",
        "parser": "Turing machine",
        "decidable": False,
        "safe": False,
        "risk": 1.0,
        "examples": ["arbitrary code in payload", "eval()", "template languages"],
    },
}


def score_schema(schema: dict) -> dict:
    """Score a message schema against the Postel patch."""
    
    envelope_complexity = schema.get("envelope_complexity", "context_free")
    payload_complexity = schema.get("payload_complexity", "context_free")
    
    env_tier = COMPLEXITY_TIERS.get(envelope_complexity, COMPLEXITY_TIERS["context_sensitive"])
    pay_tier = COMPLEXITY_TIERS.get(payload_complexity, COMPLEXITY_TIERS["context_sensitive"])
    
    # Egress strictness
    egress_strict = schema.get("egress_validation", False)
    egress_grammar = schema.get("egress_formal_grammar", False)
    
    # Ingress handling
    ingress_quarantine = schema.get("ingress_quarantine_unknown", False)
    ingress_reject_malformed = schema.get("ingress_reject_malformed", False)
    
    # Rejection capability (LangSec: "proper rejection is crucial to safe recognition")
    has_rejection = schema.get("has_explicit_rejection", False)
    
    # Score components
    complexity_score = 1.0 - (env_tier["risk"] * 0.6 + pay_tier["risk"] * 0.4)
    
    egress_score = (0.5 if egress_strict else 0) + (0.5 if egress_grammar else 0)
    
    ingress_score = (0.4 if ingress_quarantine else 0) + \
                    (0.4 if ingress_reject_malformed else 0) + \
                    (0.2 if has_rejection else 0)
    
    # Composite (LangSec weights: complexity > egress > ingress)
    composite = complexity_score * 0.4 + egress_score * 0.35 + ingress_score * 0.25
    
    if composite >= 0.8: grade = "A"
    elif composite >= 0.6: grade = "B"
    elif composite >= 0.4: grade = "C"
    elif composite >= 0.2: grade = "D"
    else: grade = "F"
    
    # LangSec diagnosis
    issues = []
    if not env_tier["safe"]:
        issues.append(f"Envelope is {env_tier['chomsky']} — requires {env_tier['parser']}. Reduce complexity.")
    if not pay_tier["safe"]:
        issues.append(f"Payload is {pay_tier['chomsky']} — exploitation surface. Quarantine required.")
    if not egress_strict:
        issues.append("No egress validation. Anti-Postel violated: strict sending required.")
    if not has_rejection:
        issues.append("No explicit rejection. LangSec: 'proper rejection is crucial to safe recognition.'")
    
    return {
        "composite_score": round(composite, 3),
        "grade": grade,
        "complexity_score": round(complexity_score, 3),
        "egress_score": round(egress_score, 3),
        "ingress_score": round(ingress_score, 3),
        "envelope": {
            "complexity": envelope_complexity,
            "chomsky": env_tier["chomsky"],
            "parser_required": env_tier["parser"],
            "decidable": env_tier["decidable"],
            "safe": env_tier["safe"],
        },
        "payload": {
            "complexity": payload_complexity,
            "chomsky": pay_tier["chomsky"],
            "safe": pay_tier["safe"],
        },
        "issues": issues,
        "langsec_note": "Sassaman & Patterson: message complexity must match parser power. Underpowered parsers = exploitation.",
    }


def demo():
    print("=== Postel Patch Scorer (LangSec) ===")
    print("Sassaman & Patterson: patch Postel's principle for security\n")
    
    # Receipt schema (well-designed)
    receipt = {
        "envelope_complexity": "context_free",   # JSON envelope
        "payload_complexity": "context_free",     # JSON payload
        "egress_validation": True,
        "egress_formal_grammar": True,            # JSON schema
        "ingress_quarantine_unknown": True,
        "ingress_reject_malformed": True,
        "has_explicit_rejection": True,
    }
    
    print("Receipt schema (JSON envelope + payload):")
    r = score_schema(receipt)
    print(f"  Score: {r['composite_score']} ({r['grade']})")
    print(f"  Envelope: {r['envelope']['chomsky']} ({r['envelope']['parser_required']})")
    print(f"  Issues: {r['issues'] or 'None'}")
    
    # Dangerous schema (eval in payload)
    dangerous = {
        "envelope_complexity": "context_free",
        "payload_complexity": "recursively_enumerable",  # arbitrary code
        "egress_validation": False,
        "egress_formal_grammar": False,
        "ingress_quarantine_unknown": False,
        "ingress_reject_malformed": False,
        "has_explicit_rejection": False,
    }
    
    print("\nDangerous schema (eval() in payload):")
    r = score_schema(dangerous)
    print(f"  Score: {r['composite_score']} ({r['grade']})")
    print(f"  Payload: {r['payload']['chomsky']} — safe={r['payload']['safe']}")
    for issue in r['issues']:
        print(f"  ⚠️ {issue}")
    
    # Simple schema (key-value only)
    simple = {
        "envelope_complexity": "regular",
        "payload_complexity": "regular",
        "egress_validation": True,
        "egress_formal_grammar": True,
        "ingress_quarantine_unknown": True,
        "ingress_reject_malformed": True,
        "has_explicit_rejection": True,
    }
    
    print("\nSimple schema (key-value, regex-parseable):")
    r = score_schema(simple)
    print(f"  Score: {r['composite_score']} ({r['grade']})")
    print(f"  Complexity: {r['complexity_score']} (max safety)")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = score_schema(data)
        print(json.dumps(result, indent=2))
    else:
        demo()
