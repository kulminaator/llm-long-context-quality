#!/usr/bin/env python3
"""Unit tests for the finding-people generator.

The contract under test: every sentence the generator emits must be TRUE
of the 2D state it was generated from.  Opening statements are checked
by re-deriving the claimed position from the sentence and the reference
positions; move statements are checked the same way against the
before/after states.  On top of that: the knownness transitions (which
coordinates the text pins down) must be exactly right, the pin pass must
close every open coordinate, and a full generation must be
self-consistent (unique positions, no leaking numbers, answers matching
the final state).

Run:  python3 unit_tests.py
"""
import math
import random
import re
import sys

import generator as G

# N is a bare alternation (one group when wrapped); CARD and D8 are
# non-capturing, so "({CARD})" in a pattern is exactly one group
N = G.NAME
CARD = r"(?:east|west|north|south)"
AXIS_OF = {"east": 0, "west": 0, "north": 1, "south": 1}
D8 = r"(?:north|south|east|west|northeast|northwest|southeast|southwest)"
UNIT_ALT = "|".join(G.UNITS)

FAILS = []


def run(name, fn):
    try:
        fn()
        print(f"PASS  {name}")
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print(f"FAIL  {name}: {e}")
        FAILS.append(name)


# ------------------------------------------------------------- the checks
# Each checker parses a SENTENCE (not generator internals) and
# re-derives the position it claims.  Equality with the real position is
# the test.


def check_open_anchor(p, s, pos):
    """The fountain line and the two edge-anchor lines."""
    m = re.fullmatch(
        rf"At the opening, {re.escape(p)} took the old fountain in the centre of the square\.", s)
    if m:
        assert pos[p] == (50.0, 50.0), s
        return
    m = re.fullmatch(
        rf"{re.escape(p)} stood on the (east|west) edge of the square, level with the fountain\.", s)
    if m:
        want = 100.0 if m.group(1) == "east" else 0.0
        assert math.isclose(pos[p][0], want) and math.isclose(pos[p][1], 50.0), s
        return
    m = re.fullmatch(
        rf"{re.escape(p)} stood on the (north|south) edge of the square, in line with the fountain\.", s)
    if m:
        want = 100.0 if m.group(1) == "north" else 0.0
        assert math.isclose(pos[p][1], want) and math.isclose(pos[p][0], 50.0), s
        return
    raise AssertionError(f"anchor line matches no known form: {s}")


def check_open(p, s, pos):
    """A regular opening statement (both coordinates pinned)."""
    m = re.fullmatch(
        rf"(?:{re.escape(p)} stood directly ({CARD}) of ({N}) and directly ({CARD}) of ({N})|"
        rf"{re.escape(p)} was set at the point directly ({CARD}) of ({N}) and directly ({CARD}) of ({N})|"
        rf"The point directly ({CARD}) of ({N}) and directly ({CARD}) of ({N}) is where {re.escape(p)} took up position)\.", s)
    if m:
        g = m.groups()
        v, b, h, c = (g[0], g[1], g[2], g[3]) if g[0] else (
            (g[4], g[5], g[6], g[7]) if g[4] else (g[8], g[9], g[10], g[11]))
        assert pos[p] == (pos[b][0], pos[c][1]), f"cross: {s}"
        assert v == ("north" if pos[c][1] > pos[b][1] else "south"), f"cross v: {s}"
        assert h == ("east" if pos[b][0] > pos[c][0] else "west"), f"cross h: {s}"
        return
    m = re.fullmatch(
        rf"{re.escape(p)} stood as far ({CARD}) of ({N}) as ({N}) is ({CARD}) of the fountain\.", s)
    if m:
        d1, a, b, d2 = m.groups()
        ax, ay = pos[a]
        if d1 in ("east", "west"):
            assert (d2 == "north") == (pos[b][1] > 50), f"asfar d2: {s}"
            off = abs(pos[b][1] - 50)
            want = ax + off if d1 == "east" else ax - off
            assert math.isclose(pos[p][0], want) and math.isclose(pos[p][1], ay), f"asfar: {s}"
        else:
            assert (d2 == "east") == (pos[b][0] > 50), f"asfar d2: {s}"
            off = abs(pos[b][0] - 50)
            want = ay + off if d1 == "north" else ay - off
            assert math.isclose(pos[p][1], want) and math.isclose(pos[p][0], ax), f"asfar: {s}"
        return
    m = re.fullmatch(
        rf"{re.escape(p)} (?:stood exactly halfway between|took the middle of the pair, exactly halfway between) ({N}) and ({N})\.", s)
    if m:
        b, c = m.groups()
        assert (pos[b][0] == pos[c][0]) ^ (pos[b][1] == pos[c][1]), f"halfway refs: {s}"
        assert math.isclose(pos[p][0], (pos[b][0] + pos[c][0]) / 2) \
            and math.isclose(pos[p][1], (pos[b][1] + pos[c][1]) / 2), f"halfway: {s}"
        return
    m = re.fullmatch(
        rf"(?:{re.escape(p)} took the spot opposite ({N}), with the fountain exactly halfway between the two|"
        rf"{re.escape(p)} and ({N}) straddled the fountain as mirror images, the fountain exactly halfway between them)\.", s)
    if m:
        b = m.group(1) or m.group(2)
        assert b != pos and b in pos, s
        assert pos[b] != (50.0, 50.0), s
        assert math.isclose(pos[p][0], 100 - pos[b][0]) \
            and math.isclose(pos[p][1], 100 - pos[b][1]), f"opposite: {s}"
        return
    m = re.fullmatch(
        rf"{re.escape(p)} stood on the (east|west) edge of the square, level with ({N})\.", s)
    if m:
        e, b = m.groups()
        want = 100.0 if e == "east" else 0.0
        assert math.isclose(pos[p][0], want) and math.isclose(pos[p][1], pos[b][1]), f"edge: {s}"
        return
    m = re.fullmatch(
        rf"{re.escape(p)} stood on the (north|south) edge of the square, in line with ({N})\.", s)
    if m:
        e, b = m.groups()
        want = 100.0 if e == "north" else 0.0
        assert math.isclose(pos[p][1], want) and math.isclose(pos[p][0], pos[b][0]), f"edge: {s}"
        return
    raise AssertionError(f"opening sentence matches no known form: {s}")


