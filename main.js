import { initStrudel, evaluate, hush, getAudioContext } from '@strudel/web';

const status = document.getElementById('status');
const codeDisplay = document.getElementById('code-display');
const iterCount = document.getElementById('iter-count');

let iteration = 0;

initStrudel({
  prebake: () => samples('github:tidalcycles/dirt-samples'),
}).then(() => {
  // Patch AudioNode.connect BEFORE any patterns play so we can tap audio
  const ctx = getAudioContext();
  if (ctx) {
    const streamDest = ctx.createMediaStreamDestination();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    const source = ctx.createMediaStreamSource(streamDest.stream);
    source.connect(analyser);

    const origConnect = AudioNode.prototype.connect;
    AudioNode.prototype.connect = function (dest, ...args) {
      const ret = origConnect.call(this, dest, ...args);
      if (dest === ctx.destination) {
        try { origConnect.call(this, streamDest); } catch (_) {}
      }
      return ret;
    };

    window.__analyser = analyser;
  }

  status.textContent = 'Ready! Click play.';
  window.__strudelReady = true;
});

// Playwright-callable: validate-only (transpile, no audio scheduling)
window.__strudelValidate = async (code) => {
  try {
    await evaluate(code, false); // transpile only, no audio
    return { success: true, error: null };
  } catch (e) {
    return { success: false, error: e.message };
  }
};

// Playwright-callable: evaluate Strudel code via the transpiler (with audio)
// Caller is responsible for sending the FULL accumulated code each time.
window.__strudelEval = async (code) => {
  try {
    hush();
    await new Promise((r) => setTimeout(r, 50));
    await evaluate(code);
    iteration++;
    if (codeDisplay) codeDisplay.textContent = code;
    if (iterCount) iterCount.textContent = `Iteration: ${iteration}`;
    status.textContent = 'Playing...';
    return { success: true, error: null };
  } catch (e) {
    return { success: false, error: e.message };
  }
};

// Playwright-callable: stop audio
window.__strudelStop = () => {
  hush();
  status.textContent = 'Stopped.';
  return { success: true };
};

// Playwright-callable: audio analysis
window.__getAudioAnalysis = async () => {
  try {
    const ctx = getAudioContext();
    const analyser = window.__analyser;
    if (!ctx || ctx.state !== 'running' || !analyser) {
      return { playing: false, rms: 0, state: ctx?.state || 'unavailable' };
    }

    // Wait a beat for audio data to flow through
    await new Promise((r) => setTimeout(r, 200));

    const data = new Float32Array(analyser.fftSize);
    analyser.getFloatTimeDomainData(data);
    const rms = Math.sqrt(data.reduce((sum, v) => sum + v * v, 0) / data.length);
    return { playing: rms > 0.001, rms, state: ctx.state };
  } catch (e) {
    return { playing: false, rms: 0, error: e.message };
  }
};

document.getElementById('play').addEventListener('click', () => {
  note('<c a f e>(3,8)').s('triangle').jux(rev).play();
  status.textContent = 'Playing...';
});

document.getElementById('stop').addEventListener('click', () => {
  hush();
  status.textContent = 'Stopped.';
});
