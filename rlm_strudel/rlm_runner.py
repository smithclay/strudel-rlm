"""DSPy RLM configuration and orchestration for Strudel pattern generation."""

from dataclasses import dataclass
import logging
import re

import dspy
from dspy.predict.rlm import RLM, REPLHistory
from rlm_strudel.browser import StrudelBrowser, BrowserCallback
from rlm_strudel.interpreter import SingleInjectInterpreter
from rlm_strudel.prompts import STRUDEL_CONTEXT, build_lofi_context_sections
from rlm_strudel.critic import StrudelCritic
from rlm_strudel.references import PRIMARY_GENRE, select_references, format_references_for_prompt
from rlm_strudel.library import RunTrace, save_run
from rlm_strudel.sanitizer import extract_section_code, sanitize_strudel, validate_semantic

logger = logging.getLogger(__name__)

LOFI_BRIEF_INSTRUCTIONS = f"""You are translating music requests into a compact {PRIMARY_GENRE} production brief.

Rules:
- Stay inside the {PRIMARY_GENRE} lane even if the user names another genre.
- Keep `tempo_cpm` between 72 and 92.
- `mood_keywords` should be 3-5 short phrases.
- `texture_keywords` should be 2-4 production cues suitable for warm, dusty, mid-forward lo-fi mixes.
- `must_include` should capture specific musical asks worth preserving.
- `avoid` should be empty unless the user clearly forbids something or the request contains ideas that would fight the lo-fi lane.
- `section_prompts` must contain exactly 4 short prompts in this order: intro, verse, chorus, outro.
- Each section prompt must mention the tempo and keep the arrangement feasible for a 4-part lo-fi song.
- `brief` should be one concise paragraph a composer can follow directly.
"""


class LoFiBriefSignature(dspy.Signature):
    """Convert the user's request into a constrained lo-fi hip hop production brief."""

    query: str = dspy.InputField(desc="Original user request")
    tempo_cpm: int = dspy.OutputField(desc="Target tempo in cycles per minute, from 72 to 92")
    mood_keywords: list[str] = dspy.OutputField(desc="3 to 5 short mood keywords")
    texture_keywords: list[str] = dspy.OutputField(desc="2 to 4 lo-fi production texture cues")
    must_include: list[str] = dspy.OutputField(desc="Concrete musical elements to include")
    avoid: list[str] = dspy.OutputField(desc="Concrete elements or directions to avoid")
    section_prompts: list[str] = dspy.OutputField(desc="Exactly 4 prompts ordered as intro, verse, chorus, outro")
    brief: str = dspy.OutputField(desc="One concise paragraph briefing the composer")


@dataclass(frozen=True)
class LoFiBriefData:
    """Normalized lo-fi brief used as structured input to the composer."""

    tempo_cpm: int
    mood_keywords: list[str]
    texture_keywords: list[str]
    must_include: list[str]
    avoid: list[str]
    section_prompts: list[str]
    brief: str


def _normalize_brief_list(value, limit: int) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    else:
        items = [str(item) for item in value]
    cleaned = [item.strip() for item in items if str(item).strip()]
    return cleaned[:limit]


def normalize_lofi_brief(raw_brief, query: str) -> LoFiBriefData:
    """Clamp and sanitize DSPy output into a stable lo-fi brief."""
    try:
        tempo_cpm = int(getattr(raw_brief, "tempo_cpm", 82))
    except (TypeError, ValueError):
        tempo_cpm = 82
    tempo_cpm = max(72, min(92, tempo_cpm))

    section_prompts = _normalize_brief_list(getattr(raw_brief, "section_prompts", []), limit=4)
    default_prompts = [
        f"Intro: sparse kick, dusty hats, soft pad. {PRIMARY_GENRE} at cpm({tempo_cpm}).",
        f"Verse: add snare, bass, fuller chords, keep the groove laid-back. {PRIMARY_GENRE} at cpm({tempo_cpm}).",
        f"Chorus: full energy, brighter filters, strongest melodic hook. {PRIMARY_GENRE} at cpm({tempo_cpm}).",
        f"Outro: strip back the layers, more room and delay, gentle wind-down. {PRIMARY_GENRE} at cpm({tempo_cpm}).",
    ]
    if len(section_prompts) < 4:
        section_prompts.extend(default_prompts[len(section_prompts):])

    brief = str(getattr(raw_brief, "brief", "") or "").strip()
    if not brief:
        brief = f"Compose a {PRIMARY_GENRE} track at cpm({tempo_cpm}) inspired by: {query}"

    return LoFiBriefData(
        tempo_cpm=tempo_cpm,
        mood_keywords=_normalize_brief_list(getattr(raw_brief, "mood_keywords", []), limit=5),
        texture_keywords=_normalize_brief_list(getattr(raw_brief, "texture_keywords", []), limit=4),
        must_include=_normalize_brief_list(getattr(raw_brief, "must_include", []), limit=5),
        avoid=_normalize_brief_list(getattr(raw_brief, "avoid", []), limit=5),
        section_prompts=section_prompts[:4],
        brief=brief,
    )


