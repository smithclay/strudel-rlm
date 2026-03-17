"""DSPy RLM configuration and orchestration for Strudel pattern generation."""

import logging
import re
import dspy
from dspy.predict.rlm import RLM, REPLHistory
from rlm_strudel.browser import StrudelBrowser, BrowserCallback
from rlm_strudel.interpreter import SingleInjectInterpreter
from rlm_strudel.prompts import STRUDEL_CONTEXT, extract_context_sections
from rlm_strudel.critic import StrudelCritic
from rlm_strudel.references import select_references, format_references_for_prompt
from rlm_strudel.library import RunTrace, save_run
from rlm_strudel.sanitizer import extract_section_code, sanitize_strudel, validate_semantic

logger = logging.getLogger(__name__)

ORCHESTRATOR_INSTRUCTIONS = """You are a music composition orchestrator. You write Python code to compose Strudel music patterns.

All reference material is pre-loaded. Start composing immediately — do NOT use print() to explore context.

Variables (pre-organized — use directly, no slicing needed):
- `sounds`: Available drum samples, synths, and bass sounds
- `forbidden`: Complete list of functions/patterns that DO NOT EXIST — read this first!
- `effects`: Effects recipes (lo-fi, spacey, aggressive, etc.)
- `genres`: Genre pattern library (hip hop, techno, ambient, etc.)
- `api`: Core functions, pattern transforms, combining patterns, song structure
- `examples`: Example compositions
- `context`: Full reference (for edge cases only)
- `query`: The user's musical request

Functions:
- `compose_section(prompt, previous_code="")` → str: Generate Strudel code via sub-agent. Returns the inner lines for stack(). Pass previous_code when revising.
- `validate_code(code)` → str: Validate Strudel code in the browser. Returns "Valid!" or "[Error] ...".
- `print(...)`: Inspect variables and results.
- `SUBMIT(strudel_code=..., explanation=...)`: Submit final composition. MUST use keyword arguments.

You are producing: {output_fields}

## Workflow — compose, assemble, submit

IMPORTANT: Call compose_section() EXACTLY ONCE per iteration. Multiple calls in one code block cause duplicate/corrupted output. One section per iteration, no exceptions.

### Iteration 1: Intro
```python
intro = compose_section("Sparse intro: kick + hi-hat + soft pad. Lo-fi hip hop at cpm(82).")
print(intro)
```
### Iteration 2: Verse
```python
verse = compose_section("Verse: add snare, bass, fuller chords. Lo-fi hip hop at cpm(82).")
print(verse)
```
### Iteration 3: Chorus
```python
chorus = compose_section("Chorus: full energy, all layers, brighter filters. Lo-fi hip hop at cpm(82).")
print(chorus)
```
### Iteration 4: Outro
```python
outro = compose_section("Outro: strip back to kick + pad, more reverb. Lo-fi hip hop at cpm(82).")
print(outro)
```
### Iteration 5: Assemble, validate, and submit
```python
full_code = f\"\"\"const intro = stack(
{{intro}}
)

const verse = stack(
{{verse}}
)

const chorus = stack(
{{chorus}}
)

const outro = stack(
{{outro}}
)

arrange(
  [4, intro],
  [8, verse],
  [8, chorus],
  [8, verse],
  [8, chorus],
  [4, outro]
).cpm(82).play()\"\"\"

result = validate_code(full_code)
print(result)
if result == "Valid!":
    SUBMIT(strudel_code=full_code, explanation="Lo-fi hip hop with verse-chorus-verse-chorus structure")
```

## FALLBACK — if compose_section or validate_code are not available

If you get a NameError for compose_section or validate_code, write Strudel code DIRECTLY using the `genres`, `effects`, and `examples` variables as templates. Do NOT waste iterations retrying broken functions.

```python
# FALLBACK: Write Strudel code directly from reference material
full_code = \"\"\"const intro = stack(
  s("bd ~ ~ ~"),
  s("hh*4").gain(0.15),
  note("<[c3,e3,g3] [a2,c3,e3]>").s("triangle").lpf(600).room(0.5).gain(0.3)
)
...
arrange([8, intro], [24, chorus], [8, outro]).cpm(82).play()\"\"\"

SUBMIT(strudel_code=full_code, explanation="Lo-fi hip hop track")
```

## SUBMIT — exact calling convention

SUBMIT uses KEYWORD arguments matching the output field names. Always call it like this:
```python
SUBMIT(strudel_code=my_code_variable, explanation="Description of the composition")
```
NEVER call SUBMIT(code, "explanation") with positional args — this will fail.

## REVISION MODE

If `query` contains '## Revision Mode', you are revising a previous attempt.
- Sections marked KEEP: copy them exactly into your new composition
- Sections marked for regeneration: use compose_section() or write directly
- Apply the critic's specific feedback

IMPORTANT RULES:
- Do NOT use print() to explore context — it's already organized for you
- Do NOT use llm_query() — use compose_section() instead
- If compose_section() fails with NameError, write code directly (see FALLBACK above)
- Always end Strudel code with .play()
- Use stack() to layer patterns, arrange() to sequence sections
- Use `const` to name each section before arrange()
- Use verse-chorus repetition: [4,intro] [8,verse] [8,chorus] [8,verse] [8,chorus] [4,outro]
- Repeating the same verse and chorus gives musical coherence — the listener hears familiar material
- Sections should CONTRAST: intro=sparse, verse=medium, chorus=full energy, outro=wind down
- MIX: bass gain 0.7-0.8, chords 0.4-0.6, hats 0.2-0.35. Chords lpf 700-1200 (warm, not muffled)."""


