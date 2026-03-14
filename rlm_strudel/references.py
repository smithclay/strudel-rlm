"""Curated reference compositions tagged with genre, tempo, and key techniques.

Provides select_references() to match user queries to the most relevant examples,
and format_references_for_prompt() to render them for inclusion in composer prompts.
"""

REFERENCES: list[dict] = [
    # 1. Lo-fi Chill Beat
    {
        "name": "Lo-fi Chill Beat",
        "genre_tags": ["lo-fi", "hip hop", "chill", "ambient"],
        "tempo": "80-90 cpm",
        "techniques": ["stack", "lpf", "room", "delay", "gain", "subdivision"],
        "code": """\
stack(
  s("bd ~ [~ bd] ~"),
  s("~ sd ~ sd").gain(0.6),
  s("[hh hh] [hh hh] [hh hh] [hh ~]").gain(0.25),
  note("<[c3,e3,g3] [a2,c3,e3] [f2,a2,c3] [g2,b2,d3]>")
    .s("triangle").lpf(800).room(0.4).delay(0.2).gain(0.5),
  note("<c2 c2 f2 g2>").s("sine").lpf(200).gain(0.6)
).cpm(82).play()""",
        "annotation": (
            "Classic lo-fi hip hop beat. Lazy swing kick with ghost note, "
            "soft triangle chords filtered low with reverb and delay for warmth, "
            "sine sub-bass. Hi-hats use subdivision for a loose shuffle feel."
        ),
    },
    # 2. Dark Synth Atmosphere
    {
        "name": "Dark Synth Atmosphere",
        "genre_tags": ["dark", "synth", "ambient", "cinematic", "industrial"],
        "tempo": "60-70 cpm",
        "techniques": ["stack", "lpf", "hpf", "shape", "room", "size", "delay", "slow"],
        "code": """\
stack(
  s("bd ~ ~ ~ bd ~ ~ ~").gain(0.8),
  s("~ ~ ~ ~ ~ ~ sd ~").room(0.5).gain(0.5),
  s("hh*4").gain(0.15).lpf(600),
  note("<[c2,eb2,g2] [bb1,d2,f2] [ab1,c2,eb2] [g1,bb1,d2]>")
    .s("sawtooth").lpf(500).resonance(15).shape(0.4)
    .room(0.6).size(0.8).gain(0.5),
  note("c1").s("sine").lpf(100).gain(0.7),
  note("c4 ~ eb4 ~ g4 ~ f4 ~").s("sawtooth")
    .lpf(1200).delay(0.4).delaytime(0.25).delayfeedback(0.5)
    .gain(0.2)
).cpm(65).play()""",
        "annotation": (
            "Dark cinematic atmosphere. Minor chords with sawtooth waveshaping "
            "for grit, sparse kick pattern, heavy reverb and delay on the lead "
            "melody, deep sine sub-bass. Restrained hi-hats filtered low."
        ),
    },
    # 3. Driving Techno
    {
        "name": "Driving Techno",
        "genre_tags": ["techno", "electronic", "dance", "club", "four-on-the-floor"],
        "tempo": "130-138 cpm",
        "techniques": ["stack", "lpf", "resonance", "every", "fast", "gain"],
        "code": """\
stack(
  s("bd bd bd bd"),
  s("~ cp ~ cp").gain(0.6),
  s("hh*8").gain(0.3),
  s("~ ~ ~ ~ ~ ~ [oh ~] ~").gain(0.4),
  note("c1 ~ c1 ~").s("sine").lpf(200).gain(0.9),
  note("c3 ~ ~ c3 ~ ~ c3 ~")
    .s("sawtooth").lpf(1500).resonance(15)
    .every(4, fast(2)).gain(0.4)
).cpm(134).play()""",
        "annotation": (
            "Four-on-the-floor techno with claps on 2 and 4, relentless hi-hats, "
            "sine sub-bass, and a resonant sawtooth stab that doubles speed every "
            "4 cycles for tension. Open hat accent on the off-beat."
        ),
    },
    # 4. Euphoric Trance Arp
    {
        "name": "Euphoric Trance Arp",
        "genre_tags": ["trance", "euphoric", "electronic", "uplifting", "dance"],
        "tempo": "136-142 cpm",
        "techniques": ["stack", "arp", "lpf", "room", "delay", "every", "add", "note"],
        "code": """\
stack(
  s("bd bd bd bd"),
  s("~ cp ~ cp").gain(0.5),
  s("hh*8").gain(0.25),
  s("~ ~ ~ ~ oh ~ ~ ~").gain(0.3),
  note("<[c3,e3,g3,b3] [a2,c3,e3,a3] [f2,a2,c3,f3] [g2,b2,d3,g3]>")
    .s("sawtooth").arp("up").lpf(2500)
    .room(0.3).delay(0.3).delaytime(0.125).delayfeedback(0.4)
    .every(8, add(note(12))).gain(0.4),
  note("<c2 a1 f1 g1>").s("sawtooth").lpf(300).gain(0.7),
  note("<c4 e4 g4 b4>/2").s("triangle").room(0.5).gain(0.2)
).cpm(138).play()""",
        "annotation": (
            "Uplifting trance with arpeggiated sawtooth chords sweeping upward, "
            "four-on-the-floor kick, sawtooth bass, airy triangle pad. The arp "
            "jumps an octave every 8 cycles for a euphoric lift. Delay adds motion."
        ),
    },
    # 5. Jazz Quartet
    {
        "name": "Jazz Quartet",
        "genre_tags": ["jazz", "swing", "mellow", "sophisticated"],
        "tempo": "120-140 cpm",
        "techniques": ["stack", "lpf", "room", "gain", "triplet subdivision"],
        "code": """\
stack(
  s("bd ~ ~ bd ~ ~ bd ~").gain(0.6),
  s("~ ~ sd ~ ~ ~ sd ~").gain(0.5),
  s("[hh hh hh] [hh hh hh] [hh hh hh] [hh hh hh]").gain(0.3),
  s("~ rd ~ ~ ~ rd ~ ~").gain(0.25),
  note("<[c3,e3,g3,b3] [d3,f3,a3,c4] [e3,g3,b3,d4] [a2,c3,e3,g3]>")
    .s("triangle").lpf(2000).room(0.3).gain(0.5),
  note("<c2 d2 e2 a1>").s("sawtooth").lpf(400).gain(0.6)
).cpm(130).play()""",
        "annotation": (
            "Jazz quartet voicing with 7th chords on triangle for a warm piano-like "
            "tone, walking bass on sawtooth, triplet hi-hats for swing feel, "
            "ride cymbal accents, and loose kick placement."
        ),
    },
    # 6. Drum & Bass Roller
    {
        "name": "Drum & Bass Roller",
        "genre_tags": ["drum and bass", "dnb", "jungle", "fast", "breakbeat"],
        "tempo": "85-90 cpm (170-180 BPM equivalent)",
        "techniques": ["stack", "lpf", "delay", "delaytime", "gain", "fast subdivision"],
        "code": """\
stack(
  s("bd ~ ~ ~ bd ~ ~ [~ bd]"),
  s("~ ~ sd ~ ~ ~ sd ~"),
  s("hh*16").gain(0.2),
  s("~ ~ ~ ~ [~ cp] ~ ~ ~").gain(0.5),
  note("<c2 [c2 ~] [~ c2] c2>").s("sawtooth").lpf(350).gain(0.8),
  note("c4 ~ eb4 ~ g4 ~ f4 ~")
    .s("sawtooth").lpf(2000).delay(0.3).delaytime(0.125).gain(0.35)
).cpm(87).play()""",
        "annotation": (
            "Drum & bass at 87 cpm (174 BPM equivalent). Breakbeat kick pattern "
            "with anticipated last hit, fast 16th hi-hats, sawtooth bass with "
            "rhythmic variation, and a delayed minor lead melody."
        ),
    },
    # 7. Dub Reggae Skank
    {
        "name": "Dub Reggae Skank",
        "genre_tags": ["reggae", "dub", "ska", "chill"],
        "tempo": "70-80 cpm",
        "techniques": ["stack", "lpf", "delay", "delaytime", "delayfeedback", "room"],
        "code": """\
stack(
  s("[~ bd] ~ [~ bd] ~"),
  s("~ sd ~ sd"),
  s("hh*4").gain(0.3),
  s("~ ~ ~ ~ ~ ~ ~ rim").gain(0.4),
  note("~ <[c3,eb3,g3] [f2,ab2,c3] [g2,bb2,d3] [c3,eb3,g3]> ~ ~")
    .s("square").lpf(600).gain(0.5),
  note("<c2 f2 g2 c2>").s("sawtooth").lpf(300)
    .delay(0.4).delaytime(0.188).delayfeedback(0.5).gain(0.7)
).cpm(75).play()""",
        "annotation": (
            "Dub reggae with offbeat kicks (skank rhythm), minor chords on square "
            "wave with low-pass filter, heavy dub delay on the bass for that classic "
            "echo, rimshot accent. Steady one-drop snare."
        ),
    },
    # 8. Funky Groove
    {
        "name": "Funky Groove",
        "genre_tags": ["funk", "groove", "soul", "disco"],
        "tempo": "100-115 cpm",
        "techniques": ["stack", "lpf", "gain", "syncopation", "jvbass"],
        "code": """\
stack(
  s("bd ~ [~ bd] ~ bd ~ [~ bd] ~"),
  s("~ ~ sd ~ ~ ~ sd [~ sd]"),
  s("hh*8").gain(0.3),
  s("[~ cp] ~ ~ ~ [~ cp] ~ ~ ~").gain(0.5),
  note("<c2 c2 f2 g2>").s("jvbass").lpf(800).gain(0.7),
  note("[~ c3] [~ e3] [~ g3] [~ c4]")
    .s("square").lpf(1000).gain(0.35)
).cpm(108).play()""",
        "annotation": (
            "Funky groove with syncopated kick and snare ghost note, jvbass for "
            "a punchy bass line, offbeat square wave stabs climbing up, "
            "clap accents on the and-of-one. Hi-hats keep it tight at 8ths."
        ),
    },
    # 9. Bossa Nova
    {
        "name": "Bossa Nova",
        "genre_tags": ["bossa nova", "latin", "brazilian", "mellow", "jazz"],
        "tempo": "130-145 cpm",
        "techniques": ["stack", "lpf", "room", "gain", "bossa rhythm"],
        "code": """\
stack(
  s("[bd ~] [~ bd] [~ bd] [bd ~]"),
  s("~ [sd ~] ~ [sd ~]").gain(0.5),
  s("[~ hh] [hh ~] [~ hh] [hh hh]").gain(0.35),
  s("~ ~ rim ~").gain(0.3),
  note("<[c3,e3,g3] [d3,f3,a3] [e3,g3,b3] [a2,c3,e3]>")
    .s("triangle").lpf(1500).room(0.3).gain(0.45),
  note("<c2 d2 e2 a1>").s("sawtooth").lpf(350).gain(0.6)
).cpm(135).play()""",
        "annotation": (
            "Bossa nova with the classic syncopated kick pattern, brushed snare "
            "feel via soft gain, off-beat hi-hats, triangle chords for warm keys, "
            "walking bass. Rimshot adds a subtle cross-stick accent."
        ),
    },
    # 10. Trap Banger
    {
        "name": "Trap Banger",
        "genre_tags": ["trap", "hip hop", "808", "hard"],
        "tempo": "70-80 cpm",
        "techniques": ["stack", "lpf", "gain", "fast hi-hats", "808 bass"],
        "code": """\
stack(
  s("bd ~ ~ ~ ~ ~ bd ~"),
  s("~ ~ ~ ~ sd ~ ~ ~"),
  s("[hh hh hh hh] [hh hh hh hh] [hh*8] [hh hh hh hh]").gain(0.25),
  s("~ ~ ~ ~ ~ ~ ~ [cp ~]").gain(0.6),
  note("<c1 ~ ~ ~ c1 ~ ~ ~>").s("sine").lpf(120).gain(0.9),
  note("~ ~ ~ ~ ~ ~ c3 ~").s("sawtooth").lpf(600).gain(0.5)
).cpm(72).play()""",
        "annotation": (
            "Hard trap beat with sparse kick and snare hits, rolling hi-hats that "
            "accelerate to 32nds in the third beat, deep 808-style sine sub-bass, "
            "clap accent at the end. Sawtooth stab for a dark melodic hit."
        ),
    },
    # 11. House Groover
    {
        "name": "House Groover",
        "genre_tags": ["house", "deep house", "dance", "club", "electronic"],
        "tempo": "120-128 cpm",
        "techniques": ["stack", "lpf", "resonance", "gain", "off-beat hats"],
        "code": """\
stack(
  s("bd ~ bd ~"),
  s("~ ~ ~ ~ ~ ~ ~ cp"),
  s("hh*4").gain(0.3),
  s("~ [~ oh] ~ [~ oh]").gain(0.35),
  note("<[c3,e3,g3] [f3,a3,c4] [g3,b3,d4] [e3,g3,b3]>")
    .s("sawtooth").lpf(1200).resonance(8).gain(0.4),
  note("c1").s("sine").gain(0.7).lpf(150)
).cpm(124).play()""",
        "annotation": (
            "Deep house groove with 4/4 kick, off-beat open hats for shuffle, "
            "clap on the last 8th note, sawtooth chord stabs with resonant filter, "
            "and a sustained sine sub-bass for low-end weight."
        ),
    },
    # 12. Chiptune Adventure
    {
        "name": "Chiptune Adventure",
        "genre_tags": ["chiptune", "8-bit", "retro", "game", "pixel"],
        "tempo": "140-155 cpm",
        "techniques": ["stack", "crush", "lpf", "square wave", "gain"],
        "code": """\
stack(
  s("bd ~ bd ~"),
  s("~ sd ~ sd"),
  s("hh*4").gain(0.3),
  note("c4 e4 g4 c5 b4 g4 e4 c4")
    .s("square").lpf(3000).gain(0.35),
  note("<c3 f3 g3 c3>")
    .s("square").lpf(600).crush(4).gain(0.5),
  note("<c2 f2 g2 c2>").s("square").lpf(400).gain(0.6)
).cpm(145).play()""",
        "annotation": (
            "8-bit chiptune with all square waves for authentic retro sound. "
            "Fast arpeggio melody, bitcrushed mid-range harmony, square bass. "
            "Simple 4/4 drums keep the energy high for a game-like feel."
        ),
    },
    # 13. Minimal Glitch
    {
        "name": "Minimal Glitch",
        "genre_tags": ["minimal", "glitch", "experimental", "electronic", "micro"],
        "tempo": "120-132 cpm",
        "techniques": ["stack", "sometimes", "fast", "delay", "delayfeedback", "random"],
        "code": """\
stack(
  s("bd ~ ~ ~ bd ~ ~ ~"),
  s("~ ~ sd? ~ ~ ~ sd? ~").gain(0.5),
  s("hh*8").sometimes(fast(2)).gain(0.2),
  s("~ ~ ~ rim? ~ ~ ~ ~").gain(0.3),
  note("c3 ~ ~ e3 ~ ~ g3 ~")
    .s("sine").delay(0.4).delaytime(0.125)
    .delayfeedback(0.4).gain(0.4),
  note("c1 ~ ~ ~").s("sine").gain(0.6)
).cpm(128).play()""",
        "annotation": (
            "Minimal glitch with sparse elements and randomness. Snare and rimshot "
            "use ? for 50% probability, hi-hats sometimes double in speed. "
            "Sine melody with delay creates micro-textures. Very stripped back."
        ),
    },
    # 14. Waltz in Three
    {
        "name": "Waltz in Three",
        "genre_tags": ["classical", "waltz", "3/4", "elegant", "cinematic"],
        "tempo": "90-110 cpm",
        "techniques": ["stack", "3/4 time", "room", "lpf", "attack", "release"],
        "code": """\
stack(
  s("bd ~ ~"),
  s("~ sd sd").gain(0.4),
  s("~ hh hh").gain(0.25),
  note("<[c3,e3,g3] [f3,a3,c4] [g3,b3,d4] [e3,g3,b3]>")
    .s("triangle").lpf(1800).room(0.4).attack(0.1).release(0.4).gain(0.45),
  note("<c2 f2 g2 e2>").s("sawtooth").lpf(400).gain(0.6),
  note("<c4 ~ e4 ~ g4 ~ e4 ~>/2")
    .s("triangle").room(0.5).delay(0.2).gain(0.25)
).cpm(100).play()""",
        "annotation": (
            "Elegant waltz in 3/4 time. Kick on beat 1, snare on beats 2 and 3 "
            "(oom-pah-pah). Triangle chords with attack/release shaping for a "
            "gentle pad feel, sawtooth bass, slow melodic line with reverb."
        ),
    },
    # 15. Ambient Dreamscape
    {
        "name": "Ambient Dreamscape",
        "genre_tags": ["ambient", "dream", "ethereal", "atmospheric", "meditation"],
        "tempo": "50-60 cpm",
        "techniques": ["stack", "room", "size", "delay", "delayfeedback", "attack", "release", "slow"],
        "code": """\
stack(
  note("<[c3,e3,g3,b3] [a2,c3,e3,g3] [f2,a2,c3,e3] [g2,b2,d3,f3]>")
    .s("triangle").room(0.8).size(0.9).lpf(1200)
    .attack(0.5).release(1).gain(0.4),
  note("<c4 e4 g4 b4>/2")
    .s("sine").room(0.9).delay(0.5).delaytime(0.25).delayfeedback(0.6)
    .gain(0.2),
  note("c1").s("sine").gain(0.5).lpf(100),
  s("~ ~ ~ ~ ~ ~ ~ noise").gain(0.05).room(0.9)
).cpm(55).play()""",
        "annotation": (
            "Slow ambient dreamscape. Lush 7th chords on triangle with long "
            "attack/release and huge reverb, sine melody that moves at half speed "
            "with heavy delay, sub-bass drone, and a barely audible noise texture "
            "with reverb for atmosphere."
        ),
    },
    # 16. Arranged Lo-fi Song
    {
        "name": "Arranged Lo-fi Song",
        "genre_tags": ["lo-fi", "hip hop", "chill", "arranged", "song structure"],
        "tempo": "82 cpm",
        "techniques": ["arrange", "const", "stack", "lpf", "room", "delay", "song structure"],
        "code": """\
const intro = stack(
  s("bd ~ ~ ~"),
  s("hh*4").gain(0.15),
  note("<[c3,e3,g3] [a2,c3,e3]>")
    .s("triangle").lpf(600).room(0.5).gain(0.3)
)

const verse = stack(
  s("bd ~ [~ bd] ~"),
  s("~ sd ~ sd").gain(0.6),
  s("[hh hh] [hh hh] [hh hh] [hh ~]").gain(0.25),
  note("<[c3,e3,g3] [a2,c3,e3] [f2,a2,c3] [g2,b2,d3]>")
    .s("triangle").lpf(800).room(0.4).delay(0.2).gain(0.5),
  note("<c2 c2 f2 g2>").s("sine").lpf(200).gain(0.6)
)

const chorus = stack(
  s("bd ~ [~ bd] ~"),
  s("~ sd ~ sd").gain(0.7),
  s("hh*8").gain(0.2),
  s("~ ~ ~ ~ ~ ~ ~ cp").gain(0.4),
  note("<[c3,e3,g3,b3] [a2,c3,e3,g3] [f2,a2,c3,e3] [g2,b2,d3,f3]>")
    .s("triangle").lpf(1200).room(0.5).delay(0.3).gain(0.5),
  note("<c2 a1 f1 g1>").s("sine").lpf(200).gain(0.7)
)

const outro = stack(
  s("bd ~ ~ ~"),
  note("<[c3,e3,g3]>").s("triangle").lpf(600).room(0.7).gain(0.25)
)

arrange(
  [4, intro],
  [8, verse],
  [8, chorus],
  [8, verse],
  [8, chorus],
  [4, outro]
).cpm(82).play()""",
        "annotation": (
            "Full lo-fi song using arrange() for structure. Intro is sparse with "
            "just kick, hats, and filtered chords. Verse adds the full beat with "
            "ghost kicks and delay chords. Chorus opens up the filter, adds clap "
            "and 7th chords. Outro strips back to a reverb-soaked ending."
        ),
    },
    # 17. Arranged Techno Track
    {
        "name": "Arranged Techno Track",
        "genre_tags": ["techno", "electronic", "dance", "club", "arranged", "song structure"],
        "tempo": "132 cpm",
        "techniques": ["arrange", "const", "stack", "lpf", "resonance", "every", "fast", "song structure"],
        "code": """\
const intro = stack(
  s("bd bd bd bd"),
  s("hh*4").gain(0.2),
  note("c1").s("sine").lpf(100).gain(0.5)
)

const buildup = stack(
  s("bd bd bd bd"),
  s("~ cp ~ cp").gain(0.4),
  s("hh*8").gain(0.25),
  note("c1 ~ c1 ~").s("sine").lpf(150).gain(0.7),
  note("c3 ~ ~ ~").s("sawtooth").lpf(800).resonance(10).gain(0.3)
)

const drop = stack(
  s("bd bd bd bd"),
  s("~ cp ~ cp").gain(0.6),
  s("hh*8").gain(0.3),
  s("~ ~ ~ ~ ~ ~ [oh ~] ~").gain(0.4),
  note("c1 ~ c1 ~").s("sine").lpf(200).gain(0.9),
  note("c3 ~ ~ c3 ~ ~ c3 ~")
    .s("sawtooth").lpf(1500).resonance(15)
    .every(4, fast(2)).gain(0.4)
)

const breakdown = stack(
  s("~ ~ ~ ~ bd ~ ~ ~").gain(0.5),
  s("hh*4").gain(0.15),
  note("<[c3,eb3,g3] [ab2,c3,eb3]>")
    .s("sawtooth").lpf(600).room(0.5).gain(0.3),
  note("c1").s("sine").lpf(100).gain(0.4)
)

const outro = stack(
  s("bd bd bd bd"),
  s("hh*4").gain(0.15),
  note("c1").s("sine").lpf(100).gain(0.4)
)

arrange(
  [4, intro],
  [8, buildup],
  [16, drop],
  [8, breakdown],
  [16, drop],
  [4, outro]
).cpm(132).play()""",
        "annotation": (
            "Full techno track with arrange(). Intro: just kick, hats, and sub. "
            "Buildup: adds clap, faster hats, and a filtered stab. Drop: full "
            "energy with resonant sawtooth that doubles speed every 4 bars, open hat. "
            "Breakdown: strips to pads and sparse kick. Second drop, then outro."
        ),
    },
    # 18. Bonus: Acid House
    {
        "name": "Acid House Squelch",
        "genre_tags": ["acid", "house", "electronic", "dance", "club", "303"],
        "tempo": "124-130 cpm",
        "techniques": ["stack", "lpf", "resonance", "every", "gain"],
        "code": """\
stack(
  s("bd bd bd bd"),
  s("~ ~ ~ ~ ~ ~ ~ cp").gain(0.5),
  s("hh*8").gain(0.25),
  s("~ [~ oh] ~ [~ oh]").gain(0.3),
  note("c2 c2 [c2 c3] c2 c2 [c2 eb2] c2 c2")
    .s("sawtooth").lpf(500).resonance(25)
    .every(2, x => x.lpf(2000)).gain(0.6),
  note("c1").s("sine").lpf(120).gain(0.7)
).cpm(126).play()""",
        "annotation": (
            "Acid house with the classic 303-style squelch. Sawtooth bass with "
            "high resonance alternates between closed and open filter every 2 cycles. "
            "Four-on-the-floor kick, off-beat open hats, clap on the last 8th."
        ),
    },
]


