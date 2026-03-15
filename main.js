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
    window.__streamDest = streamDest;
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

// --- WAV Recording ---

window.__startRecording = () => {
  const streamDest = window.__streamDest;
  if (!streamDest) return { success: false, error: 'No stream destination' };

  const recorder = new MediaRecorder(streamDest.stream, { mimeType: 'audio/webm;codecs=opus' });
  const chunks = [];
  recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
  recorder.start(100); // collect in 100ms chunks
  window.__recorder = recorder;
  window.__recordChunks = chunks;
  return { success: true };
};

window.__stopRecording = async () => {
  const recorder = window.__recorder;
  if (!recorder || recorder.state === 'inactive') {
    return { success: false, error: 'No active recording' };
  }

  return new Promise((resolve) => {
    recorder.onstop = async () => {
      const blob = new Blob(window.__recordChunks, { type: 'audio/webm' });

      // Decode webm to raw PCM, then encode as WAV
      const ctx = getAudioContext();
      const arrayBuf = await blob.arrayBuffer();
      const audioBuf = await ctx.decodeAudioData(arrayBuf);

      // Encode WAV
      const numChannels = audioBuf.numberOfChannels;
      const sampleRate = audioBuf.sampleRate;
      const length = audioBuf.length;
      const bytesPerSample = 2; // 16-bit
      const blockAlign = numChannels * bytesPerSample;
      const dataSize = length * blockAlign;
      const buffer = new ArrayBuffer(44 + dataSize);
      const view = new DataView(buffer);

      // WAV header
      const writeStr = (offset, str) => { for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i)); };
      writeStr(0, 'RIFF');
      view.setUint32(4, 36 + dataSize, true);
      writeStr(8, 'WAVE');
      writeStr(12, 'fmt ');
      view.setUint32(16, 16, true); // chunk size
      view.setUint16(20, 1, true);  // PCM
      view.setUint16(22, numChannels, true);
      view.setUint32(24, sampleRate, true);
      view.setUint32(28, sampleRate * blockAlign, true);
      view.setUint16(32, blockAlign, true);
      view.setUint16(34, 16, true); // bits per sample
      writeStr(36, 'data');
      view.setUint32(40, dataSize, true);

      // Interleave channels and write PCM
      let offset = 44;
      for (let i = 0; i < length; i++) {
        for (let ch = 0; ch < numChannels; ch++) {
          const sample = Math.max(-1, Math.min(1, audioBuf.getChannelData(ch)[i]));
          view.setInt16(offset, sample * 0x7FFF, true);
          offset += 2;
        }
      }

      // Convert to base64
      const bytes = new Uint8Array(buffer);
      let binary = '';
      for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
      const base64 = btoa(binary);

      window.__recorder = null;
      window.__recordChunks = null;
      resolve({ success: true, base64, sampleRate, channels: numChannels, durationSec: length / sampleRate });
    };
    recorder.stop();
  });
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
