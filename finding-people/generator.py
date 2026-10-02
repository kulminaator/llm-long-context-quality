#!/usr/bin/env python3
"""Finding-people puzzle generator.

The core is plain 2D math on a 100 x 100 square: positions are float
coordinates (x = metres east of the west edge, y = metres north of the
south edge), the fountain sits at the exact centre (50, 50), and every
move is simple arithmetic (a coordinate copied from another person, a
midpoint, a reflection in the centre, an offset).

The surface — the only place language happens — renders those state
changes as relative statements: "directly north of", "level with",
"as far east of A as B is north of the fountain", "exactly halfway
between", "the spot opposite".  No distance in metres and no coordinate
pair ever appears in the log.  The intro states the square's size (100
metres by 100 metres, fountain at the exact centre), so the four edges
are fixed landmarks: "on the east edge of the square" pins a position
exactly, with no number in the log.  The only other numbers anywhere in
the puzzle are clock times and meaningless decoy counts in absurd units
("about 20 frog-leaps").

A few "far enough" walks deliberately leave one coordinate open ("moved
far enough east that they now saw Bob to the west and Carol to the
east"); a short closing sequence at the end of the log pins every open
coordinate back down, so the final state — and with it both answers —
is uniquely determined.
"""
import argparse
import random
import re

# --------------------------------------------------------------- the square
X0, X1 = 0.0, 100.0
Y0, Y1 = 0.0, 100.0
FX, FY = 50.0, 50.0

EAST, WEST, NORTH, SOUTH = "east", "west", "north", "south"
CARDS = (EAST, WEST, NORTH, SOUTH)
AXIS = {EAST: 0, WEST: 0, NORTH: 1, SOUTH: 1}
OPPOSITE = {EAST: WEST, WEST: EAST, NORTH: SOUTH, SOUTH: NORTH}
# most specific direction first: a diagonal is also a pure direction,
# but the diagonal statement is strictly more informative
DIRS8 = ("northeast", "northwest", "southeast", "southwest",
         "north", "south", "east", "west")

ROSTER = [
    "Alice", "Bob", "Carol", "Dave", "Erin", "Felicia", "Gerald", "Helen",
    "Ivan", "Jasper", "Karen", "Lars", "Mona", "Ned", "Olive", "Peter",
    "Quinn", "Rosa", "Sven", "Tessa", "Uma", "Viktor", "Wendy", "Xena",
    "Yusuf", "Zora",
]
NAME = "|".join(sorted(ROSTER, key=len, reverse=True))

ITEMS = ("a glove", "a hat", "his boot", "her umbrella",
         "the warden's cap", "a sandwich wrapper")
UNITS = ("frog-leaps", "long jumps", "boot-throws", "crow-hops",
         "goat-strides", "kettle-hops")

# ------------------------------------------------------------------ helpers


def in_dir(q, p, d):
    """Is q in direction d of p?  Axis directions compare that axis only;
    diagonals compare both axes, strictly."""
    qx, qy = q
    px, py = p
    if d == "east":
        return qx > px
    if d == "west":
        return qx < px
    if d == "north":
        return qy > py
    if d == "south":
        return qy < py
    if d == "northeast":
        return qx > px and qy > py
    if d == "northwest":
        return qx < px and qy > py
    if d == "southeast":
        return qx > px and qy < py
    return qx < px and qy < py  # southwest


def direction_of(q, p):
    for d in DIRS8:
        if in_dir(q, p, d):
            return d
    raise ValueError("same position")


def in_arena(pt):
    return X0 <= pt[0] <= X1 and Y0 <= pt[1] <= Y1


def spot_free(pt, pos, p):
    """A usable new spot: a real change, inside the square, unoccupied."""
    if p in pos and pt == pos[p]:
        return False
    if not in_arena(pt):
        return False
    return not any(q != p and pos[q] == pt for q in pos)


def fmt(v):
    """Display a float without trailing zeros: 12.5, -7.5, 33.0 -> '33'."""
    return f"{round(v, 2):g}"


