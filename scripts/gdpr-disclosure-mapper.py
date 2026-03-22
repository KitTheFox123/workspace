#!/usr/bin/env python3
"""gdpr-disclosure-mapper.py — Map ATF genesis fields to GDPR Art.13/14 disclosure.

TECH-GAP-30 (sighter): CEF 2026 launched March 19 — 25 DPAs enforcing
Art.12-14 transparency. Agent controllers have zero disclosure template.
ATF genesis declarations already cover ~60% of required fields.

This tool maps ATF fields to GDPR articles and identifies gaps.

References:
- EDPB CEF 2026 (March 19, 2026): Coordinated enforcement on transparency
- GDPR Art.12: Transparent information and modalities
- GDPR Art.13: Information where data collected from data subject
- GDPR Art.14: Information where data not obtained from data subject
- EU AI Act Art.26: Deployer obligations
"""

import json
from dataclasses import dataclass, field
from typing import Optional


# GDPR Art.13(1) required disclosure fields
GDPR_ART13_FIELDS = {
    "controller_identity": {
        "gdpr_ref": "Art.13(1)(a)",
        "description": "Identity and contact details of the controller",
        "atf_mapping": "operator",
        "atf_layer": "genesis",
    },
    "dpo_contact": {
        "gdpr_ref": "Art.13(1)(b)",
        "description": "Contact details of the data protection officer",
        "atf_mapping": None,  # GAP
        "atf_layer": None,
    },
    "processing_purposes": {
        "gdpr_ref": "Art.13(1)(c)",
        "description": "Purposes of the processing",
        "atf_mapping": "capability_scope",
        "atf_layer": "genesis",
    },
    "legal_basis": {
        "gdpr_ref": "Art.13(1)(c)",
        "description": "Legal basis for the processing",
        "atf_mapping": None,  # GAP
        "atf_layer": None,
    },
    "legitimate_interests": {
        "gdpr_ref": "Art.13(1)(d)",
        "description": "Legitimate interests pursued",
        "atf_mapping": None,  # GAP
        "atf_layer": None,
    },
    "recipients": {
        "gdpr_ref": "Art.13(1)(e)",
        "description": "Recipients or categories of recipients",
        "atf_mapping": "counterparty_list",
        "atf_layer": "attestation",
    },
    "third_country_transfers": {
        "gdpr_ref": "Art.13(1)(f)",
        "description": "Third country transfer intentions",
        "atf_mapping": "infrastructure_region",
        "atf_layer": "genesis",
    },
}

# GDPR Art.13(2) additional required fields
GDPR_ART13_2_FIELDS = {
    "retention_period": {
        "gdpr_ref": "Art.13(2)(a)",
        "description": "Period for which data will be stored",
        "atf_mapping": "decay_window",
        "atf_layer": "drift",
    },
    "data_subject_rights": {
        "gdpr_ref": "Art.13(2)(b)",
        "description": "Right to access, rectification, erasure",
        "atf_mapping": "revocation_policy",
        "atf_layer": "revocation",
    },
    "right_to_withdraw": {
        "gdpr_ref": "Art.13(2)(c)",
        "description": "Right to withdraw consent",
        "atf_mapping": "voluntary_revocation",
        "atf_layer": "revocation",
    },
    "right_to_lodge_complaint": {
        "gdpr_ref": "Art.13(2)(d)",
        "description": "Right to lodge complaint with supervisory authority",
        "atf_mapping": None,  # GAP
        "atf_layer": None,
    },
    "obligation_to_provide": {
        "gdpr_ref": "Art.13(2)(e)",
        "description": "Whether provision of data is statutory/contractual",
        "atf_mapping": "scoring_criteria",
        "atf_layer": "genesis",
    },
    "automated_decision_making": {
        "gdpr_ref": "Art.13(2)(f)",
        "description": "Existence of automated decision-making including profiling",
        "atf_mapping": "model_family",
        "atf_layer": "genesis",
    },
}

# EU AI Act Art.26 deployer obligations
AI_ACT_ART26_FIELDS = {
    "deployer_identity": {
        "ref": "Art.26(1)",
        "description": "Deployer ensures AI system used in accordance with instructions",
        "atf_mapping": "operator",
        "atf_layer": "genesis",
    },
    "human_oversight": {
        "ref": "Art.26(2)",
        "description": "Human oversight measures",
        "atf_mapping": "principal_split",
        "atf_layer": "composition",
    },
    "monitoring": {
        "ref": "Art.26(5)",
        "description": "Monitor operation and report to provider",
        "atf_mapping": "behavioral_watchdog",
        "atf_layer": "drift",
    },
    "transparency_to_persons": {
        "ref": "Art.26(7)",
        "description": "Inform natural persons of AI system operation",
        "atf_mapping": "genesis_declaration",
        "atf_layer": "genesis",
    },
}


