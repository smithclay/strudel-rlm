import { initStrudel, evaluate, hush, getAudioContext } from '@strudel/web';

// Polyfill roundRect for older browsers
if (typeof CanvasRenderingContext2D !== 'undefined' && !CanvasRenderingContext2D.prototype.roundRect) {
  CanvasRenderingContext2D.prototype.roundRect = function (x, y, w, h, r) {
    if (typeof r === 'number') r = [r, r, r, r];
    const [tl, tr, br, bl] = r;
    this.moveTo(x + tl, y);
    this.lineTo(x + w - tr, y);
    this.arcTo(x + w, y, x + w, y + tr, tr);
    this.lineTo(x + w, y + h - br);
    this.arcTo(x + w, y + h, x + w - br, y + h, br);
    this.lineTo(x + bl, y + h);
    this.arcTo(x, y + h, x, y + h - bl, bl);
    this.lineTo(x, y + tl);
    this.arcTo(x, y, x + tl, y, tl);
    this.closePath();
    return this;
  };
}

const codeDisplay = document.getElementById('code-display');
const timeline = document.getElementById('timeline-list');
const phase = document.getElementById('phase');
const btnPlay = document.getElementById('btn-play');
const btnStop = document.getElementById('btn-stop');
const btnDone = document.getElementById('btn-done');
const btnViz = document.getElementById('btn-viz');
const vizCanvas = document.getElementById('viz-canvas');

// --- Audio-Reactive Visualizer ---

class Visualizer {
  static MODES = ['bars', 'waveform', 'circular'];
  static MODE_LABELS = { bars: '\u25C6 Bars', waveform: '\u25C6 Wave', circular: '\u25C6 Circular' };

