"""Compare Strudel generation quality across multiple OpenRouter models.

Runs the same musical prompt through several models, collects critic scores,
and prints a side-by-side comparison table. Optionally records audio and
scores it via the bergain CE judge (audiobox_aesthetics).

Experiment harness features:
    --repeat N       Run each model×query combo N times for statistical power
    --tag TAG        Label experiment configs (e.g., "baseline", "new-prompt-v1")
    --csv PATH       Append results to CSV for longitudinal analysis
    --analyze PATH   Analyze accumulated CSV for feature-CE correlations

Usage:
    uv run python scripts/compare_models.py "lo-fi hip hop beats to study to"
    uv run python scripts/compare_models.py "dark ambient drone" --save-code
    uv run python scripts/compare_models.py "techno banger" --record 10 --judge
    uv run python scripts/compare_models.py --judge-existing library/*.wav
    uv run python scripts/compare_models.py "dub reggae" --repeat 5 --record 30 --judge --tag baseline --csv library/experiment.csv
    uv run python scripts/compare_models.py --analyze library/experiment.csv
"""

import argparse
import csv
import glob
import json
import math
import os
import re
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
# Code feature extraction for CE correlation analysis
# ---------------------------------------------------------------------------

def extract_code_features(code: str) -> dict:
    """Extract mechanical features from Strudel code for CE correlation analysis."""
    lines = code.splitlines()

    all_lpfs, bass_lpfs, nonbass_lpfs = [], [], []
    all_gains, melodic_gains = [], []

    for line in lines:
        for m in re.finditer(r'\.lpf\((\d+)\)', line):
            val = int(m.group(1))
            is_bass = bool(re.search(r'(?:bass|jvbass|"sine")', line, re.I)) and \
                      bool(re.search(r'note\(".*?[0-2]"?\)', line))
            all_lpfs.append(val)
            (bass_lpfs if is_bass else nonbass_lpfs).append(val)
        for m in re.finditer(r'\.gain\(([\d.]+)\)', line):
            g = float(m.group(1))
            all_gains.append(g)
            if re.search(r'note\(|\.s\("(?:sawtooth|triangle|square)"', line):
                melodic_gains.append(g)

    section_names = re.findall(r'const\s+(\w+)\s*=\s*stack', code)
    sections = re.split(r'const\s+\w+\s*=\s*stack\s*\(', code)
    max_layers = 0
    for s in sections[1:]:
        lc = s.count('\n  s(') + s.count('\n  note(') + s.count('\ns(') + s.count('\nnote(')
        max_layers = max(max_layers, lc)

    cpm_match = re.search(r'\.cpm\((\d+)\)', code)

    return {
        "layer_count_max": max_layers,
        "section_count": len(section_names),
        "lpf_max_nonbass": max(nonbass_lpfs) if nonbass_lpfs else 0,
        "lpf_min_nonbass": min(nonbass_lpfs) if nonbass_lpfs else 0,
        "lpf_mean_nonbass": round(sum(nonbass_lpfs) / len(nonbass_lpfs), 1) if nonbass_lpfs else 0,
        "gain_mean": round(sum(all_gains) / len(all_gains), 3) if all_gains else 0,
        "gain_range": round(max(all_gains) - min(all_gains), 3) if len(all_gains) > 1 else 0,
        "gain_melodic_max": max(melodic_gains) if melodic_gains else 0,
        "bass_type": "sawtooth" if re.search(r'"sawtooth".*note\(".*?[0-2]', code) else
                     "sine" if re.search(r'"sine".*note\(".*?[0-2]', code) else "other",
        "has_delay": bool(re.search(r'\.delay\(', code)),
        "delay_count": len(re.findall(r'\.delay\(', code)),
        "room_count": len(re.findall(r'\.room\(', code)),
        "has_arrange": bool(re.search(r'arrange\(', code)),
        "has_repetition": bool(re.search(r'\[.*?verse\].*\[.*?chorus\].*\[.*?verse\]', code, re.DOTALL)),
        "unique_sounds": len(set(re.findall(r's\("(\w+)"', code))),
        "code_length": len(code),
        "cpm": int(cpm_match.group(1)) if cpm_match else 0,
    }


