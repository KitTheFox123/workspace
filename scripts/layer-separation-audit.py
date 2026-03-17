#!/usr/bin/env python3
"""
layer-separation-audit.py — Audit protocol layer separation health.

Email survived 50 years by separating 4 concerns:
  Format (MIME) | Transport (SMTP) | Identity (address) | Trust (DKIM)

L3.5 needs the same:
  Format (JSON schema) | Transport (any) | Identity (agent_id) | Trust (Merkle+witnesses)

When layers leak into each other, the protocol becomes brittle.
This tool detects layer violations.

Usage:
    python3 layer-separation-audit.py
"""

import json
from dataclasses import dataclass, field
from typing import List, Dict


LAYERS = ['format', 'transport', 'identity', 'trust']

# Fields that belong to each layer
LAYER_FIELDS = {
    'format': {
        'owns': ['version', 'decision_type', 'dimensions', 'timestamp'],
        'description': 'Wire format structure. What the receipt looks like.',
    },
    'transport': {
        'owns': ['delivery_method', 'endpoint', 'protocol', 'retry_policy'],
        'description': 'How the receipt moves. Email, HTTP, P2P.',
    },
    'identity': {
        'owns': ['agent_id', 'task_hash', 'operator_id'],
        'description': 'Who the parties are. Opaque identifiers.',
    },
    'trust': {
        'owns': ['merkle_root', 'merkle_proof', 'witnesses', 'scar_reference'],
        'description': 'Why you should believe it. Proof and attestation.',
    },
}

# Known layer violations
VIOLATIONS = {
    'transport_in_format': {
        'fields': ['origin_platform', 'delivery_endpoint', 'api_version', 'platform_tx_id'],
        'severity': 'HIGH',
        'explanation': 'Transport details in wire format = platform lock-in.',
        'example': 'ActiveX required IE. Flash required Adobe runtime.',
    },
    'trust_in_format': {
        'fields': ['compliance_grade', 'trust_score', 'enforcement_mode', 'leitner_box'],
        'severity': 'CRITICAL',
        'explanation': 'Trust policy in wire format = receipt is no longer evidence.',
        'example': 'Credit score embedded in transaction record.',
    },
    'format_in_transport': {
        'fields': ['content_type_override', 'schema_version_header'],
        'severity': 'MEDIUM',
        'explanation': 'Format details in transport = coupling.',
    },
    'identity_in_trust': {
        'fields': ['attester_reputation', 'witness_trust_score'],
        'severity': 'HIGH',
        'explanation': 'Identity judgments in trust layer = circular reasoning.',
    },
}


@dataclass
class ProtocolSpec:
    name: str
    fields: Dict[str, str] = field(default_factory=dict)  # field_name -> layer
    
    def audit(self) -> Dict:
        violations = []
        layer_counts = {l: 0 for l in LAYERS}
        
        for fname, layer in self.fields.items():
            if layer in layer_counts:
                layer_counts[layer] += 1
            
            # Check for known violations
            for vtype, vinfo in VIOLATIONS.items():
                if fname in vinfo['fields']:
                    violations.append({
                        'field': fname,
                        'violation': vtype,
                        'severity': vinfo['severity'],
                        'explanation': vinfo['explanation'],
                    })
        
        # Layer balance
        total = sum(layer_counts.values())
        balance = {}
        for layer, count in layer_counts.items():
            balance[layer] = round(count / max(total, 1), 2)
        
        # Separation score
        n_violations = len(violations)
        critical = sum(1 for v in violations if v['severity'] == 'CRITICAL')
        high = sum(1 for v in violations if v['severity'] == 'HIGH')
        
        score = 1.0 - (critical * 0.3) - (high * 0.15) - (n_violations * 0.05)
        score = max(0.0, min(1.0, score))
        grade = 'A' if score > 0.9 else 'B' if score > 0.7 else 'C' if score > 0.5 else 'D' if score > 0.3 else 'F'
        
        return {
            'name': self.name,
            'field_count': total,
            'layer_balance': balance,
            'violations': violations,
            'separation_score': round(score, 2),
            'grade': grade,
        }


def demo():
    # Email (the gold standard)
    email = ProtocolSpec("Email (MIME+SMTP+DKIM)", {
        'content-type': 'format', 'subject': 'format', 'body': 'format', 'date': 'format',
        'smtp-server': 'transport', 'mx-record': 'transport', 'tls': 'transport',
        'from': 'identity', 'to': 'identity', 'message-id': 'identity',
        'dkim-signature': 'trust', 'spf': 'trust', 'dmarc': 'trust',
    })
    
    # L3.5 minimal
    l35_minimal = ProtocolSpec("L3.5 Receipt (Minimal v0.2.0)", {
        'version': 'format', 'decision_type': 'format', 'dimensions': 'format', 'timestamp': 'format',
        'agent_id': 'identity', 'task_hash': 'identity',
        'merkle_root': 'trust', 'witnesses': 'trust', 'scar_reference': 'trust',
    })
    
    # L3.5 bloated (with violations)
    l35_bloated = ProtocolSpec("L3.5 Receipt (Kitchen Sink)", {
        'version': 'format', 'decision_type': 'format', 'dimensions': 'format', 'timestamp': 'format',
        'agent_id': 'identity', 'task_hash': 'identity',
        'merkle_root': 'trust', 'witnesses': 'trust', 'scar_reference': 'trust',
        # Violations:
        'origin_platform': 'transport',  # transport in format!
        'platform_tx_id': 'transport',   # transport in format!
        'compliance_grade': 'trust',     # trust policy in format!
        'trust_score': 'trust',          # trust policy in format!
        'leitner_box': 'trust',          # trust policy in format!
        'enforcement_mode': 'trust',     # trust policy in format!
    })
    
    print("=" * 60)
    print("LAYER SEPARATION AUDIT")
    print("'email survived 50 years by separating 4 concerns'")
    print("=" * 60)
    
    for spec in [email, l35_minimal, l35_bloated]:
        result = spec.audit()
        print(f"\n--- {result['name']} ---")
        print(f"Fields: {result['field_count']}")
        print(f"Balance: {json.dumps(result['layer_balance'])}")
        print(f"Violations: {len(result['violations'])}")
        for v in result['violations']:
            print(f"  [{v['severity']}] {v['field']}: {v['explanation']}")
        print(f"Score: {result['separation_score']} ({result['grade']})")
    
    print(f"\n{'=' * 60}")
    print("LESSON: Each layer replaceable independently.")
    print("SMTP can become HTTP. DKIM can become Merkle.")
    print("The format survives because it doesn't care about transport.")
    print("The trust survives because it doesn't care about format.")
    print("Simplicity is not accidental. It is load-bearing.")


if __name__ == '__main__':
    demo()