def parse_sections_from_code(code: str) -> dict[str, str]:
    """Extract const NAME = stack(...) blocks from Strudel code using paren-depth counting.

    Returns {"intro": "inner code...", "verse": "inner code...", ...}.
    """
    sections: dict[str, str] = {}
    for m in re.finditer(r"const\s+(\w+)\s*=\s*stack\s*\(", code):
        name = m.group(1).lower()
        # Find matching close paren using depth counting
        depth = 0
        start = m.end() - 1  # position of '('
        for i in range(start, len(code)):
            if code[i] == "(":
                depth += 1
            elif code[i] == ")":
                depth -= 1
                if depth == 0:
                    inner = code[m.end():i].strip()
                    sections[name] = inner
                    break
    return sections


def identify_flagged_sections(revisions: list[str]) -> set[str]:
    """Scan revision strings for section names. Returns set of flagged sections.

    Defaults to {"verse", "chorus"} if no sections explicitly named.
    """
    section_names = {"intro", "verse", "chorus", "bridge", "outro", "buildup", "drop", "breakdown"}
    flagged: set[str] = set()
    for rev in revisions:
        rev_lower = rev.lower()
        for name in section_names:
            if name in rev_lower:
                flagged.add(name)
    if not flagged:
        flagged = {"verse", "chorus"}
    return flagged


class StrudelRLM(RLM):
    """RLM that uses an orchestrator prompt for Python-based composition."""

    def _execute_iteration(self, repl, variables, history, iteration, input_args, output_field_names):
        result = super()._execute_iteration(repl, variables, history, iteration, input_args, output_field_names)
        if isinstance(result, REPLHistory) and len(result) > len(history):
            latest = result.entries[-1]
            logger.info(f"[sandbox output] {str(latest.output)[:2000]}")
        return result

    def _build_signatures(self):
        inputs_str = ", ".join(f"`{n}`" for n in self.signature.input_fields)
        final_output_names = ", ".join(self.signature.output_fields.keys())

        from dspy.predict.rlm import translate_field_type
        output_fields = "\n".join(
            f"- {translate_field_type(n, f)}"
            for n, f in self.signature.output_fields.items()
        )

        task_instructions = f"{self.signature.instructions}\n\n" if self.signature.instructions else ""
        tool_docs = self._format_tool_docs(self._user_tools)

        action_sig = (
            dspy.Signature({}, task_instructions + ORCHESTRATOR_INSTRUCTIONS.format(
                output_fields=output_fields,
            ) + tool_docs)
            .append("variables_info", dspy.InputField(desc="Metadata about the variables available in the REPL"), type_=str)
            .append("repl_history", dspy.InputField(desc="Previous REPL code executions and their outputs"), type_=REPLHistory)
            .append("iteration", dspy.InputField(desc="Current iteration number (1-indexed) out of max_iterations"), type_=str)
            .append("reasoning", dspy.OutputField(desc="Brief: what to explore, generate, or fix next. If composition is valid and complete, SUBMIT."), type_=str)
            .append("code", dspy.OutputField(desc="Python code. Use compose_section(), validate_code(), SUBMIT(). Use ```python code block."), type_=str)
        )

        extract_instructions = """Based on the REPL trajectory, extract the final outputs now.
            Review your trajectory to see what information you gathered and what values you computed, then provide the final outputs."""

        extended = ""
        if task_instructions:
            extended = "The trajectory was generated with the following objective: \n" + task_instructions + "\n"

        extract_sig = dspy.Signature(
            {**self.signature.output_fields},
            extended + extract_instructions,
        )
        extract_sig = extract_sig.prepend("repl_history", dspy.InputField(desc="Your REPL interactions so far"), type_=REPLHistory)
        extract_sig = extract_sig.prepend("variables_info", dspy.InputField(desc="Metadata about the variables available in the REPL"), type_=str)

        return action_sig, extract_sig


