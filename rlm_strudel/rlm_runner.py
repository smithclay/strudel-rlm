"""DSPy RLM configuration and orchestration for Strudel pattern generation."""

import dspy
from dspy.predict.rlm import RLM, REPLHistory
from rlm_strudel.interpreter import StrudelInterpreter
from rlm_strudel.prompts import STRUDEL_CONTEXT

STRUDEL_INSTRUCTIONS = """You are tasked with producing the following outputs given the inputs {inputs}:
{output_fields}

You have access to a Strudel live-coding REPL running in a browser. Each iteration validates your code (transpile check). Audio only plays after you SUBMIT.

DECOMPOSE your work incrementally (3-5 iterations typical):
- Iteration 1: Drums → `s("bd sd [~ bd] sd").play()`
- Iteration 2: Drums+bass → `stack(s("bd sd [~ bd] sd"), note("<c2 f2>").s("sawtooth")).play()`
- Iteration 3: Full composition → `stack(drums, bass, melody).play()` then SUBMIT

Available:
- Variables: {inputs} (your input data — the `context` variable contains the Strudel API reference)
- `SUBMIT({final_output_names})` — call this to finish! First arg = the Strudel code string, second arg = explanation string.

WORKFLOW:
1. BUILD — start with drums or a simple pattern, check output says "Valid!"
2. LAYER — add bass, melody, effects. Each iteration includes ALL patterns via stack()
3. SUBMIT — once your code is valid and complete, call SUBMIT

IMPORTANT — EACH ITERATION REPLACES PREVIOUS CODE:
- Always end with .play() in your expression
- Use stack() to layer multiple patterns simultaneously
- Each iteration must include ALL patterns you want

RULES:
- Do NOT use setbpm — use .cpm(N) to set tempo
- Comments with // are fine
- Always call .play() at the end of your expression
- NEVER use .bank() — sample banks are not loaded and will silently fail
- ONLY use these sample names: bd, sd, hh, lt, cp, noise, jvbass
- ONLY use these synths (as strings): "sawtooth", "square", "triangle", "sine"
- Never use sawtooth/square/triangle/sine as bare JS variables — always quote them as strings in .s()
- SUBMIT as soon as your code is valid and complete. Do NOT keep tweaking endlessly.

SUBMIT FORMAT:
```
SUBMIT('stack(s("bd sd"), note("c2").s("sawtooth")).play()', 'A simple beat with bass')
```
Both args are string literals. First arg is the complete Strudel code. Second is the explanation."""


class StrudelRLM(RLM):
    """RLM subclass that prompts for Strudel JS instead of Python."""

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
            dspy.Signature({}, task_instructions + STRUDEL_INSTRUCTIONS.format(
                inputs=inputs_str, final_output_names=final_output_names,
                output_fields=output_fields,
            ) + tool_docs)
            .append("variables_info", dspy.InputField(desc="Metadata about the variables available in the REPL"), type_=str)
            .append("repl_history", dspy.InputField(desc="Previous REPL code executions and their outputs"), type_=REPLHistory)
            .append("iteration", dspy.InputField(desc="Current iteration number (1-indexed) out of max_iterations"), type_=str)
            .append("reasoning", dspy.OutputField(desc="Brief: what exists, what to add/fix next. If audio is playing well, SUBMIT now."), type_=str)
            .append("code", dspy.OutputField(desc="Strudel JS code. End with .play(). When satisfied, include SUBMIT('code', 'explanation') after the code. Use ```js code block."), type_=str)
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
    url: str = "http://127.0.0.1:5173",
):
    lm = dspy.LM(model, cache=False)
    dspy.configure(lm=lm)

    interpreter = StrudelInterpreter(url=url)

    rlm = StrudelRLM(
        "context, query -> strudel_code, explanation",
        interpreter=interpreter,
        max_iterations=max_iters,
        verbose=True,
    )

    try:
        result = rlm(context=STRUDEL_CONTEXT, query=query)
        return result, interpreter
    except Exception:
        interpreter.shutdown()
        raise
