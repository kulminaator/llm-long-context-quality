# Finding People — puzzle generator

A tool to generate long, careful chain-of-thought texts for LLMs: a crowd of
people in a square, and a multi-day log of every real move. The task is to
track who ends up where — with no numbers to lean on.

The output is deliberately free of any real measurement. There is no grid
size, no coordinate, no distance in metres or blocks anywhere in
`puzzle.txt` or `question.txt`. The only digits in the whole puzzle are
clock times and the warden's guesses in units that never measure anything
(frog-leaps, crow-hops, …). Everything is relative language:

- opening placements ("Bob stood directly north of Alice and directly west of
  Carol", "Quinn stood as far south of Wendy as Rosa is west of the fountain",
  "Gerald stood exactly halfway between Yusuf and Quinn", "Uma took the spot
  opposite Gerald, fountain exactly between them", "Ivan stood on the east
  edge, level with Wendy");
- moves (aligned walks, diagonal walks, as-far-of-the-fountain walks,
  mirror walks, halfway moves, opposite moves, swaps, walks to an edge);
- a few "walked far enough" moves that only fix an interval (the new spot is
  strictly between two people on the walked line) — the exact stop is pinned
  by a later move;
- after every move, what the mover could see from the new spot (11 sighting
  phrasings, always true statements).

The log says up front that it records **every** actual change of position,
and interleaved decoys — dropped planned walks, misread crowdings, old maps,
next-day programme items — change nothing.

The final question asks which people stand strictly inside the axis-aligned
square whose NW and SE corners are two named people's final positions (chosen
so that 5–8 people qualify), plus a relational spot-check: where one person
stood relative to the fountain and relative to one other person, using the
eight directions.

The math is deliberately tiny and lives only inside the program: float
positions on a 0–100 grid, a few arithmetic placements, and an *exposure
record* — for every person, per coordinate, a marker of whether the text
emitted so far exposes that coordinate exactly. Every event record carries
what its sentence exposes (a pinned axis, a range-only "open" axis, or a
swap), and references are only drawn from exposed coordinates, so every
exact statement stays exact. The exact coordinates never appear in the
puzzle; they appear only in `solution.txt`'s hidden verification section.

## Usage

Pick a folder (16k / 32k / 64k / 128k — target token counts), feed
`puzzle.txt` + `question.txt` to the LLM (`guide.txt` is the solver brief:
read, reason, no code), then compare the answer with `solution.txt`.

Generate a new one:

```sh
python3 generator.py --tokens 16000 --seed 105 --out 16k
python3 unit_tests.py        # the verification suite
```

`generator.py` writes `puzzle.txt`, `question.txt`, `solution.txt` (the
answers, the exact positions on the hidden grid, and a full move ledger with
the state after every step). If a seed fails to build a valid puzzle, the
next seed is tried; the seed actually used is printed and recorded in the
solution.

## Verification

`unit_tests.py` (zero dependencies, `python3 unit_tests.py`) is the
verification layer:

- every opening/move/sighting sentence is parsed and its claimed position
  re-derived from the reference positions — it must equal the state the
  sentence was generated from;
- the knownness transitions are pinned exactly: "far" walks open the walked
  axis; aligned/as-far/mirror/edge walks pin only the walked axis (an open
  preserved axis must *stay* open); diagonal/halfway/opposite pin both;
  swaps exchange knownness;
- the closing sequence must pin every coordinate left open;
- a full generation must be self-consistent: unique in-arena positions, the
  event stream must reproduce the final state, the Q1/Q2 answers must match
  the final state, and no digit may appear anywhere except in clock times
  and fake-unit counts;
- the exposure markers are checked against the text itself: every emitted
  sentence is re-read and classified (which axis it pins, which axis it
  leaves a mere range, or that it is a swap), and the generator's record
  and its per-person markers must change exactly as the sentence exposes —
  nothing more, nothing less — and by the end every coordinate must be
  marked exposed.