def run_strudel_rlm(
    query: str,
    model: str = "openai/gpt-4o",
    max_iters: int = 10,
    max_llm_calls: int = 20,
    max_debate_rounds: int = 3,
    url: str = "http://127.0.0.1:5173",
):
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

    from datetime import datetime, timezone
    trace = RunTrace(
        query=query, model=model,
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    lm = dspy.LM(model, cache=False)

    browser = StrudelBrowser(url=url)
    browser.start()
    print("[strudel] Browser ready")

    callback = BrowserCallback(browser, trace=trace)
    dspy.configure(lm=lm, callbacks=[callback])

    # Select relevant reference compositions for the query
    refs = select_references(query)
    refs_text = format_references_for_prompt(refs)
    context_with_refs = STRUDEL_CONTEXT + "\n\n" + refs_text
    print(f"[strudel] Selected {len(refs)} reference compositions")

    # Pre-extract named sections for direct sandbox injection
    ctx_sections = extract_context_sections(context_with_refs)
    print(f"[strudel] Pre-organized context: {', '.join(ctx_sections.keys())}")

    # Top 2 references for compose_section (limit tokens)
    refs_text_short = format_references_for_prompt(refs[:2])

    # Build compose_section tool — wraps llm_query with FORBIDDEN + sounds prepended
    def compose_section(prompt: str, previous_code: str = "") -> str:
        """Generate a Strudel code section via sub-agent with forbidden list and sounds automatically included."""
        enriched_prompt = (
            f"You are generating Strudel (JavaScript) live-coding music.\n\n"
            f"CRITICAL — these functions DO NOT EXIST, never use them:\n"
            f"{ctx_sections['forbidden']}\n\n"
            f"AVAILABLE SOUNDS (ONLY these work):\n"
            f"{ctx_sections['sounds']}\n\n"
            f"API REFERENCE:\n"
            f"{ctx_sections['api']}\n\n"
            f"EFFECTS RECIPES:\n"
            f"{ctx_sections['effects']}\n\n"
            f"GENRE PATTERNS (use as templates):\n"
            f"{ctx_sections['genres']}\n\n"
            f"REFERENCE COMPOSITIONS (study these for style):\n"
            f"{refs_text_short}\n\n"
        )
        if previous_code:
            enriched_prompt += (
                f"PREVIOUS CODE (revise this, don't start from scratch):\n"
                f"{previous_code}\n\n"
            )
        enriched_prompt += (
            f"TASK: {prompt}\n\n"
            f"MIX PRIORITIES:\n"
            f"- FEWER, LOUDER layers (5-7 per section). Don't spread gain thin across 9+ layers.\n"
            f"- MID-RANGE PRESENCE: chords/pads at lpf 700-1200 (not 400, not 2000+). The mid-range\n"
            f"  carries the musical content — keep it warm and present, not muffled or harsh.\n"
            f"- BASS WITH HARMONICS: prefer sawtooth lpf(300-400) over sine lpf(150) for bass —\n"
            f"  sawtooth has overtones that translate on all speakers.\n"
            f"- DELAY AS PRODUCTION: .delay() with .delayfeedback(0.5-0.7) creates space and depth.\n"
            f"  This alone is more effective than piling on .room()+.delay()+.pan()+.detune() everywhere.\n"
            f"- GAIN HIERARCHY: bass 0.7-0.8, chords 0.4-0.6, hats 0.2-0.35, melody 0.3-0.4.\n"
            f"  Every element should be clearly audible at its intended level.\n\n"
            f"Return ONLY the Strudel code lines (the contents inside stack()), no markdown, no explanation."
        )
        # Use dspy's built-in llm_query via a simple LM call
        result = dspy.settings.lm(enriched_prompt)[0]
        # Extract clean section code from any LLM output format
        result = extract_section_code(result)
        # Sanitize the output
        result = sanitize_strudel(result)

        # Section-level validation with one retry
        test_code = f"stack(\n{result}\n).play()"
        validation = browser.validate_code(test_code)
        if validation != "Valid!":
            logger.warning(f"[compose_section] Invalid: {validation}")
            retry_prompt = enriched_prompt + f"\n\nERROR in your output: {validation}\nFix and return corrected code."
            result = dspy.settings.lm(retry_prompt)[0]
            result = extract_section_code(result)
            result = sanitize_strudel(result)

        # Semantic check — log warnings but don't block
        violations = validate_semantic(result)
        if violations:
            logger.warning(f"[compose_section] Semantic violations in sub-agent output: {violations}")

        # Warn if section lacks high-frequency content (all layers have lpf < 2000)
        lpf_values = [int(m.group(1)) for m in re.finditer(r'\.lpf\((\d+)\)', result)]
        has_hh = bool(re.search(r's\(".*?hh', result))
        if lpf_values and max(lpf_values) < 2000 and not has_hh:
            logger.warning(f"[compose_section] All layers filtered below 2kHz — mix may sound muffled")

        return result

    critic = StrudelCritic()
    best_result = None
    best_score = 0.0
    critique = None

    for debate_round in range(1, max_debate_rounds + 1):
        print(f"\n[strudel] === Debate Round {debate_round}/{max_debate_rounds} ===")

        # Build the composer query — include critic feedback after round 1
        composer_query = query
        if best_result and hasattr(best_result, '_critic_feedback'):
            # Mechanical revision: parse sections and identify what to keep vs regenerate
            sections = parse_sections_from_code(best_result.strudel_code)
            flagged = identify_flagged_sections(critique.revisions if critique else set())

            composer_query = (
                f"{query}\n\n"
                f"## Revision Mode — Targeted Fixes\n"
                f"SECTIONS TO KEEP (already good — copy these directly):\n"
            )
            for name, code in sections.items():
                if name not in flagged:
                    composer_query += f"\n### {name} (KEEP)\n```\n{code}\n```\n"
            composer_query += f"\nSECTIONS TO REGENERATE:\n"
            for name in flagged:
                composer_query += f"- {name}\n"
            composer_query += f"\nCritic feedback:\n{best_result._critic_feedback}\n"

        rlm = StrudelRLM(
            "sounds, forbidden, effects, genres, api, examples, context, query -> strudel_code, explanation",
            tools=[browser.validate_code, compose_section],
            max_iterations=max_iters,
            max_llm_calls=max_llm_calls,
            verbose=True,
            interpreter=SingleInjectInterpreter(),
        )

        try:
            print("[strudel] Starting composer RLM loop...")
            result = rlm(
                sounds=ctx_sections["sounds"],
                forbidden=ctx_sections["forbidden"],
                effects=ctx_sections["effects"],
                genres=ctx_sections["genres"],
                api=ctx_sections["api"],
                examples=ctx_sections["examples"],
                context=context_with_refs,
                query=composer_query,
            )
        except Exception:
            browser.shutdown()
            raise

        code = result.strudel_code if result else None
        if not code or not isinstance(code, str):
            print("[strudel] No code generated, skipping critic")
            continue

        # Sanitize — strip markdown, forbidden functions, stray .play() calls
        raw_len = len(code)
        code = sanitize_strudel(code)
        if len(code) != raw_len:
            logger.info(f"[sanitizer] Cleaned {raw_len - len(code)} chars of junk")
        result.strudel_code = code

        # Semantic validation — check for remaining forbidden patterns
        violations = validate_semantic(code)
        if violations:
            logger.warning(f"[semantic] Post-sanitize violations: {violations}")

        # Re-validate after sanitization
        validation = browser.validate_code(code)
        if validation != "Valid!":
            logger.warning(f"[sanitizer] Post-sanitize validation failed: {validation}")

        # Critic evaluation
        print("[strudel] Critic evaluating...")
        try:
            critique = critic.evaluate(query, code)
        except Exception as e:
            print(f"[strudel] Critic failed: {e}, submitting as-is")
            return result, browser

        print(f"[strudel] Critic scores: {critique}")
        print(f"[strudel] {critique.format_feedback()}")

        # Push critic scores to browser
        browser.push_critic_scores(debate_round, {
            "harmony": critique.harmony,
            "rhythm": critique.rhythm,
            "arrangement": critique.arrangement,
            "production": critique.production,
            "average": critique.average,
            "approved": critique.approved,
        })

        # Feed the trace
        trace.add_critic_round(debate_round, critique, code)

        # Track best result
        if critique.average > best_score:
            best_score = critique.average
            best_result = result
            best_result._critic_feedback = critique.format_feedback()

        if critique.approved:
            print(f"[strudel] Critic approved! (avg: {critique.average:.1f})")
            trace.finalize(code, result.explanation, "approved")
            saved = save_run(trace)
            print(f"[strudel] Saved to {saved}")
            return result, browser

        print(f"[strudel] Critic wants revisions (avg: {critique.average:.1f}, min: {critique.min_score})")

    # Max rounds reached — return best attempt
    print(f"[strudel] Max debate rounds reached. Returning best attempt (avg: {best_score:.1f})")
    trace.finalize(
        best_result.strudel_code if best_result else "",
        best_result.explanation if best_result else "",
        "max_rounds",
    )
    saved = save_run(trace)
    print(f"[strudel] Saved to {saved}")
    return best_result, browser
