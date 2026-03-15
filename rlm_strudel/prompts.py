"""Strudel API reference context — the variable space for the RLM to slice."""

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
- `"c3!2"` — replicate: repeat without changing speed
- `"c3@2"` — elongate: stretch over 2 steps
- `"c3:2"` — select sample index 2
- `"[c3, e3, g3]"` — polyrhythm: play all simultaneously within one step

## Core Functions
- `note("c3 e3 g3")` — set pitch (note names or MIDI numbers)
- `s("bd sd hh")` — trigger samples by name
- `n("0 1 2 3")` — sample index variation within a folder
- `gain(0.8)` — volume (0–1)
- `pan(0.5)` — stereo position (0=left, 0.5=center, 1=right)

## Sound Shaping
- `.lpf(2000)` or `.cutoff(2000)` — lowpass filter cutoff in Hz
- `.hpf(500)` — highpass filter
- `.resonance(10)` — filter resonance (0–40)
- `.vowel("a e i o")` — vowel filter
- `.delay(0.5)` — delay wet amount (0–1)
- `.delaytime(0.125)` — delay time in cycles
- `.delayfeedback(0.5)` — delay feedback (0–1)
- `.room(0.5)` — reverb amount (0–1)
- `.size(0.9)` — reverb size (0–1)
- `.crush(8)` — bitcrush effect (1=extreme, 16=subtle)
- `.coarse(8)` — sample rate reduction
- `.shape(0.5)` — waveshaping distortion (0–1)
- `.attack(0.1)` — attack time in seconds
- `.decay(0.2)` — decay time
- `.sustain(0.5)` — sustain level (0–1)
- `.release(0.3)` — release time
- `.speed(2)` — sample playback speed (negative = reverse)

## Pattern Transforms
- `.fast(2)` — speed up pattern (2x)
- `.slow(2)` — slow down pattern (half speed)
- `.rev()` — reverse pattern order
- `.jux(rev)` — play original left, transformed right
- `.every(4, fast(2))` — apply transform every N cycles
- `.sometimes(fast(2))` — randomly apply transform (~50%)
- `.rarely(fast(2))` — randomly apply (~25%)
- `.often(fast(2))` — randomly apply (~75%)
- `.off(0.125, add(note(7)))` — offset copy with transformation
- `.add(note(7))` — add value to pattern (transpose by 7 semitones)
- `.struct("x ~ x ~ x ~ x ~")` — impose rhythmic structure
- `.mask("1 0 1 1")` — mute steps (0=mute, 1=play)
- `.ply(2)` — subdivide each event
- `.chop(8)` — slice samples into N pieces
- `.striate(4)` — granular slicing across the pattern
- `.iter(4)` — rotate pattern each cycle
- `.chunk(4, fast(2))` — apply transform to one chunk at a time, rotating
- `.superimpose(fast(2))` — layer the pattern with a transformed copy

## Combining Patterns
- `stack(pat1, pat2)` — layer patterns simultaneously
- `cat(pat1, pat2)` — sequence patterns one after another
- `seq(pat1, pat2)` — alias for cat

## Song Structure with arrange()

`arrange([cycles, pattern], ...)` sequences patterns over time. Each entry is
`[N, pattern]` where N is the number of cycles that pattern plays before moving
to the next entry.

```
const intro = stack(
  s("bd ~ ~ ~"),
  s("hh*4").gain(0.2),
  note("c3").s("sine").lpf(400).gain(0.4)
)

const verse = stack(
  s("bd ~ [~ bd] ~"),
  s("~ sd ~ sd"),
  s("hh*8").gain(0.3),
  note("<c2 f2 g2 c2>").s("sawtooth").lpf(400).gain(0.7),
  note("<[c3,e3,g3] [f3,a3,c4]>").s("triangle").lpf(1200).gain(0.4)
)

const chorus = stack(
  s("bd [~ bd] sd [bd ~]"),
  s("hh*16").gain(0.25),
  s("~ cp ~ cp").gain(0.6),
  note("<c2 f2 g2 a1>").s("sawtooth").lpf(600).gain(0.8),
  note("<[c3,e3,g3,b3] [f3,a3,c4,e4] [g3,b3,d4,f4] [a2,c3,e3,g3]>")
    .s("sawtooth").lpf(2000).room(0.4).gain(0.5)
)

const outro = stack(
  s("bd ~ ~ ~"),
  note("c3").s("sine").room(0.8).lpf(400).gain(0.3)
)

arrange(
  [4, intro],
  [8, verse],
  [8, chorus],
  [8, verse],
  [8, chorus],
  [4, outro]
).cpm(90).play()
```

