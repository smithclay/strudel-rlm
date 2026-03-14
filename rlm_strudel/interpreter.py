"""StrudelInterpreter: thin relay to browser's evaluate().

Each iteration sends complete Strudel code via evaluate(). The LLM
builds up complexity by including ALL patterns in each iteration's code.
No macro expansion — code passes through as-is to the transpiler.
"""

import ast
import re
import time
from typing import Any, Callable

from playwright.sync_api import sync_playwright
from dspy.primitives.code_interpreter import CodeInterpreterError, FinalOutput

_CODE_FENCE_RE = re.compile(
    r"^\s*```(?:\s*\w+\s*)?\n(.*?)```\s*$",
    re.DOTALL | re.IGNORECASE,
)

_SUBMIT_RE = re.compile(
    r'SUBMIT\s*\((.*)\)\s*;?\s*$',
    re.DOTALL,
)

_SAFE_PRINT_BUILTINS = {
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "range": range,
    "repr": repr,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
}


def _strip_code_fences(code: str) -> str:
    m = _CODE_FENCE_RE.match(code)
    return m.group(1).strip() if m else code.strip()


class StrudelInterpreter:
    """DSPy CodeInterpreter that relays code to Strudel's evaluate().

    Each iteration:
    1. print(...) → evaluated locally against DSPy variables
    2. SUBMIT(...) → returns FinalOutput to end the RLM loop
    3. Everything else → sent as-is to evaluate() in the browser
    """

    def __init__(self, url="http://127.0.0.1:5173"):
        self.url = url
        self.tools: dict[str, Callable[..., str]] = {}
        self.output_fields: list[dict] | None = None
        self._tools_registered = False
        self._playwright = None
        self._browser = None
        self._page = None
        self._started = False
        self._audio_unlocked = False
        self._iteration_count = 0

    def start(self):
        if self._started:
            return
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=False)
        self._page = self._browser.new_page()
        self._page.on("console", lambda msg: print(f"[browser:{msg.type}] {msg.text}"))
        self._page.on("pageerror", lambda err: print(f"[browser:exception] {err}"))
        self._page.goto(self.url)
        self._page.wait_for_function("window.__strudelReady === true", timeout=30000)
        self._started = True

    def push_iteration(self, number: int, code: str, valid: bool, error: str | None = None):
        """Push an iteration to the browser timeline."""
        self._page.evaluate(
            "(data) => window.__strudelPushIteration(data)",
            {"number": number, "code": code, "valid": valid, "error": error},
        )

    def signal_rlm_complete(self, final_code: str):
        """Tell the browser the RLM is done and pass the final code."""
        self._page.evaluate(
            "(code) => window.__strudelRLMComplete(code)",
            final_code,
        )

    def wait_for_done(self):
        """Block until the user clicks Done or closes the browser."""
        try:
            self._page.wait_for_function("window.__userDone === true", timeout=0)
        except Exception:
            pass  # Browser was closed directly — treat as done

    def _eval_print_expr(self, expr: ast.AST, variables: dict[str, Any]) -> Any:
        compiled = compile(ast.Expression(body=expr), "<strudel-print>", "eval")
        return eval(compiled, {"__builtins__": _SAFE_PRINT_BUILTINS}, variables)

    def _handle_print_line(self, line: str, variables: dict[str, Any]) -> tuple[bool, str | None]:
        try:
            module = ast.parse(line, mode="exec")
        except SyntaxError:
            return False, None

        if len(module.body) != 1:
            return False, None

        stmt = module.body[0]
        if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
            return False, None

        call = stmt.value
        if not isinstance(call.func, ast.Name) or call.func.id != "print":
            return False, None

        try:
            parts = [str(self._eval_print_expr(arg, variables)) for arg in call.args]
            sep = " "
            end = "\n"
            for keyword in call.keywords:
                if keyword.arg == "sep":
                    sep = str(self._eval_print_expr(keyword.value, variables))
                elif keyword.arg == "end":
                    end = str(self._eval_print_expr(keyword.value, variables))
                else:
                    raise CodeInterpreterError(f"Unsupported print() keyword: {keyword.arg}")
        except Exception as e:
            raise CodeInterpreterError(f"Failed to evaluate print(): {e}") from e

        rendered = sep.join(parts)
        if end != "\n":
            rendered += end
        return True, rendered

    def _split_strudel_code(self, code: str, variables: dict[str, Any]) -> tuple[str, list[str]]:
        output_parts: list[str] = []
        strudel_lines: list[str] = []

        for line in code.split("\n"):
            stripped = line.strip()
            if not stripped:
                strudel_lines.append(line)
                continue

            handled, output = self._handle_print_line(stripped, variables)
            if handled:
                if output:
                    output_parts.append(output)
                continue

            strudel_lines.append(line)

        return "\n".join(strudel_lines).strip(), output_parts

    def execute(self, code: str, variables: dict[str, Any] | None = None) -> Any:
        if not self._started:
            self.start()

        code = _strip_code_fences(code)
        variables = variables or {}

        # Handle SUBMIT — parse args and return FinalOutput (no playback)
        submit_match = _SUBMIT_RE.search(code)
        if submit_match:
            pre_submit = code[:submit_match.start()].strip()
            if pre_submit:
                strudel_code, output_parts = self._split_strudel_code(pre_submit, variables)
                result = self._validate_in_browser(strudel_code) if strudel_code else "Valid!"
                self._iteration_count += 1
                valid = not result.startswith("[Error]")
                self.push_iteration(
                    self._iteration_count, strudel_code or pre_submit, valid,
                    result if not valid else None,
                )
                if result.startswith("[Error]"):
                    print(f"[interpreter] SUBMIT blocked — code invalid: {result}")
                    messages = [*output_parts, result]
                    return "\n".join(messages)

            args_str = submit_match.group(1)
            try:
                args = ast.literal_eval(f"({args_str},)")
                if len(args) >= 2 and self.output_fields:
                    field_names = [f["name"] for f in self.output_fields]
                    return FinalOutput(dict(zip(field_names, args)))
                elif len(args) == 1:
                    return FinalOutput(args[0])
                else:
                    return FinalOutput(args[0] if args else None)
            except Exception as e:
                raise CodeInterpreterError(f"Failed to parse SUBMIT args: {e}") from e

        # Validate in browser (transpile only, no audio)
        strudel_code, output_parts = self._split_strudel_code(code, variables)
        if strudel_code:
            result = self._validate_in_browser(strudel_code)
            self._iteration_count += 1
            valid = not result.startswith("[Error]")
            self.push_iteration(
                self._iteration_count, strudel_code, valid,
                result if not valid else None,
            )
            output_parts.append(result)

        output = "\n".join(output_parts) if output_parts else None
        print(f"[interpreter] execute() returning: {output}")
        return output

    def _validate_in_browser(self, code: str) -> str:
        """Send code to browser via __strudelValidate (transpile only, no audio)."""
        try:
            print(f"[interpreter] Validating:\n{code}")
            result = self._page.evaluate(
                "(code) => window.__strudelValidate(code)",
                code,
            )

            if result.get("success"):
                return "Valid!"
            else:
                return f"[Error] {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"[Error] {e}"

    def play_in_browser(self, code: str) -> dict:
        """Play code with audio via __strudelEval. Returns audio analysis. Called post-RLM."""
        if not self._started:
            self.start()

        print(f"[interpreter] Playing:\n{code}")
        result = self._page.evaluate(
            "(code) => window.__strudelEval(code)",
            code,
        )
        time.sleep(0.5)

        analysis = self._page.evaluate("() => window.__getAudioAnalysis()")
        if result.get("success"):
            return analysis
        else:
            return {"error": result.get("error", "Unknown error"), "playing": False}

    def shutdown(self):
        if self._browser:
            self._browser.close()
            self._browser = None
        self._page = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
        self._started = False
        self._audio_unlocked = False