def fmt_time(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def cap(s):
    return s[0].upper() + s[1:] if s else s


def rel(pt):
    """A position relative to the fountain (the answer format)."""
    return (pt[0] - FX, pt[1] - FY)

# ------------------------------------------------------- opening placement
# Every opening statement pins BOTH coordinates of the new person.  The
# two edge anchors ("on the east edge, level with the fountain") fix the
# scale, because the intro gives the square's size.


def try_open(rng, pos, p):
    """One opening statement placing p, referencing already-placed people.
    Returns (sentence, pt) or None."""
    placed = list(pos)
    kind = rng.choice(["cross"] * 3 + ["asfar"] * 3 + ["halfway"] * 2 +
                      ["opposite"] * 2 + ["edge"] * 3)
    if kind == "cross":
        for _ in range(50):
            b, c = rng.sample(placed, 2)
            bx, by = pos[b]
            cx, cy = pos[c]
            if bx == cx or by == cy:
                continue
            pt = (bx, cy)
            if not spot_free(pt, pos, p):
                continue
            v = NORTH if cy > by else SOUTH
            h = EAST if bx > cx else WEST
            s = rng.choice((
                f"{p} stood directly {v} of {b} and directly {h} of {c}.",
                f"{p} was set at the point directly {v} of {b} and directly {h} of {c}.",
                f"The point directly {v} of {b} and directly {h} of {c} is where {p} took up position.",
            ))
            return s, pt
        return None
    if kind == "asfar":
        for _ in range(50):
            a, b = rng.sample(placed, 2)
            ax, ay = pos[a]
            bx, by = pos[b]
            if rng.random() < 0.5:
                if by > FY:
                    pt = (ax + (by - FY), ay)
                    s = f"{p} stood as far {EAST} of {a} as {b} is {NORTH} of the fountain."
                elif by < FY:
                    pt = (ax - (FY - by), ay)
                    s = f"{p} stood as far {WEST} of {a} as {b} is {SOUTH} of the fountain."
                else:
                    continue
            else:
                if bx > FX:
                    pt = (ax, ay + (bx - FX))
                    s = f"{p} stood as far {NORTH} of {a} as {b} is {EAST} of the fountain."
                elif bx < FX:
                    pt = (ax, ay - (FX - bx))
                    s = f"{p} stood as far {SOUTH} of {a} as {b} is {WEST} of the fountain."
                else:
                    continue
            if not spot_free(pt, pos, p):
                continue
            return s, pt
        return None
    if kind == "halfway":
        for _ in range(50):
            b, c = rng.sample(placed, 2)
            bx, by = pos[b]
            cx, cy = pos[c]
            if by == cy and bx != cx:
                pt = ((bx + cx) / 2, by)
            elif bx == cx and by != cy:
                pt = (bx, (by + cy) / 2)
            else:
                continue
            if not spot_free(pt, pos, p):
                continue
            s = rng.choice((
                f"{p} stood exactly halfway between {b} and {c}.",
                f"{p} took the middle of the pair, exactly halfway between {b} and {c}.",
            ))
            return s, pt
        return None
    if kind == "opposite":
        for _ in range(50):
            b = rng.choice(placed)
            if pos[b] == (FX, FY):
                continue
            pt = (2 * FX - pos[b][0], 2 * FY - pos[b][1])
            if not spot_free(pt, pos, p):
                continue
            s = rng.choice((
                f"{p} took the spot opposite {b}, with the fountain exactly halfway between the two.",
                f"{p} and {b} straddled the fountain as mirror images, the fountain exactly halfway between them.",
            ))
            return s, pt
        return None
    if kind == "edge":
        for _ in range(50):
            b = rng.choice(placed)
            if rng.random() < 0.5:
                e = rng.choice((EAST, WEST))
                pt = ((X1 if e == EAST else X0), pos[b][1])
                s = f"{p} stood on the {e} edge of the square, level with {b}."
            else:
                e = rng.choice((NORTH, SOUTH))
                pt = (pos[b][0], (Y1 if e == NORTH else Y0))
                s = f"{p} stood on the {e} edge of the square, in line with {b}."
            if not spot_free(pt, pos, p):
                continue
            return s, pt
        return None
    return None


def opening(rng, people):
    """Place everyone with fully-determining relative statements.
    Returns (pos, sentences) or None.  After the opening, the text pins
    down both coordinates of every person."""
    pos, sents = {}, []
    p0 = people[0]
    pos[p0] = (FX, FY)
    sents.append(f"At the opening, {p0} took the old fountain in the centre of the square.")
    p1 = people[1]
    vedge = rng.choice((EAST, WEST))
    pos[p1] = ((X1 if vedge == EAST else X0), FY)
    sents.append(f"{p1} stood on the {vedge} edge of the square, level with the fountain.")
    p2 = people[2]
    hedge = rng.choice((NORTH, SOUTH))
    pos[p2] = (FX, (Y1 if hedge == NORTH else Y0))
    sents.append(f"{p2} stood on the {hedge} edge of the square, in line with the fountain.")
    for p in people[3:]:
        got = None
        for _ in range(200):
            got = try_open(rng, pos, p)
            if got:
                break
        if got is None:
            return None
        s, pt = got
        pos[p] = pt
        sents.append(s)
    return pos, sents

# ------------------------------------------------------------------- moves
# Every move is computed with plain arithmetic and rendered as a relative
# sentence.  Only the "far" kind leaves a coordinate open (one axis stays
# a range until the closing sequence pins it).


def try_move(rng, pos, known, time, kind=None, actor=None, axis=None):
    """One move.  known[name] = (x_pinned, y_pinned): which coordinates
    the text has pinned down exactly so far (references are only drawn
    from pinned coordinates, so every exact statement stays exact).
    Returns an event dict or None.  Events carry enough to re-render and
    to check the sentence against the state."""
    if kind is None:
        kind = rng.choice(MKINDS)
    names = list(pos)
    p = actor or rng.choice(names)
    others = [x for x in names if x != p]
    px, py = pos[p]

    if kind == "cross":
        if axis == 0:
            c = rng.choice((EAST, WEST))
        elif axis is not None:
            c = rng.choice((NORTH, SOUTH))
        else:
            c = rng.choice(CARDS)
        for _ in range(60):
            q = rng.choice(others)
            qx, qy = pos[q]
            if c in (EAST, WEST):
                if not known[q][0] or (c == EAST) != (qx > px) or py == qy:
                    continue
                pt = (qx, py)
                side = NORTH if py > qy else SOUTH
            else:
                if not known[q][1] or (c == NORTH) != (qy > py) or px == qx:
                    continue
                pt = (px, qy)
                side = EAST if px > qx else WEST
            if not spot_free(pt, pos, p):
                continue
            s = rng.choice((
                f"At {time}, {p} walked {c} until standing directly {side} of {q}.",
                f"At {time}, {p} walked {c} until they were directly {side} of {q}.",
                f"By {time}, {p} had walked {c} to the point directly {side} of {q}.",
                f"At {time}, {p} set off toward the {c} and stopped directly {side} of {q}.",
                f"At {time}, {p} went {c} until {q} lay directly {OPPOSITE[side]} of them.",
            ))
            # the sentence pins the walked axis (the stop is the alignment)
            return dict(kind=kind, actor=p, q=q, c=c, np=pt, axis=AXIS[c],
                        exposed=(AXIS[c],), s=s)
        return None

    if kind == "diag":
        for _ in range(60):
            q, r = rng.sample(others, 2)
            qx, qy = pos[q]
            rx, ry = pos[r]
            if qx == px or ry == py or qx == rx:
                continue
            if not (known[q][0] and known[r][1]):
                continue
            pt = (qx, ry)
            if not spot_free(pt, pos, p):
                continue
            v = NORTH if ry > qy else SOUTH
            h = EAST if qx > rx else WEST
            s = rng.choice((
                f"At {time}, {p} cut across the square, ending directly {v} of {q} and directly {h} of {r}.",
                f"At {time}, {p} angled across and came to rest directly {v} of {q}, directly {h} of {r}.",
                f"By {time}, {p} had worked a diagonal to the point directly {v} of {q} and directly {h} of {r}.",
            ))
            return dict(kind=kind, actor=p, q=q, r=r, np=pt, exposed=(0, 1), s=s)
        return None

    if kind == "asfar":
        if axis == 0:
            c = rng.choice((EAST, WEST))
        elif axis is not None:
            c = rng.choice((NORTH, SOUTH))
        else:
            c = rng.choice(CARDS)
        for _ in range(60):
            q = rng.choice(others)
            qx, qy = pos[q]
            if c == EAST:
                if not known[q][1] or qy <= FY or qy <= px:
                    continue
                pt = (qy, py)
                d2 = NORTH
            elif c == WEST:
                if not known[q][1] or qy >= FY or qy >= px:
                    continue
                pt = (qy, py)
                d2 = SOUTH
            elif c == NORTH:
                if not known[q][0] or qx <= FX or qx <= py:
                    continue
                pt = (px, qx)
                d2 = EAST
            else:
                if not known[q][0] or qx >= FX or qx >= py:
                    continue
                pt = (px, qx)
                d2 = WEST
            if not spot_free(pt, pos, p):
                continue
            s = rng.choice((
                f"At {time}, {p} walked {c} until standing as far {c} of the fountain as {q} is {d2} of it.",
                f"At {time}, {p} went {c} until they stood as far {c} of the fountain as {q} stood {d2} of it.",
                f"By {time}, {p} had walked {c} to the spot as far {c} of the fountain as {q} is {d2} of it.",
            ))
            return dict(kind=kind, actor=p, q=q, c=c, np=pt, axis=AXIS[c],
                        exposed=(AXIS[c],), s=s)
        return None

    if kind == "mirror":
        form = "ew" if axis == 0 else "ns" if axis is not None else rng.choice(("ew", "ns"))
        if form == "ew":
            for _ in range(60):
                line = [x for x in others if pos[x][1] == py and known[x][0]]
                if len(line) < 2:
                    return None
                q = rng.choice(line)
                r = rng.choice([x for x in line if x != q])
                side = rng.choice((EAST, WEST))
                if (side == EAST) != (pos[r][0] < pos[q][0]):
                    continue
                pt = (2 * pos[q][0] - pos[r][0], py)
                if not spot_free(pt, pos, p):
                    continue
                opp = OPPOSITE[side]
                s = rng.choice((
                    f"At {time}, {p} walked until standing as far {side} of {q} as {r} was {opp} of {q}.",
                    f"At {time}, {p} balanced the picture, ending up exactly as far {side} of {q} as {r} was {opp} of {q}.",
                    f"At {time}, {p} mirrored {r}'s offset from {q}, landing on the {side} side.",
                    f"At {time}, {p} strolled over and took a spot as far {side} of {q} as {r} was {opp} of {q}.",
                ))
                return dict(kind=kind, actor=p, q=q, r=r, side=side, np=pt, axis=0,
                            exposed=(0,), s=s)
            return None
        for _ in range(60):
            line = [x for x in others if pos[x][0] == px and known[x][1]]
            if len(line) < 2:
                return None
            q = rng.choice(line)
            r = rng.choice([x for x in line if x != q])
            side = rng.choice((NORTH, SOUTH))
            if (side == NORTH) != (pos[r][1] < pos[q][1]):
                continue
            pt = (px, 2 * pos[q][1] - pos[r][1])
            if not spot_free(pt, pos, p):
                continue
            opp = OPPOSITE[side]
            s = rng.choice((
                f"At {time}, {p} walked until standing as far {side} of {q} as {r} was {opp} of {q}.",
                f"At {time}, {p} balanced the picture, ending up exactly as far {side} of {q} as {r} was {opp} of {q}.",
                f"At {time}, {p} mirrored {r}'s offset from {q}, landing on the {side} side.",
                f"At {time}, {p} strolled over and took a spot as far {side} of {q} as {r} was {opp} of {q}.",
            ))
            return dict(kind=kind, actor=p, q=q, r=r, side=side, np=pt, axis=1,
                        exposed=(1,), s=s)
        return None

    if kind == "halfway":
        for _ in range(60):
            q, r = rng.sample(others, 2)
            qx, qy = pos[q]
            rx, ry = pos[r]
            if qy == ry and qx != rx:
                if not (known[q][0] and known[r][0] and known[q][1]):
                    continue
                pt = ((qx + rx) / 2, qy)
            elif qx == rx and qy != ry:
                if not (known[q][1] and known[r][1] and known[q][0]):
                    continue
                pt = (qx, (qy + ry) / 2)
            else:
                continue
            if not spot_free(pt, pos, p):
                continue
            s = rng.choice((
                f"At {time}, {p} walked over and stopped exactly halfway between {q} and {r}.",
                f"At {time}, {p} took the middle of the pair, exactly halfway between {q} and {r}.",
                f"By {time}, {p} had moved to stand exactly halfway between {q} and {r}.",
            ))
            return dict(kind=kind, actor=p, q=q, r=r, np=pt, exposed=(0, 1), s=s)
        return None

    if kind == "opposite":
        for _ in range(60):
            q = rng.choice(others)
            if pos[q] == (FX, FY) or not (known[q][0] and known[q][1]):
                continue
            pt = (2 * FX - pos[q][0], 2 * FY - pos[q][1])
            if not spot_free(pt, pos, p):
                continue
            s = rng.choice((
                f"At {time}, {p} crossed the square and took the spot directly opposite {q}, with the fountain exactly halfway between the two.",
                f"At {time}, {p} looped around the fountain and came up exactly opposite {q}, the fountain midway.",
                f"At {time}, {p} cut the square in two, ending up the mirror image of {q} across the fountain.",
                f"At {time}, {p} walked the long way and came to rest opposite {q}, with the fountain exactly between them.",
            ))
            return dict(kind=kind, actor=p, q=q, np=pt, exposed=(0, 1), s=s)
        return None

    if kind == "swap":
        q = rng.choice(others)
        s = rng.choice((
            f"At {time}, {p} and {q} swapped places.",
            f"At {time}, {p} traded spots with {q}.",
            f"At {time}, {p} gave {q} their spot and took {q}'s in exchange.",
            f"At {time}, a polite exchange: {p} and {q} changed places without a word.",
        ))
        return dict(kind=kind, actor=p, q=q, np=pos[q], exposed="swap", s=s)

    if kind == "edge":
        for _ in range(10):
            if axis == 0:
                c = rng.choice((EAST, WEST))
            elif axis == 1:
                c = rng.choice((NORTH, SOUTH))
            else:
                c = rng.choice(CARDS)
            if c == EAST and px >= X1:
                continue
            if c == WEST and px <= X0:
                continue
            if c == NORTH and py >= Y1:
                continue
            if c == SOUTH and py <= Y0:
                continue
            pt = ((X1 if c == EAST else X0 if c == WEST else px),
                  (Y1 if c == NORTH else Y0 if c == SOUTH else py))
            if not spot_free(pt, pos, p):
                continue
            s = rng.choice((
                f"At {time}, {p} walked {c} until reaching the {c} edge of the square.",
                f"At {time}, {p} kept walking {c} until the {c} edge of the square was under their feet.",
                f"At {time}, {p} went {c} all the way to the {c} edge of the square.",
            ))
            return dict(kind=kind, actor=p, c=c, np=pt, axis=AXIS[c],
                        exposed=(AXIS[c],), s=s)
        return None

    if kind == "far":
        c = CARDS[axis] if axis is not None else rng.choice(CARDS)
        form = rng.choice(["saw", "saw", "closer", "boot", "while"])
        for _ in range(60):
            if form in ("saw", "closer"):
                b, c2 = rng.sample(others, 2)
                # "closer to B" is a plain distance comparison, so for that
                # form both references must share p's line
                if form == "closer":
                    if c in (EAST, WEST):
                        if pos[b][1] != py or pos[c2][1] != py:
                            continue
                    elif pos[b][0] != px or pos[c2][0] != px:
                        continue
                if c in (EAST, WEST):
                    if c == EAST:
                        if not (pos[b][0] < pos[c2][0] and pos[c2][0] - pos[b][0] > 2.0):
                            continue
                        lo, hi = pos[b][0], pos[c2][0]
                        xlo = max(lo, px) + 0.1
                        xhi = hi - 0.1
                        if form == "closer":
                            xhi = min(xhi, (lo + hi) / 2 - 0.1)
                        if xhi - xlo < 0.5:
                            continue
                        pt = (rng.uniform(xlo, xhi), py)
                    else:
                        if not (pos[c2][0] < pos[b][0] and pos[b][0] - pos[c2][0] > 2.0):
                            continue
                        lo, hi = pos[c2][0], pos[b][0]
                        xlo = lo + 0.1
                        xhi = min(hi, px) - 0.1
                        if form == "closer":
                            xlo = max(xlo, (lo + hi) / 2 + 0.1)
                        if xhi - xlo < 0.5:
                            continue
                        pt = (rng.uniform(xlo, xhi), py)
                else:
                    if c == NORTH:
                        if not (pos[b][1] < pos[c2][1] and pos[c2][1] - pos[b][1] > 2.0):
                            continue
                        lo, hi = pos[b][1], pos[c2][1]
                        ylo = max(lo, py) + 0.1
                        yhi = hi - 0.1
                        if form == "closer":
                            yhi = min(yhi, (lo + hi) / 2 - 0.1)
                        if yhi - ylo < 0.5:
                            continue
                        pt = (px, rng.uniform(ylo, yhi))
                    else:
                        if not (pos[c2][1] < pos[b][1] and pos[b][1] - pos[c2][1] > 2.0):
                            continue
                        lo, hi = pos[c2][1], pos[b][1]
                        ylo = lo + 0.1
                        yhi = min(hi, py) - 0.1
                        if form == "closer":
                            ylo = max(ylo, (lo + hi) / 2 + 0.1)
                        if yhi - ylo < 0.5:
                            continue
                        pt = (px, rng.uniform(ylo, yhi))
                if not spot_free(pt, pos, p):
                    continue
                if form == "closer":
                    s = (f"At {time}, {p} moved far enough {c} that {b} was behind them to the {OPPOSITE[c]}, "
                         f"{c2} still ahead to the {c}, and {p} was closer to {b} than to {c2}.")
                else:
                    s = rng.choice((
                        f"At {time}, {p} moved far enough {c} that they now saw {b} to the {OPPOSITE[c]} and {c2} to the {c}.",
                        f"At {time}, {p} walked {c}, passing well beyond {b}, and stopped where {c2} was still to the {c}.",
                    ))
                return dict(kind=kind, actor=p, c=c, b=b, c2=c2, np=pt, axis=AXIS[c],
                            exposed=("open", AXIS[c]), s=s)
            if form == "boot":
                step = rng.uniform(3, 15)
                pt = ((px + step) if c == EAST else (px - step) if c == WEST else px,
                      (py + step) if c == NORTH else (py - step) if c == SOUTH else py)
                if not spot_free(pt, pos, p):
                    continue
                s = (f"At {time}, {p} flung {rng.choice(ITEMS)} about {rng.randint(8, 40)} "
                     f"{rng.choice(UNITS)} {c} and then walked over to it.")
                return dict(kind=kind, actor=p, c=c, np=pt, axis=AXIS[c],
                            exposed=("open", AXIS[c]), s=s)
            # form == "while"
            step = rng.uniform(3, 12)
            pt = ((px + step) if c == EAST else (px - step) if c == WEST else px,
                  (py + step) if c == NORTH else (py - step) if c == SOUTH else py)
            if not spot_free(pt, pos, p):
                continue
            behind = [x for x in others if in_dir(pos[x], pt, OPPOSITE[c])]
            if not behind:
                continue
            b = rng.choice(behind)
            s = (f"At {time}, {p} walked {c} a good while until {b} was a good way "
                 f"behind them to the {OPPOSITE[c]}.")
            return dict(kind=kind, actor=p, c=c, b=b, np=pt, axis=AXIS[c],
                        exposed=("open", AXIS[c]), s=s)
        return None
    return None


MKINDS = (["cross"] * 3 + ["diag"] * 2 + ["asfar"] * 2 + ["mirror"] +
          ["halfway"] + ["opposite"] * 2 + ["swap"] * 2 + ["edge"] * 2 +
          ["far"] * 3)


def apply_event(pos, known, ev):
    """Apply an event to (pos, known).  known[name] = (x_exposed, y_exposed):
    the exposure markers — whether the text emitted so far exposes each
    coordinate of name exactly.  ev["exposed"] records what THIS sentence
    says: a tuple of pinned axes, ("open", axis) for a far walk (the
    sentence leaves that axis a mere range), or "swap" (the two people
    trade markers)."""
    p = ev["actor"]
    if ev["exposed"] == "swap":
        q = ev["q"]
        pos[p], pos[q] = pos[q], pos[p]
        known[p], known[q] = known[q], known[p]
        return
    pos[p] = ev["np"]
    ex = ev["exposed"]
    kx, ky = known[p]
    if ex == ("open", 0):
        known[p] = (False, ky)
    elif ex == ("open", 1):
        known[p] = (kx, False)
    else:
        known[p] = (True if 0 in ex else kx, True if 1 in ex else ky)

# ---------------------------------------------------------------- sightings

CLAUSES = (
    "{p} sees {q} to the {d}",
    "looking to the {d}, {p} can see {q}",
    "glancing that way, {p} spots {q} in the {d}",
    "{q} is off to the {d} of {p}",
    "{p} catches sight of {q} in the {d}",
    "to the {d}, {p} makes out {q}",
    "further {d} along, {p} finds {q} standing",
    "{p}'s eyes find {q} out in the {d}",
    "out in the {d}, {q} stands in view of {p}",
    "from {p}'s vantage point, {q} lies to the {d}",
    "{p} has {q} to the {d}",
)


def sight_sentence(rng, pos, p):
    """1-3 true clauses about what p can see from p's new spot (or '')."""
    others = [q for q in pos if q != p]
    if len(others) < 4:
        return ""
    dirs = {q: direction_of(pos[q], pos[p]) for q in others}
    by_dir = {}
    for q in others:
        by_dir.setdefault(dirs[q], []).append(q)
    n = rng.choice((1, 2, 2, 3))
    if len(by_dir) >= n:
        targets = [rng.choice(by_dir[d]) for d in rng.sample(list(by_dir), n)]
    else:
        targets = rng.sample(others, n)
    tpls = rng.sample(CLAUSES, n)
    clauses = [t.format(p=p, q=q, d=dirs[q]) for t, q in zip(tpls, targets)]
    s = clauses[0]
    for c in clauses[1:]:
        s += (", and " if rng.random() < 0.3 else ", ") + c
    return rng.choice(("Now, from the new spot, ", "Looking around, ", "")) + s + "."

# ------------------------------------------------------- simulation + pin --


def simulate(rng, people, n_moves, pos, known):
    """Run the move stream.  Returns (pos, events, known, last_minutes)
    or None if it gets stuck."""
    pos = dict(pos)
    known = {p: tuple(v) for p, v in known.items()}
    events = []
    minutes, prev_day = 6 * 60, -1
    for i in range(n_moves):
        day = min(3, i // max(1, n_moves // 4))
        if day != prev_day:
            prev_day = day
            minutes = 6 * 60
        minutes = min(minutes + rng.randint(12, 36), 20 * 60)
        time = fmt_time(minutes)
        ev = None
        for _ in range(300):
            ev = try_move(rng, pos, known, time)
            if ev:
                break
        if ev is None:
            return None
        apply_event(pos, known, ev)
        ev["day"], ev["time"] = day, time
        ev["sight"] = sight_sentence(rng, pos, ev["actor"])
        events.append(ev)
    return pos, events, known, minutes


def pin_pass(rng, people, pos, known, events, last_minutes):
    """Append closing moves until the text pins every coordinate.
    An open coordinate is always strictly inside the square, so a walk to
    an edge always works; a cross-alignment is the fallback.  Returns
    False if stuck (the caller regenerates the puzzle)."""
    while True:
        open_axes = [(p, ax) for p in people for ax in (0, 1) if not known[p][ax]]
        if not open_axes:
            return True
        for p, ax in open_axes:
            last_minutes = min(last_minutes + rng.randint(2, 8), 23 * 60)
            time = fmt_time(last_minutes)
            ev = None
            for _ in range(300):
                ev = (try_move(rng, pos, known, time, kind="edge", actor=p, axis=ax)
                      or try_move(rng, pos, known, time, kind="cross", actor=p, axis=ax))
                if ev:
                    break
            if ev is None:
                return False
            apply_event(pos, known, ev)
            ev["day"], ev["time"] = 3, time
            ev["sight"] = sight_sentence(rng, pos, p)
            events.append(ev)

# ------------------------------------------------------------------ decoys

DKINDS = ["plan"] * 2 + ["missee"] * 2 + ["old"] + ["tomorrow"] + ["stranger"] * 2


def make_decoy(rng, people):
    """A log entry that changes nothing.  The only numbers in the log
    besides the clock live in these, always in units that never measure
    the square."""
    kind = rng.choice(DKINDS)
    p = rng.choice(people)
    n = rng.randint(8, 40)
    unit = rng.choice(UNITS)
    if kind == "plan":
        c = rng.choice(CARDS)
        return (f"{p} had intended to walk a long way {c} once the food stalls packed up — "
                f"about {n} {unit}, by the warden's count — but the idea was dropped and "
                f"{p} stayed where they were.")
    if kind == "missee":
        q = rng.choice([x for x in people if x != p])
        return (f"At a distance it looked for a moment as though {p} had moved past {q}, "
                f"but when the crowd thinned, {p} was still exactly where they had been.")
    if kind == "old":
        return (f"An old festival map from last spring showed {p} at a spot that nobody in "
                f"this year's crowd was using.")
    if kind == "tomorrow":
        c = rng.choice(CARDS)
        return (f"The programme for the next day had {p} walking a long way {c} in the "
                f"lantern parade — some {n} {unit}, the programme said — but that was not today.")
    c1, c2 = rng.sample(CARDS, 2)
    return (f"A pair of marathon joggers cut across the square from the {c1} to the {c2} "
            f"— not one of our people, just passing through.")


FILLERS = (
    "The queue for the waffle stand wound its way around the fountain.",
    "The bakers' van idled in the shade along the west side of the square.",
    "A fiddler played from a corner of the square while the crowd swirled past.",
    "The lantern stringers climbed the poles along the north side.",
    "Somewhere in the crowd, a drumline warmed up for the evening parade.",
    "The warden's assistant dozed behind the notice board.",
    "A string of paper flags snapped gently in the breeze across the square.",
    "The coffee seller counted out change, very patiently, again.",
    "Kites of every shape drifted over the crowd from the south side.",
    "The ice-cream cart rolled slowly from one corner of the square to another.",
    "A photographer crouched by the fountain, waiting for the right moment.",
    "The smell of fresh bread drifted over from the bakery on the corner.",
    "Children raced each other from the fountain to the notice board and back.",
    "The musicians tuned their boxes once more before the afternoon set.",
    "A whole bunch of balloons rose in a sudden gust, and the seller ran after them.",
    "The clock tower chimed, and the crowd lifted its heads for a moment.",
    "Seagulls worked the edge of the square, chasing the chip-throwers.",
    "The banner over the fountain had gone slightly crooked in the wind.",
    "Someone's dog performed a very dignified lap of the fountain.",
    "The paper sellers called their headlines across the square to one another.",
)

# ------------------------------------------------------------------- text --

INTRO = (
    "This is the running position log of the Riverside Festival, held over four days "
    "in the old market square, from the opening ceremony on Monday through the lantern "
    "walk on Thursday. The old fountain stands at the exact centre of the square. A "
    "person 'to the east' of another simply stands further east (likewise 'to the "
    "north', 'to the west' or 'to the south'); 'to the northwest' means further west "
    "and further north at once. 'Level with' means on the same east-west line, that "
    "is, neither further north nor further south; 'in line with' means on the same "
    "north-south line, neither further east nor further west. Walking east or west "
    "never makes a person further north or further south, and walking north or south "
    "never makes them further east or further west. The opening arrangement below "
    "places everybody. What follows records every actual change of position among the "
    "people named, each one accompanied by what the mover could see from the new spot. "
    "The log never states a distance anyone walked — the only numbers in it are clock "
    "times and a warden's guesses in units that never measure anything (frog-leaps and "
    "the like) — so the positions have to be worked out from who stands where relative "
    "to whom. Planned walks that never happened, misreadings of the crowd, notes from "
    "older maps and next-day programme items are part of the record too, and they "
    "change nothing."
)

OUTRO = (
    "With that, the festival drew to a close. The organisers' own map of the final crowd "
    "— printed before the last walks of the lantern day — was, as always, a trifle wrong "
    "about where everyone had ended up."
)

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday")


def build_text(rng, people, init_sents, events, n_decoys, target_chars):
    """Assemble the puzzle text.  Returns (text, decoys_used)."""
    event_paras = []
    for ev in events:
        line = ev["s"] + ((" " + cap(ev["sight"])) if ev["sight"] else "")
        event_paras.append({"day": ev["day"], "line": line, "fillers": 0})
    decoys = [make_decoy(rng, people) for _ in range(n_decoys)]
    order = {d: [] for d in range(4)}
    for e in event_paras:
        order[e["day"]].append(("ev", e))
    for s in decoys:
        d = rng.randrange(4)
        order[d].insert(rng.randrange(len(order[d]) + 1), ("dec", s))
    used_fill = set()

    def render():
        paras = ["RIVERSIDE FESTIVAL — POSITION LOG", INTRO,
                 "The opening arrangement."]
        paras += [cap(s) for s in init_sents]
        paras.append("---")
        for d in range(4):
            paras.append(DAYS[d])
            for kind, item in order[d]:
                paras.append(cap(item["line"]) if kind == "ev" else cap(item))
        paras.append(OUTRO)
        return "\n\n".join(paras) + "\n"

    text = render()
    guard = 0
    while len(text) < target_chars and guard < 3000:
        guard += 1
        candidates = [e for e in event_paras if e["fillers"] < 2]
        if rng.random() < 0.6 and candidates:
            e = rng.choice(candidates)
            opts = [f for f in FILLERS if f not in used_fill]
            if not opts:
                break
            f = rng.choice(opts)
            used_fill.add(f)
            e["line"] += " " + f
            e["fillers"] += 1
        else:
            s = make_decoy(rng, people)
            decoys.append(s)
            d = rng.randrange(4)
            order[d].insert(rng.randrange(len(order[d]) + 1), ("dec", s))
        text = render()
    return text, decoys

# ------------------------------------------------------- answers / solution


def pick_corners(rng, pos, people):
    """A pair (nw, se) with 5-8 people strictly inside the axis-aligned
    square between their final positions, or None."""
    for _ in range(400):
        a, b = rng.sample(people, 2)
        ax, ay = pos[a]
        bx, by = pos[b]
        if not (ax < bx and ay > by):
            continue
        inside = [p for p in people
                  if ax < pos[p][0] < bx and by < pos[p][1] < ay]
        if 5 <= len(inside) <= 8:
            return a, b, inside
    return None


def make_question(a, b, p2, p3):
    return (
        "Read the festival log above carefully, then answer both questions.\n"
        "1. Which people are standing within the square whose sides run east–west "
        "and north–south, with "
        f"{a}'s final position at its north-west corner and {b}'s final position at "
        "its south-east corner? List every person strictly inside that square "
        "(nobody on the boundary counts), no more, no less.\n"
        f"2. At the close of the festival, where was {p2} standing relative to the "
        f"fountain, and where were they relative to {p3}? Use the eight directions "
        "of the log: north, south, east, west, northeast, northwest, southeast, "
        "southwest.\n"
        "Keep in mind: walking east or west never makes a person further north or "
        "further south, walking north or south never makes them further east or "
        "further west, and a person who stands north-east of one person and "
        "south-west of another stands between the two."
    )


def ledger(people, init_pos, events, final_pos):
    """Compact per-event state dump for human checkers.  The solver never
    sees this; it lives in solution.txt only.  Coordinates are relative to
    the fountain."""
    codes = {p: p[0] for p in people}

    def compact(st):
        return " ".join(f"{codes[p]}=({fmt(st[p][0] - FX)},{fmt(st[p][1] - FY)})"
                        for p in people)

    lines = [f"MOVE LEDGER  ({' '.join(codes[p] + '=' + p for p in people)})",
             f"Initial: {compact(init_pos)}"]
    st = dict(init_pos)
    for ev in events:
        k, p = ev["kind"], ev["actor"]
        if k == "swap":
            act = f"swap {p} <-> {ev['q']}"
            st[p], st[ev["q"]] = st[ev["q"]], st[p]
        elif k == "cross":
            act = f"cross {p} {ev['c']} (aligned with {ev['q']})"
            st[p] = ev["np"]
        elif k == "diag":
            act = f"diag {p} (line of {ev['q']}, level with {ev['r']})"
            st[p] = ev["np"]
        elif k == "asfar":
            act = f"asfar {p} {ev['c']} (matching {ev['q']}'s offset)"
            st[p] = ev["np"]
        elif k == "mirror":
            act = f"mirror {p} of {ev['r']} about {ev['q']}"
            st[p] = ev["np"]
        elif k == "halfway":
            act = f"halfway {p} between {ev['q']} and {ev['r']}"
            st[p] = ev["np"]
        elif k == "opposite":
            act = f"opposite {p} of {ev['q']}"
            st[p] = ev["np"]
        elif k == "edge":
            act = f"edge {p} to {ev['c']} edge"
            st[p] = ev["np"]
        elif k == "far":
            act = f"far {p} {ev['c']} (coordinate left open)"
            st[p] = ev["np"]
        else:
            act = f"?? {k}"
        lines.append(f"D{ev['day'] + 1} {ev['time']}  {act:44s} [{compact(st)}]")
    lines.append(f"Final:   {compact(final_pos)}")
    return "\n".join(lines)


def make_solution(seed, people, pos, a, b, inside, p2, p3, init_pos, events):
    d1 = direction_of(pos[p2], (FX, FY))
    d2 = direction_of(pos[p2], pos[p3])
    lines = [f"FINDING PEOPLE — SOLUTION KEY (seed {seed})", "",
             "FINAL ANSWERS",
             f"  Q1 (square between {a} (NW corner) and {b} (SE corner)): {', '.join(inside)}",
             f"  Q2: {p2} was {d1} of the fountain, and {d2} of {p3}.",
             "",
             "EXACT POSITIONS  (hidden verification grid only — 0 to 100 metres east "
             "and north of the square's south-west corner; the puzzle itself never "
             "states any of this)"]
    for p in people:
        x, y = pos[p]
        lines.append(f"  {p} = ({fmt(x - FX)}, {fmt(y - FY)})")
    lines += ["",
              ledger(people, init_pos, events, pos)]
    return "\n".join(lines) + "\n"


UNIT_ALT = "|".join(UNITS)


def anti_grep_ok(text, decoys, inside):
    """The numbers in the puzzle must be exactly: clock times, and fake-unit
    counts (decoys and the tossed-boot walks).  No real measurement, no
    coordinate pair, anywhere."""
    body = text.replace(INTRO, "", 1)
    if re.search(r"\d+(?:\.\d+)?\s*,\s*\d+", body):
        return False  # a coordinate pair
    body = re.sub(r"\b\d{1,2}:\d{2}\b", "", body)  # clock times
    for s in decoys:
        body = body.replace(cap(s), "")
    body = re.sub(rf"(?:about|some) \d+ (?:{UNIT_ALT})", "", body)  # fake units
    if re.search(r"\d", body):
        return False  # a digit with no business being there
    if len(inside) >= 2:
        names = set(inside)
        for line in body.splitlines():
            words = {w.strip(".,;:") for w in line.split()}
            if names <= words:
                return False  # the full answer list on one line
    return True

# ----------------------------------------------------------------- generate


def generate(tokens, seed, n_people=None, n_moves=None, decoy_ratio=0.8):
    """Generate a puzzle.  Returns (text, question, solution, seed_used,
    meta) where meta carries everything the tests (and the ledger) need."""
    target_chars = tokens * 4
    n_people = n_people or min(26, 12 + tokens // 6000)
    # ~85 tokens per move (move sentence + its sighting clause + decoys)
    n_moves = n_moves or max(20, tokens // 85)
    for attempt in range(300):
        rng = random.Random(seed + attempt)
        people = rng.sample(ROSTER, n_people)
        got = opening(rng, people)
        if got is None:
            continue
        init_pos, init_sents = got
        # the opening sentences each pin both coordinates of their person
        # (the tests verify this from the text), so everyone starts pinned
        known = {p: (True, True) for p in people}
        res = simulate(rng, people, n_moves, init_pos, known)
        if res is None:
            continue
        pos, events, known, last_minutes = res
        if not pin_pass(rng, people, pos, known, events, last_minutes):
            continue
        if not all(known[p][0] and known[p][1] for p in people):
            continue
        picked = pick_corners(rng, pos, people)
        if picked is None:
            continue
        a, b, inside = picked
        p2 = rng.choice([p for p in people
                         if p not in (a, b) and pos[p] != (FX, FY)])
        p3 = rng.choice([p for p in people if p not in (a, b, p2)])
        text, decoys = build_text(rng, people, init_sents, events,
                                  int(n_moves * decoy_ratio), target_chars)
        if not anti_grep_ok(text, decoys, inside):
            continue
        question = make_question(a, b, p2, p3)
        solution = make_solution(seed + attempt, people, pos, a, b, inside,
                                 p2, p3, init_pos, events)
        meta = dict(people=people, pos=pos, init_pos=init_pos, events=events,
                    init_sents=init_sents, a=a, b=b, inside=inside, p2=p2, p3=p3,
                    decoys=decoys, known=known)
        return text, question, solution, seed + attempt, meta
    raise RuntimeError("could not generate a valid puzzle after 300 attempts")

# -------------------------------------------------------------------- main --


def main():
    ap = argparse.ArgumentParser(description="Finding-people puzzle generator")
    ap.add_argument("--tokens", type=int, default=16000,
                    help="approximate target token count (chars/4)")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--people", type=int, default=None)
    ap.add_argument("--moves", type=int, default=None)
    ap.add_argument("--decoy-ratio", type=float, default=0.8)
    ap.add_argument("--out", required=True, help="output directory")
    args = ap.parse_args()

    text, question, solution, seed_used, _ = generate(
        args.tokens, args.seed if args.seed is not None else random.randrange(10 ** 9),
        args.people, args.moves, args.decoy_ratio)

    import os
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "puzzle.txt"), "w") as f:
        f.write(text)
    with open(os.path.join(args.out, "question.txt"), "w") as f:
        f.write(question + "\n")
    with open(os.path.join(args.out, "solution.txt"), "w") as f:
        f.write(solution)
    print(f"seed {seed_used}: {len(text)} chars, "
          f"{len(_['people'])} people, {len(_['events'])} moves -> {args.out}")


if __name__ == "__main__":
    main()