def build_lofi_brief(query: str) -> LoFiBriefData:
    """Create a structured lo-fi brief from the user's request."""
    predictor = dspy.Predict(LoFiBriefSignature, instructions=LOFI_BRIEF_INSTRUCTIONS)
    with dspy.context(lm=dspy.settings.lm.copy(temperature=0.2)):
        raw_brief = predictor(query=query)
    return normalize_lofi_brief(raw_brief, query)


COMPOSER_SIGNATURE = (
    dspy.Signature(
        "sounds, forbidden, effects, genres, api, examples, context, query, brief, tempo_cpm, "
        "mood_keywords, texture_keywords, must_include, avoid, section_prompts -> strudel_code, explanation"
    )
    .with_instructions(
        f"Compose only in {PRIMARY_GENRE}. Use the structured brief and section prompts instead of re-inferring genre from scratch."
    )
    .with_updated_fields("tempo_cpm", type_=int, desc="Target tempo in cycles per minute")
    .with_updated_fields("mood_keywords", type_=list[str], desc="Structured lo-fi mood keywords")
    .with_updated_fields("texture_keywords", type_=list[str], desc="Structured lo-fi production texture cues")
    .with_updated_fields("must_include", type_=list[str], desc="Concrete musical elements to include")
    .with_updated_fields("avoid", type_=list[str], desc="Concrete elements or directions to avoid")
    .with_updated_fields("section_prompts", type_=list[str], desc="Ordered prompts for intro, verse, chorus, outro")
)

FINALIZE_INSTRUCTIONS = f"""You are finishing a {PRIMARY_GENRE} composition from an incomplete draft.

Return a final Strudel composition that:
- defines `const intro`, `const verse`, `const chorus`, and `const outro`
- uses `arrange([4, intro], [8, verse], [8, chorus], [8, verse], [8, chorus], [4, outro]).cpm(tempo_cpm).play()`
- keeps 4-5 essential layers per section
- reuses the strongest ideas from `draft_code` and `repl_history`
- respects `brief`, `must_include`, `avoid`, and `section_prompts`
- uses only valid Strudel sounds/functions

Return raw Strudel code only in `strudel_code`, no markdown fences.
"""


class FinalizeCompositionSignature(dspy.Signature):
    """Repair an incomplete draft into a full arranged lo-fi composition."""

    query: str = dspy.InputField(desc="Original user request")
    brief: str = dspy.InputField(desc="Structured lo-fi composition brief")
    tempo_cpm: int = dspy.InputField(desc="Target tempo in cycles per minute")
    mood_keywords: list[str] = dspy.InputField(desc="Structured mood keywords")
    texture_keywords: list[str] = dspy.InputField(desc="Structured texture keywords")
    must_include: list[str] = dspy.InputField(desc="Concrete musical elements to keep")
    avoid: list[str] = dspy.InputField(desc="Elements or directions to avoid")
    section_prompts: list[str] = dspy.InputField(desc="Ordered prompts for intro, verse, chorus, outro")
    draft_code: str = dspy.InputField(desc="Current draft code, possibly incomplete")
    repl_history: str = dspy.InputField(desc="Formatted REPL trajectory showing generated sections")
    shape_issues: list[str] = dspy.InputField(desc="Deterministic composition-structure issues to fix")
    validation_feedback: str = dspy.InputField(desc="Browser validation result for the draft")
    genres: str = dspy.InputField(desc="Genre reference snippets")
    effects: str = dspy.InputField(desc="Effects reference snippets")
    examples: str = dspy.InputField(desc="Example compositions")
    api: str = dspy.InputField(desc="API reference")
    forbidden: str = dspy.InputField(desc="Forbidden functions and sounds")
    strudel_code: str = dspy.OutputField(desc="Final arranged Strudel composition")
    explanation: str = dspy.OutputField(desc="1-2 sentence explanation of the final composition")


