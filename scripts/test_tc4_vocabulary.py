"""
Tests for tc4 vocabulary.py — per bro_agent test plan (contract 52a3c71c).
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from importlib import import_module
vocab_mod = import_module("tc4-vocabulary")
VocabularyAdapter = vocab_mod.VocabularyAdapter
VocabularyEntry = vocab_mod.VocabularyEntry


def test_ingest_basic():
    """1. Single raw dict → VocabularyEntry, assert term/score/source."""
    adapter = VocabularyAdapter()
    entry = adapter.ingest({"term": "liveness", "score": 0.9, "source": "gendolf"})
    assert entry.term == "liveness"
    assert entry.score == 0.9
    assert entry.source == "gendolf"


def test_ingest_defaults():
    """2. Missing optional fields → defaults applied."""
    adapter = VocabularyAdapter()
    entry = adapter.ingest({"term": "identity"})
    assert entry.score == 0.5
    assert entry.source == "unknown"
    assert entry.evidence_hash is None
    assert entry.tags == []


def test_entries_accumulate():
    """3. Multiple ingest() → entries() returns all."""
    adapter = VocabularyAdapter()
    adapter.ingest({"term": "a", "score": 0.1, "source": "x"})
    adapter.ingest({"term": "b", "score": 0.2, "source": "y"})
    adapter.ingest({"term": "c", "score": 0.3, "source": "z"})
    assert len(adapter.entries()) == 3
    assert [e.term for e in adapter.entries()] == ["a", "b", "c"]


def test_flush():
    """4. flush() returns list + clears buffer."""
    adapter = VocabularyAdapter()
    adapter.ingest({"term": "x", "score": 0.5, "source": "s"})
    adapter.ingest({"term": "y", "score": 0.6, "source": "s"})
    flushed = adapter.flush()
    assert len(flushed) == 2
    assert len(adapter.entries()) == 0  # buffer cleared


def test_as_dict():
    """5. as_dict() returns serializable output."""
    adapter = VocabularyAdapter()
    adapter.ingest({"term": "trust", "score": 0.8, "source": "kit", "evidence_hash": "abc123", "tags": ["infra"]})
    dicts = adapter.as_dict()
    assert len(dicts) == 1
    d = dicts[0]
    assert d["term"] == "trust"
    assert d["score"] == 0.8
    assert d["source"] == "kit"
    assert d["evidence_hash"] == "abc123"
    assert d["tags"] == ["infra"]


def test_score_clamping():
    """6. Score outside 0-1 → raise ValueError."""
    adapter = VocabularyAdapter()
    with pytest.raises(ValueError):
        adapter.ingest({"term": "bad", "score": 1.5, "source": "evil"})
    with pytest.raises(ValueError):
        adapter.ingest({"term": "bad", "score": -0.1, "source": "evil"})


def test_downstream_handoff():
    """7. flush() output feeds survivorship adapter stub."""
    adapter = VocabularyAdapter()
    adapter.ingest({"term": "liveness", "score": 0.95, "source": "gendolf", "tags": ["survivorship"]})
    adapter.ingest({"term": "uptime", "score": 0.88, "source": "monitor", "tags": ["survivorship"]})
    
    flushed = adapter.flush()
    
    # Simulate survivorship adapter consuming vocabulary entries
    survivorship_input = [
        {"term": e.term, "score": e.score, "source": e.source}
        for e in flushed
        if "survivorship" in e.tags
    ]
    assert len(survivorship_input) == 2
    assert survivorship_input[0]["term"] == "liveness"
    assert survivorship_input[1]["score"] == 0.88


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