@dataclass
class DisclosureAudit:
    """Audit ATF genesis against GDPR/AI Act disclosure requirements."""
    atf_fields_present: list = field(default_factory=list)

    def audit_gdpr_art13(self) -> dict:
        all_fields = {**GDPR_ART13_FIELDS, **GDPR_ART13_2_FIELDS}
        covered = []
        gaps = []
        partial = []

        for name, info in all_fields.items():
            if info["atf_mapping"] is None:
                gaps.append({
                    "field": name,
                    "gdpr_ref": info.get("gdpr_ref", ""),
                    "description": info["description"],
                    "status": "NO_ATF_MAPPING",
                })
            elif info["atf_mapping"] in self.atf_fields_present:
                covered.append({
                    "field": name,
                    "gdpr_ref": info.get("gdpr_ref", ""),
                    "atf_field": info["atf_mapping"],
                    "atf_layer": info["atf_layer"],
                    "status": "COVERED",
                })
            else:
                partial.append({
                    "field": name,
                    "gdpr_ref": info.get("gdpr_ref", ""),
                    "atf_field": info["atf_mapping"],
                    "status": "ATF_FIELD_EXISTS_BUT_NOT_DECLARED",
                })

        total = len(all_fields)
        coverage = len(covered) / total if total > 0 else 0

        return {
            "total_fields": total,
            "covered": len(covered),
            "gaps": len(gaps),
            "partial": len(partial),
            "coverage_pct": round(coverage * 100, 1),
            "grade": (
                "A" if coverage >= 0.8 else
                "B" if coverage >= 0.6 else
                "C" if coverage >= 0.4 else
                "D" if coverage >= 0.2 else "F"
            ),
            "details": {
                "covered": covered,
                "gaps": gaps,
                "partial": partial,
            },
        }

    def audit_ai_act_art26(self) -> dict:
        covered = []
        gaps = []

        for name, info in AI_ACT_ART26_FIELDS.items():
            if info["atf_mapping"] in self.atf_fields_present:
                covered.append({
                    "field": name,
                    "ref": info["ref"],
                    "atf_field": info["atf_mapping"],
                    "status": "COVERED",
                })
            else:
                gaps.append({
                    "field": name,
                    "ref": info["ref"],
                    "atf_field": info["atf_mapping"],
                    "status": "NOT_DECLARED",
                })

        total = len(AI_ACT_ART26_FIELDS)
        coverage = len(covered) / total if total > 0 else 0

        return {
            "total_fields": total,
            "covered": len(covered),
            "gaps": len(gaps),
            "coverage_pct": round(coverage * 100, 1),
            "details": {"covered": covered, "gaps": gaps},
        }

    def full_report(self) -> dict:
        gdpr = self.audit_gdpr_art13()
        ai_act = self.audit_ai_act_art26()

        return {
            "gdpr_art13": gdpr,
            "ai_act_art26": ai_act,
            "combined_coverage": round(
                (gdpr["coverage_pct"] + ai_act["coverage_pct"]) / 2, 1
            ),
            "verdict": (
                "DISCLOSURE_COMPLIANT"
                if gdpr["coverage_pct"] >= 80 and ai_act["coverage_pct"] >= 75
                else "PARTIAL_COMPLIANCE"
                if gdpr["coverage_pct"] >= 50
                else "NON_COMPLIANT"
            ),
            "recommendation": (
                "ATF genesis declaration covers majority of GDPR Art.13. "
                f"Gaps: {gdpr['gaps']} fields need manual disclosure templates. "
                "DPO contact, legal basis, legitimate interests, supervisory authority "
                "require operator-level (not agent-level) declarations."
            ),
        }


def demo():
    print("=" * 60)
    print("SCENARIO 1: Full ATF agent (kit_fox)")
    print("=" * 60)

    kit = DisclosureAudit(atf_fields_present=[
        "operator", "capability_scope", "counterparty_list",
        "infrastructure_region", "decay_window", "revocation_policy",
        "voluntary_revocation", "scoring_criteria", "model_family",
        "principal_split", "behavioral_watchdog", "genesis_declaration",
    ])
    report = kit.full_report()
    print(json.dumps(report, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Minimal agent (no ATF)")
    print("=" * 60)

    minimal = DisclosureAudit(atf_fields_present=[])
    report = minimal.full_report()
    print(json.dumps(report, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: ATF-core only agent")
    print("=" * 60)

    core = DisclosureAudit(atf_fields_present=[
        "operator", "capability_scope", "model_family",
        "genesis_declaration",
    ])
    report = core.full_report()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    demo()
