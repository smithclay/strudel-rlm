"""DSPy RLM configuration and orchestration for Strudel pattern generation."""

import logging
import dspy
from dspy.predict.rlm import RLM, REPLHistory
from rlm_strudel.browser import StrudelBrowser, BrowserCallback
from rlm_strudel.prompts import STRUDEL_CONTEXT

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
1. EXPLORE: Use print() to slice and inspect relevant sections of `context` for your task. Look for section headers with `context.find("## Section Name")`. Find genre examples, rhythm templates, effects recipes, and available sounds.
2. COMPOSE: Use llm_query() to generate each musical part (drums, bass, melody, etc.), passing focused context slices so the sub-agent has the API reference it needs. Store results in variables.
3. VALIDATE: Use validate_code() on each part and the combined result. If validation fails, fix or regenerate.
4. SUBMIT: When the full composition validates, call SUBMIT(strudel_code, explanation).

Variables persist between iterations. Build up your composition incrementally.
Write pure Python — Strudel code only appears as string values.

IMPORTANT RULES:
- Always end Strudel code strings with .play()
- Use stack() in Strudel to layer multiple patterns
- ONLY use these samples: bd, sd, hh, lt, cp, noise, jvbass
- ONLY use these synths (as strings in .s()): "sawtooth", "square", "triangle", "sine"
- NEVER use .bank() — it will silently fail
- Use .cpm(N) for tempo, NOT setbpm"""


class StrudelRLM(RLM):
    """RLM that uses an orchestrator prompt for Python-based composition."""

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
    url: str = "http://127.0.0.1:5173",
):
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

    lm = dspy.LM(model, cache=False)

    browser = StrudelBrowser(url=url)
    browser.start()
    print("[strudel] Browser ready")

    callback = BrowserCallback(browser)
    dspy.configure(lm=lm, callbacks=[callback])

    rlm = StrudelRLM(
        "context, query -> strudel_code, explanation",
        tools=[browser.validate_code],
        max_iterations=max_iters,
        max_llm_calls=max_llm_calls,
        verbose=True,
    )

    try:
        print("[strudel] Starting RLM loop...")
        result = rlm(context=STRUDEL_CONTEXT, query=query)
        return result, browser
    except Exception:
        browser.shutdown()
        raise