### Section Design Guidelines
- **Intro**: sparse — few layers, simple rhythm, low energy
- **Verse**: medium density — core beat + bass + one harmonic element
- **Chorus**: full energy — all layers active, wider stereo, brighter filters
- **Bridge**: break the pattern — change key, drop drums, shift texture
- **Outro**: wind down — strip layers, increase reverb/delay, fade gain

Sections should CONTRAST in density, energy, texture, and filter settings.
Use `const` to name each section before passing to `arrange()`.

## Available Sounds — ONLY these work. Everything else fails silently!

Drum samples (use with `s()`):
- `bd` — kick drum
- `sd` — snare drum
- `hh` — closed hi-hat
- `oh` — open hi-hat
- `lt` — low tom
- `mt` — mid tom
- `ht` — high tom
- `cp` — clap
- `rim` — rimshot
- `cr` — crash cymbal
- `rd` — ride cymbal
- `cb` — cowbell
- `noise` — noise hit

Synths (use with `note().s()`):
- `sawtooth` — bright, good for leads, pads, and chords
- `square` — hollow, good for chiptune and organ sounds
- `triangle` — soft, good for gentle leads and keys
- `sine` — pure tone, good for sub-bass and soft pads
- `.detune(12)` — detune oscillator for richer/fatter sound (use with any synth)
- `note("c3,e3,g3")` — comma-separated notes for simultaneous chords
- `.arp("up")`, `.arp("down")`, `.arp("updown")` — arpeggiate chords

Bass samples (use with `note().s()`):
- `jvbass` — punchy bass
- `bass1` — round bass
- `bass3` — aggressive bass

FORBIDDEN — these will produce silence or errors with NO warning:
- NO `.bank()` calls (e.g. `.bank("ve_bk")`) — banks are not loaded
- NO sample names besides those listed above (no piano, rhodes, organ, epiano, gretsch, kick, snare, bass, superdrums, etc.)
- NO bare `sawtooth`/`square`/`triangle`/`sine` as JS variables — always use them as strings: `.s("sawtooth")`
- NO `.distort()` — does not exist. Use `.shape(0-1)` for distortion
- NO `.res()` — does not exist. Use `.resonance(0-40)` instead
- NO `.lpq()` — does not exist. Use `.resonance(0-40)` instead
- NO `pattern()` function — does not exist. Use mini-notation strings instead
- NO `perlin` — does not exist. Use `.every()` or `.sometimes()` for variation
- NO `patterns.sine` or `patterns.*` — does not exist. Use `.slow()` and `.fast()` for movement
- NO `sine.range()` or `saw()` — does not exist as standalone. Use `.slow()` for movement
- NO `.euclid()` as a method — use mini-notation: `s("bd(3,8)")` not `s("bd").euclid(3,8)`
- NO `.perc()` — does not exist. Use `.decay()` and `.sustain(0)` instead
- NO `.fadeOut()` or `.fadeIn()` — does not exist
- NO `.adsr()` — does not exist. Use separate `.attack()`, `.decay()`, `.sustain()`, `.release()`
- NO `'7` or `'maj7` or `'m9` chord shorthand in note() — use comma-separated notes: `note("c3,e3,g3,bb3")` not `note("c3'7")`
- NO `.struct()` with numbers — use mini-notation: `s("bd(3,8)")` not `.struct("1(3,8)")`
- NO `.chord()` — does not exist. Use comma-separated notes in note()
- NO `Gibber` syntax, no `Drums()`, no `.amp` — this is Strudel, not Gibber

Want piano/keys? → `note("c3 e3 g3").s("triangle").lpf(1200)` or `.s("sawtooth").lpf(800)`
Want organ? → `note("c3").s("square").lpf(800)`
Want sub-bass? → `note("c1").s("sine")`
Want thick pad? → `note("c3,e3,g3").s("sawtooth").detune(12).lpf(1200).room(0.5)`

## Tempo
- `.cpm(N)` — cycles per minute. Default ~60. For 90 BPM hip hop, use `.cpm(90)`.
- Do NOT use `setbpm` — it does not exist.

## Genre Pattern Library

### Hip Hop (cpm: 85-95)
```
stack(
  s("bd ~ ~ ~ bd ~ ~ ~"),
  s("~ ~ sd ~ ~ ~ sd ~"),
  s("hh*8").gain(0.35),
  s("~ ~ ~ ~ ~ ~ ~ cp").gain(0.5),
  note("<c2 c2 f2 g2>").s("sawtooth").lpf(300).gain(0.8)
).cpm(88).play()
```

