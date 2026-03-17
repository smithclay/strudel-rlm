# Strudel RLM

AI-assisted live-coded music composition tool built on Strudel (TidalCycles for the browser).

## Build & Run

```bash
cd frontend && npm run build   # Build frontend
python scripts/run.py          # Run the RLM pipeline
```

## Design Context

### Users
Musicians, sound designers, and music technologists using AI-assisted live-coded composition. They expect professional, instrument-grade interfaces.

### Brand Personality
Sleek, immersive, musical. The interface should feel like a creative instrument, not a web app.

### Aesthetic Direction
Ableton Live / Push reference — dark, grid-based, precise. The experience should evoke "This is magical" + "This is alive."

- Dark background: `#0d0d1a`
- Panel backgrounds: `#131325`, `#10101e`
- Accent indigo: `#6366f1` / `#818cf8`
- Success green: `#4ade80`
- Warning amber: `#f0c040`
- Error red: `#f87171`
- Code text: `#7fdbca`
- Monospace font: SF Mono / Fira Code

### Design Principles
1. **Immersion first** — Visualizations and audio are the primary experience; chrome stays minimal
2. **Musical precision** — Timing, transitions, and animations should feel rhythmic and intentional
3. **Progressive disclosure** — Show controls when relevant (e.g., progress bar only during playback)
4. **Dark by default** — Everything optimized for low-light creative environments
5. **Instrument-grade** — Buttons, indicators, and feedback should feel tactile and responsive

### Accessibility
- Keyboard navigation required for all controls
- High contrast text on dark backgrounds
- Semantic HTML structure