def select_references(query: str, n: int = 5) -> list[dict]:
    """Score each reference by counting genre_tag matches against query words.

    Returns the top N references sorted by match score (descending).
    Falls back to a diverse set of defaults if no tags match the query.
    """
    query_words = set(query.lower().split())

    scored = []
    for ref in REFERENCES:
        score = 0
        for tag in ref["genre_tags"]:
            # Each tag can be multi-word (e.g. "hip hop", "drum and bass")
            tag_words = set(tag.lower().split())
            # Count how many query words appear in this tag
            matches = len(query_words & tag_words)
            if matches > 0:
                score += matches
        scored.append((score, ref))

    # Sort by score descending, then by original order for stability
    scored.sort(key=lambda x: x[0], reverse=True)

    top = [ref for score, ref in scored[:n] if score > 0]

    if not top:
        # Fallback: return a diverse set spanning different genres
        diverse_indices = [0, 2, 5, 8, 14]  # lo-fi, techno, dnb, bossa, ambient
        fallback = [REFERENCES[i] for i in diverse_indices if i < len(REFERENCES)]
        return fallback[:n]

    return top


def format_references_for_prompt(refs: list[dict]) -> str:
    """Format selected references into a string for inclusion in the composer prompt."""
    parts = []
    for i, ref in enumerate(refs, 1):
        tags = ", ".join(ref["genre_tags"])
        techniques = ", ".join(ref["techniques"])
        parts.append(
            f"Reference {i}: {ref['name']}\n"
            f"Genre: {tags} | Tempo: {ref['tempo']}\n"
            f"Techniques: {techniques}\n"
            f"```\n{ref['code']}\n```\n"
            f"Notes: {ref['annotation']}"
        )
    return "\n\n".join(parts)
