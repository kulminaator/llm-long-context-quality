#!/usr/bin/env python3
"""
Perplexity stress-test generator (rewritten from scratch).

Produces a long, natural-language "audit log" in which the water volume of
six tanks is changed by a stream of REAL events, interleaved with DECOY
events and dense, varied filler:

  real events : transfers, intakes, drains, slow leaks, "bled down until the
                gauge read exactly N", "moved the same volume the tank already
                held", "filled to exactly twice its previous volume",
                weather-conditional intake ("if sunlight was visible, the
                tank is to receive N extra liters") whose effect depends on
                that day's weather record, stated once at the top of the day
                (many such instructions are false flags that never fire),
                phone-interruption intake ("meaning to add N liters but
                ... ending up adding M times the intended amount", followed
                by accidentally draining only D liters — the net is a bit
                above the intended N, and none of M*N or the net is stated)
  decoys      : shelved proposals, conditional protocols that did NOT fire,
                misread gauges, notes from earlier shifts, next-day plans,
                the overflow basin / waste line (explicitly not a tank)
  filler      : dozens of distinct sentence templates with random slots, so
                there is no repeated line to skip over

The follow-up question asks for exact end-state volumes of specific tanks.
The answer is never written anywhere in the text — it can only be obtained
by faithfully tracking every state change.  Anti-grep guarantees, enforced
in code:

  * the final answer values never appear in the text, neither as digit
    strings (checked against every maximal digit run) nor as spelled-out
    words
  * amounts are sometimes rendered as words ("fourteen") or as tiny
    arithmetic expressions ("17 plus 6") so digit-grepping is incomplete
  * some amounts are given as repeated batches ("7 liters were repeatedly
    added until the added amount exceeded 20 liters"), so the true amount
    (the smallest multiple of the batch size above the threshold) must be
    computed, not read off
  * the hardest events deliberately omit their numbers, forcing the model
    to know the current state of a tank

Outputs (defaults):
  water_tank_log.txt   the long text
  question.txt      the follow-up question
  answer_key.txt    final answers + the full step-by-step ledger

Usage:
  python generator.py                          # 30k tokens, random seed
  python generator.py --tokens 60000 --seed 7  # long, reproducible
  python generator.py --combined prompt.txt    # also write text+question
"""

import argparse
import random
import re
import sys

TANKS = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta"]
DAYS = ["Monday, the 14th", "Tuesday, the 15th", "Wednesday, the 16th", "Thursday, the 17th"]

# -------------------------------------------------------------- weather ----

WARMTH = ["warm", "cold", "crisp", "mild"]
SKY = ["sunny", "overcast", "cloudy", "rainy", "drizzly"]


def make_weather(rng: random.Random):
    """Return (description, attrs) for one day's weather record.
    attrs: sun = sun rays visible, rain = any rain, windy = strong wind."""
    warmth = rng.choice(WARMTH)
    sky = rng.choice(SKY)
    windy = rng.random() < 0.35
    desc = f"a {warmth}" + (", windy" if windy else "") + f" {sky} day"
    attrs = dict(sun=(sky == "sunny"), rain=(sky in ("rainy", "drizzly")), windy=windy)
    return desc, attrs

# ---------------------------------------------------------------- numbers --

ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
        "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
        "sixteen", "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
        "eighty", "ninety"]


def num_words(n: int) -> str:
    if n >= 1000:
        th, r = divmod(n, 1000)
        return ONES[th] + " thousand " + num_words(r) if r else ONES[th] + " thousand"
    if n < 20:
        return ONES[n]
    if n < 100:
        t, o = divmod(n, 10)
        return TENS[t] + ("-" + ONES[o] if o else "")
    h, r = divmod(n, 100)
    s = ONES[h] + " hundred"
    if r:
        s += " " + num_words(r)
    return s