# Feature keys in consistent order for CSV output
FEATURE_KEYS = [
    "layer_count_max", "section_count",
    "lpf_max_nonbass", "lpf_min_nonbass", "lpf_mean_nonbass",
    "gain_mean", "gain_range", "gain_melodic_max",
    "bass_type", "has_delay", "delay_count", "room_count",
    "has_arrange", "has_repetition", "unique_sounds", "code_length", "cpm",
]


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

        features = extract_code_features(code) if code else {}

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
            "features": features,
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
            "features": {},
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
# CSV accumulation
# ---------------------------------------------------------------------------

CSV_COLUMNS = [
    "timestamp", "tag", "model", "query", "run", "status",
    "harmony", "rhythm", "arrangement", "production", "critic_avg",
    "CE", "PQ", "elapsed_s",
] + FEATURE_KEYS


def append_to_csv(csv_path: str, results: list[dict], query: str, tag: str):
    """Append result rows to a CSV file, creating it with headers if new."""
    file_exists = os.path.isfile(csv_path)
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        for r in results:
            scores = r.get("scores", {})
            ce = r.get("ce_scores") or {}
            features = r.get("features", {})
            row = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tag": tag,
                "model": r["model"].split("/")[-1],
                "query": query,
                "run": r.get("run", 1),
                "status": r["status"],
                "harmony": scores.get("harmony", ""),
                "rhythm": scores.get("rhythm", ""),
                "arrangement": scores.get("arrangement", ""),
                "production": scores.get("production", ""),
                "critic_avg": scores.get("average", ""),
                "CE": ce.get("CE", ""),
                "PQ": ce.get("PQ", ""),
                "elapsed_s": r["elapsed_s"],
            }
            for k in FEATURE_KEYS:
                row[k] = features.get(k, "")
            writer.writerow(row)
    print(f"  [csv] Appended {len(results)} row(s) to {csv_path}")


# ---------------------------------------------------------------------------
# Analyze accumulated CSV
# ---------------------------------------------------------------------------

