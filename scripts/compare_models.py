"""Compare Strudel generation quality across multiple OpenRouter models.

Runs the same musical prompt through several models, collects critic scores,
and prints a side-by-side comparison table. Optionally records audio and
scores it via the bergain CE judge (audiobox_aesthetics).

Usage:
    uv run python scripts/compare_models.py "lo-fi hip hop beats to study to"
    uv run python scripts/compare_models.py "dark ambient drone" --save-code
    uv run python scripts/compare_models.py "techno banger" --record 10 --judge
    uv run python scripts/compare_models.py --judge-existing library/*.wav
"""

import argparse
import glob
import json
import os
import sys
import time
import functools
import http.server
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, ".env"))

from rlm_strudel.rlm_runner import run_strudel_rlm
from rlm_strudel.library import LIBRARY_DIR, _slugify

# Import shared helper from run.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run import compute_skip_seconds

# ---------------------------------------------------------------------------
# Model registry — short aliases → OpenRouter model IDs
# ---------------------------------------------------------------------------

MODEL_REGISTRY = {
    "gemini-3-flash":   "openrouter/google/gemini-3-flash-preview",
    "gemini-3-pro":     "openrouter/google/gemini-3-pro-preview",
    "deepseek-v3":      "openrouter/deepseek/deepseek-chat-v3-0324",
    "claude-sonnet":    "openrouter/anthropic/claude-sonnet-4",
    "gpt-4o":           "openrouter/openai/gpt-4o",
    "qwen3-coder":      "openrouter/qwen/qwen3-coder",
}

DEFAULT_MODELS = ["gemini-3-flash", "deepseek-v3", "claude-sonnet", "gpt-4o"]

