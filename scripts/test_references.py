"""Tests for the curated reference library."""

import sys
import os

# Ensure the project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rlm_strudel.references import REFERENCES, select_references, format_references_for_prompt


def test_references_not_empty():
    """At least 15 references exist."""
    assert len(REFERENCES) >= 15, f"Expected >= 15 references, got {len(REFERENCES)}"
    print(f"PASS: test_references_not_empty ({len(REFERENCES)} references)")


def test_select_matching_query():
    """'dark ambient industrial' should return dark/ambient refs."""
    results = select_references("dark ambient industrial", n=5)
    assert len(results) > 0, "Expected at least one result"
    names = [r["name"] for r in results]
    # The Dark Synth Atmosphere or Ambient Dreamscape should be in results
    has_dark_or_ambient = any(
        "dark" in name.lower() or "ambient" in name.lower() for name in names
    )
    assert has_dark_or_ambient, f"Expected dark/ambient refs, got: {names}"
    print(f"PASS: test_select_matching_query (returned: {names})")


def test_select_fallback():
    """Nonsense query returns 5 diverse defaults."""
    results = select_references("xyzzy flurble nonsense", n=5)
    assert len(results) == 5, f"Expected 5 fallback results, got {len(results)}"
    names = [r["name"] for r in results]
    # Should be diverse — check that not all are the same genre
    all_tags = set()
    for r in results:
        all_tags.update(r["genre_tags"])
    assert len(all_tags) >= 5, f"Expected diverse fallback, got tags: {all_tags}"
    print(f"PASS: test_select_fallback (returned: {names})")


def test_format_output():
    """Formatted output contains 'Reference 1:' and code blocks."""
    refs = select_references("techno", n=3)
    output = format_references_for_prompt(refs)
    assert "Reference 1:" in output, "Expected 'Reference 1:' in output"
    assert "```" in output, "Expected code blocks in output"
    assert ".play()" in output, "Expected .play() in code blocks"
    print("PASS: test_format_output")


if __name__ == "__main__":
    test_references_not_empty()
    test_select_matching_query()
    test_select_fallback()
    test_format_output()
    print("\nAll tests passed!")
