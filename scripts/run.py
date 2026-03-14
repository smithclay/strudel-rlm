"""CLI entry point: starts Vite dev server and runs DSPy RLM for Strudel."""

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, ".env"))

from rlm_strudel.rlm_runner import run_strudel_rlm


def _wait_for_url(url: str, proc: subprocess.Popen, timeout: float = 20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"Vite exited before becoming ready at {url}")

        try:
            with urllib.request.urlopen(url, timeout=1):
                return
        except urllib.error.URLError:
            time.sleep(0.25)

    raise RuntimeError(f"Timed out waiting for Vite at {url}")


def start_vite(url: str):
    """Start the Vite dev server as a subprocess and wait until it is ready."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 5173
    proc = subprocess.Popen(
        ["npm", "run", "dev", "--", "--host", host, "--port", str(port), "--strictPort"],
        cwd=project_root,
    )
    _wait_for_url(url, proc)
    return proc


def stop_process(proc: subprocess.Popen):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description="Generate Strudel patterns with DSPy RLM")
    parser.add_argument("query", help="Natural language description of the desired music pattern")
    parser.add_argument("--model", default="openrouter/google/gemini-3-flash-preview", help="LLM model")
    parser.add_argument("--max-iters", type=int, default=10, help="Max RLM iterations (default: 10)")
    parser.add_argument("--max-llm-calls", type=int, default=20, help="Max sub-LLM calls via llm_query (default: 20)")
    parser.add_argument("--no-vite", action="store_true", help="Skip starting Vite (if already running)")
    parser.add_argument("--url", default="http://127.0.0.1:5173", help="Strudel app URL")
    args = parser.parse_args()

    vite_proc = None
    if not args.no_vite:
        print(f"Starting Vite dev server at {args.url}...")
        vite_proc = start_vite(args.url)

    browser = None
    try:
        print(f"\nGenerating pattern for: {args.query}")
        print(f"Using model: {args.model}")
        print(f"Max iterations: {args.max_iters}\n")

        result, browser = run_strudel_rlm(
            args.query,
            args.model,
            args.max_iters,
            max_llm_calls=args.max_llm_calls,
            url=args.url,
        )

        print("\n" + "=" * 60)
        print("RESULT")
        print("=" * 60)
        print(f"\nStrudel Code:\n{result.strudel_code}")
        print(f"\nExplanation:\n{result.explanation}")
        print("\n" + "=" * 60)

        # Play the result in the browser
        code = result.strudel_code
        if code:
            if ".play()" not in code:
                code = code.rstrip().rstrip(";") + ".play()"
            try:
                browser.signal_rlm_complete(code)
            except Exception as e:
                print(f"[warn] signal_rlm_complete failed: {e}")
            try:
                browser.play_in_browser(code)
            except Exception as e:
                print(f"[warn] play_in_browser failed: {e}")
            try:
                input("\nPress Enter to exit...")
            except EOFError:
                browser.wait_for_done()
        else:
            print("\n[warn] No strudel code was generated.")

    finally:
        if browser:
            browser.shutdown()
        if vite_proc:
            stop_process(vite_proc)


if __name__ == "__main__":
    main()
