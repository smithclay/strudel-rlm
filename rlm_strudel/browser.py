"""Playwright browser management and DSPy callback for Strudel RLM."""

import base64
import os
import struct
import time
import wave

from playwright.sync_api import sync_playwright
from dspy.utils.callback import BaseCallback


class StrudelBrowser:
    """Manages the Playwright browser for Strudel validation and playback."""

    def __init__(self, url="http://127.0.0.1:5173"):
        self.url = url
        self._playwright = None
        self._browser = None
        self._page = None
        self._started = False

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

    def validate_code(self, code: str) -> str:
        """Validate Strudel code in the browser (transpile only, no audio).

        Returns "Valid!" or "[Error] ...".
        """
        if not self._started:
            self.start()
        try:
            result = self._page.evaluate(
                "(code) => window.__strudelValidate(code)",
                code,
            )
            if result.get("success"):
                return "Valid!"
            else:
                err = result.get("error", "Unknown error")
                # Truncate long errors to avoid overwhelming the sandbox
                if len(err) > 500:
                    err = err[:500] + "... [truncated]"
                return f"[Error] {err}"
        except Exception as e:
            err = str(e)
            if len(err) > 500:
                err = err[:500] + "... [truncated]"
            return f"[Error] {err}"

    def push_iteration(self, number: int, code: str, valid: bool, error: str | None = None):
        """Push an iteration to the browser timeline UI."""
        if self._page:
            self._page.evaluate(
                "(data) => window.__strudelPushIteration(data)",
                {"number": number, "code": code, "valid": valid, "error": error},
            )

    def push_critic_scores(self, round_num: int, scores: dict):
        """Push critic evaluation scores to the browser UI."""
        if self._page:
            try:
                self._page.evaluate(
                    "(data) => window.__strudelPushCriticScores && window.__strudelPushCriticScores(data)",
                    {"round": round_num, **scores},
                )
            except Exception as e:
                print(f"[browser] push_critic_scores failed (non-fatal): {e}")

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
            pass

    def play_in_browser(self, code: str) -> dict:
        """Play code by clicking the Play button (ensures user gesture for AudioContext)."""
        if not self._started:
            self.start()
        print(f"[browser] Playing via button click...")
        # Click the Play button — Playwright clicks count as user gestures,
        # which is required for AudioContext.resume() to work.
        self._page.click("#btn-play")
        time.sleep(1.0)
        analysis = self._page.evaluate("() => window.__getAudioAnalysis()")
        return analysis

    def start_recording(self):
        """Start recording audio output from the browser."""
        if not self._page:
            return
        result = self._page.evaluate("() => window.__startRecording()")
        if result.get("success"):
            print("[browser] Recording started")
        else:
            print(f"[browser] Recording failed: {result.get('error')}")

    def stop_recording(self, output_path: str) -> str | None:
        """Stop recording and save WAV to output_path. Returns path or None."""
        if not self._page:
            return None
        try:
            # __stopRecording returns a Promise — Playwright auto-awaits it
            # Use wait_for_function to allow enough time for WAV encoding
            self._page.wait_for_function("true", timeout=2000)  # brief sync
            result = self._page.evaluate("() => window.__stopRecording()")
        except Exception as e:
            print(f"[browser] Stop recording error: {e}")
            return None
        if not result or not result.get("success"):
            print(f"[browser] Stop recording failed: {result.get('error') if result else 'no result'}")
            return None

        wav_bytes = base64.b64decode(result["base64"])
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(wav_bytes)

        duration = result.get("durationSec", 0)
        size_kb = len(wav_bytes) / 1024
        print(f"[browser] Saved {size_kb:.0f}KB WAV ({duration:.1f}s) to {output_path}")

        # Post-process: trim leading silence then normalize
        _trim_leading_silence(output_path, threshold_db=-40.0)
        _normalize_wav(output_path, target_peak_db=-1.0)

        return output_path

    def shutdown(self):
        if self._browser:
            self._browser.close()
            self._browser = None
        self._page = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
        self._started = False


def _normalize_wav(path: str, target_peak_db: float = -1.0):
    """Normalize a WAV file in-place to target peak dB using only stdlib."""
    try:
        with wave.open(path, "rb") as wf:
            params = wf.getparams()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

        if params.sampwidth != 2:
            print(f"[normalize] Skipping — only 16-bit WAV supported (got {params.sampwidth * 8}-bit)")
            return

        n_samples = n_frames * params.nchannels
        samples = list(struct.unpack(f"<{n_samples}h", raw))

        peak = max(abs(s) for s in samples) if samples else 0
        if peak == 0:
            print("[normalize] Skipping — silent file")
            return

        import math
        target_peak = 10 ** (target_peak_db / 20) * 32767
        scale = target_peak / peak
        normalized = [max(-32768, min(32767, int(s * scale))) for s in samples]

        with wave.open(path, "wb") as wf:
            wf.setparams(params)
            wf.writeframes(struct.pack(f"<{n_samples}h", *normalized))

        gain_db = 20 * math.log10(scale) if scale > 0 else 0
        print(f"[normalize] peak={peak}/32767 → applied {gain_db:+.1f}dB to reach {target_peak_db}dB target")
    except Exception as e:
        print(f"[normalize] Failed (non-fatal): {e}")


def _trim_leading_silence(path: str, threshold_db: float = -40.0):
    """Trim leading silence from a WAV file in-place."""
    try:
        import math
        threshold_amp = int(10 ** (threshold_db / 20) * 32767)

        with wave.open(path, "rb") as wf:
            params = wf.getparams()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

        if params.sampwidth != 2:
            return

        n_samples = n_frames * params.nchannels
        samples = struct.unpack(f"<{n_samples}h", raw)

        # Find first frame where any channel exceeds threshold
        first_loud = 0
        for i in range(0, n_samples, params.nchannels):
            if any(abs(samples[i + ch]) > threshold_amp for ch in range(params.nchannels)):
                first_loud = i // params.nchannels
                break
        else:
            return  # all silent, don't destroy the file

        if first_loud == 0:
            return  # no leading silence

        trimmed_frames = n_frames - first_loud
        trimmed_samples = samples[first_loud * params.nchannels:]

        with wave.open(path, "wb") as wf:
            wf.setparams(params._replace(nframes=trimmed_frames))
            wf.writeframes(struct.pack(f"<{len(trimmed_samples)}h", *trimmed_samples))

        trimmed_ms = first_loud / params.framerate * 1000
        print(f"[trim] Removed {trimmed_ms:.0f}ms of leading silence")
    except Exception as e:
        print(f"[trim] Failed (non-fatal): {e}")


class BrowserCallback(BaseCallback):
    """DSPy callback that pushes RLM iterations to the browser timeline
    and feeds the observability trace.

    Fires on on_module_end after each generate_action Predict call,
    identified by outputs having both 'reasoning' and 'code' attributes.
    """

    def __init__(self, browser: StrudelBrowser, trace=None):
        self.browser = browser
        self.trace = trace
        self._iteration = 0

    def on_module_end(self, call_id, outputs, exception=None):
        if exception or outputs is None:
            return
        # generate_action produces outputs with reasoning + code
        if hasattr(outputs, "code") and hasattr(outputs, "reasoning"):
            self._iteration += 1
            self.browser.push_iteration(self._iteration, outputs.code, True, None)
            if self.trace:
                self.trace.add_iteration(
                    self._iteration, outputs.code,
                    reasoning=getattr(outputs, "reasoning", ""),
                )
