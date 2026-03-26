#!/usr/bin/env python3
"""
witness-validator.py — Validate attestation anchors against public witness criteria.

From Clawk thread with santaclawd: "COMMIT_ANCHOR needs an external witness to be real evidence.
self-hosted git = self-attested claim with extra steps."

Valid public witness properties (derived from CT model, RFC 9162, Sigstore Rekor):
1. APPEND_ONLY: entries can only be added, never deleted
2. TAMPER_EVIDENT: Merkle tree or equivalent — any change to existing entries is detectable
3. INDEPENDENT_MONITOR: third parties can verify consistency without trusting the log operator
4. INCLUSION_PROOF: can prove a specific entry exists in the log at a specific time
5. TEMPORAL_ANCHOR: cryptographic timestamp (SCT or equivalent) from a trusted source

Witness hierarchy (strongest → weakest):
- Tier 1: Multiple independent CT-style logs with SCTs (RFC 9162)
- Tier 2: Single transparency log with independent monitors (Sigstore Rekor, Go sumdb)
- Tier 3: Public forge with immutable history (GitHub, GitLab — conditional)
- Tier 4: Timestamping authority only (RFC 3161)
- Tier 5: Self-hosted with external timestamp (marginal)
- INVALID: Self-hosted without external witness

Sources:
- RFC 9162: Certificate Transparency Version 2.0
- Sigstore Rekor v2 (OpenSSF, Dec 2025)
- rekor-monitor: proactive identity misuse detection
- Go checksum database (go.dev/ref/mod#checksum-database)
"""

from dataclasses import dataclass, field
from enum import IntEnum
from datetime import datetime, timezone
from typing import Optional


class WitnessTier(IntEnum):
    """Witness strength tiers. Lower = stronger."""
    MULTI_CT_LOG = 1        # Multiple independent CT-style logs with SCTs
    SINGLE_TRANSPARENCY = 2  # Single transparency log with monitors
    PUBLIC_FORGE = 3         # GitHub/GitLab with immutable refs
    TSA_ONLY = 4             # RFC 3161 timestamp authority only
    SELF_EXTERNAL_TS = 5     # Self-hosted + external timestamp
    INVALID = 99             # Self-attested, no external witness


class WitnessProperty:
    """Properties a witness system can have."""
    APPEND_ONLY = "append_only"
    TAMPER_EVIDENT = "tamper_evident"
    INDEPENDENT_MONITOR = "independent_monitor"
    INCLUSION_PROOF = "inclusion_proof"
    TEMPORAL_ANCHOR = "temporal_anchor"
    IMMUTABLE_REFS = "immutable_refs"


@dataclass
class WitnessSystem:
    """A system that can serve as a public witness for attestation anchors."""
    name: str
    url: str
    properties: set[str]
    tier: WitnessTier
    operator: str
    independent_monitors: int = 0  # Number of known independent monitors
    max_entry_age_hours: Optional[int] = None  # How long entries are guaranteed to persist
    notes: str = ""


@dataclass
class AttestationAnchor:
    """An anchor point for an attestation — where it's recorded."""
    anchor_type: str        # "git_commit", "ct_sct", "rekor_entry", "tsa_token", etc.
    witness_system: str     # Name of the witness system
    entry_id: str           # ID within the witness system
    timestamp: str          # When anchored
    inclusion_proof: Optional[str] = None  # Merkle inclusion proof if available
    sct: Optional[str] = None  # Signed Certificate Timestamp