### Lo-fi Hip Hop (cpm: 80-90)
```
stack(
  s("bd ~ [~ bd] ~"),
  s("~ sd ~ sd").gain(0.6),
  s("[hh hh] [hh hh] [hh hh] [hh ~]").gain(0.25),
  note("<[c3,e3,g3] [a2,c3,e3] [f2,a2,c3] [g2,b2,d3]>")
    .s("triangle").lpf(800).room(0.4).delay(0.2).gain(0.5)
).cpm(82).play()
```

### Jazz (cpm: 110-140)
```
stack(
  s("bd ~ ~ bd ~ ~ bd ~").gain(0.6),
  s("~ ~ sd ~ ~ ~ sd ~").gain(0.5),
  s("[hh hh hh] [hh hh hh] [hh hh hh] [hh hh hh]").gain(0.3),
  note("<[c3,e3,g3,b3] [d3,f3,a3,c4] [e3,g3,b3,d4] [a2,c3,e3,g3]>")
    .s("triangle").lpf(2000).room(0.3).gain(0.5),
  note("<c2 d2 e2 a1>").s("sawtooth").lpf(400).gain(0.6)
).cpm(130).play()
```

### Techno (cpm: 125-140)
```
stack(
  s("bd bd bd bd"),
  s("~ cp ~ cp").gain(0.6),
  s("hh*8").gain(0.3),
  s("~ ~ ~ ~ ~ ~ [hh ~] ~").gain(0.5),
  note("c1 ~ c1 ~").s("sine").lpf(200).gain(0.9),
  note("c3 ~ ~ c3 ~ ~ c3 ~")
    .s("sawtooth").lpf(1500).resonance(15)
    .every(4, fast(2)).gain(0.4)
).cpm(132).play()
```

### Drum & Bass (cpm: 85-90, equivalent to ~170 BPM)
```
stack(
  s("bd ~ ~ ~ bd ~ ~ [~ bd]"),
  s("~ ~ sd ~ ~ ~ sd ~"),
  s("hh*16").gain(0.2),
  s("~ ~ ~ ~ [~ cp] ~ ~ ~").gain(0.5),
  note("<c2 [c2 ~] [~ c2] c2>").s("sawtooth").lpf(350).gain(0.8),
  note("c4 ~ eb4 ~ g4 ~ f4 ~")
    .s("sawtooth").lpf(2000).delay(0.3).delaytime(0.125).gain(0.35)
).cpm(87).play()
```

### Ambient (cpm: 50-70)
```
stack(
  note("<[c3,e3,g3,b3] [a2,c3,e3,g3] [f2,a2,c3,e3] [g2,b2,d3,f3]>")
    .s("triangle").room(0.8).size(0.9).lpf(1200)
    .attack(0.5).release(1).gain(0.4),
  note("<c4 e4 g4 b4>/2")
    .s("sine").room(0.9).delay(0.5).delaytime(0.25).delayfeedback(0.6)
    .gain(0.2),
  note("c1").s("sine").gain(0.5).lpf(100)
).cpm(55).play()
```

### Reggae / Dub (cpm: 70-80)
```
stack(
  s("[~ bd] ~ [~ bd] ~"),
  s("~ sd ~ sd"),
  s("hh*4").gain(0.3),
  note("~ <[c3,eb3,g3] [f2,ab2,c3] [g2,bb2,d3] [c3,eb3,g3]> ~ ~")
    .s("square").lpf(600).gain(0.5),
  note("<c2 f2 g2 c2>").s("sawtooth").lpf(300)
    .delay(0.4).delaytime(0.188).delayfeedback(0.5).gain(0.7)
).cpm(75).play()
```

### Bossa Nova (cpm: 130-145)
```
stack(
  s("[bd ~] [~ bd] [~ bd] [bd ~]"),
  s("~ [sd ~] ~ [sd ~]").gain(0.5),
  s("[~ hh] [hh ~] [~ hh] [hh hh]").gain(0.35),
  note("<[c3,e3,g3] [d3,f3,a3] [e3,g3,b3] [a2,c3,e3]>")
    .s("triangle").lpf(1500).room(0.3).gain(0.45),
  note("<c2 d2 e2 a1>").s("sawtooth").lpf(350).gain(0.6)
).cpm(135).play()
```

