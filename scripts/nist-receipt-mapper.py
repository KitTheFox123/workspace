#!/usr/bin/env python3
"""NIST CAISI RFI → Receipt Chain Mapper

Maps NIST CAISI RFI questions (Jan 2026, closes March 9) to receipt chain
artifacts. Shows which receipt fields answer which regulatory questions.

Also maps Verisk CG 35 08 (Jan 2026) insurance exclusion requirements.

Two regulators, one artifact: receipt chains serve both audit and insurance.

Usage:
  python nist-receipt-mapper.py --demo
  echo '{"receipts": [...]}' | python nist-receipt-mapper.py --json
"""

import json
import sys
from datetime import datetime

# NIST CAISI RFI categories (Federal Register 2026-00206)
NIST_CATEGORIES = {
    "adversarial_data": {
        "question": "How can adversarial data be detected in agent inputs?",
        "receipt_fields": ["evidence_hash", "proof_type", "attester_did"],
        "mapping": "Content hashing + provenance tracking detects tampering. Proof-class diversity scores flag single-source manipulation.",
        "weight": 0.15,
    },
    "insecure_models": {
        "question": "How to ensure model integrity in agentic systems?",
        "receipt_fields": ["generation_sig", "model_version", "attester_did"],
        "mapping": "Generation signatures bind output to specific model+version. Attestation chains verify execution integrity.",
        "weight": 0.15,
    },
    "misaligned_objectives": {
        "question": "How to detect and mitigate objective misalignment?",
        "receipt_fields": ["dispatch_profile", "settlement_trigger", "evidence_hash"],
        "mapping": "Pre-registered dispatch profiles commit objectives before execution. Settlement triggers make alignment verifiable.",
        "weight": 0.15,
    },
    "autonomous_actions": {
        "question": "How to audit autonomous agent actions on real-world systems?",
        "receipt_fields": ["timestamp", "attester_did", "contract_id", "evidence_hash", "delegation_proof"],
        "mapping": "Receipt chains = audit trail. Each action logged with timestamp, actor, evidence hash. Delegation proofs track authority.",
        "weight": 0.20,
    },
    "accountability": {
        "question": "Who is accountable when agents cause harm?",
        "receipt_fields": ["attester_did", "delegation_proof", "operator_id"],
        "mapping": "Delegation proofs establish chain of authority. Respondeat superior: operator liable for agent actions within scope.",
        "weight": 0.20,
    },
    "transparency": {
        "question": "How to make agent decision-making transparent?",
        "receipt_fields": ["evidence_hash", "proof_type", "attestation_chain"],
        "mapping": "Receipt chains provide forensic trail. Proof-class diversity ensures multiple independent verification layers.",
        "weight": 0.15,
    },
}

# Verisk CG 35 08 requirements (Jan 2026)
VERISK_REQUIREMENTS = {
    "gen_ai_definition": {
        "description": "Machine-based learning system that creates content",
        "receipt_mapping": "generation_sig identifies AI-generated content. proof_type distinguishes AI from human.",
        "exclusion_risk": "Without receipts, ALL output potentially excluded from coverage.",
    },
    "content_provenance": {
        "description": "Proof of content origin and generation process",
        "receipt_mapping": "evidence_hash + generation_sig + attester_did = provenance chain.",
        "exclusion_risk": "No provenance = no way to distinguish AI-generated from human-created.",
    },
    "liability_chain": {
        "description": "Clear chain of responsibility for AI-generated content",
        "receipt_mapping": "delegation_proof + operator_id + attestation_chain = liability chain.",
        "exclusion_risk": "No delegation proof = unclear liability = exclusion applies.",
    },
    "audit_capability": {
        "description": "Ability to reconstruct decision process post-incident",
        "receipt_mapping": "Full receipt chain with timestamps, evidence hashes, and attestation links.",
        "exclusion_risk": "No audit trail = no defense against exclusion invocation.",
    },
}

# Receipt schema fields
RECEIPT_FIELDS = {
    "timestamp": "When the action occurred (ISO 8601)",
    "attester_did": "Who attests to this action (DID or key fingerprint)",
    "contract_id": "Which contract/task this relates to",
    "evidence_hash": "Content-addressable hash of the evidence",
    "proof_type": "Class of proof (payment/generation/transport/witness)",
    "sig": "Cryptographic signature over the receipt",
    "delegation_proof": "Chain of authority from operator to agent",
    "dispatch_profile": "Pre-registered execution parameters",
    "settlement_trigger": "Conditions for automatic settlement",
    "generation_sig": "Signature binding output to model+version",
    "model_version": "Model identifier + version hash",
    "operator_id": "Human operator identity binding",
    "attestation_chain": "Linked list of attestation receipts",
}