def _pearson_r(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Compute Pearson correlation coefficient and approximate p-value (stdlib only)."""
    n = len(xs)
    if n < 3:
        return 0.0, 1.0
    mx = sum(xs) / n
    my = sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs) / (n - 1)) if n > 1 else 0
    sy = math.sqrt(sum((y - my) ** 2 for y in ys) / (n - 1)) if n > 1 else 0
    if sx == 0 or sy == 0:
        return 0.0, 1.0
    r = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / ((n - 1) * sx * sy)
    r = max(-1.0, min(1.0, r))
    # Approximate two-tailed p-value via t-distribution
    if abs(r) >= 1.0:
        return r, 0.0
    t = r * math.sqrt((n - 2) / (1 - r * r))
    # Rough p-value approximation using normal CDF for large-ish n
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2))))
    return r, p


def analyze_csv(csv_path: str):
    """Read accumulated CSV and print feature-CE correlation report."""
    if not os.path.isfile(csv_path):
        print(f"[error] File not found: {csv_path}")
        sys.exit(1)

    with open(csv_path, newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("[error] CSV is empty")
        sys.exit(1)

    # Filter to rows with CE scores
    scored = [r for r in rows if r.get("CE") and r["CE"] != ""]
    print(f"\nCE Score Feature Correlations (N={len(scored)} scored runs, {len(rows)} total)")
    print("=" * 80)

    if len(scored) < 3:
        print("  Not enough scored runs for correlation analysis (need >= 3).")
        print("  Run more experiments with --record and --judge.\n")
    else:
        ce_vals = [float(r["CE"]) for r in scored]

        # Numeric features only
        numeric_features = [k for k in FEATURE_KEYS if k not in ("bass_type",)]

        correlations = []
        for feat in numeric_features:
            vals = []
            ces = []
            for r, ce in zip(scored, ce_vals):
                v = r.get(feat, "")
                if v == "" or v is None:
                    continue
                # Convert booleans stored as strings
                if v in ("True", "False"):
                    v = 1.0 if v == "True" else 0.0
                try:
                    vals.append(float(v))
                    ces.append(ce)
                except ValueError:
                    continue
            if len(vals) < 3:
                continue
            r_val, p_val = _pearson_r(vals, ces)
            # Quartile split for high/low CE means
            sorted_pairs = sorted(zip(ces, vals))
            q = max(1, len(sorted_pairs) // 4)
            low_mean = sum(v for _, v in sorted_pairs[:q]) / q if q > 0 else 0
            high_mean = sum(v for _, v in sorted_pairs[-q:]) / q if q > 0 else 0
            correlations.append((feat, r_val, p_val, high_mean, low_mean))

        correlations.sort(key=lambda x: abs(x[1]), reverse=True)

        print(f"\n{'Feature':<25} {'r':>6} {'p-value':>9}  {'High-CE mean':>13} {'Low-CE mean':>12}")
        print("-" * 80)
        for feat, r_val, p_val, high_mean, low_mean in correlations:
            sig = "*" if p_val < 0.05 else " "
            print(f"{feat:<25} {r_val:>6.2f} {p_val:>9.3f}{sig} {high_mean:>13.2f} {low_mean:>12.2f}")
        print("-" * 80)
        print("  * = p < 0.05\n")

    # Group by tag
    tags = {}
    for r in scored:
        t = r.get("tag", "(none)") or "(none)"
        tags.setdefault(t, []).append(float(r["CE"]))

    if tags:
        print("By tag:")
        for tag, ces in sorted(tags.items()):
            n = len(ces)
            mean = sum(ces) / n
            std = math.sqrt(sum((c - mean) ** 2 for c in ces) / n) if n > 1 else 0
            print(f"  {tag:<25} N={n:<4} CE mean={mean:.2f}  std={std:.2f}")
        print()

    # Group by model
    models = {}
    for r in scored:
        m = r.get("model", "unknown")
        models.setdefault(m, []).append(float(r["CE"]))

    if len(models) > 1:
        print("By model:")
        for model, ces in sorted(models.items()):
            n = len(ces)
            mean = sum(ces) / n
            std = math.sqrt(sum((c - mean) ** 2 for c in ces) / n) if n > 1 else 0
            print(f"  {model:<25} N={n:<4} CE mean={mean:.2f}  std={std:.2f}")
        print()


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

    parser.add_argument("--repeat", type=int, default=1, help="Repeat each model N times (for statistical power)")
    parser.add_argument("--tag", default="", metavar="TAG", help="Label for this experiment config (e.g., 'baseline', 'new-prompt-v1')")
    parser.add_argument("--csv", metavar="PATH", help="Append results to CSV for longitudinal analysis")
    parser.add_argument("--analyze", metavar="CSV", help="Analyze accumulated CSV for feature-CE correlations (skips generation)")

    parser.add_argument(
        "--judge-existing", nargs="+", metavar="WAV",
        help="Score existing WAV files via CE judge (skips generation entirely)",
    )
    parser.add_argument(
        "--normalize", action="store_true",
        help="When used with --judge-existing, also score a normalized copy for comparison",
    )

    args = parser.parse_args()

    # Analyze mode — read CSV and print report, then exit
    if args.analyze:
        analyze_csv(args.analyze)
        return

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
        parser.error("query is required when not using --judge-existing or --analyze")

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

    total_runs = len(model_ids) * args.repeat
    print(f"\nQuery: \"{args.query}\"")
    print(f"Models: {len(model_ids)}  ×  Repeats: {args.repeat}  =  {total_runs} total runs")
    if args.tag:
        print(f"Tag: {args.tag}")
    for mid in model_ids:
        print(f"  - {mid}")
    print(f"Settings: max_iters={args.max_iters}, max_debate_rounds={args.max_debate_rounds}")
    print()

    # Run each model × repeat sequentially
    results = []
    run_num = 0
    for i, model_id in enumerate(model_ids):
        model_short = model_id.split("/")[-1]
        for rep in range(1, args.repeat + 1):
            run_num += 1
            print(f"\n{'='*60}")
            print(f"  [{run_num}/{total_runs}] {model_short} run {rep}/{args.repeat}")
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
            r["run"] = rep
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

    # Append to CSV if requested
    if args.csv:
        append_to_csv(args.csv, results, args.query, args.tag)

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
