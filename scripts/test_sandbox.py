"""Diagnostic script to isolate PythonInterpreter sandbox failures.

Run: uv run python scripts/test_sandbox.py
"""

import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, ".env"))

from dspy.primitives.python_interpreter import PythonInterpreter
from rlm_strudel.interpreter import SingleInjectInterpreter
from rlm_strudel.prompts import STRUDEL_CONTEXT


def mock_validate(code: str) -> str:
    """Mock validate_code that doesn't need a browser."""
    if ".play()" in code:
        return "Valid!"
    return "[Error] Missing .play()"


def run_test(name, fn):
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")
    try:
        fn()
        print(f"  PASS")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")


def test_basic_execution():
    """Test 1: Basic code execution."""
    repl = PythonInterpreter()
    try:
        result = repl.execute("x = 2 + 2\nprint(x)")
        print(f"  Output: {result!r}")
        assert "4" in str(result), f"Expected '4' in output, got: {result}"
    finally:
        repl.shutdown()


def test_variable_injection():
    """Test 2: Inject the full 14KB STRUDEL_CONTEXT."""
    repl = PythonInterpreter()
    try:
        result = repl.execute(
            'print(f"context length: {len(context)}")',
            variables={"context": STRUDEL_CONTEXT},
        )
        print(f"  Output: {result!r}")
        assert "context length:" in str(result), f"Variable injection failed: {result}"
    finally:
        repl.shutdown()


def test_tool_call():
    """Test 3: Call a tool from inside the sandbox."""
    repl = PythonInterpreter(tools={"validate_code": mock_validate})
    try:
        result = repl.execute(
            'result = validate_code(\'s("bd sd").play()\')\nprint(result)'
        )
        print(f"  Output: {result!r}")
        assert "Valid" in str(result), f"Tool call failed: {result}"
    finally:
        repl.shutdown()


def test_multiple_iterations():
    """Test 4: Multiple executions on the same interpreter (simulates RLM loop)."""
    repl = PythonInterpreter(tools={"validate_code": mock_validate})
    try:
        # Iteration 1: inject context
        r1 = repl.execute(
            'print(f"context chars: {len(context)}")',
            variables={"context": STRUDEL_CONTEXT, "query": "test query"},
        )
        print(f"  Iter 1 output: {r1!r}")

        # Iteration 2: use persisted state (re-inject variables like RLM does)
        r2 = repl.execute(
            'code = \'s("bd sd").play()\'\nresult = validate_code(code)\nprint(result)',
            variables={"context": STRUDEL_CONTEXT, "query": "test query"},
        )
        print(f"  Iter 2 output: {r2!r}")

        # Iteration 3: another iteration with re-injection
        r3 = repl.execute(
            'print("still alive")',
            variables={"context": STRUDEL_CONTEXT, "query": "test query"},
        )
        print(f"  Iter 3 output: {r3!r}")
    finally:
        repl.shutdown()


def test_single_inject_interpreter():
    """Test 5: SingleInjectInterpreter only injects once."""
    repl = SingleInjectInterpreter(tools={"validate_code": mock_validate})
    try:
        # First call: injects variables
        r1 = repl.execute(
            'print(f"context chars: {len(context)}")',
            variables={"context": STRUDEL_CONTEXT, "query": "test query"},
        )
        print(f"  Iter 1 output: {r1!r}")

        # Second call: should skip injection but state persists
        r2 = repl.execute(
            'code = \'s("bd sd").play()\'\nresult = validate_code(code)\nprint(result)',
            variables={"context": STRUDEL_CONTEXT, "query": "test query"},
        )
        print(f"  Iter 2 output: {r2!r}")

        # Third call: verify state still persists
        r3 = repl.execute(
            'print(f"query={query}, context_len={len(context)}")',
            variables={"context": STRUDEL_CONTEXT, "query": "test query"},
        )
        print(f"  Iter 3 output: {r3!r}")
    finally:
        repl.shutdown()


if __name__ == "__main__":
    tests = [
        ("Basic execution", test_basic_execution),
        ("Variable injection (14KB context)", test_variable_injection),
        ("Tool call from sandbox", test_tool_call),
        ("Multiple iterations (vanilla PythonInterpreter)", test_multiple_iterations),
        ("SingleInjectInterpreter", test_single_inject_interpreter),
    ]

    for name, fn in tests:
        run_test(name, fn)

    print(f"\n{'='*60}")
    print("All tests complete.")
