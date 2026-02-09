#!/usr/bin/env python3
"""Score my own posts/comments for quality metrics.

Metrics:
- Word count (longer = more substance, up to a point)
- Citation count (URLs, paper references, "et al.", year patterns)
- Question marks (engagement drivers)
- Unique vocabulary ratio (type-token ratio)
- Specificity score (named entities, numbers, dates)

Usage:
    python3 scripts/engagement-quality.py [--file FILE] [--text TEXT] [--scan-log FILE]
"""

import argparse
import re
import sys
import json
from collections import Counter
from pathlib import Path


def count_citations(text: str) -> int:
    """Count research citations and URLs."""
    patterns = [
        r'https?://\S+',           # URLs
        r'\b\w+\s+et\s+al\.?',     # "Smith et al."
        r'\b(?:19|20)\d{2}\b',     # Year references (1900-2099)
        r'(?:PMC|PMID|DOI|arXiv)\s*:?\s*\S+',  # Paper IDs
        r'\([^)]*\d{4}[^)]*\)',    # Parenthetical citations like (Smith 2024)
    ]
    citations = set()
    for p in patterns:
        for m in re.finditer(p, text):
            citations.add(m.group())
    return len(citations)


def count_questions(text: str) -> int:
    """Count question marks (engagement signals)."""
    return text.count('?')


def unique_vocab_ratio(text: str) -> float:
    """Type-token ratio: unique words / total words."""
    words = re.findall(r'\b[a-zA-Z]{2,}\b', text.lower())
    if not words:
        return 0.0
    return len(set(words)) / len(words)


def specificity_score(text: str) -> int:
    """Count specific details: numbers, proper nouns, technical terms."""
    specifics = 0
    # Numbers (not years)
    specifics += len(re.findall(r'\b\d+(?:\.\d+)?%?\b', text))
    # Capitalized words (potential proper nouns, excluding sentence starts)
    specifics += len(re.findall(r'(?<=[.!?]\s)[A-Z][a-z]+|(?<=\s)[A-Z][a-z]{2,}', text))
    # Technical terms (heuristic: words with underscores, camelCase, hyphens in technical context)
    specifics += len(re.findall(r'\b[a-z]+[-_][a-z]+\b', text))
    return specifics


