"""Tests for the critic parser — no LLM calls required."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rlm_strudel.critic import parse_critic_output, CriticResult

SAMPLE_APPROVED = """
HARMONY: 8/10 — All layers in C major, bass supports chord roots
RHYTHM: 7/10 — Good groove, snare on 2&4, hats add movement
ARRANGEMENT: 8/10 — Uses arrange() with clear intro/verse/chorus/outro
PRODUCTION: 7/10 — Good gain balance, reverb serves the mood
REVISIONS: None — composition approved.
"""

SAMPLE_NEEDS_WORK = """
HARMONY: 8/10 — Solid key consistency
RHYTHM: 5/10 — Too rigid, no syncopation for a funk piece
ARRANGEMENT: 4/10 — Just a single loop, no sections
PRODUCTION: 7/10 — Effects are tasteful
REVISIONS:
- Add syncopated kick pattern for funk groove
- Use arrange() to create at least intro, main, and outro sections
- Add ghost snares for rhythmic interest
"""

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


def test_parse_approved():
    print("\n--- test_parse_approved ---")
    r = parse_critic_output(SAMPLE_APPROVED)
    check("harmony", r.harmony == 8, f"got {r.harmony}")
    check("rhythm", r.rhythm == 7, f"got {r.rhythm}")
    check("arrangement", r.arrangement == 8, f"got {r.arrangement}")
    check("production", r.production == 7, f"got {r.production}")
    check("average", r.average == 7.5, f"got {r.average}")
    check("min_score", r.min_score == 7, f"got {r.min_score}")
    check("approved", r.approved is True, f"got {r.approved}")
    check("no_revisions", len(r.revisions) == 0, f"got {r.revisions}")
    check("reasons_harmony", "C major" in r.reasons.get("harmony", ""), f"got {r.reasons}")


def test_parse_needs_work():
    print("\n--- test_parse_needs_work ---")
    r = parse_critic_output(SAMPLE_NEEDS_WORK)
    check("harmony", r.harmony == 8, f"got {r.harmony}")
    check("rhythm", r.rhythm == 5, f"got {r.rhythm}")
    check("arrangement", r.arrangement == 4, f"got {r.arrangement}")
    check("production", r.production == 7, f"got {r.production}")
    check("approved", r.approved is False, f"got {r.approved}")
    check("has_revisions", len(r.revisions) == 3, f"got {len(r.revisions)}: {r.revisions}")
    check("revision_content", "syncopated" in r.revisions[0].lower(), f"got {r.revisions[0]}")


def test_parse_edge_case():
    print("\n--- test_parse_edge_case ---")
    # Lowercase labels, missing reason on one line
    edge = """
harmony: 6/10
rhythm: 7/10 — decent
arrangement: 5/10 — okay
production: 8/10 — great
REVISIONS:
- fix it
"""
    r = parse_critic_output(edge)
    check("harmony", r.harmony == 6, f"got {r.harmony}")
    check("rhythm", r.rhythm == 7, f"got {r.rhythm}")
    check("arrangement", r.arrangement == 5, f"got {r.arrangement}")
    check("production", r.production == 8, f"got {r.production}")
    check("missing_reason_default", r.reasons.get("harmony", "") == "", "should be empty")
    check("has_revision", len(r.revisions) == 1, f"got {r.revisions}")

    # Completely missing dimension defaults to 5
    partial = "HARMONY: 9/10 — great\nREVISIONS: None"
    r2 = parse_critic_output(partial)
    check("default_rhythm", r2.rhythm == 5, f"got {r2.rhythm}")
    check("default_arrangement", r2.arrangement == 5, f"got {r2.arrangement}")


def test_format_feedback():
    print("\n--- test_format_feedback ---")
    r = parse_critic_output(SAMPLE_APPROVED)
    fb = r.format_feedback()
    check("contains_harmony", "HARMONY:" in fb, fb[:80])
    check("contains_avg", "7.5" in fb, fb)
    check("contains_approved", "approved" in fb.lower(), fb)

    r2 = parse_critic_output(SAMPLE_NEEDS_WORK)
    fb2 = r2.format_feedback()
    check("contains_revisions", "syncopated" in fb2.lower(), fb2[:200])
    check("repr_works", "NEEDS WORK" in repr(r2), repr(r2))


if __name__ == "__main__":
    test_parse_approved()
    test_parse_needs_work()
    test_parse_edge_case()
    test_format_feedback()
    print(f"\n{'='*40}")
    print(f"  {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
    else:
        print("  All tests passed!")