class CompositionFinalizer(dspy.Module):
    """Use a typed DSPy repair step when the RLM returns an incomplete draft."""

    def __init__(self) -> None:
        self.repair = dspy.Predict(FinalizeCompositionSignature, instructions=FINALIZE_INSTRUCTIONS)

    def forward(
        self,
        *,
        query: str,
        brief: str,
        tempo_cpm: int,
        mood_keywords: list[str],
        texture_keywords: list[str],
        must_include: list[str],
        avoid: list[str],
        section_prompts: list[str],
        draft_code: str,
        repl_history: str,
        shape_issues: list[str],
        validation_feedback: str,
        genres: str,
        effects: str,
        examples: str,
        api: str,
        forbidden: str,
    ):
        cleaned = sanitize_strudel(draft_code or "")
        if not composition_shape_issues(cleaned) and validation_feedback == "Valid!":
            return dspy.Prediction(strudel_code=cleaned, explanation=brief)

        with dspy.context(lm=dspy.settings.lm.copy(temperature=0.2)):
            repaired = self.repair(
                query=query,
                brief=brief,
                tempo_cpm=tempo_cpm,
                mood_keywords=mood_keywords,
                texture_keywords=texture_keywords,
                must_include=must_include,
                avoid=avoid,
                section_prompts=section_prompts,
                draft_code=cleaned,
                repl_history=repl_history,
                shape_issues=shape_issues,
                validation_feedback=validation_feedback,
                genres=genres,
                effects=effects,
                examples=examples,
                api=api,
                forbidden=forbidden,
            )

        return dspy.Prediction(
            strudel_code=sanitize_strudel(repaired.strudel_code),
            explanation=str(getattr(repaired, "explanation", "") or "").strip() or brief,
        )