def check_move(ev, before, after):
    """Verify one move event's sentence against the before/after states."""
    k, p, s = ev["kind"], ev["actor"], ev["s"]
    px, py = before[p]
    ax, ay = after[p]

    if k == "cross":
        m = re.search(rf"{re.escape(p)} (?:walked ({CARD}) until (?:standing|they were) directly ({CARD}) of ({N})|"
                      rf"had walked ({CARD}) to the point directly ({CARD}) of ({N})|"
                      rf"set off toward the ({CARD}) and stopped directly ({CARD}) of ({N})|"
                      rf"went ({CARD}) until ({N}) lay directly ({CARD}) of them)\.", s)
        assert m, f"cross sentence matches no form: {s}"
        g = m.groups()
        if g[0]:
            c, side, q = g[0], g[1], g[2]
        elif g[3]:
            c, side, q = g[3], g[4], g[5]
        elif g[6]:
            c, side, q = g[6], g[7], g[8]
        else:
            c, q, side = g[9], g[10], g[11]
        if g[9]:
            # "went {c} until {q} lay directly {side} of them": q's side is of THEM
            assert G.in_dir(before[q], after[p], side), f"cross inv side: {s}"
        else:
            assert G.in_dir(after[p], before[q], side), f"cross side: {s}"
        if c in ("east", "west"):
            assert math.isclose(ax, before[q][0]) and math.isclose(ay, py), f"cross: {s}"
        else:
            assert math.isclose(ay, before[q][1]) and math.isclose(ax, px), f"cross: {s}"
        assert (c == "east") == (ax > px) and (c == "north") == (ay > py), f"cross dir: {s}"
        return

    if k == "diag":
        m = re.search(rf"{re.escape(p)} (?:cut across the square, ending|angled across and came to rest|"
                      rf"had worked a diagonal to the point) directly ({CARD}) of ({N})(?: and |, )directly ({CARD}) of ({N})\.", s)
        assert m, f"diag sentence matches no form: {s}"
        v, q, h, r = m.groups()
        assert math.isclose(ax, before[q][0]) and math.isclose(ay, before[r][1]), f"diag: {s}"
        assert G.in_dir(after[p], before[q], v), f"diag v: {s}"
        assert G.in_dir(after[p], before[r], h), f"diag h: {s}"
        return

    if k == "asfar":
        m = re.search(rf"{re.escape(p)} (?:walked|went|had walked) ({CARD}) "
                      rf"(?:until (?:standing|they stood)|to the spot) as far ({CARD}) of the fountain as "
                      rf"({N}) (?:is|stood) ({CARD}) of it\.", s)
        assert m, f"asfar sentence matches no form: {s}"
        c, c2, q, d2 = m.groups()
        assert c == c2, s
        if c in ("east", "west"):
            assert math.isclose(ax, before[q][1]) and math.isclose(ay, py), f"asfar: {s}"
            assert (d2 == "north") == (before[q][1] > 50), f"asfar d2: {s}"
        else:
            assert math.isclose(ay, before[q][0]) and math.isclose(ax, px), f"asfar: {s}"
            assert (d2 == "east") == (before[q][0] > 50), f"asfar d2: {s}"
        assert (c == "east") == (ax > px) and (c == "north") == (ay > py), f"asfar dir: {s}"
        return

    if k == "mirror":
        m = re.search(rf"{re.escape(p)} (?:walked until standing as far|balanced the picture, ending up exactly as far|"
                      rf"strolled over and took a spot as far) ({CARD}) of ({N}) as ({N}) was ({CARD}) of ({N})\.", s)
        if m:
            side, q, r, opp, q2 = m.groups()
            assert q == q2, s
            assert opp == G.OPPOSITE[side], s
            if side in ("east", "west"):
                assert math.isclose(ay, py), f"mirror preserved: {s}"
                assert (opp == "east") == (before[r][0] > before[q][0]), f"mirror r not {opp} of q: {s}"
                assert math.isclose(ax - before[q][0], before[q][0] - before[r][0]), f"mirror dist: {s}"
                assert (side == "east") == (ax > before[q][0]), f"mirror side: {s}"
            else:
                assert math.isclose(ax, px), f"mirror preserved: {s}"
                assert (opp == "north") == (before[r][1] > before[q][1]), f"mirror r not {opp} of q: {s}"
                assert math.isclose(ay - before[q][1], before[q][1] - before[r][1]), f"mirror dist: {s}"
                assert (side == "north") == (ay > before[q][1]), f"mirror side: {s}"
            return
        m = re.search(rf"{re.escape(p)} mirrored ({N})'s offset from ({N}), landing on the ({CARD}) side\.", s)
        if m:
            r, q, side = m.groups()
            if side in ("east", "west"):
                assert math.isclose(ay, py), f"mirror preserved: {s}"
                assert math.isclose(abs(ax - before[q][0]), abs(before[r][0] - before[q][0])), f"mirror dist: {s}"
                assert ((side == "east") == (ax > before[q][0])), f"mirror side: {s}"
                assert ((side == "east") == (before[r][0] < before[q][0])), f"mirror r side: {s}"
            else:
                assert math.isclose(ax, px), f"mirror preserved: {s}"
                assert math.isclose(abs(ay - before[q][1]), abs(before[r][1] - before[q][1])), f"mirror dist: {s}"
                assert ((side == "north") == (ay > before[q][1])), f"mirror side: {s}"
                assert ((side == "north") == (before[r][1] < before[q][1])), f"mirror r side: {s}"
            return
        raise AssertionError(f"mirror sentence matches no form: {s}")

    if k == "halfway":
        m = re.search(rf"{re.escape(p)} (?:walked over and stopped exactly halfway between|"
                      rf"took the middle of the pair, exactly halfway between|"
                      rf"had moved to stand exactly halfway between) ({N}) and ({N})\.", s)
        assert m, f"halfway sentence matches no form: {s}"
        q, r = m.groups()
        assert (before[q][0] == before[r][0]) ^ (before[q][1] == before[r][1]), f"halfway refs: {s}"
        assert math.isclose(ax, (before[q][0] + before[r][0]) / 2) \
            and math.isclose(ay, (before[q][1] + before[r][1]) / 2), f"halfway: {s}"
        return

    if k == "opposite":
        m = re.search(rf"{re.escape(p)} (?:crossed the square and took the spot directly opposite|"
                      rf"looped around the fountain and came up exactly opposite|"
                      rf"cut the square in two, ending up the mirror image of|"
                      rf"walked the long way and came to rest opposite) ({N})(?:[^.]*)\.", s)
        assert m, f"opposite sentence matches no form: {s}"
        q = m.group(1)
        assert before[q] != (50.0, 50.0), s
        assert math.isclose(ax, 100 - before[q][0]) and math.isclose(ay, 100 - before[q][1]), f"opposite: {s}"
        return

    if k == "swap":
        m = re.search(rf"(?:{re.escape(p)} and ({N}) swapped places|"
                      rf"{re.escape(p)} traded spots with ({N})|"
                      rf"{re.escape(p)} gave ({N}) their spot and took \3's in exchange|"
                      rf"a polite exchange: {re.escape(p)} and ({N}) changed places without a word)\.", s)
        assert m, f"swap sentence matches no form: {s}"
        q = next(g for g in m.groups() if g)
        assert (ax, ay) == before[q] and (after[q][0], after[q][1]) == (px, py), f"swap: {s}"
        return

    if k == "edge":
        m = re.search(rf"{re.escape(p)} (?:walked|kept walking|went) ({CARD}) "
                      rf"(?:until reaching the|until the|all the way to the) \1 edge of the square", s)
        assert m, f"edge sentence matches no form: {s}"
        c = m.group(1)
        if c in ("east", "west"):
            want = 100.0 if c == "east" else 0.0
            assert math.isclose(ax, want) and math.isclose(ay, py), f"edge: {s}"
        else:
            want = 100.0 if c == "north" else 0.0
            assert math.isclose(ay, want) and math.isclose(ax, px), f"edge: {s}"
        return

    if k == "far":
        m = re.search(rf"{re.escape(p)} moved far enough ({CARD}) that they now saw ({N}) to the ({CARD}) and ({N}) to the ({CARD})\.", s)
        if m:
            c, b, d1, c2, d2 = m.groups()
            assert d1 == G.OPPOSITE[c] and d2 == c, s
            axi = 0 if c in ("east", "west") else 1
            lo, hi = (before[b][axi], before[c2][axi]) if c in ("east", "north") else (before[c2][axi], before[b][axi])
            assert lo < after[p][axi] < hi, f"far interval: {s}"
            assert after[p][1 - axi] == before[p][1 - axi], f"far preserved: {s}"
            assert (c == "east") == (ax > px) and (c == "north") == (ay > py), f"far dir: {s}"
            return
        m = re.search(rf"{re.escape(p)} walked ({CARD}), passing well beyond ({N}), and stopped where ({N}) was still to the ({CARD})\.", s)
        if m:
            c, b, c2, d2 = m.groups()
            assert d2 == c, s
            axi = 0 if c in ("east", "west") else 1
            lo, hi = (before[b][axi], before[c2][axi]) if c in ("east", "north") else (before[c2][axi], before[b][axi])
            assert lo < after[p][axi] < hi, f"far interval: {s}"
            assert after[p][1 - axi] == before[p][1 - axi], f"far preserved: {s}"
            return
        m = re.search(rf"{re.escape(p)} moved far enough ({CARD}) that ({N}) was behind them to the ({CARD}), "
                      rf"({N}) still ahead to the ({CARD}), and {re.escape(p)} was closer to ({N}) than to ({N})\.", s)
        if m:
            c, b, d1, c2, d2, b2, c3 = m.groups()
            assert b == b2 and c2 == c3 and d1 == G.OPPOSITE[c] and d2 == c, s
            axi = 0 if c in ("east", "west") else 1
            lo, hi = (before[b][axi], before[c2][axi]) if c in ("east", "north") else (before[c2][axi], before[b][axi])
            assert lo < after[p][axi] < hi, f"far interval: {s}"
            assert math.dist(after[p], after[b]) < math.dist(after[p], after[c2]), f"far closer: {s}"
            assert after[p][1 - axi] == before[p][1 - axi], f"far preserved: {s}"
            return
        m = re.search(rf"{re.escape(p)} flung .+? about \d+ (?:{UNIT_ALT}) ({CARD}) and then walked over to it\.", s)
        if m:
            c = m.group(1)
            axi = 0 if c in ("east", "west") else 1
            assert (c == "east") == (ax > px) and (c == "north") == (ay > py), f"boot dir: {s}"
            assert after[p][1 - axi] == before[p][1 - axi], f"boot preserved: {s}"
            return
        m = re.search(rf"{re.escape(p)} walked ({CARD}) a good while until ({N}) was a good way behind them to the ({CARD})\.", s)
        if m:
            c, b, d1 = m.groups()
            assert d1 == G.OPPOSITE[c], s
            assert G.in_dir(before[b], after[p], d1), f"while behind: {s}"
            axi = 0 if c in ("east", "west") else 1
            assert (c == "east") == (ax > px) and (c == "north") == (ay > py), f"while dir: {s}"
            assert after[p][1 - axi] == before[p][1 - axi], f"while preserved: {s}"
            return
        raise AssertionError(f"far sentence matches no form: {s}")
    raise AssertionError(f"unknown move kind {k}")


