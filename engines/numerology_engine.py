"""
Numerology Compatibility Engine
================================
Full pipeline: birth date + full name  ->  core numbers  ->  compatibility report.

Uses the Pythagorean letter system and preserves master numbers (11, 22, 33).
Pair scores & weights are loaded from compatibility-engine-data.json.
"""

import json
import os
import re
from dataclasses import dataclass, field, asdict

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MASTER_NUMBERS = {11, 22, 33}
REDUCTION_MAP = {11: 2, 22: 4, 33: 6}

# Pythagorean letter map: A=1 ... I=9, J=1 ... R=9, S=1 ... Z=8
PYTHAGOREAN = {ch: (i % 9) + 1 for i, ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")}

# Chaldean letter map (no letter maps to 9 — sacred number in this tradition)
CHALDEAN = {
    'A': 1, 'I': 1, 'J': 1, 'Q': 1, 'Y': 1,
    'B': 2, 'K': 2, 'R': 2,
    'C': 3, 'G': 3, 'L': 3, 'S': 3,
    'D': 4, 'M': 4, 'T': 4,
    'E': 5, 'H': 5, 'N': 5, 'X': 5,
    'U': 6, 'V': 6, 'W': 6,
    'O': 7, 'Z': 7,
    'F': 8, 'P': 8,
}

LETTER_SYSTEMS = {"pythagorean": PYTHAGOREAN, "chaldean": CHALDEAN}
DEFAULT_SYSTEM = "chaldean"

VOWELS = set("AEIOU")


# ---------------------------------------------------------------------------
# Core reduction logic
# ---------------------------------------------------------------------------

def reduce_number(n: int, keep_masters: bool = True) -> int:
    """Reduce a number to a single digit, preserving master numbers if asked."""
    while n > 9:
        if keep_masters and n in MASTER_NUMBERS:
            return n
        n = sum(int(d) for d in str(n))
    return n


def digit_sum(n: int) -> int:
    return sum(int(d) for d in str(n))


# ---------------------------------------------------------------------------
# Name handling
# ---------------------------------------------------------------------------

def clean_name(name: str) -> str:
    """Uppercase and strip everything except A-Z."""
    return re.sub(r"[^A-Z]", "", name.upper())


def is_vowel(ch: str, prev: str | None, nxt: str | None) -> bool:
    """
    Vowel test with the standard Y rule:
    Y counts as a vowel when it is NOT adjacent-preceded/followed logic —
    convention used here: Y is a vowel when it does not sit next to another vowel
    and serves as the syllable's vowel sound (approximation: Y is a vowel
    if its neighbors are not vowels).
    """
    if ch in VOWELS:
        return True
    if ch == "Y":
        prev_v = prev in VOWELS if prev else False
        next_v = nxt in VOWELS if nxt else False
        return not (prev_v or next_v)
    return False


def name_letter_values(name: str, system: str = DEFAULT_SYSTEM) -> list[tuple[str, int, bool]]:
    """Return (letter, value, is_vowel) for each letter of the cleaned name."""
    letter_map = LETTER_SYSTEMS[system]
    s = clean_name(name)
    out = []
    for i, ch in enumerate(s):
        prev = s[i - 1] if i > 0 else None
        nxt = s[i + 1] if i < len(s) - 1 else None
        out.append((ch, letter_map[ch], is_vowel(ch, prev, nxt)))
    return out


# ---------------------------------------------------------------------------
# Core number calculations
# ---------------------------------------------------------------------------

def life_path(day: int, month: int, year: int,
              method: str = "components") -> int:
    """
    Life Path with two configurable methods:
    - "components" (default): reduce day, month, year independently
      (keeping masters), then sum and reduce. Detects masters like
      29/11/1993 -> 11+11+22.
    - "flat": sum every digit of the full date, then reduce (keeping
      masters only at the final stage). Simpler; used by some traditions.
    """
    if method == "components":
        d = reduce_number(day)
        m = reduce_number(month)
        y = reduce_number(digit_sum(year))
        return reduce_number(d + m + y)
    if method == "flat":
        total = digit_sum(day) + digit_sum(month) + digit_sum(year)
        return reduce_number(total)
    raise ValueError(f"Unknown life path method: {method}")


def birth_day_number(day: int) -> int:
    """The raw day (1-31) is kept for the Birth Day chart; also give reduced form."""
    return reduce_number(day)


def personal_year(day: int, month: int, target_year: int) -> int:
    """
    Personal Year = reduce(reduce(day) + reduce(month) + reduce(target_year)).
    Masters are NOT preserved here — personal years cycle 1-9 by tradition.
    """
    d = reduce_number(day, keep_masters=False)
    m = reduce_number(month, keep_masters=False)
    y = reduce_number(digit_sum(target_year), keep_masters=False)
    return reduce_number(d + m + y, keep_masters=False)


def universal_year(target_year: int) -> int:
    return reduce_number(digit_sum(target_year), keep_masters=False)


# --- Part 3 additions (10 Aug 2026) -----------------------------------------
# Tension archetypes, diagnostic cross-pairs, relationship seasons, couple
# signature, master-blend visibility, calculation lock, compound profiles.
# All deterministic lookups over numbers already computed — no change to the
# seven-layer weighted score anywhere in this block.

PY_WORD = {1: "Beginnings", 2: "Partnership", 3: "Expression", 4: "Building",
           5: "Change", 6: "Responsibility", 7: "Reflection", 8: "Power",
           9: "Completion"}

# Personal-year pairings that classically pull in different directions —
# named so a couple can recognise the season, not fear it.
SEASON_WATCH = {
    frozenset({4, 3}): "One builds structure while the other seeks expression — the risk is reading structure as restriction, or sociability as noise.",
    frozenset({4, 5}): "One consolidates while the other craves change — name it, or routine and restlessness will argue on your behalf.",
    frozenset({8, 6}): "One pushes outward at work while the other tends the home front — ambition can read as absence, care as pressure.",
    frozenset({6, 8}): "One pushes outward at work while the other tends the home front — ambition can read as absence, care as pressure.",
    frozenset({1, 9}): "One is starting a chapter the other is closing — different clocks, not different commitment.",
    frozenset({7, 3}): "One turns inward while the other turns outward — solitude and social energy need explicit scheduling this year.",
    frozenset({5, 6}): "One seeks movement while the other seeks roots — the freedom-vs-security theme gets a seasonal spotlight.",
}

# Number-pair tension archetypes (reduced digits). Frozensets so 5-6 == 6-5;
# single-element sets mean "both partners carry the same charged digit".
TENSION_ARCHETYPES = {
    frozenset({1}): ("Independence vs Independence",
        "Two self-directed wills. Decisions stall not from apathy but because neither instinctively yields — agree in advance whose call each domain is."),
    frozenset({8}): ("Control vs Control",
        "Two executives in one house. Superb for building, demanding for deciding — the watch-point is who holds authority over what."),
    frozenset({5}): ("Freedom vs Freedom",
        "Two movers. Exciting and low-friction day to day; the risk is that nobody anchors — roots need to be a deliberate joint project."),
    frozenset({5, 6}): ("Freedom vs Security",
        "One is fed by variety and movement, the other by home and continuity. Neither is wrong; unnamed, each reads the other as restriction or abandonment."),
    frozenset({4, 5}): ("Stability vs Change",
        "One builds systems, the other rearranges them. Handled consciously it's renewal with a foundation; unconsciously it's constant low-grade friction."),
    frozenset({3, 8}): ("Expression vs Power",
        "One leads with words and warmth, the other with results and authority — money style is where this usually surfaces first."),
    frozenset({1, 8}): ("Independence vs Authority",
        "Self-direction meets command. Strong mutual respect when lanes are clear; a power struggle when they aren't."),
    frozenset({1, 2}): ("Autonomy vs Togetherness",
        "One recharges alone and decides solo; the other bonds through consultation. The fix is simple and unglamorous: say which mode you're in."),
    frozenset({4, 9}): ("Method vs Meaning",
        "One asks 'is it done properly?', the other 'does it matter?' — a strong pairing when each credits the other's question."),
    frozenset({7, 3}): ("Depth vs Lightness",
        "One goes inward for truth, the other outward for joy. Each can feel the other is missing the point — usually both are half right."),
}

PERSONAL_YEAR_THEMES = {
    1: "A beginnings year — new starts, fresh direction, plant the seed now.",
    2: "A partnership year — patience, cooperation, the slow behind-the-scenes work.",
    3: "An expression year — visibility, communication, social growth, creative output.",
    4: "A foundation year — work, systems, health routines, structure beneath the plans of previous years.",
    5: "A change year — travel, variety, unexpected turns; go with movement rather than against it.",
    6: "A responsibility year — home, family, and the people who depend on you move to the centre.",
    7: "A reflection year — introspection, study, stepping back before the next push forward.",
    8: "A power year — career, money, and visible results; ambition gets real traction.",
    9: "A completion year — endings, release, closing a chapter before the next 1-year begins.",
}


def destiny_number(full_name: str, system: str = DEFAULT_SYSTEM) -> int:
    """
    Expression/Destiny.
    Pythagorean convention: reduce each name part first, then sum.
    Chaldean convention: sum the whole name (compound), then reduce.
    """
    if system == "chaldean":
        total = sum(v for _, v, _ in name_letter_values(full_name, system))
        return reduce_number(total)
    total = 0
    for part in full_name.split():
        part_sum = sum(v for _, v, _ in name_letter_values(part, system))
        total += reduce_number(part_sum)
    return reduce_number(total)


def compound_number(full_name: str, system: str = DEFAULT_SYSTEM) -> int:
    """
    Chaldean compound (unreduced) name number — read alongside the single
    digit in Chaldean tradition (e.g., 23 'Royal Star', 18, 26 cautionary).
    Returns the first two-digit-or-less stage of reduction.
    """
    total = sum(v for _, v, _ in name_letter_values(full_name, system))
    while total > 52:  # traditional Chaldean compound meanings run to 52
        total = digit_sum(total)
    return total


def soul_urge_number(full_name: str, system: str = DEFAULT_SYSTEM) -> int:
    """Heart's Desire: vowels only."""
    if system == "chaldean":
        total = sum(v for _, v, vowel in name_letter_values(full_name, system) if vowel)
        return reduce_number(total) if total else 0
    total = 0
    for part in full_name.split():
        part_sum = sum(v for _, v, vowel in name_letter_values(part, system) if vowel)
        total += reduce_number(part_sum) if part_sum else 0
    return reduce_number(total) if total else 0


def personality_number(full_name: str, system: str = DEFAULT_SYSTEM) -> int:
    """Outer personality: consonants only."""
    if system == "chaldean":
        total = sum(v for _, v, vowel in name_letter_values(full_name, system) if not vowel)
        return reduce_number(total) if total else 0
    total = 0
    for part in full_name.split():
        part_sum = sum(v for _, v, vowel in name_letter_values(part, system) if not vowel)
        total += reduce_number(part_sum) if part_sum else 0
    return reduce_number(total) if total else 0


# ---------------------------------------------------------------------------
# Person profile
# ---------------------------------------------------------------------------

@dataclass
class Profile:
    name: str
    day: int
    month: int
    year: int
    system: str = DEFAULT_SYSTEM      # "chaldean" or "pythagorean"
    lp_method: str = "components"     # "components" or "flat"
    life_path: int = field(init=False)
    birth_day: int = field(init=False)
    birth_day_raw: int = field(init=False)
    destiny: int = field(init=False)
    compound: int = field(init=False)
    soul_urge: int = field(init=False)
    personality: int = field(init=False)

    def __post_init__(self):
        if self.system not in LETTER_SYSTEMS:
            raise ValueError(f"Unknown system: {self.system}")
        if not (1 <= self.day <= 31 and 1 <= self.month <= 12):
            raise ValueError("Invalid birth date")
        self.life_path = life_path(self.day, self.month, self.year,
                                   self.lp_method)
        self.birth_day_raw = self.day
        self.birth_day = birth_day_number(self.day)
        self.destiny = destiny_number(self.name, self.system)
        self.compound = compound_number(self.name, self.system)
        self.soul_urge = soul_urge_number(self.name, self.system)
        self.personality = personality_number(self.name, self.system)

    @property
    def has_master(self) -> bool:
        return any(n in MASTER_NUMBERS for n in
                   (self.life_path, self.destiny, self.soul_urge, self.personality))

    def letters(self) -> list[dict]:
        """Letter-by-letter Chaldean/Pythagorean working, for the 'name
        confirmation' section — one row per letter of the cleaned name."""
        return [{"letter": ch, "value": v, "vowel": is_v}
                for ch, v, is_v in name_letter_values(self.name, self.system)]

    def personal_year(self, target_year: int) -> int:
        return personal_year(self.day, self.month, target_year)

    def dominance(self) -> dict:
        """Which digits 1-9 repeat across this person's five core numbers,
        and which don't show up at all. Life Path/Destiny/Personality are
        fully reduced (masters included) for this count only — dominance is
        about the underlying digit-theme, not about flagging every master
        number as its own repeat."""
        reduced = [
            reduce_number(self.life_path, keep_masters=False),
            self.birth_day,
            reduce_number(self.destiny, keep_masters=False),
            self.soul_urge,
            reduce_number(self.personality, keep_masters=False),
        ]
        counts: dict[int, int] = {}
        for n in reduced:
            counts[n] = counts.get(n, 0) + 1
        dominant = sorted([n for n, c in counts.items() if c >= 2],
                          key=lambda n: -counts[n])
        underrepresented = [n for n in range(1, 10) if n not in counts]
        return {"counts": counts, "dominant": dominant, "underrepresented": underrepresented}

    def numbers(self) -> dict:
        return {
            "life_path": self.life_path,
            "birth_day": self.birth_day,
            "destiny": self.destiny,
            "soul_urge": self.soul_urge,
            "personality": self.personality,
        }


# ---------------------------------------------------------------------------
# Compatibility engine
# ---------------------------------------------------------------------------

class CompatibilityEngine:
    def __init__(self, data_path: str, content_path: str | None = None):
        with open(data_path) as f:
            self.data = json.load(f)
        self.pairs = self.data["life_path_pairs"]
        self.master_pairs = self.data["master_pairs"]
        self.weights = self.data["layer_weights"]
        self.groups = self.data["affinity_groups"]
        self.bands = self.data["output_bands"]
        blend = self.data["master_number_rule"]["blend"]
        self.master_w = blend["master_weight"]
        self.reduced_w = blend["reduced_weight"]

        # Interpretive content (birthday profiles, LP x Destiny combos, full
        # pairing dynamic/strengths/friction/advice text) — a sibling file to
        # the scoring data, kept separate since it's pure copy, not scoring
        # logic. Optional: if missing, lookups below just return None so the
        # engine still runs (older deployments / tests without the content
        # file don't break).
        if content_path is None:
            content_path = os.path.join(os.path.dirname(data_path) or ".",
                                        "numerology_content_data.json")
        self.content = None
        if os.path.exists(content_path):
            with open(content_path) as f:
                self.content = json.load(f)

    # -- interpretive content lookups -----------------------------------------

    def birthday_profile(self, day: int) -> dict | None:
        """Full narrative for a raw birth-day (1-31), e.g. 17 -> 'The Immortal Achiever'."""
        if not self.content:
            return None
        return self.content["birthday_profiles"].get(str(day))

    def lp_destiny_combo(self, life_path: int, destiny: int) -> dict | None:
        """LP x Destiny combo narrative, e.g. (6, 1) -> 'The family general'.
        Falls back to the reduced-number combo if no master-specific entry
        was authored for this exact pairing (source material only covers
        master combos where the LIFE PATH itself is 11/22)."""
        if not self.content:
            return None
        combos = self.content["lp_destiny_combos"]
        key = f"{life_path}-{destiny}"
        if key in combos:
            return combos[key]
        rlp = REDUCTION_MAP.get(life_path, life_path)
        rdest = REDUCTION_MAP.get(destiny, destiny)
        return combos.get(f"{rlp}-{rdest}")

    def pair_full_text(self, a: int, b: int) -> dict | None:
        """Reduced-level dynamic/strengths/friction/advice for a pairing."""
        if not self.content:
            return None
        ra, rb = REDUCTION_MAP.get(a, a), REDUCTION_MAP.get(b, b)
        lo, hi = sorted((ra, rb))
        return self.content["pair_text"].get(f"{lo}-{hi}")

    def master_pair_note(self, a: int, b: int) -> dict | None:
        """Master-level short note for a pairing, only when a master number
        (11/22/33) is actually involved and the source material covers this
        exact combination."""
        if not self.content or not (a in MASTER_NUMBERS or b in MASTER_NUMBERS):
            return None
        lo, hi = sorted((a, b))
        return self.content["master_pair_text"].get(f"{lo}-{hi}")

    # -- pair lookup ---------------------------------------------------------

    def _key(self, a: int, b: int) -> str:
        lo, hi = sorted((a, b))
        return f"{lo}-{hi}"

    def _base_pair_score(self, a: int, b: int) -> tuple[float, str]:
        """Score for two numbers where masters are already handled/reduced."""
        lo, hi = sorted((a, b))
        for key in (f"{lo}-{hi}", f"{hi}-{lo}"):
            if key in self.pairs:
                entry = self.pairs[key]
                return float(entry["score"]), entry.get("title", key)
            if key in self.master_pairs:
                return float(self.master_pairs[key]["score"]), key
        raise KeyError(f"No pair entry for {lo}-{hi}")

    def pair_score(self, a: int, b: int) -> dict:
        """
        Full pair score with master blending:
        score = 0.6 * master-level + 0.4 * reduced-level (when masters involved).
        Adds affinity-group bonus for reduced numbers in the same natural group.
        """
        masters_involved = a in MASTER_NUMBERS or b in MASTER_NUMBERS
        ra, rb = REDUCTION_MAP.get(a, a), REDUCTION_MAP.get(b, b)

        if masters_involved:
            master_score, title = self._base_pair_score(a, b)
            reduced_score, _ = self._base_pair_score(ra, rb)
            score = self.master_w * master_score + self.reduced_w * reduced_score
        else:
            score, title = self._base_pair_score(a, b)

        # affinity bonus (on reduced forms)
        for group in ("mind", "practical", "heart"):
            members = set(self.groups[group])
            if ra in members and rb in members:
                score = min(score + self.groups["same_group_bonus"],
                            self.groups["bonus_cap"])
                break

        result = {
            "numbers": (a, b),
            "score": round(score, 2),
            "title": title,
            "high_voltage": masters_involved,
        }
        reduced_text = self.pair_full_text(a, b)
        if reduced_text:
            result["full_text"] = reduced_text
        if masters_involved:
            master_note = self.master_pair_note(a, b)
            if master_note:
                result["master_note"] = master_note
            result["reduced_numbers"] = (ra, rb)
        return result

    # -- full report ---------------------------------------------------------

    # -- Part 3 (10 Aug 2026) ------------------------------------------------

    NUMBER_ESSENCE = {1: "leadership and self-drive", 2: "partnership and sensitivity",
        3: "expression and joy", 4: "discipline and building", 5: "freedom and change",
        6: "care, home and responsibility", 7: "reflection and depth",
        8: "ambition and material mastery", 9: "compassion and completion",
        11: "intuition and inspiration", 22: "master-builder energy",
        33: "master-teacher devotion"}

    # Traditional Chaldean compound themes (Cheiro's attributions; several
    # higher compounds classically share a lower one's meaning — mapped via
    # the standard equivalences). Phrased as associations, never predictions.
    COMPOUND_THEMES = {
        10: "the wheel — self-contained rise and fall; confidence carries it",
        11: "hidden trials — strength tested quietly from two sides",
        12: "the sacrifice — giving that must learn to also receive",
        13: "regeneration — change and renewal, misread by the fearful as unlucky",
        14: "movement and risk — luck with people and money that rewards prudence",
        15: "magnetism — charm and eloquence; gifts that grow with integrity",
        16: "the tower — sudden reversals; asks for humility and planning",
        17: "the star — hope, peace, and a name that outlasts setbacks",
        18: "the struggle — materialism vs spirit; calls for honest dealing",
        19: "the sun — warmth, success, and promises kept",
        20: "the awakening — a call to purpose; slow starts, meaningful arcs",
        21: "the crown — earned success after effort; advancement and honours",
        22: "the good man deceived — trusting nature; asks for discernment",
        23: "the royal star — protection and help from those above",
        24: "assistance and gain — support from partnerships and affection",
        25: "strength through experience — early lessons, later reward",
        26: "partnerships under care — generosity that must choose wisely",
        27: "the sceptre — authority through creative intellect; command earned",
        28: "contradictions — promising starts that ask to be secured twice",
        29: "uncertainties — trials through others; steadied by clear boundaries",
        30: "the thinker — retrospection and mental depth over material race",
        31: "the recluse — self-containment; genius comfortable in its own company",
        43: "upheaval — revolution and reversal; steadied by patience",
        51: "the warrior — sudden advancement; strength under exposure",
    }
    _COMPOUND_EQUIV = {32: 23, 33: 24, 34: 25, 35: 26, 36: 27, 37: 23, 38: 29,
                       39: 30, 40: 31, 41: 32, 42: 24, 44: 26, 45: 27, 46: 37,
                       47: 29, 48: 30, 49: 31, 50: 32, 52: 43}

    def compound_profile(self, p: Profile) -> dict:
        c = p.compound
        base = c
        seen = set()
        while base in self._COMPOUND_EQUIV and base not in seen:
            seen.add(base)
            base = self._COMPOUND_EQUIV[base]
        theme = self.COMPOUND_THEMES.get(base)
        return {"compound": c, "reduces_to": p.destiny,
                "theme": theme,
                "note": "Traditional Chaldean associations — treated here as a symbolic relationship theme, not a prediction."}

    def tension_pairs(self, p1: Profile, p2: Profile) -> dict:
        """Named tension archetypes across the couple's core numbers.
        Same-slot comparison, slots in priority order; masters reduced for
        archetype lookup (11→2, 22→4, 33→6). Diagnostic language only."""
        slots = [("life_path", "Life Path"), ("soul_urge", "Soul Urge"),
                 ("destiny", "Destiny"), ("personality", "Personality")]
        found = []
        for key, label in slots:
            a = reduce_number(getattr(p1, key), keep_masters=False)
            b = reduce_number(getattr(p2, key), keep_masters=False)
            arch = TENSION_ARCHETYPES.get(frozenset({a, b}))
            if arch:
                found.append({"slot": key, "slot_label": label,
                              "numbers": [getattr(p1, key), getattr(p2, key)],
                              "name": arch[0], "line": arch[1]})
        return {"pairs": found,
                "primary": found[0] if found else None,
                "note": "Tension names are conversation labels, not defects — every archetype above is workable when named."}

    def diagnostic_pairs(self, p1: Profile, p2: Profile) -> list[dict]:
        """Cross-number checks shown for insight only — ZERO weight in the
        seven-layer score (the score's layers are untouched)."""
        specs = [
            ("soul_urge", "destiny", "Does what I emotionally need fit what you are trying to become?"),
            ("life_path", "destiny", "Does your life's direction support my expression?"),
            ("birth_day", "destiny", "Does natural daily style fit the other's life expression?"),
        ]
        out = []
        for ka, kb, q in specs:
            out.append({
                "pair": f"{ka}_x_{kb}", "question": q,
                "a_to_b": self.pair_score(getattr(p1, ka), getattr(p2, kb))["score"],
                "b_to_a": self.pair_score(getattr(p2, ka), getattr(p1, kb))["score"],
                "weight": 0})
        return out

    def couple_signature(self, p1: Profile, p2: Profile) -> dict:
        """Supplementary 'relationship number': the two Life Paths combined
        and reduced. Explicitly a side-lens — carries no weight anywhere."""
        n = reduce_number(p1.life_path + p2.life_path, keep_masters=True)
        essence = self.NUMBER_ESSENCE.get(n, "a rare master vibration")
        return {"number": n, "theme": essence,
                "label": "Supplementary numerology lens — not part of the compatibility score."}

    def person_chapter(self, p: Profile, target_year: int | None = None) -> dict:
        """Everything needed for one person's individual chapter: core
        numbers, name-confirmation letter working, the birth-day narrative,
        the Life-Path x Destiny combo narrative, and (if a year is given)
        their personal year for that year."""
        out = {
            "name": p.name,
            **p.numbers(),
            "compound": p.compound,
            "has_master": p.has_master,
            "letters": p.letters(),
            "birthday_profile": self.birthday_profile(p.birth_day_raw),
            "lp_destiny_combo": self.lp_destiny_combo(p.life_path, p.destiny),
            "dominance": p.dominance(),
            # Part 3: calculation integrity, made visible and enforced.
            "calculation_lock": self._calculation_lock(p),
            "compound_profile": self.compound_profile(p),
            "master_blend": ({
                "slots": [k for k, v in p.numbers().items() if v in MASTER_NUMBERS],
                "rule": "Master numbers are preserved, not auto-reduced: interpretation blends 60% the master's voltage with 40% its reduced root.",
            } if p.has_master else None),
        }
        if target_year is not None:
            out["personal_year"] = p.personal_year(target_year)
        return out

    @staticmethod
    def _calculation_lock(p: Profile) -> dict:
        """Displayed letters must BE the stored name — enforced, not assumed.
        The sample-page letter-mismatch incident is the reason this exists:
        if the letter working ever diverges from the name every number hangs
        off, the report must fail loudly rather than render confidently."""
        letters_joined = "".join(l["letter"] for l in p.letters())
        expected = clean_name(p.name).replace(" ", "")
        if letters_joined.replace(" ", "").upper() != expected.upper():
            raise ValueError(
                f"calculation integrity check failed for '{p.name}': "
                f"letter working '{letters_joined}' != cleaned name '{expected}'")
        return {"name_used": p.name, "letter_count": len(p.letters()),
                "verified": True,
                "note": "Spelling locked at intake; every number below is computed from exactly these letters."}

    def couple_timeline(self, p1: Profile, p2: Profile, start_year: int, years: int = 5) -> list[dict]:
        """Personal-year timeline for both people across a run of years, each
        year's pair of numbers glossed with its one-line theme. Purely a
        multi-year application of the same personal_year()/PERSONAL_YEAR_THEMES
        already used for the single 'current year' figure — no new rule."""
        out = []
        for offset in range(years):
            y = start_year + offset
            py1, py2 = p1.personal_year(y), p2.personal_year(y)
            # Part 3: 'relationship season' — the two personal years named as
            # one couple-level theme, with a watch-line for classically
            # divergent pairings. Lookup only; no new computation.
            season = (PY_WORD[py1] if py1 == py2
                      else f"{PY_WORD[py1]} + {PY_WORD[py2]}")
            out.append({
                "year": y,
                p1.name: {"personal_year": py1, "theme": PERSONAL_YEAR_THEMES[py1]},
                p2.name: {"personal_year": py2, "theme": PERSONAL_YEAR_THEMES[py2]},
                "universal_year": universal_year(y),
                "season": season,
                "watch": SEASON_WATCH.get(frozenset({py1, py2})),
            })
        return out

    # Regroups the seven scored layers into named relationship dimensions —
    # a presentation lens on numbers already computed above, not a new score.
    # A dimension backed by more than one layer is its weighted average
    # (weighted by that layer's engine weight) rather than a plain mean, so a
    # layer the engine treats as more decisive also carries more say in the
    # dimension it feeds.
    _BLUEPRINT_MAP = [
        ("emotional_bond", "Emotional Bond", ["soul_urge_x_soul_urge"]),
        ("life_direction", "Life Direction", ["life_path_x_life_path", "cross_destiny_x_lifepath_avg"]),
        ("shared_mission", "Shared Mission", ["destiny_x_destiny"]),
        ("daily_ease", "Daily Ease & Social Style", ["personality_x_personality"]),
        ("inner_outer_match", "What You Show vs What I Crave", ["cross_soulurge_x_personality_avg"]),
        ("everyday_flavour", "Everyday Flavour", ["birthday_x_birthday"]),
    ]

    def relationship_blueprint(self, layers: dict) -> list[dict]:
        out = []
        for key, label, layer_keys in self._BLUEPRINT_MAP:
            present = [(k, layers[k]["score"]) for k in layer_keys if k in layers]
            if not present:
                continue
            wsum = sum(self.weights.get(k, 1) for k, _ in present)
            score = sum(s * self.weights.get(k, 1) for k, s in present) / wsum
            score = round(score, 2)
            signal = "green" if score >= 7.5 else "amber" if score >= 5.5 else "red"
            out.append({"key": key, "label": label, "score": score, "signal": signal,
                        "layers": layer_keys})
        return out

    def compare(self, p1: Profile, p2: Profile, target_year: int | None = None) -> dict:
        layers = {
            "life_path_x_life_path":
                self.pair_score(p1.life_path, p2.life_path),
            "soul_urge_x_soul_urge":
                self.pair_score(p1.soul_urge, p2.soul_urge),
            "destiny_x_destiny":
                self.pair_score(p1.destiny, p2.destiny),
            "personality_x_personality":
                self.pair_score(p1.personality, p2.personality),
            "birthday_x_birthday":
                self.pair_score(p1.birth_day, p2.birth_day),
        }

        # cross-aspect checks (averaged both directions)
        cross_dl = (self.pair_score(p1.destiny, p2.life_path)["score"] +
                    self.pair_score(p2.destiny, p1.life_path)["score"]) / 2
        cross_sp = (self.pair_score(p1.soul_urge, p2.personality)["score"] +
                    self.pair_score(p2.soul_urge, p1.personality)["score"]) / 2
        layers["cross_destiny_x_lifepath_avg"] = {"score": round(cross_dl, 2)}
        layers["cross_soulurge_x_personality_avg"] = {"score": round(cross_sp, 2)}

        # weighted final score
        final = sum(layers[k]["score"] / 10 * w
                    for k, w in self.weights.items()) * 100
        final = round(final, 1)

        band = next(b["band"] for b in self.bands
                    if b["min"] <= final <= b["max"])

        # superpower / growth edge among the 5 direct layers
        direct = {k: v for k, v in layers.items() if "cross" not in k}
        superpower = max(direct, key=lambda k: direct[k]["score"])
        growth_edge = min(direct, key=lambda k: direct[k]["score"])

        # report flags (+ structured detail so callers don't have to
        # recompute *why* a flag fired to narrate it)
        flags = []
        flag_details = {}
        if p1.has_master or p2.has_master:
            flags.append("high_voltage")
            flag_details["high_voltage"] = {
                p1.name: [k for k, v in p1.numbers().items() if v in MASTER_NUMBERS],
                p2.name: [k for k, v in p2.numbers().items() if v in MASTER_NUMBERS],
            }
        lp_score = layers["life_path_x_life_path"]["score"]
        if lp_score <= 4 and final >= 55:
            flags.append("opposites_integration")
        # echo pattern: same number in >= 3 fields across both people
        fields_1 = {f"{p1.name}:{k}": v for k, v in p1.numbers().items()}
        fields_2 = {f"{p2.name}:{k}": v for k, v in p2.numbers().items()}
        all_fields = {**fields_1, **fields_2}
        echoes = {}
        for n in set(all_fields.values()):
            hits = [field for field, v in all_fields.items() if v == n]
            if len(hits) >= 3:
                echoes[n] = hits
        if echoes:
            flags.append("echo_pattern")
            flag_details["echo_pattern"] = echoes

        return {
            "person_1": self.person_chapter(p1, target_year),
            "person_2": self.person_chapter(p2, target_year),
            "layers": layers,
            "final_score": final,
            "band": band,
            "superpower_layer": superpower,
            "growth_edge_layer": growth_edge,
            "flags": flags,
            "flag_details": flag_details,
            "universal_year": universal_year(target_year) if target_year is not None else None,
            "target_year": target_year,
            "relationship_blueprint": self.relationship_blueprint(layers),
            "couple_timeline": self.couple_timeline(p1, p2, target_year, years=5) if target_year is not None else None,
            # Part 3 (10 Aug 2026): diagnostic lenses — none of these touch
            # the weighted score above.
            "tension_pairs": self.tension_pairs(p1, p2),
            "diagnostic_pairs": self.diagnostic_pairs(p1, p2),
            "couple_signature": self.couple_signature(p1, p2),
        }


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    engine = CompatibilityEngine("compatibility-engine-data.json")

    # Individual profile demo (Chaldean default)
    p1 = Profile(name="Aarav Kumar Sharma", day=23, month=8, year=1992)
    p2 = Profile(name="Priya Nair", day=4, month=12, year=1994)

    print(f"=== PROFILES (system: {p1.system}) ===")
    for p in (p1, p2):
        print(f"{p.name}: LP={p.life_path} BD={p.birth_day_raw}(->{p.birth_day}) "
              f"Destiny={p.destiny} Compound={p.compound} "
              f"SoulUrge={p.soul_urge} Personality={p.personality} "
              f"Master={p.has_master}")

    print("\n=== SYSTEM COMPARISON (same person, both systems) ===")
    for sys_name in ("chaldean", "pythagorean"):
        q = Profile(name="Aarav Kumar Sharma", day=23, month=8, year=1992,
                    system=sys_name)
        print(f"{sys_name:>12}: Destiny={q.destiny} Compound={q.compound} "
              f"SoulUrge={q.soul_urge} Personality={q.personality}")

    print("\n=== COMPATIBILITY REPORT ===")
    report = engine.compare(p1, p2)
    print(json.dumps(report, indent=2))

    # Sanity checks
    print("\n=== SANITY CHECKS ===")
    t = Profile(name="Test Person", day=29, month=11, year=1993)
    print(f"29/11/1993 -> Life Path {t.life_path} (11+11+22=44 -> 8)")
    t2 = Profile(name="Test Person", day=22, month=4, year=2000)
    print(f"22/04/2000 -> Life Path {t2.life_path} (22+4+2=28 -> 1)")
    # Chaldean hand-check: PRIYA = P8+R2+I1+Y1+A1 = 13 -> 4; NAIR = N5+A1+I1+R2 = 9
    # Full name compound = 13+9 = 22 -> destiny 22 (master) or reduced 4
    c = Profile(name="Priya Nair", day=1, month=1, year=2000)
    print(f"'Priya Nair' Chaldean: Compound={c.compound} Destiny={c.destiny} "
          f"(hand-calc: 22)")

    print("\n=== CONFIG MODES ===")
    for sys_name in ("chaldean", "pythagorean"):
        for lp_m in ("components", "flat"):
            m = Profile(name="Aarav Kumar Sharma", day=29, month=11, year=1993,
                        system=sys_name, lp_method=lp_m)
            print(f"system={sys_name:>12} lp_method={lp_m:>10}: "
                  f"LP={m.life_path} Destiny={m.destiny}")
