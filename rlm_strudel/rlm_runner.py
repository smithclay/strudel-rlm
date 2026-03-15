"""DSPy RLM configuration and orchestration for Strudel pattern generation."""

import logging
import dspy
from dspy.predict.rlm import RLM, REPLHistory
from rlm_strudel.browser import StrudelBrowser, BrowserCallback
from rlm_strudel.interpreter import SingleInjectInterpreter
from rlm_strudel.prompts import STRUDEL_CONTEXT
from rlm_strudel.critic import StrudelCritic
from rlm_strudel.references import select_references, format_references_for_prompt
from rlm_strudel.library import RunTrace, save_run

logger = logging.getLogger(__name__)

ORCHESTRATOR_INSTRUCTIONS = """You are a music composition orchestrator. You write Python code to compose Strudel music patterns.

You have access to the following variables and functions:

Variables:
- `context`: Strudel API reference + pattern library ({context_len} chars). DO NOT read it all — use Python string slicing and `.find()` to extract relevant sections.
- `query`: The user's musical request.

Built-in functions:
- `llm_query(prompt)` → str: Delegate a task to a sub-agent. Use this to generate Strudel code snippets. Pass relevant slices of `context` so the sub-agent knows the API and available sounds.
- `validate_code(code)` → str: Validate a Strudel code string in the browser. Returns "Valid!" or "[Error] ...".
- `print(...)`: Inspect variables and results. This is how you see output between iterations.
- `SUBMIT(strudel_code, explanation)`: Submit final composition. First arg = complete Strudel code string, second arg = explanation string.

You are producing: {output_fields}

Workflow:
1. EXPLORE: Use print() to slice and inspect relevant sections of `context` for your task. Look for section headers with `context.find("## Section Name")`. Find genre examples, rhythm templates, effects recipes, available sounds, and REFERENCE COMPOSITIONS.
2. COMPOSE SECTIONS: Build the composition in sections — use llm_query() to generate each section (intro, verse, chorus, bridge, outro) as separate `const` variables using `stack()`. Pass focused context slices and reference examples so the sub-agent has the API reference it needs.
3. VALIDATE: Use validate_code() on each section individually and on the combined result. If validation fails, fix or regenerate.
4. STRUCTURE: Wire sections together using `arrange([cycles, pattern], ...)`. Set appropriate cycle durations per section. Ensure sections contrast in energy, density, and texture.
5. SUBMIT: When the full arranged composition validates, call SUBMIT(strudel_code, explanation).

Variables persist between iterations. Build up your composition incrementally.
Write pure Python — Strudel code only appears as string values.

IMPORTANT RULES:
- Always end Strudel code strings with .play()
- Use stack() to layer multiple patterns within each section
- Use arrange() to sequence sections into a full song (intro, verse, chorus, etc.)
- Use `const` to name each section before arrange()
- Drums: bd, sd, hh, oh, lt, mt, ht, cp, rim, cr, rd, cb, noise
- Bass: jvbass, bass1, bass3
- Synths (as strings in .s()): "sawtooth", "square", "triangle", "sine"
- Technique: .detune(N) for fat pads, note("c3,e3,g3") for chords, .arp("up") for arpeggios
- NEVER use .bank() — it will silently fail
- NEVER use .distort(), .res(), .lpq(), .fadeOut(), .fadeIn(), .adsr(), .perc(), .chord() — they don't exist
- NEVER use pattern(), perlin, patterns.*, sine.range(), saw() — they don't exist
- NEVER use chord shorthand like note("c3'7") — use comma-separated: note("c3,e3,g3,bb3")
- Use .resonance(0-40) for filter resonance, .shape(0-1) for distortion
- Use separate .attack(), .decay(), .sustain(), .release() — NOT .adsr()
- Use mini-notation for Euclidean: s("bd(3,8)") — NOT .euclid()
- Use .cpm(N) for tempo, NOT setbpm
- Sections should CONTRAST: intro=sparse, verse=medium, chorus=full energy, outro=wind down"""


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
                context_len=len(STRUDEL_CONTEXT),
                output_fields=output_fields,
            ) + tool_docs)
            .append("variables_info", dspy.InputField(desc="Metadata about the variables available in the REPL"), type_=str)
            .append("repl_history", dspy.InputField(desc="Previous REPL code executions and their outputs"), type_=REPLHistory)
            .append("iteration", dspy.InputField(desc="Current iteration number (1-indexed) out of max_iterations"), type_=str)
            .append("reasoning", dspy.OutputField(desc="Brief: what to explore, generate, or fix next. If composition is valid and complete, SUBMIT."), type_=str)
            .append("code", dspy.OutputField(desc="Python code. Use print(), llm_query(), validate_code(), SUBMIT(). Use ```python code block."), type_=str)
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

    critic = StrudelCritic()
    best_result = None
    best_score = 0.0

    for debate_round in range(1, max_debate_rounds + 1):
        print(f"\n[strudel] === Debate Round {debate_round}/{max_debate_rounds} ===")

        # Build the composer query — include critic feedback after round 1
        composer_query = query
        if best_result and hasattr(best_result, '_critic_feedback'):
            composer_query = (
                f"{query}\n\n"
                f"## Critic Feedback from Previous Round\n"
                f"The critic scored your previous attempt and wants these revisions:\n"
                f"{best_result._critic_feedback}\n\n"
                f"## Previous Code (to revise, not start from scratch)\n"
                f"```\n{best_result.strudel_code}\n```\n\n"
                f"Fix the issues the critic identified while keeping what scored well."
            )

        rlm = StrudelRLM(
            "context, query -> strudel_code, explanation",
            tools=[browser.validate_code],
            max_iterations=max_iters,
            max_llm_calls=max_llm_calls,
            verbose=True,
            interpreter=SingleInjectInterpreter(),
        )

        try:
            print("[strudel] Starting composer RLM loop...")
            result = rlm(context=context_with_refs, query=composer_query)
        except Exception:
            browser.shutdown()
            raise

        code = result.strudel_code
        if not code:
            print("[strudel] No code generated, skipping critic")
            continue

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