SIGHT_PATTERNS = (
    (rf"({N}) sees ({N}) to the ({D8})", ("p", "q", "d")),
    (rf"looking to the ({D8}), ({N}) can see ({N})", ("d", "p", "q")),
    (rf"glancing that way, ({N}) spots ({N}) in the ({D8})", ("p", "q", "d")),
    (rf"({N}) is off to the ({D8}) of ({N})", ("q", "d", "p")),
    (rf"({N}) catches sight of ({N}) in the ({D8})", ("p", "q", "d")),
    (rf"to the ({D8}), ({N}) makes out ({N})", ("d", "p", "q")),
    (rf"further ({D8}) along, ({N}) finds ({N}) standing", ("d", "p", "q")),
    (rf"({N})'s eyes find ({N}) out in the ({D8})", ("p", "q", "d")),
    (rf"out in the ({D8}), ({N}) stands in view of ({N})", ("d", "q", "p")),
    (rf"from ({N})'s vantage point, ({N}) lies to the ({D8})", ("p", "q", "d")),
    (rf"({N}) has ({N}) to the ({D8})", ("p", "q", "d")),
)


def check_sight(line, pos, p):
    """Every sighting clause on the line must be true of pos."""
    for rx, order in SIGHT_PATTERNS:
        for m in re.finditer(rx, line):
            vals = dict(zip(order, m.groups()))
            assert G.in_dir(pos[vals["q"]], pos[vals["p"]], vals["d"]), \
                f"sighting clause false: {line[:90]}"


