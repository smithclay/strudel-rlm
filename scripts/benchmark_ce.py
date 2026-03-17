"""Benchmark CE scores across audio treatment variants.

Takes WAV files and applies treatments independently (normalize, trim silence,
both), scores all variants via the bergain CE judge, and prints a comparison matrix.

Usage:
    uv run python scripts/benchmark_ce.py library/*.wav
    uv run python scripts/benchmark_ce.py recording.wav --treatments normalize trim both
"""

import argparse
import os
import shutil
import sys
import tempfile

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, ".env"))

from rlm_strudel.browser import _normalize_wav, _trim_leading_silence
from scripts.compare_models import score_audio_ce


TREATMENTS = {
    "original": lambda path: None,
    "normalize": lambda path: _normalize_wav(path),
    "trim": lambda path: _trim_leading_silence(path),
    "trim+norm": lambda path: (_trim_leading_silence(path), _normalize_wav(path)),
}


def benchmark_file(wav_path: str, treatments: list[str]) -> dict:
    """Score a WAV file under each treatment. Returns {treatment: scores_dict}."""
    results = {}
    for treatment in treatments:
        if treatment == "original":
            scores = score_audio_ce(wav_path)
        else:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.close()
            shutil.copy2(wav_path, tmp.name)
            TREATMENTS[treatment](tmp.name)
            scores = score_audio_ce(tmp.name)
            os.unlink(tmp.name)
        results[treatment] = scores
    return results


def main():
    parser = argparse.ArgumentParser(description="Benchmark CE scores across audio treatments")
    parser.add_argument("files", nargs="+", help="WAV files to benchmark")
    parser.add_argument(
        "--treatments", nargs="+",
        default=["original", "normalize", "trim", "trim+norm"],
        choices=list(TREATMENTS.keys()),
        help="Treatments to apply (default: all)",
    )
    args = parser.parse_args()

    # Header
    treat_cols = "".join(f"  {t:>10} CE  PQ" for t in args.treatments)
    print(f"\n{'File':<35}{treat_cols}")
    print("-" * (35 + 16 * len(args.treatments)))

    all_results = []
    for wav in args.files:
        if not os.path.isfile(wav):
            print(f"{os.path.basename(wav):<35}  (not found)")
            continue

        name = os.path.basename(wav)[:33]
        results = benchmark_file(wav, args.treatments)
        all_results.append((wav, results))

        row = f"{name:<35}"
        for t in args.treatments:
            s = results.get(t)
            if s:
                row += f"  {s.get('CE', 0):>10.2f}  {s.get('PQ', 0):>4.1f}"
            else:
                row += f"  {'err':>10}  {'err':>4}"
        print(row)

    # Summary: average CE improvement per treatment vs original
    if len(all_results) > 1:
        print(f"\n{'AVERAGE':>35}", end="")
        for t in args.treatments:
            ces = [r[t].get("CE", 0) for _, r in all_results if r.get(t)]
            avg = sum(ces) / len(ces) if ces else 0
            print(f"  {avg:>10.2f}     ", end="")
        print()

        if "original" in args.treatments:
            print(f"{'DELTA vs original':>35}", end="")
            orig_ces = [r["original"].get("CE", 0) for _, r in all_results if r.get("original")]
            orig_avg = sum(orig_ces) / len(orig_ces) if orig_ces else 0
            for t in args.treatments:
                ces = [r[t].get("CE", 0) for _, r in all_results if r.get(t)]
                avg = sum(ces) / len(ces) if ces else 0
                delta = avg - orig_avg
                print(f"  {delta:>+10.2f}     ", end="")
            print()

    print()


if __name__ == "__main__":
    main()
