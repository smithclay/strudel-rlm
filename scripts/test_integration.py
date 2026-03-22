"""Integration tests for the v2 pipeline — no LLM calls required."""

import sys
import os
import inspect
from types import SimpleNamespace

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
    from rlm_strudel.prompts import build_lofi_context_sections
    from rlm_strudel.rlm_runner import (
        run_strudel_rlm,
        ORCHESTRATOR_INSTRUCTIONS,
        normalize_lofi_brief,
        composition_shape_issues,
    )
    assert REFERENCES is not None, "REFERENCES is None"
    assert callable(select_references), "select_references not callable"
    assert callable(format_references_for_prompt), "format_references_for_prompt not callable"
    assert callable(parse_critic_output), "parse_critic_output not callable"
    assert callable(build_lofi_context_sections), "build_lofi_context_sections not callable"
    assert callable(normalize_lofi_brief), "normalize_lofi_brief not callable"
    assert callable(composition_shape_issues), "composition_shape_issues not callable"
    assert callable(run_strudel_rlm), "run_strudel_rlm not callable"
    assert ORCHESTRATOR_INSTRUCTIONS is not None, "ORCHESTRATOR_INSTRUCTIONS is None"


def test_orchestrator_has_new_features():
    """ORCHESTRATOR_INSTRUCTIONS contains expected v3 keywords."""
    from rlm_strudel.rlm_runner import ORCHESTRATOR_INSTRUCTIONS
    for keyword in ["compose_section", "validate_code", "SUBMIT", "arrange()", "forbidden", "section_prompts", "tempo_cpm", "brief"]:
        assert keyword in ORCHESTRATOR_INSTRUCTIONS, f"Missing '{keyword}' in ORCHESTRATOR_INSTRUCTIONS"


def test_context_has_new_features():
    """STRUDEL_CONTEXT contains expected v2 content."""
    from rlm_strudel.prompts import STRUDEL_CONTEXT
    for keyword in ["arrange(", "oh", "detune", "Section Design Guidelines"]:
        assert keyword in STRUDEL_CONTEXT, f"Missing '{keyword}' in STRUDEL_CONTEXT"


def test_reference_pipeline():
    """References stay in the lo-fi lane and format correctly."""
    from rlm_strudel.references import select_references, format_references_for_prompt
    refs = select_references("study beat with intro chorus outro", n=3)
    assert len(refs) > 0, "No references returned"
    formatted = format_references_for_prompt(refs)
    assert "Reference 1:" in formatted, "Formatted output missing 'Reference 1:'"
    assert "```" in formatted, "Formatted output missing code blocks"
    assert all("lo-fi" in r["genre_tags"] for r in refs), f"Expected lo-fi refs, got: {[r['genre_tags'] for r in refs]}"
    assert all("hip hop" in r["genre_tags"] for r in refs), f"Expected hip hop refs, got: {[r['genre_tags'] for r in refs]}"
    assert any("arranged" in r["genre_tags"] for r in refs), f"Expected an arranged lo-fi ref, got: {[r['name'] for r in refs]}"


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


def test_extract_context_sections():
    """extract_context_sections returns all expected keys with content."""
    from rlm_strudel.prompts import STRUDEL_CONTEXT, extract_context_sections
    sections = extract_context_sections(STRUDEL_CONTEXT)
    for key in ["sounds", "forbidden", "effects", "genres", "api", "examples"]:
        assert key in sections, f"Missing section key '{key}'"
        assert len(sections[key]) > 50, f"Section '{key}' too short: {len(sections[key])} chars"
    # Verify content correctness
    assert "bd" in sections["sounds"], "sounds section missing 'bd'"
    assert ".bank()" in sections["forbidden"], "forbidden section missing '.bank()'"
    assert "Lo-fi" in sections["effects"], "effects section missing 'Lo-fi'"
    assert "Hip Hop" in sections["genres"], "genres section missing 'Hip Hop'"
    assert "note(" in sections["api"], "api section missing 'note('"