# ------------------------------------------------------------------ tests --


def test_helpers():
    # most specific true direction
    assert G.direction_of((60, 40), (50, 50)) == "southeast"
    assert G.direction_of((40, 60), (50, 50)) == "northwest"
    assert G.direction_of((55, 55), (50, 50)) == "northeast"
    assert G.direction_of((60, 50), (50, 50)) == "east"
    assert G.direction_of((50, 40), (50, 50)) == "south"
    assert G.in_dir((50, 60), (50, 50), "north")
    assert not G.in_dir((50, 60), (50, 50), "northeast")
    assert G.fmt(12.5) == "12.5" and G.fmt(33.0) == "33" and G.fmt(-7.5) == "-7.5"
    assert G.fmt(0.0) == "0" and G.fmt(25.25) == "25.25"
    rng = random.Random(1)
    for _ in range(300):
        p = (rng.uniform(-5, 105), rng.uniform(-5, 105))
        q = (rng.uniform(-5, 105), rng.uniform(-5, 105))
        if p == q:
            continue
        d = G.direction_of(q, p)
        assert G.in_dir(q, p, d)
        # the returned direction is the most specific one: a pure answer
        # means the other axis is exactly equal
        if d in ("north", "south"):
            assert q[0] == p[0]
        if d in ("east", "west"):
            assert q[1] == p[1]


