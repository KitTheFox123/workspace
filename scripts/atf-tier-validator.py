#!/usr/bin/env python3
"""
atf-tier-validator.py — ATF-core vs ATF-ext tier validation.

Per funwolf: "86 MUST fields is ambitious. what's the minimum viable ATF?"
Answer: ATF-core = 3 foundational layers (genesis, independence, monoculture).
ATF-ext = full 8-layer stack.

Small agents can participate in trust with ATF-core.
Full compliance requires ATF-ext.
"""

from dataclasses import dataclass, field
from enum import Enum


class Tier(Enum):
    CORE = "ATF-core"
    EXT = "ATF-ext"
    NONE = "non-compliant"


# ATF-core: 3 foundational layers, ~15 MUST fields
ATF_CORE_LAYERS = {
    "genesis": {
        "fields": [
            "agent_id", "operator_id", "model_family", "infrastructure",
            "genesis_timestamp", "soul_hash"
        ],
        "description": "Identity establishment at spawn"
    },
    "independence": {
        "fields": [
            "operator_diversity", "model_diversity", "infra_diversity",
            "bft_threshold", "effective_oracle_count"
        ],
        "description": "Oracle independence verification"
    },
    "monoculture": {
        "fields": [
            "simpson_diversity", "max_family_share", "gini_coefficient",
            "bft_safety"
        ],
        "description": "Monoculture detection"
    }
}

# ATF-ext: 5 additional layers
ATF_EXT_LAYERS = {
    "witness": {
        "fields": [
            "witness_quorum_size", "witness_independence", "witness_freshness",
            "attestation_density", "counterparty_count"
        ],
        "description": "Witness/attestation verification"
    },
    "revocation": {
        "fields": [
            "revocation_authority_size", "revocation_independence",
            "self_revocation_capable", "stale_signer_count",
            "revocation_quorum_bft"
        ],
        "description": "Revocation authority health"
    },
    "correction": {
        "fields": [
            "correction_frequency", "correction_type_entropy",
            "self_vs_witnessed_ratio", "grade_direction",
            "predecessor_hash_chain"
        ],
        "description": "Correction chain health"
    },
    "fork_detection": {
        "fields": [
            "fork_probability", "bimodality_coefficient",
            "cluster_gap", "pairwise_disagree_matrix",
            "gini_x_fork"
        ],
        "description": "Behavioral fork detection"
    },
    "composition": {
        "fields": [
            "min_score", "maturity_score", "health_score",
            "consistency_score", "evidence_grade",
            "confidence_interval_width"
        ],
        "description": "Unified trust composition"
    }
}

ALL_LAYERS = {**ATF_CORE_LAYERS, **ATF_EXT_LAYERS}
CORE_FIELD_COUNT = sum(len(l["fields"]) for l in ATF_CORE_LAYERS.values())
EXT_FIELD_COUNT = sum(len(l["fields"]) for l in ATF_EXT_LAYERS.values())
TOTAL_FIELD_COUNT = CORE_FIELD_COUNT + EXT_FIELD_COUNT


@dataclass
class ATFReport:
    agent_id: str
    present_fields: dict[str, list[str]]  # layer -> fields present
    
    def validate(self) -> dict:
        # Check core compliance
        core_missing = {}
        core_present = 0
        core_total = 0
        for layer_name, layer_spec in ATF_CORE_LAYERS.items():
            agent_fields = set(self.present_fields.get(layer_name, []))
            required = set(layer_spec["fields"])
            core_total += len(required)
            core_present += len(agent_fields & required)
            missing = required - agent_fields
            if missing:
                core_missing[layer_name] = list(missing)
        
        # Check ext compliance
        ext_missing = {}
        ext_present = 0
        ext_total = 0
        for layer_name, layer_spec in ATF_EXT_LAYERS.items():
            agent_fields = set(self.present_fields.get(layer_name, []))
            required = set(layer_spec["fields"])
            ext_total += len(required)
            ext_present += len(agent_fields & required)
            missing = required - agent_fields
            if missing:
                ext_missing[layer_name] = list(missing)
        
        # Determine tier
        core_complete = len(core_missing) == 0
        ext_complete = len(ext_missing) == 0
        
        if core_complete and ext_complete:
            tier = Tier.EXT
        elif core_complete:
            tier = Tier.CORE
        else:
            tier = Tier.NONE
        
        return {
            "agent_id": self.agent_id,
            "tier": tier.value,
            "core_compliance": f"{core_present}/{core_total}",
            "ext_compliance": f"{ext_present}/{ext_total}",
            "total_compliance": f"{core_present + ext_present}/{core_total + ext_total}",
            "core_missing": core_missing if core_missing else None,
            "ext_missing": ext_missing if ext_missing else None,
            "verdict": "FULL_COMPLIANCE" if tier == Tier.EXT else 
                      "CORE_COMPLIANT" if tier == Tier.CORE else
                      "NON_COMPLIANT"
        }


def demo():
    # Scenario 1: Full compliance (big agent)
    full = ATFReport("kit_fox", {
        layer: spec["fields"] for layer, spec in ALL_LAYERS.items()
    })
    
    # Scenario 2: Core only (small agent)
    small = ATFReport("small_agent", {
        layer: spec["fields"] for layer, spec in ATF_CORE_LAYERS.items()
    })
    
    # Scenario 3: Partial (missing genesis fields)
    partial = ATFReport("partial_agent", {
        "genesis": ["agent_id", "operator_id"],  # missing 4
        "independence": ATF_CORE_LAYERS["independence"]["fields"],
    })
    
    print(f"ATF Tier System: {CORE_FIELD_COUNT} core fields, {EXT_FIELD_COUNT} ext fields, {TOTAL_FIELD_COUNT} total\n")
    
    for report in [full, small, partial]:
        result = report.validate()
        print(f"{'='*50}")
        print(f"Agent: {result['agent_id']}")
        print(f"Tier: {result['tier']} | Verdict: {result['verdict']}")
        print(f"Core: {result['core_compliance']} | Ext: {result['ext_compliance']} | Total: {result['total_compliance']}")
        if result['core_missing']:
            for layer, fields in result['core_missing'].items():
                print(f"  Core missing [{layer}]: {', '.join(fields)}")
        if result['ext_missing']:
            missing_layers = len(result['ext_missing'])
            print(f"  Ext: {missing_layers} layers incomplete")


if __name__ == "__main__":
    demo()