def test_build_lofi_context_sections():
    """build_lofi_context_sections trims genre/effects context to the lo-fi lane."""
    from rlm_strudel.prompts import STRUDEL_CONTEXT, build_lofi_context_sections
    sections = build_lofi_context_sections(STRUDEL_CONTEXT)
    assert "Lo-fi Hip Hop" in sections["genres"], "lo-fi genre subsection missing"
    assert "Hip Hop" in sections["genres"], "hip hop subsection missing"
    assert "Techno" not in sections["genres"], "genres section should be narrowed to lo-fi"
    assert "Lo-fi Sound" in sections["effects"], "lo-fi effects subsection missing"
    assert "Warm Analog" in sections["effects"], "warm analog effects subsection missing"
    assert "Acid Squelch" not in sections["effects"], "effects section should be narrowed to lo-fi"


def test_normalize_lofi_brief():
    """normalize_lofi_brief clamps tempo and pads missing section prompts."""
    from rlm_strudel.rlm_runner import normalize_lofi_brief
    raw = SimpleNamespace(
        tempo_cpm=140,
        mood_keywords=["dusty", "late-night", "warm"],
        texture_keywords=["vinyl crackle", "soft saturation"],
        must_include=["swing hats"],
        avoid="hard trap drums",
        section_prompts=["Intro only"],
        brief="",
    )
    brief = normalize_lofi_brief(raw, "study beat")
    assert brief.tempo_cpm == 92, f"Tempo should clamp to 92, got {brief.tempo_cpm}"
    assert len(brief.section_prompts) == 4, f"Expected 4 section prompts, got {brief.section_prompts}"
    assert "cpm(92)" in brief.section_prompts[1], f"Expected normalized tempo in section prompts, got {brief.section_prompts}"
    assert "lo-fi hip hop" in brief.brief.lower(), f"Expected fallback brief to mention lo-fi hip hop, got: {brief.brief}"


def test_composition_shape_issues_complete():
    """composition_shape_issues accepts a full arranged song."""
    from rlm_strudel.rlm_runner import composition_shape_issues
    code = '''const intro = stack(
  s("bd ~ ~ ~")
)

const verse = stack(
  s("bd ~ [~ bd] ~")
)

const chorus = stack(
  s("bd ~ [~ bd] ~"),
  s("hh*8").gain(0.2)
)

const outro = stack(
  s("bd ~ ~ ~")
)

arrange(
  [4, intro],
  [8, verse],
  [8, chorus],
  [8, verse],
  [8, chorus],
  [4, outro]
).cpm(78).play()'''
    assert composition_shape_issues(code) == [], f"Expected complete composition, got {composition_shape_issues(code)}"


def test_composition_shape_issues_partial():
    """composition_shape_issues flags incomplete drafts."""
    from rlm_strudel.rlm_runner import composition_shape_issues
    code = '''stack(
  s("bd ~ ~ ~"),
  s("hh*4").gain(0.2)
).cpm(78).play()'''
    issues = composition_shape_issues(code)
    assert "missing arrange() song structure" in issues, f"Expected arrange() issue, got {issues}"
    assert any("missing section: chorus" == issue for issue in issues), f"Expected missing chorus, got {issues}"


def test_validate_semantic():
    """validate_semantic catches forbidden patterns."""
    from rlm_strudel.sanitizer import validate_semantic
    # Clean code should have no violations
    clean = 'note("c3 e3 g3").s("sawtooth").lpf(800).play()\n'
    assert validate_semantic(clean) == [], f"Expected no violations for clean code, got {validate_semantic(clean)}"
    # Forbidden patterns should be caught
    dirty = '.bank("ve_bk").distort(0.5).adsr(0.1, 0.2, 0.5, 0.3)'
    violations = validate_semantic(dirty)
    assert len(violations) >= 3, f"Expected >= 3 violations, got {len(violations)}: {violations}"


def test_orchestrator_no_explore_step():
    """Orchestrator instructions should NOT contain EXPLORE step."""
    from rlm_strudel.rlm_runner import ORCHESTRATOR_INSTRUCTIONS
    assert "EXPLORE" not in ORCHESTRATOR_INSTRUCTIONS, "ORCHESTRATOR_INSTRUCTIONS still contains EXPLORE step"
    assert "context.find" not in ORCHESTRATOR_INSTRUCTIONS, "ORCHESTRATOR_INSTRUCTIONS still references context.find()"