ORCHESTRATOR_INSTRUCTIONS = """You are a music composition orchestrator. You write Python code to compose Strudel music patterns.

All reference material is pre-loaded. Start composing immediately — do NOT use print() to explore context.

Variables (pre-organized — use directly, no slicing needed):
- `sounds`: Available drum samples, synths, and bass sounds
- `forbidden`: Complete list of functions/patterns that DO NOT EXIST — read this first!
- `effects`: Lo-fi-focused effects recipes
- `genres`: Lo-fi / hip hop pattern library only
- `api`: Core functions, pattern transforms, combining patterns, song structure
- `examples`: Example compositions
- `context`: Full reference (for edge cases only)
- `query`: The user's musical request
- `brief`: Structured lo-fi composition brief
- `tempo_cpm`: Target tempo as an integer
- `mood_keywords`: Short mood descriptors for the track
- `texture_keywords`: Production texture cues to lean into
- `must_include`: Concrete musical elements that should appear
- `avoid`: Things that should stay out of the composition
- `section_prompts`: Ordered prompts for intro, verse, chorus, outro

Functions:
- `compose_section(prompt, previous_code="")` → str: Generate Strudel code via sub-agent. Returns the inner lines for stack(). Pass previous_code when revising.
- `critique_code(code)` → str: Returns code with inline // IDEA: suggestions from a producer ear. Use after composing the chorus. Suggestions are creative nudges, not errors — incorporate the ones that serve the vibe. // IDEA-BIG: comments are whole-mix thoughts for assembly time.
- `validate_code(code)` → str: Validate Strudel code in the browser. Returns "Valid!" or "[Error] ...".
- `print(...)`: Inspect variables and results.
- `SUBMIT(strudel_code=..., explanation=...)`: Submit final composition. MUST use keyword arguments.

You are producing: {output_fields}

## Workflow — compose, assemble, submit

IMPORTANT: Call compose_section() at most TWICE per iteration (once to compose, optionally once to revise after critique_code). Multiple unrelated compose calls cause duplicate/corrupted output.

### Iteration 1: Intro
```python
intro = compose_section(section_prompts[0])
print(intro)
```
### Iteration 2: Verse
```python
verse = compose_section(section_prompts[1])
print(verse)
```
### Iteration 3: Chorus (compose + producer ear)
```python
chorus_prompt = section_prompts[2]
chorus = compose_section(chorus_prompt)
annotated = critique_code(f"stack(\\n{{chorus}}\\n)")
# Producer suggestions — incorporate what serves the vibe, keep the energy
import re
if re.search(r"// IDEA: ", annotated):
    chorus = compose_section(chorus_prompt + " Incorporate these producer suggestions where they improve the feel — keep the same layers and energy.", previous_code=annotated)
print(chorus)
```
### Iteration 4: Outro
```python
outro = compose_section(section_prompts[3])
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
).cpm(tempo_cpm).play()\"\"\"

result = validate_code(full_code)
print(result)
if result == "Valid!":
    SUBMIT(strudel_code=full_code, explanation=brief)
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
arrange([8, intro], [24, chorus], [8, outro]).cpm(tempo_cpm).play()\"\"\"

SUBMIT(strudel_code=full_code, explanation=brief)
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
- Use `brief`, `tempo_cpm`, `must_include`, `avoid`, and `section_prompts` as the source of truth for the track
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


REQUIRED_SECTIONS = ("intro", "verse", "chorus", "outro")


def composition_shape_issues(code: str) -> list[str]:
    """Return structural issues that make a composition incomplete for submission."""
    if not code or not code.strip():
        return ["missing final code"]

    issues: list[str] = []
    if "arrange(" not in code:
        issues.append("missing arrange() song structure")
    if ".play()" not in code:
        issues.append("missing .play() terminator")

    sections = parse_sections_from_code(code)
    if not sections:
        issues.append("missing const stack() section definitions")
    for name in REQUIRED_SECTIONS:
        if name not in sections:
            issues.append(f"missing section: {name}")

    return issues


def format_repl_history(history: REPLHistory | None, max_output_chars: int = 6000) -> str:
    """Format REPL history safely for reuse in the finalizer."""
    if not history:
        return "No REPL history available."
    return history.format(max_output_chars=max_output_chars)


class StrudelRLM(RLM):
    """RLM that uses an orchestrator prompt for Python-based composition."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_history: REPLHistory | None = None

    def _execute_iteration(self, repl, variables, history, iteration, input_args, output_field_names):
        result = super()._execute_iteration(repl, variables, history, iteration, input_args, output_field_names)
        if isinstance(result, REPLHistory) and len(result) > len(history):
            self.last_history = result
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
            Review your trajectory to see what information you gathered and what values you computed, then provide the final outputs.
            Only return a final composition if the trajectory includes a complete arranged song with const intro/verse/chorus/outro and `.play()`, or an explicit `SUBMIT(...)`.
            If the trajectory only contains section drafts or other incomplete work, return empty strings instead of guessing."""

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
    max_tokens: int | None = None,
):
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

    from datetime import datetime, timezone
    trace = RunTrace(
        query=query, model=model,
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    lm = dspy.LM(model, cache=False, max_tokens=max_tokens)

    browser = StrudelBrowser(url=url)
    browser.start()
    print("[strudel] Browser ready")

    callback = BrowserCallback(browser, trace=trace)
    dspy.configure(lm=lm, callbacks=[callback])

    lofi_brief = build_lofi_brief(query)
    print(
        f"[strudel] Structured brief: cpm={lofi_brief.tempo_cpm}, "
        f"mood={', '.join(lofi_brief.mood_keywords) or 'n/a'}"
    )

    # Select relevant lo-fi reference compositions for the query
    refs = select_references(f"{query} arranged song")
    refs_text = format_references_for_prompt(refs)
    context_with_refs = STRUDEL_CONTEXT + "\n\n" + refs_text
    print(f"[strudel] Selected {len(refs)} reference compositions")

    # Pre-extract named sections for direct sandbox injection
    ctx_sections = build_lofi_context_sections(context_with_refs)
    print(f"[strudel] Pre-organized context: {', '.join(ctx_sections.keys())}")

    # Top 2 references for compose_section (limit tokens)
    refs_text_short = format_references_for_prompt(refs[:2])

    # Build compose_section tool — wraps llm_query with FORBIDDEN + sounds prepended
    def compose_section(prompt: str, previous_code: str = "") -> str:
        """Generate a Strudel code section via sub-agent with forbidden list and sounds automatically included."""
        enriched_prompt = (
            f"You are generating Strudel (JavaScript) live-coding music.\n\n"
            f"PRIMARY GENRE: {PRIMARY_GENRE}\n"
            f"STRUCTURED BRIEF: {lofi_brief.brief}\n"
            f"TARGET TEMPO: cpm({lofi_brief.tempo_cpm})\n"
            f"MOOD KEYWORDS: {', '.join(lofi_brief.mood_keywords) or 'none'}\n"
            f"TEXTURE KEYWORDS: {', '.join(lofi_brief.texture_keywords) or 'none'}\n"
            f"MUST INCLUDE: {', '.join(lofi_brief.must_include) or 'none'}\n"
            f"AVOID: {', '.join(lofi_brief.avoid) or 'none'}\n\n"
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
            f"- MINIMAL LAYERS (4-5 per section MAX). Each layer must be essential — kick, bass,\n"
            f"  chords, one melodic element, one percussion. Fewer voices = clearer mix = more impact.\n"
            f"  Don't spread gain thin across 6+ layers.\n"
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

    def critique_code(code: str) -> str:
        """Analyze code for production issues. Returns code with inline // CRITIC: comments."""
        from rlm_strudel.critic import critique_code_inline
        return critique_code_inline(code)

    critic = StrudelCritic()
    finalizer = CompositionFinalizer()
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
            COMPOSER_SIGNATURE,
            tools=[browser.validate_code, compose_section, critique_code],
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
                brief=lofi_brief.brief,
                tempo_cpm=lofi_brief.tempo_cpm,
                mood_keywords=lofi_brief.mood_keywords,
                texture_keywords=lofi_brief.texture_keywords,
                must_include=lofi_brief.must_include,
                avoid=lofi_brief.avoid,
                section_prompts=lofi_brief.section_prompts,
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

        validation = browser.validate_code(code)
        shape_issues = composition_shape_issues(code)

        if shape_issues or validation != "Valid!":
            print(f"[strudel] Finalizer repairing draft: {shape_issues or [validation]}")
            finalized = finalizer(
                query=query,
                brief=lofi_brief.brief,
                tempo_cpm=lofi_brief.tempo_cpm,
                mood_keywords=lofi_brief.mood_keywords,
                texture_keywords=lofi_brief.texture_keywords,
                must_include=lofi_brief.must_include,
                avoid=lofi_brief.avoid,
                section_prompts=lofi_brief.section_prompts,
                draft_code=code,
                repl_history=format_repl_history(getattr(rlm, "last_history", None)),
                shape_issues=shape_issues,
                validation_feedback=validation,
                genres=ctx_sections["genres"],
                effects=ctx_sections["effects"],
                examples=ctx_sections["examples"],
                api=ctx_sections["api"],
                forbidden=ctx_sections["forbidden"],
            )
            code = sanitize_strudel(finalized.strudel_code)
            result.strudel_code = code
            if getattr(finalized, "explanation", "").strip():
                result.explanation = finalized.explanation

            validation = browser.validate_code(code)
            shape_issues = composition_shape_issues(code)
            if shape_issues:
                logger.warning(f"[finalizer] Draft still incomplete after repair: {shape_issues}")
            if validation != "Valid!":
                logger.warning(f"[finalizer] Post-repair validation failed: {validation}")

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