def score_compliance(receipts: list) -> dict:
    """Score a set of receipts against NIST + Verisk requirements."""
    all_fields = set()
    for r in receipts:
        all_fields.update(r.keys())
    
    # NIST compliance
    nist_scores = {}
    nist_total = 0
    for cat_id, cat in NIST_CATEGORIES.items():
        required = set(cat["receipt_fields"])
        present = required & all_fields
        coverage = len(present) / len(required) if required else 0
        nist_scores[cat_id] = {
            "coverage": round(coverage, 2),
            "present": sorted(present),
            "missing": sorted(required - present),
            "question": cat["question"],
        }
        nist_total += coverage * cat["weight"]
    
    # Verisk compliance
    verisk_scores = {}
    verisk_fields_needed = {"generation_sig", "evidence_hash", "attester_did", "delegation_proof", "operator_id", "attestation_chain"}
    verisk_present = verisk_fields_needed & all_fields
    verisk_coverage = len(verisk_present) / len(verisk_fields_needed)
    
    for req_id, req in VERISK_REQUIREMENTS.items():
        verisk_scores[req_id] = {
            "description": req["description"],
            "receipt_mapping": req["receipt_mapping"],
            "exclusion_risk": req["exclusion_risk"] if verisk_coverage < 0.75 else "LOW — receipt chain provides evidence against exclusion.",
        }
    
    # Overall
    nist_grade = "A" if nist_total > 0.8 else "B" if nist_total > 0.6 else "C" if nist_total > 0.4 else "F"
    verisk_grade = "A" if verisk_coverage > 0.8 else "B" if verisk_coverage > 0.6 else "C" if verisk_coverage > 0.4 else "F"
    
    insurable = verisk_coverage > 0.6
    
    return {
        "nist_compliance": round(nist_total, 3),
        "nist_grade": nist_grade,
        "nist_categories": nist_scores,
        "verisk_coverage": round(verisk_coverage, 3),
        "verisk_grade": verisk_grade,
        "verisk_requirements": verisk_scores,
        "insurable": insurable,
        "receipt_fields_present": sorted(all_fields),
        "recommendation": "Receipt chain meets regulatory requirements." if nist_total > 0.7 and verisk_coverage > 0.6 
            else "Add missing receipt fields to improve compliance." if nist_total > 0.4 
            else "Critical gaps — agent actions may be unauditable and uninsurable.",
    }


def demo():
    print("=" * 60)
    print("NIST CAISI RFI + Verisk CG 35 08 Receipt Mapper")
    print("=" * 60)
    
    # TC3-style receipt chain (good)
    tc3_receipts = [
        {"timestamp": "2026-02-24T10:00:00Z", "attester_did": "did:key:kit_fox", "contract_id": "tc3", 
         "evidence_hash": "sha256:abc123", "proof_type": "generation", "sig": "ed25519:...",
         "generation_sig": "sha256:model_output", "delegation_proof": "ilya→kit_fox",
         "dispatch_profile": "subjective-research", "settlement_trigger": "score>0.7",
         "operator_id": "ilya", "attestation_chain": "kit→bro_agent"},
        {"timestamp": "2026-02-24T12:00:00Z", "attester_did": "did:key:bro_agent",
         "evidence_hash": "sha256:def456", "proof_type": "witness", "sig": "ed25519:...",
         "attestation_chain": "bro_agent→kit_fox"},
    ]
    
    print("\n--- TC3 Receipt Chain (Full) ---")
    result = score_compliance(tc3_receipts)
    print(f"NIST: {result['nist_grade']} ({result['nist_compliance']})")
    print(f"Verisk: {result['verisk_grade']} ({result['verisk_coverage']})")
    print(f"Insurable: {'✅' if result['insurable'] else '❌'}")
    print(f"Recommendation: {result['recommendation']}")
    
    # Minimal receipt (bad)
    minimal = [
        {"timestamp": "2026-02-24T10:00:00Z", "evidence_hash": "sha256:abc"},
    ]
    
    print("\n--- Minimal Receipt (No attestation) ---")
    result = score_compliance(minimal)
    print(f"NIST: {result['nist_grade']} ({result['nist_compliance']})")
    print(f"Verisk: {result['verisk_grade']} ({result['verisk_coverage']})")
    print(f"Insurable: {'✅' if result['insurable'] else '❌'}")
    print(f"Recommendation: {result['recommendation']}")
    for cat_id, cat in result['nist_categories'].items():
        if cat['missing']:
            print(f"  {cat_id}: missing {cat['missing']}")
    
    # No receipts at all
    print("\n--- No Receipts (Silent Agent) ---")
    result = score_compliance([{}])
    print(f"NIST: {result['nist_grade']} ({result['nist_compliance']})")
    print(f"Verisk: {result['verisk_grade']} ({result['verisk_coverage']})")
    print(f"Insurable: {'✅' if result['insurable'] else '❌'}")
    print(f"Recommendation: {result['recommendation']}")
    
    print("\n--- Key Insight ---")
    print("NIST wants: audit trail for autonomous actions (RFI closes March 9)")
    print("Verisk wants: provenance for insurability (CG 35 08, Jan 2026)")
    print("Same artifact: receipt chain with proof-class diversity.")
    print("Silent agents = unauditable + uninsurable. Ship receipts.")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = score_compliance(data.get("receipts", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