def score_text(text: str) -> dict:
    """Score a piece of text on quality metrics."""
    words = text.split()
    word_count = len(words)
    citations = count_citations(text)
    questions = count_questions(text)
    vocab_ratio = unique_vocab_ratio(text)
    specifics = specificity_score(text)
    
    # Composite score (0-100)
    # Word count: 0-25 pts (optimal 80-250 words)
    if word_count < 20:
        wc_score = word_count
    elif word_count <= 250:
        wc_score = 25
    else:
        wc_score = max(15, 25 - (word_count - 250) // 50)
    
    # Citations: 0-30 pts (3 pts each, max 10)
    cite_score = min(30, citations * 3)
    
    # Questions: 0-15 pts (5 pts each, max 3)
    q_score = min(15, questions * 5)
    
    # Vocabulary richness: 0-15 pts
    vocab_score = int(vocab_ratio * 20)  # TTR of 0.75 = 15 pts
    
    # Specificity: 0-15 pts
    spec_score = min(15, specifics)
    
    total = min(100, wc_score + cite_score + q_score + vocab_score + spec_score)
    
    return {
        'word_count': word_count,
        'citations': citations,
        'questions': questions,
        'vocab_ratio': round(vocab_ratio, 3),
        'specificity': specifics,
        'scores': {
            'word_count': wc_score,
            'citations': cite_score,
            'questions': q_score,
            'vocabulary': vocab_score,
            'specificity': spec_score,
            'total': total,
        },
        'grade': grade(total),
    }


def grade(score: int) -> str:
    """Letter grade from score."""
    if score >= 80: return 'A'
    if score >= 65: return 'B'
    if score >= 50: return 'C'
    if score >= 35: return 'D'
    return 'F'


def extract_posts_from_log(filepath: str) -> list:
    """Extract post/comment content from daily log file."""
    posts = []
    text = Path(filepath).read_text()
    
    # Find Moltbook/Clawk post content patterns
    # Look for content after comment IDs or post descriptions
    sections = re.split(r'\n(?=\d+\.\s)', text)
    for section in sections:
        # Match numbered items that look like posts/comments
        m = re.match(r'\d+\.\s+(?:\w+\s*—\s*)?(.*?)(?:\n|$)', section)
        if m:
            content = m.group(1).strip()
            if len(content) > 20:  # Skip very short entries
                posts.append(content)
    
    return posts


def scan_daily_log(filepath: str):
    """Scan a daily log and score all identifiable posts."""
    text = Path(filepath).read_text()
    
    # Extract writing action descriptions
    lines = text.split('\n')
    posts = []
    current = None
    
    for line in lines:
        # Match lines that look like post/comment descriptions
        m = re.match(r'\s*\d+\.\s+(?:[\w-]+\s*—\s*)?(.*)', line)
        if m and ('—' in line or 'comment' in line.lower() or 'post' in line.lower() 
                   or 'reply' in line.lower() or 'standalone' in line.lower()):
            desc = m.group(1).strip()
            if len(desc) > 15:
                posts.append(desc)
    
    if not posts:
        print("No posts found in log file.")
        return
    
    print(f"Found {len(posts)} post descriptions in {filepath}\n")
    print(f"{'#':>3} {'Grade':>5} {'Score':>5} {'Words':>5} {'Cites':>5} {'Qs':>3} {'TTR':>5} | Description")
    print('-' * 90)
    
    scores = []
    for i, post in enumerate(posts, 1):
        result = score_text(post)
        scores.append(result['scores']['total'])
        desc = post[:60] + '...' if len(post) > 60 else post
        print(f"{i:3} {result['grade']:>5} {result['scores']['total']:>5} "
              f"{result['word_count']:>5} {result['citations']:>5} "
              f"{result['questions']:>3} {result['vocab_ratio']:>5.3f} | {desc}")
    
    if scores:
        print(f"\n{'Avg':>9} {sum(scores)/len(scores):>5.1f}")
        print(f"{'Best':>9} {max(scores):>5}")
        print(f"{'Worst':>9} {min(scores):>5}")


def main():
    parser = argparse.ArgumentParser(description='Score post/comment quality')
    parser.add_argument('--text', '-t', help='Text to score')
    parser.add_argument('--file', '-f', help='File containing text to score')
    parser.add_argument('--scan-log', '-s', help='Scan daily log for posts')
    parser.add_argument('--json', action='store_true', help='JSON output')
    args = parser.parse_args()
    
    if args.scan_log:
        scan_daily_log(args.scan_log)
    elif args.text:
        result = score_text(args.text)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Grade: {result['grade']} ({result['scores']['total']}/100)")
            print(f"  Words: {result['word_count']} ({result['scores']['word_count']}pts)")
            print(f"  Citations: {result['citations']} ({result['scores']['citations']}pts)")
            print(f"  Questions: {result['questions']} ({result['scores']['questions']}pts)")
            print(f"  Vocab TTR: {result['vocab_ratio']} ({result['scores']['vocabulary']}pts)")
            print(f"  Specificity: {result['specificity']} ({result['scores']['specificity']}pts)")
    elif args.file:
        text = Path(args.file).read_text()
        result = score_text(text)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Grade: {result['grade']} ({result['scores']['total']}/100)")
            for k, v in result['scores'].items():
                if k != 'total':
                    print(f"  {k}: {v}pts")
    else:
        # Demo mode
        demo = ("New Caledonian crows (Corvus moneduloides) create compound tools by combining "
                "non-functional parts — an ability previously seen only in great apes (von Bayern et al. 2018, "
                "Scientific Reports). Their brains contain 1.5 billion pallial neurons despite weighing ~10g "
                "(Olkowicz et al. 2016, PNAS). How do walnut-sized brains outperform primates?")
        result = score_text(demo)
        print("Demo scoring:")
        print(f"Grade: {result['grade']} ({result['scores']['total']}/100)")
        for k, v in result.items():
            if k != 'scores' and k != 'grade':
                print(f"  {k}: {v}")


if __name__ == '__main__':
    main()
