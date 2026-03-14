"""Strudel API reference context for the LLM."""

STRUDEL_CONTEXT = """
# Strudel Live Coding Reference

Strudel is a JavaScript live-coding environment for music. Patterns are built
by chaining functions and must end with `.play()` to produce sound.

## Mini-Notation Syntax
- `"c3 e3 g3"` — sequence of events (space-separated)
- `"c3 [e3 g3]"` — subdivision: e3 and g3 share the time of one step
- `"<c3 e3 g3>"` — alternation: cycle through one per cycle
- `"c3(3,8)"` — Euclidean rhythm: 3 pulses over 8 steps
- `"c3*2"` — repeat: play twice as fast
- `"c3/2"` — slow down: play half as fast
- `"~"` — rest (silence)
- `"c3?"` — random: 50% chance to play

## Core Functions
- `note("c3 e3 g3")` — set pitch (note names or MIDI numbers)
- `s("bd sd hh")` — trigger samples by name
- `n("0 1 2 3")` — sample index variation within a folder
- `gain(0.8)` — volume (0–1)
- `pan(0.5)` — stereo position (0=left, 0.5=center, 1=right)

## Sound Shaping
- `.lpf(2000)` or `.cutoff(2000)` — lowpass filter cutoff in Hz
- `.hpf(500)` — highpass filter
- `.resonance(10)` — filter resonance
- `.vowel("a e i o")` — vowel filter
- `.delay(0.5)` — delay wet amount (0–1)
- `.delaytime(0.125)` — delay time
- `.delayfeedback(0.5)` — delay feedback
- `.room(0.5)` — reverb amount (0–1)
- `.crush(8)` — bitcrush effect

## Pattern Transforms
- `.fast(2)` — speed up pattern
- `.slow(2)` — slow down pattern
- `.rev()` — reverse pattern
- `.jux(rev)` — play original left, transformed right
- `.every(4, fast(2))` — apply transform every N cycles
- `.sometimes(fast(2))` — randomly apply transform
- `.off(0.125, add(note(7)))` — offset copy with transformation

## Combining Patterns
- `stack(pat1, pat2)` — layer patterns simultaneously
- `cat(pat1, pat2)` — sequence patterns one after another

## Available Sounds — ONLY these work. Everything else fails silently!

Drum samples (use with `s()`):
- `bd` — kick drum
- `sd` — snare drum
- `hh` — closed hi-hat
- `lt` — low tom
- `cp` — clap
- `noise` — noise hit

Synths (use with `note().s()`):
- `sawtooth` — bright, good for leads, pads, and chords
- `square` — hollow, good for chiptune and organ sounds
- `triangle` — soft, good for gentle leads and keys
- `sine` — pure tone, good for sub-bass and soft pads

Bass samples (use with `note().s()`):
- `jvbass` — punchy bass

FORBIDDEN — these will produce silence with NO error:
- NO `.bank()` calls (e.g. `.bank("ve_bk")`) — banks are not loaded
- NO sample names besides those listed above (no piano, rhodes, organ, epiano, gretsch, kick, snare, oh, bass, superdrums, etc.)
- NO bare `sawtooth`/`square`/`triangle`/`sine` as JS variables — always use them as strings: `.s("sawtooth")`

Want piano/keys? → `note("c3 e3 g3").s("triangle").lpf(1200)` or `.s("sawtooth").lpf(800)`
Want organ? → `note("c3").s("square").lpf(800)`
Want sub-bass? → `note("c1").s("sine")`

## Tempo
- `.cpm(N)` — cycles per minute. Default ~60. For 90 BPM hip hop, use `.cpm(90)`.

## Examples

Simple beat:
```
s("bd sd [~ bd] sd").play()
```

Layered beat with bass:
```
stack(
  s("bd [~ bd] sd [bd ~ ~ bd]"),
  s("hh*8").gain(0.4),
  note("<c2 f2 g2 a1>").s("sawtooth").lpf(400)
).play()
```

Melodic pattern:
```
note("c4 eb4 g4 bb4")
  .s("sawtooth")
  .lpf(800)
  .room(0.3)
  .delay(0.3)
  .play()
```

Full composition:
```
stack(
  s("bd [~ bd] [~ bd] bd"),
  s("[~ cp] ~ [~ cp] ~").gain(0.7),
  s("hh*4").gain(0.3),
  note("<c2 f2 g2 a1>").s("sawtooth").lpf(400),
  note("c4 e4 g4 b4").s("triangle").room(0.3)
).cpm(90).play()
```

## Incremental Composition

Each iteration validates your code (no audio until SUBMIT). Always include everything:

Iteration 1 — drums (expect "Valid!"):
```
s("bd sd [~ bd] sd").play()
```
Iteration 2 — drums + bass (expect "Valid!"):
```
stack(
  s("bd sd [~ bd] sd"),
  note("<c2 f2 g2 a1>").s("sawtooth").lpf(400)
).play()
```
Iteration 3 — full, then SUBMIT:
```
stack(
  s("bd sd [~ bd] sd"),
  note("<c2 f2 g2 a1>").s("sawtooth").lpf(400),
  note("c4 e4 g4 b4").s("triangle").room(0.3)
).cpm(90).play()

SUBMIT('stack(s("bd sd [~ bd] sd"), note("<c2 f2 g2 a1>").s("sawtooth").lpf(400), note("c4 e4 g4 b4").s("triangle").room(0.3)).cpm(90).play()', 'A layered beat with sawtooth bass and triangle melody at 90 BPM')
```
"""