  constructor(canvas, analyser) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.analyser = analyser;
    this.analyser.fftSize = 256;
    this.freqData = new Uint8Array(this.analyser.frequencyBinCount);
    this.timeData = new Uint8Array(this.analyser.fftSize);
    this.mode = 0;
    this.rafId = null;
    this.glowAlpha = 0;
    this.avgEnergy = 0;
    this.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    // Cycle progress tracking
    this.playStartTime = 0;
    this.cycleDuration = 1;
    this.cycleCount = 0;
    this.progressFill = document.getElementById('progress-fill');
    this.progressBar = document.getElementById('progress-bar');
    this.cycleCountEl = document.getElementById('cycle-count');
    this.progressRow = document.getElementById('progress-row');
  }

  parseCpm(code) {
    const m = code.match(/\.cpm\((\d+(?:\.\d+)?)\)/);
    return m ? parseFloat(m[1]) : 60;
  }

  parseTotalCycles(code) {
    // For arrange() patterns, sum up all the cycle counts: arrange([4, intro], [8, verse], ...)
    const arrangeMatch = code.match(/arrange\s*\(([\s\S]*?)\)\s*\./);
    if (arrangeMatch) {
      const nums = [...arrangeMatch[1].matchAll(/\[\s*(\d+)\s*,/g)];
      if (nums.length > 0) {
        return nums.reduce((sum, m) => sum + parseInt(m[1]), 0);
      }
    }
    return 0; // 0 = simple looping pattern, use single-cycle mode
  }

  start() {
    if (!this.reducedMotion) {
      this.canvas.style.display = 'block';
    }
    codeDisplay.classList.add('playing');
    this.resize();
    this._onResize = () => this.resize();
    window.addEventListener('resize', this._onResize);
    // Cycle progress setup
    const code = window.__finalCode || '';
    this.playStartTime = getAudioContext().currentTime;
    this.cycleDuration = 60 / this.parseCpm(code);
    this.totalCycles = this.parseTotalCycles(code);
    this.cycleCount = 0;
    if (this.totalCycles > 0) {
      this.cycleCountEl.textContent = `1 / ${this.totalCycles}`;
    } else {
      this.cycleCountEl.textContent = 'Cycle 1';
    }
    this.progressRow.style.display = 'flex';
    this.loop();
  }

  stop() {
    if (this.rafId) cancelAnimationFrame(this.rafId);
    this.rafId = null;
    window.removeEventListener('resize', this._onResize);
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    this.canvas.style.display = 'none';
    codeDisplay.classList.remove('playing');
    // Reset cycle progress
    this.progressRow.style.display = 'none';
    this.progressFill.style.transform = 'scaleX(0)';
    this.progressBar.setAttribute('aria-valuenow', '0');
  }

  resize() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    this.canvas.width = rect.width * devicePixelRatio;
    this.canvas.height = rect.height * devicePixelRatio;
    this.ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    this.w = rect.width;
    this.h = rect.height;
  }

  cycleMode() {
    this.mode = (this.mode + 1) % Visualizer.MODES.length;
    return Visualizer.MODES[this.mode];
  }

  loop() {
    if (!this.reducedMotion) {
      this.draw();
    }
    // Update cycle progress bar
    const elapsed = getAudioContext().currentTime - this.playStartTime;
    const currentCycle = Math.floor(elapsed / this.cycleDuration);

    if (this.totalCycles > 0) {
      // Arranged song: bar tracks full song progress
      const totalDuration = this.totalCycles * this.cycleDuration;
      const songPhase = Math.min(elapsed / totalDuration, 1);
      this.progressFill.style.transform = `scaleX(${songPhase})`;
      this.progressBar.setAttribute('aria-valuenow', String(Math.round(songPhase * 100)));
      if (currentCycle !== this.cycleCount) {
        this.cycleCount = currentCycle;
        const displayCycle = Math.min(this.cycleCount + 1, this.totalCycles);
        this.cycleCountEl.textContent = `${displayCycle} / ${this.totalCycles}`;
      }
    } else {
      // Looping pattern: bar tracks single cycle
      const phase = (elapsed % this.cycleDuration) / this.cycleDuration;
      this.progressFill.style.transform = `scaleX(${phase})`;
      this.progressBar.setAttribute('aria-valuenow', String(Math.round(phase * 100)));
      if (currentCycle !== this.cycleCount) {
        this.cycleCount = currentCycle;
        this.cycleCountEl.textContent = `Cycle ${this.cycleCount + 1}`;
      }
    }
    this.rafId = requestAnimationFrame(() => this.loop());
  }

  draw() {
    const { ctx, w, h } = this;
    this.analyser.getByteFrequencyData(this.freqData);
    this.analyser.getByteTimeDomainData(this.timeData);

    // Trail effect — warm dark base
    ctx.fillStyle = 'rgba(20, 16, 12, 0.25)';
    ctx.fillRect(0, 0, w, h);

    this.detectBeat();

    // Background glow on beat — warm copper pulse
    if (this.glowAlpha > 0.01) {
      const grad = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w * 0.6);
      grad.addColorStop(0, `rgba(200, 150, 60, ${this.glowAlpha})`);
      grad.addColorStop(1, 'rgba(200, 150, 60, 0)');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);
    }

    const mode = Visualizer.MODES[this.mode];
    if (mode === 'bars') this.drawBars();
    else if (mode === 'waveform') this.drawWaveform();
    else if (mode === 'circular') this.drawCircular();
  }

  detectBeat() {
    const bassEnergy = this.freqData[0] + this.freqData[1] + this.freqData[2] + this.freqData[3];
    if (this.avgEnergy > 0 && bassEnergy > this.avgEnergy * 1.8) {
      this.glowAlpha = 0.4;
    }
    this.avgEnergy = this.avgEnergy * 0.95 + bassEnergy * 0.05;
    this.glowAlpha *= 0.92;
  }

  _barColor(i, count) {
    const t = i / count;
    // Warm palette: amber → copper → warm rose
    if (t < 0.4) {
      const u = t / 0.4;
      return `oklch(${72 + u * 6}% ${0.14 + u * 0.04} ${55 + u * 15})`;
    } else if (t < 0.75) {
      const u = (t - 0.4) / 0.35;
      return `oklch(${68 - u * 8}% ${0.12 + u * 0.02} ${40 - u * 15})`;
    } else {
      const u = (t - 0.75) / 0.25;
      return `oklch(${60 + u * 10}% ${0.10 - u * 0.04} ${25 + u * 20})`;
    }
  }

  drawBars() {
    const { ctx, freqData, w, h } = this;
    const barCount = 64;
    const gap = 2;
    const barW = (w - gap * (barCount - 1)) / barCount;

    for (let i = 0; i < barCount; i++) {
      const val = freqData[i] / 255;
      const barH = val * h * 0.8;
      const x = i * (barW + gap);
      const y = h - barH;
      ctx.fillStyle = this._barColor(i, barCount);
      ctx.beginPath();
      ctx.roundRect(x, y, barW, barH, 2);
      ctx.fill();
    }
  }

  drawWaveform() {
    const { ctx, timeData, w, h } = this;
    const len = timeData.length;
    ctx.beginPath();
    ctx.strokeStyle = 'oklch(78% 0.08 165)';
    ctx.lineWidth = 2;

    for (let i = 0; i < len; i++) {
      const x = (i / (len - 1)) * w;
      const y = (timeData[i] / 255) * h;
      if (i === 0) ctx.moveTo(x, y);
      else {
        const px = ((i - 1) / (len - 1)) * w;
        const py = (timeData[i - 1] / 255) * h;
        ctx.quadraticCurveTo(px + (x - px) / 2, py, (px + x) / 2, (py + y) / 2);
      }
    }
    ctx.stroke();
  }

  drawCircular() {
    const { ctx, freqData, w, h } = this;
    const cx = w / 2;
    const cy = h / 2;
    const radius = Math.min(w, h) * 0.35;
    const barCount = 64;

    for (let i = 0; i < barCount; i++) {
      const angle = (i / barCount) * Math.PI * 2 - Math.PI / 2;
      const val = freqData[i] / 255;
      const len = val * radius;
      const x1 = cx + Math.cos(angle) * (radius * 0.3);
      const y1 = cy + Math.sin(angle) * (radius * 0.3);
      const x2 = cx + Math.cos(angle) * (radius * 0.3 + len);
      const y2 = cy + Math.sin(angle) * (radius * 0.3 + len);

      ctx.beginPath();
      ctx.strokeStyle = this._barColor(i, barCount);
      ctx.lineWidth = 3;
      ctx.lineCap = 'round';
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    }
  }
}