# Known witness systems
KNOWN_WITNESSES = {
    "rekor": WitnessSystem(
        name="Sigstore Rekor",
        url="https://rekor.sigstore.dev",
        properties={
            WitnessProperty.APPEND_ONLY,
            WitnessProperty.TAMPER_EVIDENT,
            WitnessProperty.INDEPENDENT_MONITOR,
            WitnessProperty.INCLUSION_PROOF,
            WitnessProperty.TEMPORAL_ANCHOR,
        },
        tier=WitnessTier.SINGLE_TRANSPARENCY,
        operator="Linux Foundation / Sigstore",
        independent_monitors=5,  # rekor-monitor instances
        notes="Rekor v2 GA. OpenSSF-funded monitoring. Merkle tree + independent witnesses.",
    ),
    "ct_google": WitnessSystem(
        name="Google CT Logs",
        url="https://ct.googleapis.com/logs",
        properties={
            WitnessProperty.APPEND_ONLY,
            WitnessProperty.TAMPER_EVIDENT,
            WitnessProperty.INDEPENDENT_MONITOR,
            WitnessProperty.INCLUSION_PROOF,
            WitnessProperty.TEMPORAL_ANCHOR,
        },
        tier=WitnessTier.MULTI_CT_LOG,
        operator="Google",
        independent_monitors=10,
        notes="RFC 9162 compliant. Multiple independent logs. SCTs required.",
    ),
    "go_sumdb": WitnessSystem(
        name="Go Checksum Database",
        url="https://sum.golang.org",
        properties={
            WitnessProperty.APPEND_ONLY,
            WitnessProperty.TAMPER_EVIDENT,
            WitnessProperty.INDEPENDENT_MONITOR,
            WitnessProperty.INCLUSION_PROOF,
            WitnessProperty.TEMPORAL_ANCHOR,
        },
        tier=WitnessTier.SINGLE_TRANSPARENCY,
        operator="Google / Go Team",
        independent_monitors=3,
        notes="Transparency log for Go module checksums. Witness protocol.",
    ),
    "github": WitnessSystem(
        name="GitHub",
        url="https://github.com",
        properties={
            WitnessProperty.IMMUTABLE_REFS,
            WitnessProperty.TEMPORAL_ANCHOR,  # Commit timestamps (weak)
        },
        tier=WitnessTier.PUBLIC_FORGE,
        operator="Microsoft / GitHub",
        independent_monitors=0,  # No independent monitors of GitHub itself
        notes="Public commits are immutable refs but GitHub is the sole operator. "
              "Force-push can rewrite history. Trust the platform, not the protocol.",
    ),
    "gitlab": WitnessSystem(
        name="GitLab",
        url="https://gitlab.com",
        properties={
            WitnessProperty.IMMUTABLE_REFS,
            WitnessProperty.TEMPORAL_ANCHOR,
        },
        tier=WitnessTier.PUBLIC_FORGE,
        operator="GitLab Inc",
        independent_monitors=0,
        notes="Same caveats as GitHub. Protected branches help but operator controls.",
    ),
    "rfc3161_tsa": WitnessSystem(
        name="RFC 3161 TSA",
        url="",
        properties={
            WitnessProperty.TEMPORAL_ANCHOR,
        },
        tier=WitnessTier.TSA_ONLY,
        operator="Various",
        notes="Proves existence at a time. No append-only log, no inclusion proof.",
    ),
    "self_hosted_git": WitnessSystem(
        name="Self-hosted Git",
        url="",
        properties=set(),  # No witness properties
        tier=WitnessTier.INVALID,
        operator="Self",
        notes="Self-attested claim with extra steps. No external witness.",
    ),
}


class WitnessValidator:
    """Validate attestation anchors against public witness criteria."""
    
    # Minimum properties for each acceptance level
    FORENSIC_MINIMUM = {
        WitnessProperty.APPEND_ONLY,
        WitnessProperty.TAMPER_EVIDENT,
        WitnessProperty.TEMPORAL_ANCHOR,
    }
    
    STRONG_MINIMUM = FORENSIC_MINIMUM | {
        WitnessProperty.INDEPENDENT_MONITOR,
        WitnessProperty.INCLUSION_PROOF,
    }
    
    def validate_anchor(self, anchor: AttestationAnchor) -> dict:
        """Validate an attestation anchor against witness criteria."""
        witness = KNOWN_WITNESSES.get(anchor.witness_system)
        
        if witness is None:
            return {
                "status": "UNKNOWN_WITNESS",
                "tier": WitnessTier.INVALID,
                "message": f"Unknown witness system: {anchor.witness_system}",
                "forensic_value": False,
            }
        
        # Check property coverage
        has_forensic = self.FORENSIC_MINIMUM.issubset(witness.properties)
        has_strong = self.STRONG_MINIMUM.issubset(witness.properties)
        missing_forensic = self.FORENSIC_MINIMUM - witness.properties
        missing_strong = self.STRONG_MINIMUM - witness.properties
        
        # Determine acceptance
        if has_strong:
            acceptance = "STRONG"
        elif has_forensic:
            acceptance = "FORENSIC"
        elif WitnessProperty.TEMPORAL_ANCHOR in witness.properties:
            acceptance = "WEAK"
        else:
            acceptance = "REJECTED"
        
        # Inclusion proof bonus
        inclusion_verified = anchor.inclusion_proof is not None
        sct_present = anchor.sct is not None
        
        return {
            "status": acceptance,
            "tier": witness.tier,
            "tier_name": witness.tier.name,
            "witness": witness.name,
            "operator": witness.operator,
            "properties": sorted(witness.properties),
            "missing_for_forensic": sorted(missing_forensic) if missing_forensic else [],
            "missing_for_strong": sorted(missing_strong) if missing_strong else [],
            "independent_monitors": witness.independent_monitors,
            "inclusion_proof_verified": inclusion_verified,
            "sct_present": sct_present,
            "forensic_value": has_forensic,
            "notes": witness.notes,
        }
    
    def compare_anchors(self, anchors: list[AttestationAnchor]) -> dict:
        """Compare multiple anchors and recommend the strongest."""
        results = [(a, self.validate_anchor(a)) for a in anchors]
        results.sort(key=lambda x: x[1]["tier"])
        
        return {
            "best_anchor": results[0][1] if results else None,
            "all_anchors": [
                {
                    "anchor_type": a.anchor_type,
                    "witness": r["witness"],
                    "tier": r["tier"],
                    "status": r["status"],
                }
                for a, r in results
            ],
            "recommendation": self._recommend(results),
        }
    
    def _recommend(self, results: list) -> str:
        tiers = [r[1]["tier"] for r in results]
        if not tiers:
            return "No anchors provided."
        best = min(tiers)
        if best <= WitnessTier.SINGLE_TRANSPARENCY:
            return "Strong witness coverage. Independent monitors verify log integrity."
        elif best == WitnessTier.PUBLIC_FORGE:
            return "Acceptable but platform-dependent. Add a transparency log anchor for forensic strength."
        elif best == WitnessTier.TSA_ONLY:
            return "Temporal proof only. No tamper evidence or inclusion proof. Upgrade to Rekor or CT log."
        else:
            return "No valid public witness. Self-hosted anchors are self-attested claims."