def random_state(rng, n):
    """n people at distinct interior positions drawn from a shared value
    pool, so that 'same line' references actually exist.  All pinned."""
    pool = [i * 2.0 for i in range(3, 50)]  # 6 .. 98
    people = rng.sample(G.ROSTER, n)
    pos = {}
    for p in people:
        for _ in range(1000):
            pt = (rng.choice(pool), rng.choice(pool))
            if all(pt != pos[q] for q in pos):
                pos[p] = pt
                break
    known = {p: (True, True) for p in people}
    return people, pos, known


def test_opening_expresses_state():
    for seed in range(300):
        rng = random.Random(seed)
        n = rng.randint(8, 16)
        people = rng.sample(G.ROSTER, n)
        got = G.opening(rng, people)
        assert got is not None, f"opening failed for seed {seed}"
        pos, sents = got
        assert len(set(pos.values())) == n, f"seed {seed}: positions not distinct"
        assert all(G.in_arena(pt) for pt in pos.values()), f"seed {seed}: out of arena"
        for p, s in zip(people, sents):
            if p in (people[0], people[1], people[2]):
                check_open_anchor(p, s, pos)
            else:
                check_open(p, s, pos)


def test_moves_express_state():
    kinds = sorted(set(G.MKINDS))
    seen = set()
    for trial in range(6000):
        rng = random.Random(10_000 + trial)
        people, pos, known = random_state(rng, rng.randint(8, 14))
        kind = rng.choice(kinds)
        ev = None
        for _ in range(100):
            ev = G.try_move(rng, dict(pos), known, "09:00", kind=kind)
            if ev:
                break
        if ev is None:
            continue  # kind inapplicable for this state: fine
        seen.add(kind)
        before = dict(pos)
        after = dict(pos)
        if ev["kind"] == "swap":
            after[ev["actor"]] = before[ev["q"]]
            after[ev["q"]] = before[ev["actor"]]
        else:
            after[ev["actor"]] = ev["np"]
        check_move(ev, before, after)
        # the state update must agree with the event
        p2 = dict(pos)
        k2 = {x: tuple(v) for x, v in known.items()}
        G.apply_event(p2, k2, ev)
        assert p2 == after, f"apply_event disagrees with event ({kind}, trial {trial})"
    missing = set(kinds) - seen
    assert not missing, f"these kinds never occurred in the trials: {missing}"


def test_sight_sentences_are_true():
    for trial in range(3000):
        rng = random.Random(20_000 + trial)
        people, pos, known = random_state(rng, rng.randint(8, 14))
        p = rng.choice(people)
        s = G.sight_sentence(rng, pos, p)
        if not s:
            continue
        check_sight(s, pos, p)