### House (cpm: 120-130)
```
stack(
  s("bd ~ bd ~"),
  s("~ ~ ~ ~ ~ ~ ~ cp"),
  s("hh*4").gain(0.3),
  s("~ [~ hh] ~ [~ hh]").gain(0.4),
  note("<[c3,e3,g3] [f3,a3,c4] [g3,b3,d4] [e3,g3,b3]>")
    .s("sawtooth").lpf(1200).resonance(8).gain(0.4),
  note("c1").s("sine").gain(0.7).lpf(150)
).cpm(124).play()
```

### Trap (cpm: 70-80)
```
stack(
  s("bd ~ ~ ~ ~ ~ bd ~"),
  s("~ ~ ~ ~ sd ~ ~ ~"),
  s("[hh hh hh hh] [hh hh hh hh] [hh*8] [hh hh hh hh]").gain(0.25),
  s("~ ~ ~ ~ ~ ~ ~ [cp ~]").gain(0.6),
  note("<c1 ~ ~ ~ c1 ~ ~ ~>").s("sine").lpf(120).gain(0.9),
  note("~ ~ ~ ~ ~ ~ c3 ~").s("sawtooth").lpf(600).gain(0.5)
).cpm(72).play()
```

### Funk (cpm: 100-115)
```
stack(
  s("bd ~ [~ bd] ~ bd ~ [~ bd] ~"),
  s("~ ~ sd ~ ~ ~ sd [~ sd]"),
  s("hh*8").gain(0.3),
  s("[~ cp] ~ ~ ~ [~ cp] ~ ~ ~").gain(0.5),
  note("<c2 c2 f2 g2>").s("jvbass").lpf(800).gain(0.7),
  note("[~ c3] [~ e3] [~ g3] [~ c4]")
    .s("square").lpf(1000).gain(0.35)
).cpm(108).play()
```

### Chiptune / 8-bit (cpm: 130-160)
```
stack(
  s("bd ~ bd ~"),
  s("~ sd ~ sd"),
  s("hh*4").gain(0.3),
  note("c4 e4 g4 c5 b4 g4 e4 c4")
    .s("square").lpf(3000).gain(0.35),
  note("<c3 f3 g3 c3>")
    .s("square").lpf(600).crush(4).gain(0.5),
  note("<c2 f2 g2 c2>").s("square").lpf(400).gain(0.6)
).cpm(145).play()
```

### Minimal / Glitch (cpm: 120-135)
```
stack(
  s("bd ~ ~ ~ bd ~ ~ ~"),
  s("~ ~ sd? ~ ~ ~ sd? ~").gain(0.5),
  s("hh*8").sometimes(fast(2)).gain(0.2),
  note("c3 ~ ~ e3 ~ ~ g3 ~")
    .s("sine").delay(0.4).delaytime(0.125)
    .delayfeedback(0.4).gain(0.4),
  note("c1 ~ ~ ~").s("sine").gain(0.6)
).cpm(128).play()
```

## Rhythm Templates

### Common Time Signatures
- 4/4 (default): `s("bd sd bd sd")` — 4 steps per cycle
- 3/4 waltz: `s("bd sd sd")` — 3 steps per cycle
- 6/8 compound: `s("[bd ~ ~] [~ ~ bd] [~ bd ~] [~ ~ ~]")` or `s("bd(2,6)")`
- 5/4 odd meter: `s("bd sd bd sd bd")`
- 7/8 odd meter: `s("[bd sd bd] [sd bd sd bd]")`

### Euclidean Rhythms
Euclidean patterns distribute N pulses evenly across M steps:
- `s("bd(3,8)")` — 3 hits in 8 steps (Cuban tresillo: x..x..x.)
- `s("bd(5,8)")` — 5 hits in 8 steps (Cuban cinquillo: x.xx.xx.)
- `s("bd(4,7)")` — 4 in 7 (Turkish rhythm)
- `s("bd(5,12)")` — 5 in 12
- `s("bd(7,16)")` — 7 in 16 (West African bell pattern)
- `s("bd(3,8,2)")` — 3rd arg rotates the pattern by 2 steps

### Syncopation Recipes
**Off-beat emphasis:**
```
s("~ bd ~ bd")  // off-beat kicks
s("[~ sd] ~ [~ sd] ~")  // syncopated snare
```
**Anticipated beats:**
```
s("bd ~ ~ bd ~ ~ bd ~")  // kick anticipates beat 3
```
**Ghost notes:**
```
stack(
  s("bd ~ ~ ~ bd ~ ~ ~"),
  s("~ ~ sd ~ ~ ~ sd ~"),
  s("[~ sd] ~ [~ sd] ~").gain(0.2)  // ghost snares
)
```