def run_demo():
    """Demonstrate witness validation across anchor types."""
    validator = WitnessValidator()
    
    print("=" * 70)
    print("WITNESS VALIDATOR — ATF ATTESTATION ANCHOR VERIFICATION")
    print("=" * 70)
    
    scenarios = [
        ("Rekor transparency log entry", AttestationAnchor(
            anchor_type="rekor_entry",
            witness_system="rekor",
            entry_id="24601",
            timestamp=datetime.now(timezone.utc).isoformat(),
            inclusion_proof="deadbeef...",
        )),
        ("Google CT log with SCT", AttestationAnchor(
            anchor_type="ct_sct",
            witness_system="ct_google",
            entry_id="ct-log-entry-456",
            timestamp=datetime.now(timezone.utc).isoformat(),
            sct="signed-certificate-timestamp...",
            inclusion_proof="merkle-proof...",
        )),
        ("GitHub public commit", AttestationAnchor(
            anchor_type="git_commit",
            witness_system="github",
            entry_id="abc123def456",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )),
        ("RFC 3161 timestamp only", AttestationAnchor(
            anchor_type="tsa_token",
            witness_system="rfc3161_tsa",
            entry_id="tsa-token-789",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )),
        ("Self-hosted git (INVALID)", AttestationAnchor(
            anchor_type="git_commit",
            witness_system="self_hosted_git",
            entry_id="self-abc123",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )),
    ]
    
    for name, anchor in scenarios:
        result = validator.validate_anchor(anchor)
        status_icon = {"STRONG": "✓", "FORENSIC": "~", "WEAK": "⚠", "REJECTED": "✗"}.get(result["status"], "?")
        print(f"\n{status_icon} {name}")
        print(f"  Witness: {result['witness']} (Tier {result['tier']}: {result['tier_name']})")
        print(f"  Status: {result['status']}")
        print(f"  Properties: {', '.join(result['properties']) or 'NONE'}")
        if result.get("missing_for_strong"):
            print(f"  Missing for STRONG: {', '.join(result['missing_for_strong'])}")
        print(f"  Forensic value: {result['forensic_value']}")
        print(f"  Monitors: {result['independent_monitors']}")
    
    # Compare all anchors
    print(f"\n{'=' * 70}")
    print("ANCHOR COMPARISON")
    comparison = validator.compare_anchors([a for _, a in scenarios])
    for a in comparison["all_anchors"]:
        print(f"  Tier {a['tier']}: {a['witness']} ({a['status']})")
    print(f"\n  Recommendation: {comparison['recommendation']}")
    
    print(f"\n{'=' * 70}")
    print("Key: self-hosted git = self-attested claim with extra steps.")
    print("Minimum forensic value requires: append_only + tamper_evident + temporal_anchor.")
    print("Strong requires: + independent_monitor + inclusion_proof.")
    print("The witness model: entry can't be hidden/deleted/modified. Monitoring IS the security.")


if __name__ == "__main__":
    run_demo()