# ---------------------------------------------------------------------------
# Server helpers (reused from run.py)
# ---------------------------------------------------------------------------

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
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 5173
    dist_dir = os.path.join(project_root, "frontend", "dist")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=dist_dir)
    server = http.server.HTTPServer((host, port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _wait_for_url(url)
    return server

# ---------------------------------------------------------------------------
# CE Judge scoring via bergain aesthetics endpoint
# ---------------------------------------------------------------------------

JUDGE_URL = os.environ.get(
    "BERGAIN_JUDGE_URL",
    "https://smithclay--bergain-aesthetics-judge-score.modal.run",
)


def score_audio_ce(file_path: str) -> dict | None:
    """Send a WAV file to the bergain aesthetics judge for CE/PQ/PC/CU scores.

    Returns dict like {"CE": 5.8, "PQ": 7.2, "PC": 4.5, "CU": 8.1} or None on failure.
    """
    import requests

    try:
        with open(file_path, "rb") as f:
            resp = requests.post(
                JUDGE_URL,
                files={"file": ("audio.wav", f, "audio/wav")},
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            # Handle both {"scores": {...}} and flat {"CE": ...} formats
            return data.get("scores", data)
    except Exception as e:
        print(f"  [judge] CE scoring failed: {e}")
        return None


def find_latest_wav(prefix_hint: str = "") -> str | None:
    """Find the most recently created WAV file in the library directory."""
    wavs = sorted(glob.glob(os.path.join(LIBRARY_DIR, "*.wav")), key=os.path.getmtime, reverse=True)
    return wavs[0] if wavs else None


# ---------------------------------------------------------------------------
# Run one model and collect results
# ---------------------------------------------------------------------------

def run_single_model(
    model_id: str,
    query: str,
    max_iters: int,
    max_llm_calls: int,
    max_debate_rounds: int,
    url: str,
    record_seconds: int = 0,
    judge: bool = False,
) -> dict:
    """Run a single model and return a results dict."""
    start_time = time.time()
    try:
        result, browser = run_strudel_rlm(
            query=query,
            model=model_id,
            max_iters=max_iters,
            max_llm_calls=max_llm_calls,
            max_debate_rounds=max_debate_rounds,
            url=url,
        )
        elapsed = time.time() - start_time

        code = result.strudel_code if result else ""
        explanation = result.explanation if result else ""

        # Extract critic scores from the trace stored on browser callback
        scores = {}
        if hasattr(result, "_critic_feedback"):
            feedback = result._critic_feedback
        else:
            feedback = ""

        # Parse scores from the library trace (most recent .trace.json)
        trace_files = sorted(
            [f for f in os.listdir(LIBRARY_DIR) if f.endswith(".trace.json")],
            reverse=True,
        ) if os.path.isdir(LIBRARY_DIR) else []

        if trace_files:
            with open(os.path.join(LIBRARY_DIR, trace_files[0])) as f:
                trace = json.load(f)
            if trace.get("critic_rounds"):
                last_round = trace["critic_rounds"][-1]
                scores = {
                    "harmony": last_round["harmony"],
                    "rhythm": last_round["rhythm"],
                    "arrangement": last_round["arrangement"],
                    "production": last_round["production"],
                    "average": last_round["average"],
                    "approved": last_round["approved"],
                }

        # Record audio and optionally score via CE judge
        wav_path = None
        ce_scores = None
        if record_seconds > 0 and code:
            try:
                play_code = code if ".play()" in code else code.rstrip().rstrip(";") + ".play()"
                try:
                    browser.signal_rlm_complete(play_code)
                except Exception:
                    pass
                browser.play_in_browser(play_code)
                # Skip intro sections to record the chorus/drop
                skip_s = compute_skip_seconds(code)
                if skip_s > 0:
                    print(f"  [record] Skipping {skip_s:.1f}s of intro...")
                    time.sleep(skip_s)
                browser.start_recording()
                print(f"  [record] Recording {record_seconds}s...")
                time.sleep(record_seconds)
                # Derive WAV path from latest library .js
                js_files = sorted(glob.glob(os.path.join(LIBRARY_DIR, "*.js")))
                wav_path = js_files[-1].replace(".js", ".wav") if js_files else os.path.join(LIBRARY_DIR, "recording.wav")
                browser.stop_recording(wav_path)
                print(f"  [record] Saved {os.path.basename(wav_path)}")
            except Exception as e:
                print(f"  [record] Recording failed: {e}")

        if judge:
            # Use recorded WAV, or find the latest one from the pipeline
            score_path = wav_path or find_latest_wav()
            if score_path:
                print(f"  [judge] Scoring {os.path.basename(score_path)}...")
                ce_scores = score_audio_ce(score_path)
                if ce_scores:
                    ce = ce_scores.get("CE", 0)
                    pq = ce_scores.get("PQ", 0)
                    print(f"  [judge] CE={ce:.2f}  PQ={pq:.2f}")
            else:
                print("  [judge] No WAV file found to score")

        browser.shutdown()

        return {
            "model": model_id,
            "status": "ok",
            "code": code,
            "explanation": explanation,
            "scores": scores,
            "ce_scores": ce_scores,
            "wav_path": wav_path,
            "feedback": feedback,
            "elapsed_s": round(elapsed, 1),
        }

    except Exception as e:
        elapsed = time.time() - start_time
        return {
            "model": model_id,
            "status": f"error: {e}",
            "code": "",
            "explanation": "",
            "scores": {},
            "ce_scores": None,
            "wav_path": None,
            "feedback": "",
            "elapsed_s": round(elapsed, 1),
        }


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def print_comparison_table(results: list[dict], query: str):
    """Print a formatted comparison table."""
    has_ce = any(r.get("ce_scores") for r in results)

    print("\n" + "=" * 90)
    print(f"  MODEL COMPARISON — \"{query}\"")
    print("=" * 90)

    # Header
    ce_hdr = "  CE    PQ" if has_ce else ""
    print(f"\n{'Model':<35} {'H':>3} {'R':>3} {'A':>3} {'P':>3} {'Avg':>5}{ce_hdr} {'Time':>7} {'Status':<10}")
    print("-" * 90)

    # Sort by CE score if available, otherwise by critic average
    def sort_key(r):
        ce = r.get("ce_scores", {}) or {}
        return (ce.get("CE", 0), r["scores"].get("average", 0))
    ranked = sorted(results, key=sort_key, reverse=True)

    for r in ranked:
        s = r["scores"]
        ce = r.get("ce_scores") or {}
        model_short = r["model"].split("/")[-1][:33]
        if s:
            approved = " *" if s.get("approved") else ""
            ce_col = f"  {ce['CE']:>4.1f}  {ce['PQ']:>4.1f}" if ce else ("    —     —" if has_ce else "")
            print(
                f"{model_short:<35} {s['harmony']:>3} {s['rhythm']:>3} "
                f"{s['arrangement']:>3} {s['production']:>3} "
                f"{s['average']:>5.1f}{approved}{ce_col} {r['elapsed_s']:>6.0f}s {'ok':<10}"
            )
        else:
            ce_col = "    —     —" if has_ce else ""
            print(
                f"{model_short:<35} {'—':>3} {'—':>3} {'—':>3} {'—':>3} "
                f"{'—':>5} {ce_col} {r['elapsed_s']:>6.0f}s {r['status'][:10]:<10}"
            )

    print("-" * 90)
    print("  * = critic approved    H/R/A/P = critic scores (1-10)")
    if has_ce:
        print("  CE = Content Enjoyment (audiobox_aesthetics)    PQ = Production Quality")
    print()

    # Detail section — show feedback for each model
    for r in ranked:
        model_short = r["model"].split("/")[-1]
        if r["feedback"]:
            print(f"--- {model_short} feedback ---")
            print(r["feedback"])
            print()


def save_results(results: list[dict], query: str, output_dir: str):
    """Save all results to a comparison directory."""
    os.makedirs(output_dir, exist_ok=True)

    # Save summary JSON
    summary_path = os.path.join(output_dir, "summary.json")
    summary = {
        "query": query,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": [
            {
                "model": r["model"],
                "status": r["status"],
                "scores": r["scores"],
                "ce_scores": r.get("ce_scores"),
                "wav_path": r.get("wav_path"),
                "elapsed_s": r["elapsed_s"],
                "explanation": r["explanation"],
            }
            for r in results
        ],
    }
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Summary: {summary_path}")

    # Save each model's code as a .js file
    for r in results:
        if r["code"]:
            model_slug = _slugify(r["model"].split("/")[-1], max_len=30)
            js_path = os.path.join(output_dir, f"{model_slug}.js")
            s = r["scores"]
            with open(js_path, "w") as f:
                f.write(f"// Model: {r['model']}\n")
                f.write(f"// Query: {query}\n")
                if s:
                    f.write(f"// Scores: H={s['harmony']} R={s['rhythm']} "
                            f"A={s['arrangement']} P={s['production']} "
                            f"avg={s['average']:.1f}\n")
                f.write(f"// Time: {r['elapsed_s']}s\n\n")
                f.write(r["code"])
                if not r["code"].endswith("\n"):
                    f.write("\n")
            print(f"  Code: {js_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Compare Strudel generation quality across OpenRouter models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Available model aliases:\n"
            + "\n".join(f"  {alias:<20} {model_id}" for alias, model_id in MODEL_REGISTRY.items())
            + f"\n\nDefault models: {', '.join(DEFAULT_MODELS)}"
        ),
    )
    parser.add_argument("query", nargs="?", default="", help="Musical prompt (same for all models)")
    parser.add_argument(
        "--models", nargs="+", default=DEFAULT_MODELS, metavar="MODEL",
        help=f"Model aliases or full OpenRouter IDs (default: {' '.join(DEFAULT_MODELS)})",
    )
    parser.add_argument("--save-code", action="store_true", help="Save Strudel code for each model")
    parser.add_argument("--output-dir", default=None, help="Directory for saved code (default: library/compare_<timestamp>)")
    parser.add_argument("--max-iters", type=int, default=6, help="Max RLM iterations per model (default: 6)")
    parser.add_argument("--max-llm-calls", type=int, default=20, help="Max sub-LLM calls (default: 20)")
    parser.add_argument("--max-debate-rounds", type=int, default=2, help="Max debate rounds per model (default: 2)")
    parser.add_argument("--record", type=int, default=0, metavar="SEC", help="Record N seconds of audio per model (0=disabled, recommended: 30)")
    parser.add_argument("--judge", action="store_true", help="Score recordings via bergain CE judge endpoint")
    parser.add_argument("--no-server", action="store_true", help="Skip starting the static server")
    parser.add_argument("--url", default="http://127.0.0.1:5173", help="Strudel app URL")

    parser.add_argument(
        "--judge-existing", nargs="+", metavar="WAV",
        help="Score existing WAV files via CE judge (skips generation entirely)",
    )
    parser.add_argument(
        "--normalize", action="store_true",
        help="When used with --judge-existing, also score a normalized copy for comparison",
    )

    args = parser.parse_args()

    # Score existing files mode — no generation needed
    if args.judge_existing:
        print(f"\nScoring {len(args.judge_existing)} WAV file(s) via CE judge...\n")
        hdr_extra = "  CE(n) PQ(n)" if args.normalize else ""
        print(f"{'File':<45} {'CE':>5} {'PQ':>5} {'PC':>5} {'CU':>5}{hdr_extra}")
        print("-" * (75 + (14 if args.normalize else 0)))
        for wav in args.judge_existing:
            if not os.path.isfile(wav):
                print(f"{wav:<45} {'—':>5} {'—':>5} {'—':>5} {'—':>5}")
                continue
            scores = score_audio_ce(wav)
            name = os.path.basename(wav)[:43]
            norm_col = ""
            if args.normalize and scores:
                import shutil
                import tempfile
                from rlm_strudel.browser import _normalize_wav, _trim_leading_silence
                tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                tmp.close()
                shutil.copy2(wav, tmp.name)
                _trim_leading_silence(tmp.name)
                _normalize_wav(tmp.name)
                norm_scores = score_audio_ce(tmp.name)
                os.unlink(tmp.name)
                if norm_scores:
                    norm_col = f"  {norm_scores.get('CE',0):>5.2f} {norm_scores.get('PQ',0):>5.2f}"
                else:
                    norm_col = f"  {'err':>5} {'err':>5}"
            if scores:
                print(f"{name:<45} {scores.get('CE',0):>5.2f} {scores.get('PQ',0):>5.2f} "
                      f"{scores.get('PC',0):>5.2f} {scores.get('CU',0):>5.2f}{norm_col}")
            else:
                print(f"{name:<45} {'err':>5} {'err':>5} {'err':>5} {'err':>5}")
        print()
        return

    if not args.query:
        parser.error("query is required when not using --judge-existing")

    # Resolve model aliases
    model_ids = []
    for m in args.models:
        if m in MODEL_REGISTRY:
            model_ids.append(MODEL_REGISTRY[m])
        elif "/" in m:
            model_ids.append(m)
        else:
            print(f"[error] Unknown model alias '{m}'. Available: {', '.join(MODEL_REGISTRY.keys())}")
            sys.exit(1)

    # Start server
    server = None
    if not args.no_server:
        print(f"Starting static server at {args.url}...")
        server = start_static_server(args.url)

    print(f"\nQuery: \"{args.query}\"")
    print(f"Models: {len(model_ids)}")
    for mid in model_ids:
        print(f"  - {mid}")
    print(f"Settings: max_iters={args.max_iters}, max_debate_rounds={args.max_debate_rounds}")
    print()

    # Run each model sequentially
    results = []
    for i, model_id in enumerate(model_ids, 1):
        model_short = model_id.split("/")[-1]
        print(f"\n{'='*60}")
        print(f"  [{i}/{len(model_ids)}] Running: {model_short}")
        print(f"{'='*60}\n")

        r = run_single_model(
            model_id=model_id,
            query=args.query,
            max_iters=args.max_iters,
            max_llm_calls=args.max_llm_calls,
            max_debate_rounds=args.max_debate_rounds,
            url=args.url,
            record_seconds=args.record,
            judge=args.judge,
        )
        results.append(r)

        s = r["scores"]
        if s:
            print(f"\n  >> {model_short}: avg={s['average']:.1f} "
                  f"(H={s['harmony']} R={s['rhythm']} A={s['arrangement']} P={s['production']}) "
                  f"in {r['elapsed_s']}s")
        else:
            print(f"\n  >> {model_short}: {r['status']} in {r['elapsed_s']}s")

    # Print comparison table
    print_comparison_table(results, args.query)

    # Save code if requested
    if args.save_code:
        if args.output_dir:
            output_dir = args.output_dir
        else:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            slug = _slugify(args.query, max_len=30)
            output_dir = os.path.join(LIBRARY_DIR, f"compare_{ts}_{slug}")

        print(f"Saving results to {output_dir}/")
        save_results(results, args.query, output_dir)

    # Cleanup
    if server:
        server.shutdown()


if __name__ == "__main__":
    main()