def test_knownness_transitions():
    """The knownness rules, exactly:
    - far walk:  walked axis becomes OPEN, preserved axis unchanged
    - cross/asfar/mirror/edge: walked axis pinned, preserved unchanged
      (an open preserved axis STAYS OPEN — the regression this pins)
    - diag/halfway/opposite: both pinned
    - swap: the two people exchange knownness
    Each subtest builds its own small state, geometry chosen so the move
    is always applicable.
    """
    rng = random.Random(7)

    def scenario():
        nonlocal rng
        pos = {"A": (50.0, 50.0), "B": (60.0, 50.0), "C": (70.0, 50.0),
               "D": (40.0, 20.0)}
        known = {p: (True, True) for p in pos}

        def do(kind, actor, axis=None):
            ev = None
            for _ in range(300):
                ev = G.try_move(rng, dict(pos), known, "10:00",
                                kind=kind, actor=actor, axis=axis)
                if ev:
                    break
            assert ev is not None, f"{kind} for {actor} (axis {axis}) never applicable"
            G.apply_event(pos, known, ev)
            return ev
        return pos, known, do

    # 1. far east: walked axis opens, preserved axis stays known
    pos, known, do = scenario()
    do("far", "D", axis=0)
    assert known["D"] == (False, True), known["D"]

    # 2. far east with the preserved axis already open: both open
    pos, known, do = scenario()
    known["D"] = (True, False)
    do("far", "D", axis=0)
    assert known["D"] == (False, False), known["D"]

    # 3. cross north: walked axis pinned (preserved was known)
    pos, known, do = scenario()
    do("cross", "D", axis=1)
    assert known["D"] == (True, True), known["D"]

    # 4. cross north with x open: x MUST STAY OPEN (regression)
    pos, known, do = scenario()
    known["D"] = (False, True)
    do("cross", "D", axis=1)
    assert known["D"] == (False, True), f"cross closed the open preserved axis: {known['D']}"

    # 5. asfar north with x open: x MUST STAY OPEN (regression)
    pos, known, do = scenario()
    pos["B"] = (60.0, 60.0)
    pos["C"] = (70.0, 60.0)
    known["D"] = (False, True)
    do("asfar", "D", axis=1)
    assert known["D"] == (False, True), f"asfar closed the open preserved axis: {known['D']}"

    # 6. asfar north with x known: x pinned
    pos, known, do = scenario()
    pos["B"] = (60.0, 60.0)
    do("asfar", "D", axis=1)
    assert known["D"] == (True, True), known["D"]

    # 7. edge east: open x pinned
    pos, known, do = scenario()
    known["D"] = (False, True)
    do("edge", "D", axis=0)
    assert known["D"] == (True, True), known["D"]

    # 8. diag: both pinned even when the preserved axis was open
    pos, known, do = scenario()
    pos["C"] = (70.0, 30.0)
    pos["D"] = (40.0, 70.0)
    known["D"] = (False, True)
    do("diag", "D")
    assert known["D"] == (True, True), known["D"]

    # 9. halfway: both pinned
    pos, known, do = scenario()
    pos["D"] = (80.0, 20.0)
    do("halfway", "D")
    assert known["D"] == (True, True), known["D"]

    # 10. opposite: both pinned
    pos, known, do = scenario()
    pos["C"] = (70.0, 30.0)
    pos["D"] = (80.0, 20.0)
    do("opposite", "D")
    assert known["D"] == (True, True), known["D"]

    # 11. mirror east-west with y open: y MUST STAY OPEN (regression)
    pos = {"A": (50.0, 42.7), "B": (60.0, 42.7), "C": (70.0, 42.7),
           "D": (80.0, 42.7)}
    known = {p: (True, True) for p in pos}
    known["D"] = (True, False)
    ev = None
    for _ in range(300):
        ev = G.try_move(rng, dict(pos), known, "10:00", kind="mirror", actor="D", axis=0)
        if ev:
            break
    assert ev is not None, "mirror never applicable in subtest 11"
    G.apply_event(pos, known, ev)
    assert known["D"] == (True, False), f"mirror closed the open preserved axis: {known['D']}"

    # 12. mirror with everything known: walked axis pinned
    pos, known, do = scenario()
    pos["D"] = (80.0, 50.0)
    do("mirror", "D", axis=0)
    assert known["D"] == (True, True), known["D"]

    # 13. swap exchanges knownness
    pos, known, do = scenario()
    pos["A"] = (70.0, 50.0)
    pos["B"] = (50.0, 50.0)
    pos["C"] = (60.0, 50.0)
    pos["D"] = (80.0, 50.0)
    do("far", "A", axis=0)
    assert known["A"] == (False, True), known["A"]
    kb_before = dict(known)
    ev = do("swap", "A")
    q = ev["q"]
    assert known["A"] == kb_before[q] and known[q] == kb_before["A"], \
        f"swap did not exchange knownness: {known['A']} vs {known[q]}"


def test_pin_pass_closes_all():
    for seed in range(200):
        rng = random.Random(30_000 + seed)
        people, pos, known = random_state(rng, rng.randint(8, 16))
        for _ in range(rng.randint(1, 6)):
            p = rng.choice(people)
            ax = rng.choice((0, 1))
            known[p] = (known[p][0], known[p][1])
            known[p] = (False if ax == 0 else known[p][0],
                        False if ax == 1 else known[p][1])
        st0 = dict(pos)
        events = []
        ok = G.pin_pass(rng, people, pos, known, events, 20 * 60)
        assert ok, f"pin_pass failed seed {seed}"
        assert all(known[p][0] and known[p][1] for p in people), \
            f"seed {seed}: axes left open"
        assert len(set(pos.values())) == len(people), f"seed {seed}: collision"
        # every closing sentence must be true of the state it was made from
        st = dict(st0)
        for ev in events:
            b4 = dict(st)
            if ev["kind"] == "swap":
                st[ev["actor"]], st[ev["q"]] = st[ev["q"]], st[ev["actor"]]
            else:
                st[ev["actor"]] = ev["np"]
            check_move(ev, b4, st)
        assert st == pos