### Polyrhythm Techniques
```
stack(
  s("bd bd bd"),          // 3 beats per cycle
  s("sd sd sd sd")        // 4 beats per cycle — creates 3:4 polyrhythm
)
```
```
stack(
  s("hh(3,8)"),           // Euclidean 3-over-8
  s("cp(5,8)")            // Euclidean 5-over-8
)
```

## Effects Recipes

### Lo-fi Sound
```
.lpf(800).crush(12).room(0.3).gain(0.5)
```
Warm, degraded quality. Good for lo-fi hip hop pads and keys.

### Spacey / Ethereal
```
.room(0.8).size(0.9).delay(0.5).delaytime(0.25).delayfeedback(0.5).lpf(2000)
```
Big reverb + long delay. Good for ambient pads and sparse melodies.

### Aggressive / Distorted
```
.shape(0.7).lpf(3000).resonance(20).gain(0.6)
```
Waveshaping distortion with resonant filter. Good for acid bass and aggressive leads.

### Warm Analog
```
.lpf(1200).resonance(5).room(0.2).gain(0.6)
```
Gentle filter with slight resonance and room. Good for warm pads and bass.

### Dub Echo
```
.delay(0.5).delaytime(0.188).delayfeedback(0.6).room(0.3).hpf(200)
```
Classic dub delay with high-pass to keep it clean. Good for skank chords and melodica.

### Acid Squelch
```
.s("sawtooth").lpf(400).resonance(25).every(2, x => x.lpf(2000))
```
Resonant filter sweep. Alternates between closed and open filter.

### Chiptune / Retro
```
.s("square").crush(4).lpf(3000).gain(0.4)
```
Bitcrushed square wave for 8-bit sounds.

### Underwater / Muffled
```
.lpf(400).room(0.6).gain(0.4)
```
Heavy low-pass for submerged, distant sounds.

## Composition Strategies

### Layering Patterns
Build compositions by stacking complementary layers:
1. **Foundation**: Kick + bass (share the low end — don't overlap)
2. **Groove**: Snare/clap + hi-hats (define the feel)
3. **Harmony**: Chords/pads (fill the mid-range)
4. **Melody**: Lead line or arpeggios (sits on top)
5. **Texture**: Effects, noise hits, ghost notes (add interest)

### Creating Variation with `every()`
```
.every(4, fast(2))          // double speed every 4 cycles
.every(3, rev)              // reverse every 3 cycles
.every(8, add(note(12)))    // octave up every 8 cycles
.every(4, x => x.lpf(400)) // filter sweep every 4 cycles
```

### Building Tension and Release
```
// Tension: add layers, increase density
s("hh*4").every(4, fast(2))   // hi-hats get busier

// Release: strip back, simplify
.sometimes(x => x.gain(0))    // random dropouts

// Filter builds:
.lpf(sine.range(200, 4000).slow(8))  // sweeping filter (if supported)
```

### Call and Response
```
stack(
  note("c4 e4 g4 ~").s("sawtooth"),   // call
  note("~ ~ ~ c5").s("triangle")       // response
)
```

### Rhythmic Displacement with `off()`
```
note("c3 e3 g3 b3")
  .s("sawtooth")
  .off(0.125, add(note(12)))  // offset copy an octave up
  .lpf(1200)
```

### Using `jux()` for Stereo Width
```
s("bd sd [~ bd] sd")
  .jux(rev)  // original on left, reversed on right
```

### Progressive Composition
Start minimal, add complexity:
```
// Cycle 1-4: just drums
// Cycle 5-8: add bass
// Cycle 9+: full arrangement
```
Use `every()` and `sometimes()` to create this evolution within a single pattern.

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

Complex layered piece with effects:
```
stack(
  s("bd [~ bd] sd [~ bd]"),
  s("[~ cp] ~ [~ cp] ~").gain(0.5),
  s("hh*8").gain(0.2).sometimes(fast(2)),
  note("<c2 f2 g2 eb2>").s("sawtooth").lpf(300).gain(0.8),
  note("<[c3,e3,g3] [f3,a3,c4] [g3,b3,d4] [eb3,g3,bb3]>")
    .s("triangle").lpf(1500).room(0.4).gain(0.4),
  note("c4 ~ e4 ~ g4 ~ b4 ~")
    .s("sawtooth").lpf(2000).delay(0.3).delaytime(0.125)
    .gain(0.3).jux(rev)
).cpm(95).play()
```
"""
