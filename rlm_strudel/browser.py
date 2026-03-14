"""Playwright browser management and DSPy callback for Strudel RLM."""

import time

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
            print(f"[browser] Validating:\n{code}")
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

    def push_iteration(self, number: int, code: str, valid: bool, error: str | None = None):
        """Push an iteration to the browser timeline UI."""
        if self._page:
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

    def shutdown(self):
        if self._browser:
            self._browser.close()
            self._browser = None
        self._page = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
        self._started = False


class BrowserCallback(BaseCallback):
    """DSPy callback that pushes RLM iterations to the browser timeline.

    Fires on on_module_end after each generate_action Predict call,
    identified by outputs having both 'reasoning' and 'code' attributes.
    """

    def __init__(self, browser: StrudelBrowser):
        self.browser = browser
        self._iteration = 0

    def on_module_end(self, call_id, outputs, exception=None):
        if exception or outputs is None:
            return
        # generate_action produces outputs with reasoning + code
        if hasattr(outputs, "code") and hasattr(outputs, "reasoning"):
            self._iteration += 1
            self.browser.push_iteration(self._iteration, outputs.code, True, None)