def test_decoys():
    rng = random.Random(40_000)
    for i in range(1000):
        d = G.make_decoy(rng, G.ROSTER)
        low = d.lower()
        assert "metre" not in low, d
        assert not re.search(r"\d+\s*,\s*\d+", d), d
        m = re.search(rf"(?:about|some) (\d+) (?:{UNIT_ALT})", d)
        if m:
            assert 8 <= int(m.group(1)) <= 40, d
        assert (m is not None
                or "still exactly where they had been" in d
                or "nobody in this year's crowd" in d
                or "but that was not today" in d
                or "not one of our people" in d), d


def independent_anti_grep(text, decoys, inside):
    """The test's own copy of the number-hygiene rule (independent of the
    generator's): after removing the intro, clock times, decoy lines and
    fake-unit counts, no digit may remain, and no coordinate pair may
    appear anywhere in the body."""
    body = text.replace(G.INTRO, "", 1)
    assert not re.search(r"\d+(?:\.\d+)?\s*,\s*\d+", body), "coordinate pair in text"
    body = re.sub(r"\b\d{1,2}:\d{2}\b", "", body)
    for s in decoys:
        body = body.replace(G.cap(s), "")
    body = re.sub(rf"(?:about|some) \d+ (?:{UNIT_ALT})", "", body)
    m = re.search(r"\d", body)
    assert not m, f"stray digit: ...{body[max(0, m.start() - 40):m.end() + 40]}..."
    if len(inside) >= 2:
        names = set(inside)
        for line in body.splitlines():
            words = {w.strip(".,;:") for w in line.split()}
            assert not names <= words, f"answer list on one line: {line[:80]}"


def test_full_generation():
    for tokens, seed in ((16000, 105), (64000, 303), (128000, 404)):
        text, question, solution, used, meta = G.generate(tokens, seed)
        people, pos = meta["people"], meta["pos"]
        a, b, inside, p2 = meta["a"], meta["b"], meta["inside"], meta["p2"]
        # positions: unique, in arena, all pinned by the text
        assert len(set(pos.values())) == len(people)
        assert all(G.in_arena(pt) for pt in pos.values())
        assert all(meta["known"][p] == (True, True) for p in people)
        # opening sentences true
        for p, s in zip(people, meta["init_sents"]):
            if p in (people[0], people[1], people[2]):
                check_open_anchor(p, s, meta["init_pos"])
            else:
                check_open(p, s, meta["init_pos"])
        # every event's sentence true of the state it was made from
        st = dict(meta["init_pos"])
        for ev in meta["events"]:
            before = dict(st)
            if ev["kind"] == "swap":
                st[ev["actor"]], st[ev["q"]] = st[ev["q"]], st[ev["actor"]]
            else:
                st[ev["actor"]] = ev["np"]
            check_move(ev, before, st)
            if ev["sight"]:
                check_sight(ev["sight"], st, ev["actor"])
        assert st == pos, "event stream does not reproduce the final state"
        # the answers, recomputed from the final state
        ax, ay = pos[a]
        bx, by = pos[b]
        assert ax < bx and ay > by
        recomputed = sorted(p for p in people if ax < pos[p][0] < bx and by < pos[p][1] < ay)
        assert sorted(inside) == recomputed, f"Q1 mismatch: {inside} vs {recomputed}"
        assert 5 <= len(inside) <= 8
        assert p2 not in (a, b)
        p3 = meta["p3"]
        assert p3 not in (a, b, p2)
        # the question names the right people
        assert a in question and b in question and p2 in question and p3 in question
        # the Q2 answer in the solution is the true relational description
        m = re.search(rf"^  Q2: {re.escape(p2)} was (\S+) of the fountain, and (\S+) of {re.escape(p3)}\.$",
                      solution, re.M)
        assert m, "Q2 answer not in solution"
        assert m.group(1) == G.direction_of(pos[p2], (50.0, 50.0)), m.groups()
        assert m.group(2) == G.direction_of(pos[p2], pos[p3]), m.groups()
        for p in people:
            m = re.search(rf"^  {re.escape(p)} = \((-?\d+(?:\.\d+)?), (-?\d+(?:\.\d+)?)\)$",
                          solution, re.M)
            assert m, f"{p} not in solution"
            assert math.isclose(float(m.group(1)), pos[p][0] - 50, abs_tol=0.01)
            assert math.isclose(float(m.group(2)), pos[p][1] - 50, abs_tol=0.01)
        # number hygiene (test's own checker)
        independent_anti_grep(text, meta["decoys"], inside)
        print(f"    {tokens}: seed {used}, {len(people)} people, "
              f"{len(meta['events'])} moves, {len(text)} chars "
              f"≈ {len(text) // 4} tokens, Q1={len(inside)} inside, "
              f"Q2={p2} ({G.direction_of(pos[p2], (50.0, 50.0))} of fountain, "
              f"{G.direction_of(pos[p2], pos[meta['p3']])} of {meta['p3']})")