def test_extract_section_code_raw_lines():
    """extract_section_code returns raw inner lines as-is."""
    from rlm_strudel.sanitizer import extract_section_code
    raw = '  s("bd ~ ~ ~"),\n  s("hh*4").gain(0.3)'
    result = extract_section_code(raw)
    assert 's("bd ~ ~ ~")' in result, f"Expected raw lines preserved, got: {result}"
    assert "stack(" not in result, f"Should not contain stack(), got: {result}"


def test_extract_section_code_stack_wrapper():
    """extract_section_code unwraps stack(...)."""
    from rlm_strudel.sanitizer import extract_section_code
    raw = 'stack(\n  s("bd ~ ~ ~"),\n  s("hh*4").gain(0.3)\n).cpm(82).play()'
    result = extract_section_code(raw)
    assert 's("bd ~ ~ ~")' in result, f"Expected inner code, got: {result}"
    assert "stack(" not in result, f"Should not contain stack(), got: {result}"
    assert ".play()" not in result, f"Should not contain .play(), got: {result}"
    assert ".cpm(" not in result, f"Should not contain .cpm(), got: {result}"


def test_extract_section_code_const_stack():
    """extract_section_code unwraps const NAME = stack(...)."""
    from rlm_strudel.sanitizer import extract_section_code
    raw = 'const intro = stack(\n  s("bd ~ ~ ~"),\n  s("hh*4").gain(0.3)\n)'
    result = extract_section_code(raw)
    assert 's("bd ~ ~ ~")' in result, f"Expected inner code, got: {result}"
    assert "const" not in result, f"Should not contain const, got: {result}"
    assert "stack(" not in result, f"Should not contain stack(), got: {result}"


def test_extract_section_code_arrange():
    """extract_section_code extracts first stack() body from arrange() output."""
    from rlm_strudel.sanitizer import extract_section_code
    raw = '''const intro = stack(
  s("bd ~ ~ ~"),
  s("hh*4").gain(0.3)
)

const verse = stack(
  s("bd ~ [~ bd] ~"),
  s("~ sd ~ sd").gain(0.6)
)

arrange(
  [4, intro],
  [8, verse]
).cpm(82).play()'''
    result = extract_section_code(raw)
    assert 's("bd ~ ~ ~")' in result, f"Expected first stack body, got: {result}"
    assert "arrange(" not in result, f"Should not contain arrange(), got: {result}"


def test_parse_sections_from_code():
    """parse_sections_from_code extracts named sections from a full composition."""
    from rlm_strudel.rlm_runner import parse_sections_from_code
    code = '''const intro = stack(
  s("bd ~ ~ ~"),
  s("hh*4").gain(0.15)
)

const verse = stack(
  s("bd ~ [~ bd] ~"),
  s("~ sd ~ sd").gain(0.6),
  note("<[c3,e3,g3]>").s("triangle").lpf(800).gain(0.5)
)

const chorus = stack(
  s("bd ~ [~ bd] ~"),
  s("~ sd ~ sd").gain(0.7),
  s("hh*8").gain(0.2)
)

arrange(
  [4, intro],
  [8, verse],
  [8, chorus]
).cpm(82).play()'''
    sections = parse_sections_from_code(code)
    assert "intro" in sections, f"Missing 'intro', got keys: {list(sections.keys())}"
    assert "verse" in sections, f"Missing 'verse', got keys: {list(sections.keys())}"
    assert "chorus" in sections, f"Missing 'chorus', got keys: {list(sections.keys())}"
    assert len(sections) == 3, f"Expected 3 sections, got {len(sections)}"
    assert 's("bd ~ ~ ~")' in sections["intro"], f"Intro content wrong: {sections['intro']}"
    assert "note(" in sections["verse"], f"Verse should contain note(): {sections['verse']}"


