"""Integration tests for the v2 pipeline — no LLM calls required."""

import sys
import os
import inspect

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

passed = 0
failed = 0


def run_test(name, fn):
    global passed, failed
    try:
        fn()
        passed += 1
        print(f"  PASS  {name}")
    except Exception as e:
        failed += 1
        print(f"  FAIL  {name}  {e}")


def test_imports():
    """All new modules import cleanly."""
    from rlm_strudel.references import REFERENCES, select_references, format_references_for_prompt
    from rlm_strudel.critic import StrudelCritic, parse_critic_output, CriticResult
    from rlm_strudel.rlm_runner import run_strudel_rlm, ORCHESTRATOR_INSTRUCTIONS
    assert REFERENCES is not None, "REFERENCES is None"
    assert callable(select_references), "select_references not callable"
    assert callable(format_references_for_prompt), "format_references_for_prompt not callable"
    assert callable(parse_critic_output), "parse_critic_output not callable"
    assert callable(run_strudel_rlm), "run_strudel_rlm not callable"
    assert ORCHESTRATOR_INSTRUCTIONS is not None, "ORCHESTRATOR_INSTRUCTIONS is None"


def test_orchestrator_has_new_features():
    """ORCHESTRATOR_INSTRUCTIONS contains expected v2 keywords."""
    from rlm_strudel.rlm_runner import ORCHESTRATOR_INSTRUCTIONS
    for keyword in ["arrange()", "oh", "bass1", "detune", "STRUCTURE"]:
        assert keyword in ORCHESTRATOR_INSTRUCTIONS, f"Missing '{keyword}' in ORCHESTRATOR_INSTRUCTIONS"


def test_context_has_new_features():
    """STRUDEL_CONTEXT contains expected v2 content."""
    from rlm_strudel.prompts import STRUDEL_CONTEXT
    for keyword in ["arrange(", "oh", "detune", "Section Design Guidelines"]:
        assert keyword in STRUDEL_CONTEXT, f"Missing '{keyword}' in STRUDEL_CONTEXT"


def test_reference_pipeline():
    """References select and format correctly for a genre query."""
    from rlm_strudel.references import select_references, format_references_for_prompt
    refs = select_references("dark ambient atmospheric", n=5)
    assert len(refs) > 0, "No references returned"
    formatted = format_references_for_prompt(refs)
    assert "Reference 1:" in formatted, "Formatted output missing 'Reference 1:'"
    assert "```" in formatted, "Formatted output missing code blocks"
    # At least one result should be relevant to the query
    names = [r["name"] for r in refs]
    has_relevant = any(
        "dark" in n.lower() or "ambient" in n.lower() or "atmospheric" in n.lower()
        for n in names
    )
    assert has_relevant, f"No relevant refs for 'dark ambient atmospheric', got: {names}"


def test_critic_pipeline():
    """Critic parser handles a well-formed approved evaluation."""
    from rlm_strudel.critic import parse_critic_output
    evaluation = """
HARMONY: 8/10 — All layers in C major, bass supports chord roots
RHYTHM: 7/10 — Good groove, snare on 2&4, hats add movement
ARRANGEMENT: 8/10 — Uses arrange() with clear intro/verse/chorus/outro
PRODUCTION: 7/10 — Good gain balance, reverb serves the mood
REVISIONS: None — composition approved.
"""
    result = parse_critic_output(evaluation)
    assert result.harmony == 8, f"Expected harmony=8, got {result.harmony}"
    assert result.rhythm == 7, f"Expected rhythm=7, got {result.rhythm}"
    assert result.arrangement == 8, f"Expected arrangement=8, got {result.arrangement}"
    assert result.production == 7, f"Expected production=7, got {result.production}"
    assert result.approved is True, f"Expected approved=True, got {result.approved}"
    assert len(result.revisions) == 0, f"Expected no revisions, got {result.revisions}"


def test_run_function_signature():
    """run_strudel_rlm accepts max_debate_rounds parameter."""
    from rlm_strudel.rlm_runner import run_strudel_rlm
    sig = inspect.signature(run_strudel_rlm)
    params = list(sig.parameters.keys())
    assert "max_debate_rounds" in params, f"'max_debate_rounds' not in params: {params}"
    # Check it has a default value
    default = sig.parameters["max_debate_rounds"].default
    assert default != inspect.Parameter.empty, "max_debate_rounds has no default"
    assert isinstance(default, int), f"Expected int default, got {type(default)}"


if __name__ == "__main__":
    print("\n=== Integration Tests: v2 Pipeline ===")
    run_test("test_imports", test_imports)
    run_test("test_orchestrator_has_new_features", test_orchestrator_has_new_features)
    run_test("test_context_has_new_features", test_context_has_new_features)
    run_test("test_reference_pipeline", test_reference_pipeline)
    run_test("test_critic_pipeline", test_critic_pipeline)
    run_test("test_run_function_signature", test_run_function_signature)
    print(f"\n{'='*40}")
    print(f"  {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
    else:
        print("  All tests passed!")
