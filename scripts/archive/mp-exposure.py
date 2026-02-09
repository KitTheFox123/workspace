#!/usr/bin/env python3
"""Microplastic exposure estimator based on Leslie 2022 & Lee 2024 data.

Usage:
  python3 scripts/mp-exposure.py --profile
  python3 scripts/mp-exposure.py --facts
  python3 scripts/mp-exposure.py --sources
"""

import argparse
import json
import sys

# Data from Leslie 2022 (Environ Int) and Lee 2024 (Sci Rep)
STUDIES = {
    "Leslie 2022": {
        "journal": "Environment International",
        "n": 22,
        "detection_rate": 0.77,
        "method": "Py-GC/MS",
        "polymers": ["PET (50%)", "PS (33%)", "PE (25%)"],
        "doi": "10.1016/j.envint.2022.107199"
    },
    "Lee 2024": {
        "journal": "Scientific Reports",
        "n": 36,
        "detection_rate": 0.889,
        "mean_mps_per_ml": 4.2,
        "method": "µ-FTIR",
        "polymers": ["PS (58.3%)", "PP (50%)", "PE (38.9%)", "PET (16.7%)"],
        "coagulation_link": True,
        "doi": "10.1038/s41598-024-81931-9"
    },
    "Marfella 2024": {
        "journal": "NEJM",
        "finding": "MPs in arterial plaques → cardiovascular events",
        "doi": "10.1056/NEJMoa2309822"
    }
}

RISK_FACTORS = {
    "plastic_food_containers": {"risk": "HIGH", "evidence": "Lee 2024: ≥50% plastic containers → 6.8 vs 2.4 MPs/mL"},
    "bottled_water": {"risk": "HIGH", "evidence": "Cox 2019: bottled water drinkers consume ~90K more MPs/year"},
    "plastic_teabags": {"risk": "MODERATE", "evidence": "Hernandez 2019: billions of nano/microparticles per cup"},
    "microwave_plastic": {"risk": "HIGH", "evidence": "Hussain 2023: heating releases MPs from containers"},
    "face_masks": {"risk": "LOW-MOD", "evidence": "Inhalation route, short exposure"},
}

BODY_LOCATIONS = [
    "Blood (Leslie 2022, Lee 2024)",
    "Placenta (Ragusa 2021)", 
    "Lungs (Amato-Lourenço 2021)",
    "Liver (Horvatits 2022)",
    "Breast milk (Ragusa 2022)",
    "Arterial plaques (Marfella 2024)",
    "Saphenous vein (Rotchell 2023)",
    "Feces (Yan 2021)",
    "Sputum (Huang 2022)",
]

def show_facts():
    print("=== Microplastics in Humans: Key Facts ===\n")
    print(f"Detection rate in blood: 77-89% of healthy adults")
    print(f"Mean concentration: ~4.2 MPs/mL (Lee 2024)")
    print(f"Dominant polymers: polystyrene, polypropylene, polyethylene")
    print(f"Size range: 20-50 µm most common")
    print(f"Total blood volume ~5L → ~21,000 MP particles circulating")
    print(f"\nFound in {len(BODY_LOCATIONS)} body locations:")
    for loc in BODY_LOCATIONS:
        print(f"  • {loc}")
    print(f"\nHealth associations:")
    print(f"  • Prolonged clotting time (aPTT)")
    print(f"  • Elevated CRP (inflammation)")
    print(f"  • Elevated fibrinogen")
    print(f"  • Cardiovascular events (Marfella 2024, NEJM)")

def show_profile():
    print("=== Exposure Risk Profile ===\n")
    for factor, info in RISK_FACTORS.items():
        print(f"[{info['risk']:>8}] {factor.replace('_', ' ').title()}")
        print(f"           {info['evidence']}\n")

def show_sources():
    print("=== Sources ===\n")
    for name, data in STUDIES.items():
        print(f"{name}")
        print(f"  Journal: {data.get('journal', 'N/A')}")
        print(f"  DOI: {data.get('doi', 'N/A')}")
        if 'n' in data:
            print(f"  N={data['n']}, Detection: {data['detection_rate']*100:.0f}%")
        print()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Microplastic exposure info")
    parser.add_argument("--facts", action="store_true", help="Key facts")
    parser.add_argument("--profile", action="store_true", help="Risk profile")
    parser.add_argument("--sources", action="store_true", help="Source papers")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()
    
    if args.json:
        json.dump({"studies": STUDIES, "risk_factors": RISK_FACTORS, "body_locations": BODY_LOCATIONS}, sys.stdout, indent=2)
    elif args.profile:
        show_profile()
    elif args.sources:
        show_sources()
    else:
        show_facts()