def test_identify_flagged_sections():
    """identify_flagged_sections extracts section names from revision text."""
    from rlm_strudel.rlm_runner import identify_flagged_sections
    revisions = [
        "[chorus] open lpf from 400 to 1200",
        "[verse] add syncopated kick",
    ]
    flagged = identify_flagged_sections(revisions)
    assert "chorus" in flagged, f"Expected 'chorus' flagged, got: {flagged}"
    assert "verse" in flagged, f"Expected 'verse' flagged, got: {flagged}"
    assert "intro" not in flagged, f"'intro' should not be flagged, got: {flagged}"

    # Empty revisions should default to verse+chorus
    default = identify_flagged_sections([])
    assert default == {"verse", "chorus"}, f"Expected default {{verse, chorus}}, got: {default}"


def test_critic_slash5_reason_parsing():
    """Critic parser handles /5 scores and strips markdown from reasons."""
    from rlm_strudel.critic import parse_critic_output
    evaluation = """
**Harmony**: 4/5 — **good key consistency**
**Rhythm**: 3/5 — *needs more syncopation*
**Arrangement**: 4/5 — **decent structure**
**Production**: 3/5 — *could use more polish*
REVISIONS:
- [chorus] add more energy to the filter sweep
"""
    result = parse_critic_output(evaluation)
    # /5 scores should be doubled
    assert result.harmony == 8, f"Expected harmony=8 (4*2), got {result.harmony}"
    assert result.rhythm == 6, f"Expected rhythm=6 (3*2), got {result.rhythm}"
    # Reasons should have markdown stripped
    assert "**" not in result.reasons.get("harmony", ""), f"Reason still has markdown: {result.reasons}"
    assert "*" not in result.reasons.get("rhythm", ""), f"Reason still has markdown: {result.reasons}"
    assert len(result.revisions) >= 1, f"Expected revisions, got: {result.revisions}"


def test_critic_with_revisions():
    """Critic parser handles an evaluation with revision suggestions."""
    from rlm_strudel.critic import parse_critic_output
    evaluation = """
HARMONY: 6/10 — layers clash in bridge
RHYTHM: 5/10 — kick pattern too rigid
ARRANGEMENT: 7/10 — good section contrast
PRODUCTION: 6/10 — hats too loud
REVISIONS:
- [bridge] change chord voicing to avoid clash
- [verse] add ghost kick on beat 3
- [chorus] reduce hat gain from 0.4 to 0.2
"""
    result = parse_critic_output(evaluation)
    assert result.harmony == 6
    assert result.rhythm == 5
    assert result.approved is False
    assert len(result.revisions) == 3, f"Expected 3 revisions, got {len(result.revisions)}"


if __name__ == "__main__":
    print("\n=== Integration Tests: v3 Pipeline ===")
    run_test("test_imports", test_imports)
    run_test("test_orchestrator_has_new_features", test_orchestrator_has_new_features)
    run_test("test_context_has_new_features", test_context_has_new_features)
    run_test("test_reference_pipeline", test_reference_pipeline)
    run_test("test_critic_pipeline", test_critic_pipeline)
    run_test("test_run_function_signature", test_run_function_signature)
    run_test("test_extract_context_sections", test_extract_context_sections)
    run_test("test_build_lofi_context_sections", test_build_lofi_context_sections)
    run_test("test_normalize_lofi_brief", test_normalize_lofi_brief)
    run_test("test_composition_shape_issues_complete", test_composition_shape_issues_complete)
    run_test("test_composition_shape_issues_partial", test_composition_shape_issues_partial)
    run_test("test_validate_semantic", test_validate_semantic)
    run_test("test_orchestrator_no_explore_step", test_orchestrator_no_explore_step)
    run_test("test_extract_section_code_raw_lines", test_extract_section_code_raw_lines)
    run_test("test_extract_section_code_stack_wrapper", test_extract_section_code_stack_wrapper)
    run_test("test_extract_section_code_const_stack", test_extract_section_code_const_stack)
    run_test("test_extract_section_code_arrange", test_extract_section_code_arrange)
    run_test("test_parse_sections_from_code", test_parse_sections_from_code)
    run_test("test_identify_flagged_sections", test_identify_flagged_sections)
    run_test("test_critic_slash5_reason_parsing", test_critic_slash5_reason_parsing)
    run_test("test_critic_with_revisions", test_critic_with_revisions)
    print(f"\n{'='*40}")
    print(f"  {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
    else:
        print("  All tests passed!")