def render_repeat(rng: random.Random, n: int):
    """Return (x, y) for the phrasing "x liters were repeatedly added until
    the added amount exceeded y liters", whose implied total is the smallest
    multiple of x strictly greater than y — which equals n by construction
    (x divides n, y in [n-x, n-1]).  None if n has no usable divisor."""
    divs = [d for d in range(2, min(16, n // 2) + 1) if n % d == 0]
    if not divs:
        return None
    x = rng.choice(divs)
    y = rng.randint(n - x, n - 1)
    return x, y


def render_amount(rng: random.Random, n: int) -> str:
    """Render a number as digits, words, or a tiny arithmetic expression."""
    r = rng.random()
    if r < 0.60:
        return str(n)
    if r < 0.88:
        return num_words(n)
    a = rng.randint(1, n - 1)
    if rng.random() < 0.8:
        return f"{a} plus {n - a}"
    b = rng.randint(2, 4)
    return f"{n + 2 * b} minus {2 * b}"


# ----------------------------------------------------------------- filler --

CREW = ["Mirela", "Okafor", "Dunn", "Petrov", "Lindqvist", "Achebe"]
AREAS = ["the intake hall", "the filtration gallery", "the pump room",
         "the control booth", "the east yard", "the chemical store",
         "the sludge bay", "the north catwalk"]
EQUIP = ["clarifier", "dosing pump", "UV array", "sludge auger",
         "backwash manifold", "feed grinder"]
ITEMS = ["filter media", "coagulant drums", "gaskets", "sensor probes",
         "safety gloves", "calibration weights"]
COMPANIES = ["Hargrove & Sons", "Meridian Supply Co.", "Kestrel Industrial"]
NOISES = ["tick", "hum", "clunk", "groan"]
DIRECTIONS = ["north", "south", "east", "west", "northeast", "southwest"]
UNITS = ["°C", "kPa", "percent", "rpm"]

FILLER_TEMPLATES = [
    "The {sensor} in {area} read {n1} {unit} at the top of the hour.",
    "The {sensor} on the {equip} reported {n1} {unit}, comfortably within tolerance.",
    "A {sensor} alarm tone sounded once in {area} and cleared itself.",
    "{crew} spent the morning calibrating the {equip} in {area}.",
    "{crew} radioed the control booth to confirm that the {equip} schedule was unchanged.",
    "{crew} mentioned that the {item} supplier had raised prices again.",
    "{crew} noted in the log that the {equip} sounded 'a bit tired,' which was not a rated condition.",
    "The {equip} gave off a faint {noise} that no one could quite identify.",
    "The {equip} ran hotter than {n1} degrees for a few minutes before settling.",
    "The {equip} maintenance tag in {area} had been replaced with a handwritten one.",
    "The generator in the pump room cycled on briefly when the {equip} drew extra current.",
    "A delivery of {item} arrived, palletized and short by {small} units.",
    "The {item} inventory count came in {small} under the spreadsheet figure.",
    "A forklift moved two pallets of {item} into {area}.",
    "A contractor from {company} inspected the {equip} and signed the clipboard without comment.",
    "Frost formed on the north-facing panels of {area}.",
    "Dust from {area} drifted across the walkway and onto the {equip}.",
    "The shift handover note was, as usual, a single word: fine.",
    "Security logs show a visitor badge scanned at a gate near {area} at {time}.",
    "The barometer hovered near {n1} millibars all day.",
    "Someone left a coffee cup on the {equip} housing. It was still warm when {crew} found it.",
    "A crow landed on the {equip} and watched the work with what could only be called interest.",
    "Crews repainted {area} after the last audit flagged peeling around the {equip}.",
]


def filler_sentence(rng: random.Random, safe, used: set = None) -> str:
    for _ in range(20):
        t = rng.choice(FILLER_TEMPLATES)
        sensor = f"Sensor {rng.randint(2, 40)}-{rng.choice('ABCDEF')}"
        dir1 = rng.choice(DIRECTIONS)
        dir2 = rng.choice([d for d in DIRECTIONS if d != dir1])
        s = t.format(
        sensor=sensor,
        area=rng.choice(AREAS),
        equip=rng.choice(EQUIP),
        item=rng.choice(ITEMS),
        crew=rng.choice(CREW),
        company=rng.choice(COMPANIES),
        noise=rng.choice(NOISES),
        dir1=dir1,
        dir2=dir2,
        unit=rng.choice(UNITS),
        time=f"{rng.randint(6, 18):02d}:{rng.choice(['04', '15', '30', '47'])}",
            n1=safe(10, 90),
            small=rng.randint(1, 9),
        )
        if used is None or s not in used:
            if used is not None:
                used.add(s)
            return s
    return s  # pool exhausted; allow a repeat as last resort


def filler_paragraph(rng: random.Random, safe, n: int = 0, used: set = None) -> str:
    k = n or rng.randint(2, 5)
    out = []
    while len(out) < k:
        out.append(filler_sentence(rng, safe, used))
    return " ".join(out)


def safe(rng: random.Random, lo: int, hi: int, avoid: set) -> int:
    while True:
        v = rng.randint(lo, hi)
        if v not in avoid:
            return v


# -------------------------------------------------------------- simulation --

# weighted bag of real event kinds
KINDS = ["transfer"] * 3 + ["intake"] * 2 + ["waste"] * 2 + ["evap"] + \
        ["drain_to"] + ["mirror"] * 2 + ["double"] + ["wx"] * 2 + ["phone"]


def make_event(rng: random.Random, state: dict, time: str):
    """Create a valid real event (or None if the kind is inapplicable)."""
    kind = rng.choice(KINDS)
    if kind == "transfer":
        s, d = rng.sample(TANKS, 2)
        hi = min(70, state[s] - 15)
        if hi < 10:
            return None
        return dict(kind=kind, src=s, dst=d, amt=rng.randint(10, hi), time=time)
    if kind == "intake":
        return dict(kind=kind, src=rng.choice(TANKS), amt=rng.randint(15, 80), time=time)
    if kind == "waste":
        s = rng.choice(TANKS)
        hi = min(60, state[s] - 20)
        if hi < 10:
            return None
        return dict(kind=kind, src=s, amt=rng.randint(10, hi), time=time)
    if kind == "evap":
        s = rng.choice(TANKS)
        hi = min(15, state[s] - 5)
        if hi < 3:
            return None
        return dict(kind=kind, src=s, amt=rng.randint(3, hi), time=time)
    if kind == "drain_to":
        s = rng.choice(TANKS)
        k = rng.randint(80, 140)
        if abs(k - state[s]) < 15:
            return None
        return dict(kind=kind, src=s, amt=k, time=time)
    if kind == "mirror":
        # move into A exactly what A already holds, drawing from B
        a, b = rng.sample(TANKS, 2)
        if state[b] < state[a] + 5:
            return None
        return dict(kind=kind, src=a, dst=b, amt=state[a], time=time)
    if kind == "double":
        s = rng.choice(TANKS)
        if state[s] * 2 > 1600:
            return None
        return dict(kind=kind, src=s, amt=state[s], time=time)
    if kind == "wx":
        # conditional intake: fires only if the day's weather meets the condition
        return dict(kind=kind, src=rng.choice(TANKS), amt=rng.randint(20, 90),
                    cond=rng.choice(["sun", "dry", "wind"]), time=time)
    if kind == "phone":
        # operator means to add I, phone distraction makes it M*I, the follow-up
        # drain of D = (M-1)*I - excess is short of the full correction, so the
        # net addition (M*I - D) is a bit above the intended I.  The drain
        # follows the addition inside this same event, so the level never dips.
        s = rng.choice(TANKS)
        intended = rng.randint(20, 80)
        mult = rng.randint(2, 4)
        excess = rng.randint(2, max(3, intended // 3))
        drain = (mult - 1) * intended - excess
        if drain < 5:
            return None
        return dict(kind=kind, src=s, amt=mult * intended - drain,
                    intended=intended, mult=mult, drain=drain, time=time)
    return None


def apply_event(state: dict, ev: dict, wx: dict) -> None:
    k = ev["kind"]
    if k == "transfer":
        state[ev["src"]] -= ev["amt"]
        state[ev["dst"]] += ev["amt"]
    elif k == "intake":
        state[ev["src"]] += ev["amt"]
    elif k in ("waste", "evap"):
        state[ev["src"]] -= ev["amt"]
    elif k == "drain_to":
        state[ev["src"]] = ev["amt"]
    elif k == "mirror":
        state[ev["dst"]] -= ev["amt"]
        state[ev["src"]] += ev["amt"]
    elif k == "double":
        state[ev["src"]] *= 2
    elif k == "wx":
        c = ev["cond"]
        fired = wx["sun"] if c == "sun" else (not wx["rain"] if c == "dry" else wx["windy"])
        ev["fired"] = fired
        if fired:
            state[ev["src"]] += ev["amt"]
    elif k == "phone":
        state[ev["src"]] += ev["amt"]  # amt is already the net (M*I - drain)


def ledger_line(day: int, ev: dict, state: dict) -> str:
    st = " ".join(f"{t[0]}={state[t]}" for t in TANKS)
    k = ev["kind"]
    if k == "transfer":
        act = f"transfer {ev['amt']} L {ev['src']} -> {ev['dst']}"
    elif k == "intake":
        act = f"intake +{ev['amt']} L into {ev['src']}"
    elif k == "waste":
        act = f"waste -{ev['amt']} L from {ev['src']}"
    elif k == "evap":
        act = f"leak -{ev['amt']} L from {ev['src']}"
    elif k == "drain_to":
        act = f"{ev['src']} bled down to {ev['amt']} L"
    elif k == "mirror":
        act = f"{ev['src']} doubled (took its own volume, {ev['amt']} L, from {ev['dst']})"
    elif k == "wx":
        cond = {"sun": "sun", "dry": "no rain", "wind": "windy"}[ev["cond"]]
        act = (f"wx-instr +{ev['amt']} L into {ev['src']} (if {cond}) "
               f"{'FIRED' if ev['fired'] else 'not fired'}")
    elif k == "phone":
        act = (f"phone-intake net +{ev['amt']} L into {ev['src']} "
               f"(meant {ev['intended']}, x{ev['mult']}, drained {ev['drain']})")
    else:
        act = f"{ev['src']} doubled to {state[ev['src']]} L (intake)"
    return f"D{day} {ev['time']}  {act:42s} [{st}]"


def simulate(rng: random.Random, n_events: int):
    """Run the real event stream.
    Returns (events, snapshots, initial, final, weather) where weather maps
    day index -> (description, attrs)."""
    initial = {t: rng.randint(150, 700) for t in TANKS}
    state = dict(initial)
    weather = {d: make_weather(rng) for d in range(4)}
    events, snapshots = [], []
    minutes, prev_day = 6 * 60, -1
    for i in range(n_events):
        day = min(3, i // max(1, n_events // 4))
        if day != prev_day:
            minutes, prev_day = 6 * 60, day
        minutes += rng.randint(25, 70)
        minutes = min(minutes, 19 * 60 + 50)
        time = f"{minutes // 60:02d}:{minutes % 60:02d}"
        ev = None
        while ev is None:
            ev = make_event(rng, state, time)
        apply_event(state, ev, weather[day][1])
        ev["day"] = day
        events.append(ev)
        snapshots.append(dict(state))
    return events, snapshots, initial, state, weather


# ---------------------------------------------------------------- decoys ---

DECOY_KINDS = ["shelved"] * 3 + ["unmet"] * 3 + ["old_note"] * 2 + \
              ["misread"] * 2 + ["future"] * 2 + ["basin"]


def make_decoy(rng: random.Random, state: dict, avoid: set):
    kind = rng.choice(DECOY_KINDS)
    safe = lambda lo, hi: safe_(rng, lo, hi, avoid)
    if kind == "shelved":
        s, d = rng.sample(TANKS, 2)
        return dict(kind=kind, src=s, dst=d, amt=safe(10, 60))
    if kind == "unmet":
        s = rng.choice(TANKS)
        return dict(kind=kind, src=s, thr=state[s] + rng.randint(10, 80), amt=safe(10, 40))
    if kind == "old_note":
        s = rng.choice(TANKS)
        return dict(kind=kind, src=s, amt=safe(50, 900))
    if kind == "misread":
        s = rng.choice(TANKS)
        fake = max(10, state[s] + rng.choice([-1, 1]) * rng.randint(5, 40))
        return dict(kind=kind, src=s, amt=safe(max(1, fake - 5), fake + 5))
    if kind == "future":
        d = rng.choice(TANKS)
        return dict(kind=kind, dst=d, amt=safe(15, 70))
    if kind == "basin":
        return dict(kind=kind, amt=safe(5, 40))
    return None


def safe_(rng, lo, hi, avoid):
    return safe(rng, lo, hi, avoid)


def render_decoy(rng: random.Random, d: dict) -> str:
    k = d["kind"]
    a = render_amount(rng, d.get("amt", 0))
    if k == "shelved":
        return rng.choice([
            f"There was talk of moving {a} liters from Tank {d['src']} to Tank {d['dst']}, "
            f"but the proposal was shelved before the shift ended.",
            f"{rng.choice(CREW)} suggested pumping {a} liters out of Tank {d['src']}, "
            f"and the idea was quietly dropped.",
            f"A transfer of {a} liters from {d['src']} to {d['dst']} was pencilled into the plan, "
            f"then crossed out again.",
        ])
    if k == "unmet":
        return (f"Protocol required that, if Tank {d['src']} exceeded {d['thr']} liters, "
                f"{a} liters be drained to the waste line. The reading came in below the "
                f"threshold, so nothing was drained.")
    if k == "old_note":
        return (f"A note left by an earlier shift claimed that Tank {d['src']} held "
                f"{render_amount(rng, d['amt'])} liters, but the current gauge reading told "
                f"a different story.")
    if k == "misread":
        return (f"The gauge on Tank {d['src']} flickered, briefly showing "
                f"{render_amount(rng, d['amt'])}, but {rng.choice(CREW)} dismissed it as a "
                f"sensor fault.")
    if k == "future":
        return f"The schedule for the following day called for pumping {a} liters into Tank {d['dst']}."
    if k == "basin":
        return (f"The overflow basin outside the plant — not one of the six tanks — shed "
                f"{a} liters into the storm drain.")
    return ""


# --------------------------------------------------------------- rendering --

def render_event(rng: random.Random, ev: dict) -> str:
    k, t = ev["kind"], ev["time"]
    amt = render_amount(rng, ev["amt"])
    if rng.random() < 0.15:
        rr = render_repeat(rng, ev["amt"])
        if rr:
            x, y = rr
            if k == "transfer":
                return (f"At {t}, the main pump moved {x} liters from Tank {ev['src']} to "
                        f"Tank {ev['dst']} in repeated cycles, continuing until the moved "
                        f"amount had exceeded {y} liters.")
            if k == "intake":
                return (f"At {t}, the intake line fed {x} liters into Tank {ev['src']} over "
                        f"and over, stopping only once the amount added that way had "
                        f"exceeded {y} liters.")
            if k == "waste":
                return (f"At {t}, {x} liters were repeatedly drawn from Tank {ev['src']} into "
                        f"the waste line, continuing until the drawn amount had exceeded "
                        f"{y} liters.")
            if k == "evap":
                return (f"A faulty seal let {x} liters seep out of Tank {ev['src']} in repeated "
                        f"spurts, the seepage continuing until the lost amount had exceeded "
                        f"{y} liters.")
    if k == "transfer":
        return rng.choice([
            f"At {t}, the main pump moved {amt} liters from Tank {ev['src']} to Tank {ev['dst']}.",
            f"Tank {ev['src']} supplied {amt} liters to Tank {ev['dst']} at {t}.",
            f"At {t}, {amt} liters were transferred from Tank {ev['src']} into Tank {ev['dst']}.",
            f"A transfer of {amt} liters ran from Tank {ev['src']} to Tank {ev['dst']} at {t}.",
        ])
    if k == "intake":
        return rng.choice([
            f"At {t}, the intake line fed {amt} liters into Tank {ev['src']}.",
            f"Tank {ev['src']} received {amt} liters from the municipal intake at {t}.",
        ])
    if k == "waste":
        return rng.choice([
            f"At {t}, {amt} liters were drawn from Tank {ev['src']} into the waste line.",
            f"The waste valve on Tank {ev['src']} was opened at {t}, removing {amt} liters.",
        ])
    if k == "evap":
        return rng.choice([
            f"A faulty seal let {amt} liters seep out of Tank {ev['src']} sometime during the shift.",
            f"An undetected leak cost Tank {ev['src']} {amt} liters by the end of the day.",
        ])
    if k == "drain_to":
        return rng.choice([
            f"The technician bled Tank {ev['src']} down until the gauge read exactly {amt} liters.",
            f"Tank {ev['src']} was drawn down at {t} until exactly {amt} liters remained.",
        ])
    if k == "mirror":
        return rng.choice([
            f"At {t}, the operator moved into Tank {ev['src']} exactly the volume it already held, "
            f"drawing the water from Tank {ev['dst']}.",
            f"Tank {ev['src']} was doubled in place at {t} by a siphon fed from Tank {ev['dst']}.",
        ])
    if k == "double":
        return (f"Maintenance topped Tank {ev['src']} off to exactly twice its previous volume "
                f"at {t}, drawing from the municipal intake.")
    if k == "wx":
        # deliberately states no outcome: the effect depends on the day's weather record
        cond = {"sun": "if sunlight was visible",
                "dry": "on a day without rain",
                "wind": "if it had been windy"}[ev["cond"]]
        crew = rng.choice(CREW)
        return (f"At {t}, {crew} went outside to check the weather and then followed the "
                f"standing instruction for Tank {ev['src']}: {cond}, the tank is to receive "
                f"{amt} extra liters.")
    if k == "phone":
        # states the intended amount and the multiplier, never the pumped total
        # (M*I) nor the net (M*I - drain): both must be computed
        crew = rng.choice(CREW)
        i_amt = render_amount(rng, ev["intended"])
        d_amt = render_amount(rng, ev["drain"])
        return (f"At {t}, {crew} was meaning to add {i_amt} liters to Tank {ev['src']} but "
                f"glancing at their phone while the pump ran and ending up adding "
                f"{ev['mult']} times the intended amount. They followed up by accidentally "
                f"draining only {d_amt} liters from Tank {ev['src']}.")
    return ""


INTRO = (
    "This is the consolidated audit log for the Meridian Water Reclamation "
    "Facility, covering the four working days from Monday the 14th through "
    "Thursday the 17th. The facility holds treated water pending release in "
    "six tanks, designated Alpha, Beta, Gamma, Delta, Epsilon, and Zeta. All "
    "volumes are stated in liters. The overflow basin outside the plant and "
    "the waste line are not tanks and are not part of the audit. The log "
    "below is a faithful merge of pump records, shift notes, and supervisor "
    "entries; where the shifts disagreed, the corrected reading is the one "
    "that stands. Each day's entry opens with that day's weather record, and "
    "any standing instruction that refers to the weather always means the "
    "conditions recorded in that day's opening line."
)


def build_text(rng: random.Random, events, decoys, avoid: set, target_chars: int,
               initial: dict = None, weather: dict = None) -> str:
    safe = lambda lo, hi: safe_(rng, lo, hi, avoid)

    # opening line stating the original volumes before the audit window
    init_line = ""
    if initial:
        init_line = (
            "At the start of the audit window, before any of the recorded "
            "shifts began, the morning readings stood at "
            + ", ".join(f"{t} {initial[t]} liters" for t in TANKS)
            + "."
        )

    # render fixed content first so we can budget the filler
    rendered_events = {id(ev): render_event(rng, ev) for ev in events}
    rendered_decoys = [render_decoy(rng, d) for d in decoys]
    fake_total = safe(1000, 3000)
    outro = (
        "With that, the audit window closed. The intake manifest for the week — compiled "
        f"before the final transfers — listed total facility holdings at {fake_total} "
        "liters, a figure the auditors never corroborated against the gauges."
    )

    used_fill = set()   # never repeat a filler sentence verbatim
    used_decoy = set()  # never repeat a decoy sentence verbatim

    fixed = len(INTRO) + len(init_line) + len(outro)
    fixed += sum(len(s) for s in rendered_events.values())
    fixed += sum(len(s) for s in rendered_decoys)
    fixed += 4 * 40  # day headers

    # distribute filler paragraphs: one before each event, extras after
    paras_total = max(1, (target_chars - fixed) // 230)
    per = paras_total // len(events)
    extra = paras_total - per * len(events)

    parts = ["MERIDIAN WATER RECLAMATION FACILITY — AUDIT LOG\n", INTRO + "\n"]
    if init_line:
        parts.append(init_line + "\n")
    day = -1
    for i, ev in enumerate(events):
        if ev["day"] != day:
            day = ev["day"]
            parts.append(f"--- {DAYS[day]} ---\n")
            if weather:
                parts.append(f"It was {weather[day][0]}.\n")
        before = filler_paragraph(rng, safe, max(1, per + (1 if i < extra else 0)), used_fill)
        parts.append(before + "\n")
        ev_para = rendered_events[id(ev)]
        if rng.random() < 0.5:
            ev_para += " " + filler_sentence(rng, safe, used_fill)
        parts.append(ev_para + "\n")
        # attach a decoy to roughly half the events, right after the event
        di = i // 2
        if di < len(decoys) and rendered_decoys[di] not in used_decoy:
            used_decoy.add(rendered_decoys[di])
            parts.append(rendered_decoys[di] + "\n")
        if i < extra:
            parts.append(filler_paragraph(rng, safe, used=used_fill) + "\n")

    parts.append(outro + "\n")
    text = "\n".join(parts)

    # top up to hit the target length
    while len(text) < target_chars * 0.97:
        text += "\n" + filler_paragraph(rng, safe, rng.randint(3, 5), used_fill) + "\n"
    return text


def anti_grep_ok(text: str, avoid: set) -> bool:
    """The avoid-set numbers must not appear as digit runs or as words."""
    runs = set(int(x) for x in re.findall(r"\d+", text))
    if runs & avoid:
        return False
    low = text.lower()
    for v in avoid:
        if num_words(v) in low:
            return False
    return True


# ------------------------------------------------------------------ main ---

def generate(tokens: int, seed: int, n_events: int, decoy_ratio: float):
    target_chars = tokens * 4
    for attempt in range(300):
        rng = random.Random(seed + attempt)

        events, snapshots, initial, final, weather = simulate(rng, n_events)
        finals = list(final.values())
        top = max(finals)
        # unique maximum, and no final value equal to an initial one (anti-grep)
        if finals.count(top) != 1:
            continue
        if set(finals) & set(initial.values()):
            continue
        avoid = set(finals) | {sum(finals)}

        n_decoys = int(n_events * decoy_ratio)
        decoys = []
        # decoy k is printed right after real event 2*k (see build_text), so it
        # must be constructed from the state at that placement point — not from
        # a random snapshot — otherwise e.g. an "unmet" decoy's "the reading
        # came in below the threshold" claim can contradict the actual log
        for k in range(n_decoys):
            idx = min(2 * k, len(snapshots) - 1)
            d = None
            while d is None:
                d = make_decoy(rng, snapshots[idx], avoid)
            decoys.append(d)

        text = build_text(rng, events, decoys, avoid, target_chars, initial, weather)
        if not anti_grep_ok(text, avoid):
            continue

        # question: part 1 asks the SECOND-largest tank (trap: not the max)
        ranked = sorted(TANKS, key=lambda t: final[t], reverse=True)
        q1_tank, q2_tank = ranked[1], ranked[0]

        ledger = "\n".join(
            ledger_line(ev["day"] + 1, ev, snapshots[i])
            for i, ev in enumerate(events)
        )
        answer_key = f"""PERPLEXITY STRESS TEST — ANSWER KEY (seed {seed + attempt})

FINAL ANSWERS
  Q1: Tank {q1_tank} held {final[q1_tank]} liters at the close of the audit.
  Q2: Tank {q2_tank} held the greatest volume: {final[q2_tank]} liters.

FULL LEDGER  (A=Alpha B=Beta G=Gamma D=Delta E=Epsilon Z=Zeta, liters)
Initial: {" ".join(f"{t}={initial[t]}" for t in TANKS)}
{ledger}
Final:   {" ".join(f"{t}={final[t]}" for t in TANKS)}
"""
        question = (
            "Read the audit log above carefully. Answer the following:\n"
            f"1. At the close of the audit (end of the Thursday shift), how many liters "
            f"of water were in Tank {q1_tank}?\n"
            f"2. Which of the six tanks held the greatest volume at that moment, and "
            f"exactly how many liters did it hold?\n"
            "Answer both parts precisely."
        )
        return text, question, answer_key, seed + attempt

    raise RuntimeError("could not generate a valid test after 300 attempts")


def main():
    ap = argparse.ArgumentParser(description="Perplexity stress-test generator")
    ap.add_argument("--tokens", type=int, default=30000, help="approx. target token count (chars/4)")
    ap.add_argument("--seed", type=int, default=None, help="RNG seed (default: random)")
    ap.add_argument("--events", type=int, default=None,
                    help="number of real state-changing events (default: tokens/500)")
    ap.add_argument("--decoy-ratio", type=float, default=0.8,
                    help="decoys per real event (default 0.8)")
    ap.add_argument("--out", default="water_tank_log.txt")
    ap.add_argument("--question", default="question.txt")
    ap.add_argument("--answer", default="answer_key.txt")
    ap.add_argument("--combined", default=None,
                    help="optionally also write text+question to this file")
    args = ap.parse_args()

    seed = args.seed if args.seed is not None else random.randrange(10**6)
    n_events = args.events or max(12, args.tokens // 500)

    text, question, answer_key, used_seed = generate(
        args.tokens, seed, n_events, args.decoy_ratio)

    with open(args.out, "w") as f:
        f.write(text)
    with open(args.question, "w") as f:
        f.write(question + "\n")
    with open(args.answer, "w") as f:
        f.write(answer_key)
    if args.combined:
        with open(args.combined, "w") as f:
            f.write(text + "\n---\n\n" + question + "\n")

    print(f"wrote {args.out}        ({len(text)} chars, ~{len(text) // 4} tokens)")
    print(f"wrote {args.question}")
    print(f"wrote {args.answer}       (seed {used_seed})")
    print("anti-grep verified: answer values appear nowhere in the text")
    print("NOTE: do not open the answer key while testing a model.")


if __name__ == "__main__":
    main()
