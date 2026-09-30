#!/usr/bin/env python3
"""Independent verifier: re-derives the final tank state by parsing the
generated natural-language text, then compares with answer_key.txt.
This checks that rendering bugs (wrong tank, wrong number, omitted event)
would be caught — i.e. the text is self-consistent with the key."""
import os, re, sys, random

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from generator import TANKS, num_words

# word -> number lookup (1..3000)
WORD2N = {}
for n in range(1, 3001):
    WORD2N[num_words(n)] = n

def repeat_total(x: int, y: int) -> int:
    """Smallest multiple of x strictly greater than y (matches generator render_repeat)."""
    return x * ((y + x) // x)


def parse_amount(tok):
    tok = tok.strip().rstrip(".")
    if re.fullmatch(r"\d+", tok):
        return int(tok)
    m = re.fullmatch(r"(.+) plus (.+)", tok)
    if m:
        return parse_amount(m.group(1)) + parse_amount(m.group(2))
    m = re.fullmatch(r"(.+) minus (.+)", tok)
    if m:
        return parse_amount(m.group(1)) - parse_amount(m.group(2))
    m = re.fullmatch(r"([a-z]+) hundred(.*)", tok)
    if m:
        rest = m.group(2).strip()
        return WORD2N[m.group(1)] * 100 + (parse_amount(rest) if rest else 0)
    return WORD2N[tok]

NUM = (r"(?:\d+|[a-z]+(?:-[a-z]+)?"
       r"(?: hundred (?:[a-z]+(?:-[a-z]+)?(?: [a-z]+(?:-[a-z]+)?)?)?)?)")
AMT = rf"({NUM}(?: (?:plus|minus) {NUM})?)"

PATTERNS = [
    # (regex, handler)  — handlers take (state, match)
    (re.compile(rf"moved {AMT} liters from Tank (\w+) to Tank (\w+)"),
     lambda s, m: (s.update({m.group(2): s[m.group(2)] - parse_amount(m.group(1)),
                             m.group(3): s[m.group(3)] + parse_amount(m.group(1))}) or s)),
    (re.compile(rf"Tank (\w+) supplied {AMT} liters to Tank (\w+)"),
     lambda s, m: (s.update({m.group(1): s[m.group(1)] - parse_amount(m.group(2)),
                             m.group(3): s[m.group(3)] + parse_amount(m.group(2))}) or s)),
    (re.compile(rf"{AMT} liters were transferred from Tank (\w+) into Tank (\w+)"),
     lambda s, m: (s.update({m.group(2): s[m.group(2)] - parse_amount(m.group(1)),
                             m.group(3): s[m.group(3)] + parse_amount(m.group(1))}) or s)),
    (re.compile(rf"A transfer of {AMT} liters ran from Tank (\w+) to Tank (\w+)"),
     lambda s, m: (s.update({m.group(2): s[m.group(2)] - parse_amount(m.group(1)),
                             m.group(3): s[m.group(3)] + parse_amount(m.group(1))}) or s)),
    (re.compile(rf"fed {AMT} liters into Tank (\w+)"),
     lambda s, m: (s.update({m.group(2): s[m.group(2)] + parse_amount(m.group(1))}) or s)),
    (re.compile(rf"Tank (\w+) received {AMT} liters from the municipal intake"),
     lambda s, m: (s.update({m.group(1): s[m.group(1)] + parse_amount(m.group(2))}) or s)),
    (re.compile(rf"drawn from Tank (\w+) into the waste line"),
     None),  # handled with amount pattern below
    (re.compile(rf"removing {AMT} liters"),
     None),
    (re.compile(rf"let {AMT} liters seep out of Tank (\w+)"),
     lambda s, m: (s.update({m.group(2): s[m.group(2)] - parse_amount(m.group(1))}) or s)),
    (re.compile(rf"cost Tank (\w+) {AMT} liters by the end of the day"),
     lambda s, m: (s.update({m.group(1): s[m.group(1)] - parse_amount(m.group(2))}) or s)),
    (re.compile(rf"bled Tank (\w+) down until the gauge read exactly {AMT} liters"),
     lambda s, m: (s.update({m.group(1): parse_amount(m.group(2))}) or s)),
    (re.compile(rf"Tank (\w+) was drawn down at \d\d:\d\d until exactly {AMT} liters remained"),
     lambda s, m: (s.update({m.group(1): parse_amount(m.group(2))}) or s)),
    (re.compile(r"moved into Tank (\w+) exactly the volume it already held, drawing the water from Tank (\w+)"),
     lambda s, m: (s.update({m.group(2): s[m.group(2)] - s[m.group(1)],
                             m.group(1): s[m.group(1)] * 2}) or s)),
    (re.compile(r"Tank (\w+) was doubled in place at \d\d:\d\d by a siphon fed from Tank (\w+)"),
     lambda s, m: (s.update({m.group(2): s[m.group(2)] - s[m.group(1)],
                             m.group(1): s[m.group(1)] * 2}) or s)),
    (re.compile(r"topped Tank (\w+) off to exactly twice its previous volume"),
     lambda s, m: (s.update({m.group(1): s[m.group(1)] * 2}) or s)),
    # phone-interruption intake: net = M * intended - drain (neither M*I nor
    # the net is stated in the text)
    (re.compile(rf"was meaning to add {AMT} liters to Tank (\w+) but glancing at their phone while the pump ran "
                rf"and ending up adding (\d+) times the intended amount\. They followed up by accidentally "
                rf"draining only {AMT} liters from Tank (\w+)"),
     lambda s, m: (s.update({m.group(2): s[m.group(2)]
                             + int(m.group(3)) * parse_amount(m.group(1))
                             - parse_amount(m.group(4))}) or s)),
]

# repeated-batch phrasings (generator render_repeat): the real amount is the
# smallest multiple of the batch size strictly above the threshold, not the
# batch size itself. Checked BEFORE the generic patterns, which would match
# the shared prefix and under-apply.
REPEAT_PATTERNS = [
    (re.compile(rf"moved (\d+) liters from Tank (\w+) to Tank (\w+) in repeated cycles, continuing until the moved amount had exceeded (\d+) liters"),
     "transfer"),
    (re.compile(rf"fed (\d+) liters into Tank (\w+) over and over, stopping only once the amount added that way had exceeded (\d+) liters"),
     "intake"),
    (re.compile(rf"(\d+) liters were repeatedly drawn from Tank (\w+) into the waste line, continuing until the drawn amount had exceeded (\d+) liters"),
     "waste"),
    (re.compile(rf"let (\d+) liters seep out of Tank (\w+) in repeated spurts, the seepage continuing until the lost amount had exceeded (\d+) liters"),
     "evap"),
]


# weather-conditional intake (generator kind "wx"): the line states no
# outcome; it fires only if the current day's weather record (the "It was a
# ... day." line right after the day header) meets the condition.
WX_RX = re.compile(
    rf"standing instruction for Tank (\w+): (if sunlight was visible|on a day without rain|if it had been windy), "
    rf"the tank is to receive ({AMT}) extra liters")

# "unmet" decoy: asserts the tank's reading was below the threshold at that
# point — check the claim against the state actually derived so far.
UNMET_RX = re.compile(
    rf"Protocol required that, if Tank (\w+) exceeded (\d+) liters, {AMT} liters "
    rf"be drained to the waste line\. The reading came in below the threshold, "
    rf"so nothing was drained\.")


def weather_attrs(line: str) -> dict:
    low = line.lower()
    return {"sun": "sunny" in low,
            "rain": "rainy" in low or "drizzly" in low,
            "windy": "windy" in low}


def apply_repeat(state, kind, m):
    # groups: transfer=(x, src, dst, y); intake/waste/evap=(x, tank, y)
    x, y = m.group(1), (m.group(4) if kind == "transfer" else m.group(3))
    n = repeat_total(int(x), int(y))
    if kind == "transfer":
        state[m.group(2)] -= n
        state[m.group(3)] += n
    elif kind == "intake":
        state[m.group(2)] += n
    else:
        state[m.group(2)] -= n
    return state


# combine the two-part waste patterns
def apply_all(text):
    state = None
    problems = []
    for line in open("./answer_key.txt"):
        if line.startswith("Initial:"):
            state = {name: int(v) for name, v in re.findall(r"(\w+)=(\d+)", line.split(":", 1)[1])}
    # walk the text in order; for each line try every pattern
    weather = None  # attrs of the current day, from its opening weather record
    for line in text.splitlines():
        if line.startswith("It was a "):
            weather = weather_attrs(line)
            continue
        m = UNMET_RX.search(line)
        if m:
            tank, thr = m.group(1), int(m.group(2))
            if state[tank] >= thr:
                problems.append(f"unmet decoy false: {tank}={state[tank]} is not below threshold {thr}")
            continue
        # repeated-batch events take precedence (and consume the whole line)
        hit = False
        for rx, kind in REPEAT_PATTERNS:
            m = rx.search(line)
            if m:
                state = apply_repeat(state, kind, m)
                hit = True
                break
        if hit:
            continue
        m = WX_RX.search(line)
        if m:
            cond = m.group(2)
            if cond == "if sunlight was visible":
                ok = bool(weather and weather["sun"])
            elif cond == "on a day without rain":
                ok = bool(weather and not weather["rain"])
            else:  # "if it had been windy"
                ok = bool(weather and weather["windy"])
            if ok:
                state[m.group(1)] += parse_amount(m.group(3))
            continue
        for rx, fn in PATTERNS:
            if fn is None:
                continue
            m = rx.search(line)
            if m:
                state = fn(state, m)
        # waste: "X liters were drawn from Tank S into the waste line"
        m = re.search(rf"({AMT}) liters were drawn from Tank (\w+) into the waste line", line)
        if m:
            state[m.group(3)] -= parse_amount(m.group(1))
        m = re.search(rf"The waste valve on Tank (\w+) was opened at \d\d:\d\d, removing ({AMT}) liters", line)
        if m:
            state[m.group(1)] -= parse_amount(m.group(2))
    return state, problems

def main():
    text = open("./water_tank_log.txt").read()
    derived, problems = apply_all(text)
    key = {}
    for line in open("./answer_key.txt"):
        if line.startswith("Final:"):
            key = {name: int(v) for name, v in re.findall(r"(\w+)=(\d+)", line.split(":", 1)[1])}
    print("derived from text:", derived)
    print("answer key:       ", key)
    if problems:
        print("INCONSISTENCIES in text:")
        for p in problems:
            print("   -", p)
    if problems:
        print("MISMATCH — text contradicts itself!")
    else:
        print("MATCH" if derived == key else "MISMATCH — rendering bug!")

if __name__ == "__main__":
    main()
