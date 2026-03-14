"""CLI entry point: starts a static file server and runs DSPy RLM for Strudel."""

import argparse
import functools
import http.server
import os
import sys
import threading
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


def _wait_for_url(url: str, timeout: float = 10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return
        except urllib.error.URLError:
            time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for server at {url}")


def start_static_server(url: str):
    """Serve dist/ with Python's built-in HTTP server."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 5173
    dist_dir = os.path.join(project_root, "dist")

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=dist_dir)
    server = http.server.HTTPServer((host, port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _wait_for_url(url)
    return server


def main():
    parser = argparse.ArgumentParser(description="Generate Strudel patterns with DSPy RLM")
    parser.add_argument("query", help="Natural language description of the desired music pattern")
    parser.add_argument("--model", default="openrouter/google/gemini-3-flash-preview", help="LLM model")
    parser.add_argument("--max-iters", type=int, default=10, help="Max RLM iterations (default: 10)")
    parser.add_argument("--max-llm-calls", type=int, default=20, help="Max sub-LLM calls via llm_query (default: 20)")
    parser.add_argument("--max-debate-rounds", type=int, default=3, help="Max composer/critic debate rounds (default: 3)")
    parser.add_argument("--no-server", action="store_true", help="Skip starting the static server (if already running)")
    parser.add_argument("--url", default="http://127.0.0.1:5173", help="Strudel app URL")
    args = parser.parse_args()

    server = None
    if not args.no_server:
        print(f"Starting static server at {args.url}...")
        server = start_static_server(args.url)

    browser = None
    try:
        print(f"\nGenerating pattern for: {args.query}")
        print(f"Using model: {args.model}")
        print(f"Max iterations: {args.max_iters}, Max debate rounds: {args.max_debate_rounds}\n")

        result, browser = run_strudel_rlm(
            args.query,
            args.model,
            args.max_iters,
            max_llm_calls=args.max_llm_calls,
            max_debate_rounds=args.max_debate_rounds,
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
        if server:
            server.shutdown()


if __name__ == "__main__":
    main()