let visualizer = null;

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
    // Dynamics compressor for perceived loudness + recording quality
    const compressor = ctx.createDynamicsCompressor();
    compressor.threshold.value = -20;
    compressor.knee.value = 10;
    compressor.ratio.value = 4;
    compressor.attack.value = 0.003;
    compressor.release.value = 0.25;

    // Makeup gain to compensate for compression
    const makeupGain = ctx.createGain();
    makeupGain.gain.value = 2.0; // +6dB

    // Recording destination taps from after compressor+gain
    const streamDest = ctx.createMediaStreamDestination();
    compressor.connect(makeupGain);
    makeupGain.connect(streamDest);

    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    const source = ctx.createMediaStreamSource(streamDest.stream);
    source.connect(analyser);

    const origConnect = AudioNode.prototype.connect;
    AudioNode.prototype.connect = function (dest, ...args) {
      const ret = origConnect.call(this, dest, ...args);
      if (dest === ctx.destination) {
        try { origConnect.call(this, compressor); } catch (_) {}
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
  card.setAttribute('role', 'listitem');
  card.setAttribute('tabindex', '0');
  card.setAttribute('aria-label', `Iteration ${number}, ${valid ? 'valid' : 'error'}`);
  card.innerHTML = `
    <div class="iter-header">
      <span class="iter-num">#${number}</span>
      <span class="iter-badge">${valid ? 'valid' : 'error'}</span>
    </div>
    <div class="iter-preview">${(code || error || '').substring(0, 60)}</div>
  `;

  const idx = iterations.length - 1;
  card.addEventListener('click', () => selectIteration(idx));
  card.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      selectIteration(idx);
    }
  });
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

  // Push final code as a special timeline entry
  const data = { number: '✓', code: finalCode, valid: true, error: null };
  iterations.push(data);
  const card = document.createElement('div');
  card.className = 'iter-card valid final';
  card.setAttribute('role', 'listitem');
  card.setAttribute('tabindex', '0');
  card.setAttribute('aria-label', 'Final iteration, valid');
  card.innerHTML = `
    <div class="iter-header">
      <span class="iter-num">Final</span>
      <span class="iter-badge">strudel</span>
    </div>
    <div class="iter-preview">${finalCode.substring(0, 60)}</div>
  `;
  const idx = iterations.length - 1;
  card.addEventListener('click', () => selectIteration(idx));
  card.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      selectIteration(idx);
    }
  });
  timeline.appendChild(card);
  selectIteration(idx);
  card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

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
        // Start visualizer
        if (window.__analyser) {
          if (!visualizer) visualizer = new Visualizer(vizCanvas, window.__analyser);
          visualizer.start();
          btnViz.disabled = false;
        }
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
  if (visualizer) visualizer.stop();
  btnViz.disabled = true;
  phase.textContent = window.__finalCode ? 'Ready to play' : 'Composing...';
  phase.className = window.__finalCode ? 'ready' : 'composing';
});

btnViz.addEventListener('click', () => {
  if (!visualizer) return;
  const mode = visualizer.cycleMode();
  btnViz.textContent = Visualizer.MODE_LABELS[mode];
});

btnDone.addEventListener('click', () => {
  window.__userDone = true;
  hush();
  if (visualizer) visualizer.stop();
  btnPlay.disabled = true;
  btnStop.disabled = true;
  btnDone.disabled = true;
  btnViz.disabled = true;
  phase.textContent = 'Shutting down...';
  phase.className = 'shutting-down';
});