# ------------------------------------- exposure markers, checked against text
# The generator's `known` dict is the exposure record: for every person it
# marks, per coordinate, whether the text emitted so far exposes that
# coordinate exactly.  Every event dict also carries `exposed`: what THIS
# sentence says — a tuple of pinned axes, ("open", axis) for a far walk
# (the sentence leaves that axis a mere range), or "swap".  This test
# re-reads each emitted sentence, works out what it exposes, and checks
# that the record and the markers agree with the text.


def classify_sentence(s):
    """What does one emitted sentence expose?  Returns (ax,) / (0, 1) for
    a pinned axis, ("open", ax) for a far walk, "swap" for a swap, or None
    if the sentence matches no known move form."""
    if re.search(r"swapped places|traded spots with|their spot and took|polite exchange:", s):
        return "swap"
    m = re.search(rf"moved far enough ({CARD})|walked ({CARD}), passing well beyond|"
                  rf"flung [^.]*? about \d+ (?:{UNIT_ALT}) ({CARD})|walked ({CARD}) a good while", s)
    if m:
        return ("open", AXIS_OF[next(g for g in m.groups() if g)])
    m = re.search(rf"as far ({CARD}) of the fountain", s)
    if m:
        return (AXIS_OF[m.group(1)],)
    m = re.search(rf"as far ({CARD}) of ({N}) as|landing on the ({CARD}) side", s)
    if m:
        return (AXIS_OF[m.group(1) or m.group(3)],)
    if "exactly halfway between" in s:
        return (0, 1)
    if re.search(r"opposite|mirror image of", s):
        return (0, 1)
    if re.search(r"cut across the square, ending|angled across|had worked a diagonal", s):
        return (0, 1)
    m = re.search(rf"the ({CARD}) edge of the square", s)
    if m:
        return (AXIS_OF[m.group(1)],)
    m = re.search(rf"walked ({CARD}) until|had walked ({CARD}) to the point|"
                  rf"set off toward the ({CARD})|went ({CARD}) until", s)
    if m:
        return (AXIS_OF[next(g for g in m.groups() if g)],)
    return None


def test_exposure_markers():
    for tokens, seed in ((16000, 11), (64000, 22), (128000, 33)):
        text, question, solution, used, meta = G.generate(tokens, seed)
        people, events = meta["people"], meta["events"]
        # --- the opening: each sentence exposes both axes of its subject,
        # and every name it references was already placed
        placed = set()
        for p, s in zip(people, meta["init_sents"]):
            refs = set(re.findall(rf"\b(?:{N})\b", s)) - {p}
            assert refs <= placed, f"opening references a person not yet placed: {s[:90]}"
            placed.add(p)
        assert placed == set(people), "opening does not place everybody"
        # --- the moves: record, markers and text must all agree
        known = {p: (True, True) for p in people}
        pstate = dict(meta["init_pos"])
        for ev in events:
            kb = {x: tuple(v) for x, v in known.items()}
            exp = classify_sentence(ev["s"])
            assert exp is not None, f"unclassified move sentence: {ev['s'][:100]}"
            assert exp == ev["exposed"], \
                f"record disagrees with text: {exp} vs {ev['exposed']}: {ev['s'][:100]}"
            G.apply_event(pstate, known, ev)
            p = ev["actor"]
            if exp == "swap":
                assert known[p] == kb[ev["q"]] and known[ev["q"]] == kb[p], \
                    f"swap markers not exchanged: {ev['s'][:90]}"
            elif exp[0] == "open":
                ax = exp[1]
                assert known[p][ax] is False, f"open axis not unmarked: {ev['s'][:90]}"
                other = 1 - ax
                assert known[p][other] == kb[p][other], f"preserved marker changed: {ev['s'][:90]}"
            else:
                for ax in (0, 1):
                    if ax in exp:
                        assert known[p][ax] is True, f"exposed axis not marked: {ev['s'][:90]}"
                    else:
                        assert known[p][ax] == kb[p][ax], f"unexposed marker changed: {ev['s'][:90]}"
        assert all(v == (True, True) for v in known.values()), \
            f"unexposed coordinates at the end: {known}"
        print(f"    {tokens}: {len(events)} sentences, markers agreed with the text")


def main():
    run("helpers (directions, fmt)", test_helpers)
    run("opening sentences express the state (300 seeds)", test_opening_expresses_state)
    run("move sentences express the state (all kinds, 6000 trials)", test_moves_express_state)
    run("sighting sentences are true (3000 trials)", test_sight_sentences_are_true)
    run("knownness transitions (incl. open preserved axes)", test_knownness_transitions)
    run("pin pass closes every open axis (200 seeds)", test_pin_pass_closes_all)
    run("decoys (1000 samples)", test_decoys)
    run("full generation is self-consistent (16k/64k/128k)", test_full_generation)
    run("exposure markers are marked exactly as the text exposes",
        test_exposure_markers)
    print()
    if FAILS:
        print(f"{len(FAILS)} test(s) FAILED: {', '.join(FAILS)}")
        sys.exit(1)
    print("all tests passed")


if __name__ == "__main__":
    main()
