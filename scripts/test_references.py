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
    """Song-structured queries should return lo-fi refs and include arranged examples."""
    results = select_references("study beat with intro verse chorus outro", n=5)
    assert len(results) > 0, "Expected at least one result"
    names = [r["name"] for r in results]
    assert all("lo-fi" in r["genre_tags"] for r in results), f"Expected lo-fi refs, got: {results}"
    has_arranged = any("arranged" in r["genre_tags"] for r in results)
    assert has_arranged, f"Expected an arranged lo-fi ref, got: {names}"
    print(f"PASS: test_select_matching_query (returned: {names})")


def test_select_fallback():
    """Nonsense query still returns the stable lo-fi reference pack."""
    results = select_references("xyzzy flurble nonsense", n=5)
    assert len(results) >= 2, f"Expected lo-fi fallback results, got {len(results)}"
    names = [r["name"] for r in results]
    assert all("lo-fi" in r["genre_tags"] for r in results), f"Expected lo-fi fallback, got: {results}"
    assert all("hip hop" in r["genre_tags"] for r in results), f"Expected hip hop fallback, got: {results}"
    print(f"PASS: test_select_fallback (returned: {names})")


def test_format_output():
    """Formatted output contains 'Reference 1:' and code blocks."""
    refs = select_references("study beat", n=3)
    output = format_references_for_prompt(refs)
    assert "Reference 1:" in output, "Expected 'Reference 1:' in output"
    assert "```" in output, "Expected code blocks in output"
    assert ".play()" in output, "Expected .play() in code blocks"
    assert "Lo-fi" in output or "hip hop" in output, "Expected lo-fi labeling in output"
    print("PASS: test_format_output")


if __name__ == "__main__":
    test_references_not_empty()
    test_select_matching_query()
    test_select_fallback()
    test_format_output()
    print("\nAll tests passed!")
