#!/usr/bin/env python3
"""Overview effect quotes and research reference tool.
Inspired by astronaut cognitive shifts documented by Yaden et al. (2016)."""

import argparse
import json
import random

QUOTES = [
    {"author": "William Anders", "mission": "Apollo 8", "year": 1968,
     "quote": "We set out to explore the moon and instead discovered the Earth."},
    {"author": "Neil Armstrong", "mission": "Apollo 11", "year": 1969,
     "quote": "I didn't feel like a giant. I felt very, very small."},
    {"author": "Edgar Mitchell", "mission": "Apollo 14", "year": 1971,
     "quote": "You develop an instant global consciousness, a people orientation, an intense dissatisfaction with the state of the world."},
    {"author": "Ron Garan", "mission": "ISS Expedition 28", "year": 2011,
     "quote": "When you look at Earth from that vantage point, you can't imagine that we divide ourselves along the lines that we do."},
    {"author": "Chris Hadfield", "mission": "ISS Expedition 35", "year": 2013,
     "quote": "The atmosphere is paper-thin. It's the thickness of a coat of varnish on a globe."},
    {"author": "Mae Jemison", "mission": "STS-47", "year": 1992,
     "quote": "The first thing that struck me was how thin the atmosphere was."},
]

STUDIES = [
    {"authors": "Yaden et al.", "year": 2016, "journal": "Psychology of Consciousness",
     "finding": "Overview effect maps to self-transcendent experience. 'Small self' phenomenon."},
    {"authors": "White, Frank", "year": 1987, "journal": "Book: The Overview Effect",
     "finding": "Coined the term. Interviewed dozens of astronauts. Cognitive shift from seeing Earth."},
    {"authors": "Frontiers in Psychology", "year": 2021, "journal": "Frontiers in Psychology",
     "finding": "ISS cupola Earthgazing reduces stress, heightens creativity, changes vagal tone."},
    {"authors": "Keltner & Haidt", "year": 2003, "journal": "Cognition and Emotion",
     "finding": "Awe = vastness + need for accommodation. Two key ingredients of overview effect."},
]

def main():
    parser = argparse.ArgumentParser(description="Overview effect research reference")
    parser.add_argument("--quote", action="store_true", help="Random astronaut quote")
    parser.add_argument("--studies", action="store_true", help="Key research papers")
    parser.add_argument("--all", action="store_true", help="All quotes")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.studies:
        if args.json:
            print(json.dumps(STUDIES, indent=2))
        else:
            for s in STUDIES:
                print(f"  {s['authors']} ({s['year']}, {s['journal']})")
                print(f"    → {s['finding']}\n")
    elif args.all:
        for q in QUOTES:
            print(f'  "{q["quote"]}"')
            print(f'    — {q["author"]}, {q["mission"]} ({q["year"]})\n')
    else:
        q = random.choice(QUOTES)
        if args.json:
            print(json.dumps(q, indent=2))
        else:
            print(f'  "{q["quote"]}"')
            print(f'    — {q["author"]}, {q["mission"]} ({q["year"]})')

if __name__ == "__main__":
    main()
