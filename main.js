import { initStrudel, evaluate, hush, getAudioContext } from '@strudel/web';

const codeDisplay = document.getElementById('code-display');
const timeline = document.getElementById('timeline');
const phase = document.getElementById('phase');
const btnPlay = document.getElementById('btn-play');
const btnStop = document.getElementById('btn-stop');
const btnDone = document.getElementById('btn-done');

// State
const iterations = [];
let selectedIndex = null;
window.__userDone = false;

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

  window.__strudelReady = true;
});

// --- Iteration timeline API (called from Python via Playwright) ---

window.__strudelPushIteration = (data) => {
  const { number, code, valid, error } = data;
  iterations.push(data);

  // Create card in timeline
  const card = document.createElement('div');
  card.className = `iter-card ${valid ? 'valid' : 'error'}`;
  card.innerHTML = `
    <div class="iter-header">
      <span class="iter-num">#${number}</span>
      <span class="iter-badge">${valid ? 'valid' : 'error'}</span>
    </div>
    <div class="iter-preview">${(code || error || '').substring(0, 60)}</div>
  `;

  const idx = iterations.length - 1;
  card.addEventListener('click', () => selectIteration(idx));
  timeline.appendChild(card);

  // Auto-select latest and scroll
  selectIteration(idx);
  card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
};

function selectIteration(idx) {
  selectedIndex = idx;
  const data = iterations[idx];

  // Update code display
  if (data.valid) {
    codeDisplay.textContent = data.code;
  } else {
    codeDisplay.textContent = `// Error: ${data.error}\n\n${data.code}`;
  }

  // Update card selection styles
  const cards = timeline.querySelectorAll('.iter-card');
  cards.forEach((c, i) => c.classList.toggle('selected', i === idx));
}

// --- RLM lifecycle (called from Python via Playwright) ---

window.__strudelRLMComplete = (finalCode) => {
  window.__finalCode = finalCode;
  btnPlay.disabled = false;
  btnDone.disabled = false;
  phase.textContent = 'Ready to play';
  phase.className = 'ready';
};

// --- Strudel eval/validate APIs (unchanged) ---

window.__strudelValidate = async (code) => {
  try {
    // Strip .play() so validation never starts audio
    const safeCode = code.replace(/\.play\(\)\s*;?\s*$/, '');
    await evaluate(safeCode, false);
    return { success: true, error: null };
  } catch (e) {
    return { success: false, error: e.message };
  }
};

window.__strudelEval = async (code) => {
  try {
    hush();
    await new Promise((r) => setTimeout(r, 50));
    await evaluate(code);
    return { success: true, error: null };
  } catch (e) {
    return { success: false, error: e.message };
  }
};

window.__strudelStop = () => {
  hush();
  return { success: true };
};

window.__getAudioAnalysis = async () => {
  try {
    const ctx = getAudioContext();
    const analyser = window.__analyser;
    if (!ctx || ctx.state !== 'running' || !analyser) {
      return { playing: false, rms: 0, state: ctx?.state || 'unavailable' };
    }

    await new Promise((r) => setTimeout(r, 200));

    const data = new Float32Array(analyser.fftSize);
    analyser.getFloatTimeDomainData(data);
    const rms = Math.sqrt(data.reduce((sum, v) => sum + v * v, 0) / data.length);
    return { playing: rms > 0.001, rms, state: ctx.state };
  } catch (e) {
    return { playing: false, rms: 0, error: e.message };
  }
};

// --- Button handlers ---

btnPlay.addEventListener('click', async () => {
  console.log('[play] clicked, finalCode?', !!window.__finalCode);
  try {
    const ctx = getAudioContext();
    console.log('[play] AudioContext state:', ctx?.state);
    if (ctx && ctx.state === 'suspended') {
      await ctx.resume();
      console.log('[play] AudioContext resumed');
    }
    if (window.__finalCode) {
      const result = await window.__strudelEval(window.__finalCode);
      console.log('[play] eval result:', result);
      if (result.success) {
        phase.textContent = 'Playing';
        phase.className = 'ready';
      } else {
        phase.textContent = `Error: ${result.error}`;
      }
    } else {
      console.log('[play] no finalCode set');
    }
  } catch (e) {
    console.error('[play] error:', e);
  }
});

btnStop.addEventListener('click', () => {
  hush();
  phase.textContent = window.__finalCode ? 'Ready to play' : 'Composing...';
  phase.className = window.__finalCode ? 'ready' : 'composing';
});

btnDone.addEventListener('click', () => {
  window.__userDone = true;
  hush();
  btnPlay.disabled = true;
  btnStop.disabled = true;
  btnDone.disabled = true;
  phase.textContent = 'Shutting down...';
  phase.className = 'shutting-down';
});
