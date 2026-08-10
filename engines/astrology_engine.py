"""
Vedic Astrology Engine
======================
Pipeline: birth date/time/place -> sidereal chart (Lahiri ayanamsa)
          -> North Indian & South Indian chart structures
          -> Compatibility: Ashtakoota (North, 36 gunas) + Dasa Porutham (South)
          -> Manglik (Kuja) dosha check

Uses Swiss Ephemeris (Moshier model — no data files needed).
Whole-sign houses (the standard for Vedic rasi charts).
"""

import swisseph as swe
import datetime
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Constants & reference tables
# ---------------------------------------------------------------------------

swe.set_sid_mode(swe.SIDM_LAHIRI)
FLAGS = swe.FLG_MOSEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
         "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]

SIGN_LORDS = ["Mars", "Venus", "Mercury", "Moon", "Sun", "Mercury",
              "Venus", "Mars", "Jupiter", "Saturn", "Saturn", "Jupiter"]

NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni",
    "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha",
    "Jyeshtha", "Mula", "Purvashada", "Uttarashada", "Shravana",
    "Dhanishta", "Shatabhisha", "Purvabhadra", "Uttarabhadra", "Revati",
]

PLANETS = {
    "Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS,
    "Mercury": swe.MERCURY, "Jupiter": swe.JUPITER, "Venus": swe.VENUS,
    "Saturn": swe.SATURN, "Rahu": swe.MEAN_NODE,  # Ketu derived from Rahu
}

# --- Panchang tables ---------------------------------------------------------

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday"]

TITHI_NAMES = ["Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami",
               "Shashthi", "Saptami", "Ashtami", "Navami", "Dashami",
               "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi"]

YOGAS = ["Vishkambha", "Priti", "Ayushman", "Saubhagya", "Shobhana",
         "Atiganda", "Sukarman", "Dhriti", "Shoola", "Ganda", "Vriddhi",
         "Dhruva", "Vyaghata", "Harshana", "Vajra", "Siddhi", "Vyatipata",
         "Variyana", "Parigha", "Shiva", "Siddha", "Sadhya", "Shubha",
         "Shukla", "Brahma", "Indra", "Vaidhriti"]

# --- Ashtakoota tables ------------------------------------------------------

# Varna by moon sign (0=Aries): Kshatriya fire, Vaishya earth, Shudra air, Brahmin water
VARNA = ["Kshatriya", "Vaishya", "Shudra", "Brahmin"] * 3  # indexed by sign % 4
VARNA_RANK = {"Brahmin": 4, "Kshatriya": 3, "Vaishya": 2, "Shudra": 1}

# Vashya group by moon sign
VASHYA = ["Chatushpada", "Chatushpada", "Manava", "Jalachara", "Vanachara",
          "Manava", "Manava", "Keeta", "Manava", "Jalachara", "Manava",
          "Jalachara"]
# (Sagittarius counted Manava for 1st half convention; Capricorn Jalachara
#  2nd-half convention — configurable simplification.)
VASHYA_GROUPS = ["Chatushpada", "Manava", "Jalachara", "Vanachara", "Keeta"]
VASHYA_MATRIX = [
    # rows = groom group, cols = bride group        Cha  Man  Jal  Van  Kee
    [2.0, 1.0, 1.0, 0.0, 1.0],   # Chatushpada
    [1.0, 2.0, 0.5, 0.0, 1.0],   # Manava
    [1.0, 0.5, 2.0, 1.0, 1.0],   # Jalachara
    [0.0, 0.0, 1.0, 2.0, 0.0],   # Vanachara
    [1.0, 1.0, 1.0, 0.0, 2.0],   # Keeta
]
def vashya_points(g1: str, g2: str) -> float:
    return VASHYA_MATRIX[VASHYA_GROUPS.index(g1)][VASHYA_GROUPS.index(g2)]

# Yoni animal by nakshatra index
YONI = ["Horse", "Elephant", "Sheep", "Serpent", "Serpent", "Dog", "Cat",
        "Sheep", "Cat", "Rat", "Rat", "Cow", "Buffalo", "Tiger", "Buffalo",
        "Tiger", "Deer", "Deer", "Dog", "Monkey", "Mongoose", "Monkey",
        "Lion", "Horse", "Lion", "Cow", "Elephant"]

# Full classical 14x14 yoni matrix (symmetric, configurable data)
YONI_ANIMALS = ["Horse", "Elephant", "Sheep", "Serpent", "Dog", "Cat", "Rat",
                "Cow", "Buffalo", "Tiger", "Deer", "Monkey", "Mongoose", "Lion"]
YONI_MATRIX = [
    # Hor Ele She Ser Dog Cat Rat Cow Buf Tig Dee Mon Mng Lio
    [4, 2, 2, 3, 2, 2, 2, 1, 0, 1, 3, 3, 2, 1],   # Horse
    [2, 4, 3, 3, 2, 2, 2, 2, 3, 1, 2, 3, 2, 0],   # Elephant
    [2, 3, 4, 2, 1, 2, 1, 3, 3, 1, 2, 0, 3, 1],   # Sheep
    [3, 3, 2, 4, 2, 1, 1, 1, 1, 2, 2, 2, 0, 2],   # Serpent
    [2, 2, 1, 2, 4, 2, 1, 2, 2, 1, 0, 2, 1, 1],   # Dog
    [2, 2, 2, 1, 2, 4, 0, 2, 2, 1, 3, 3, 2, 1],   # Cat
    [2, 2, 1, 1, 1, 0, 4, 2, 2, 2, 2, 2, 1, 2],   # Rat
    [1, 2, 3, 1, 2, 2, 2, 4, 3, 0, 3, 2, 2, 1],   # Cow
    [0, 3, 3, 1, 2, 2, 2, 3, 4, 1, 2, 2, 2, 1],   # Buffalo
    [1, 1, 1, 2, 1, 1, 2, 0, 1, 4, 1, 1, 2, 1],   # Tiger
    [3, 2, 2, 2, 0, 3, 2, 3, 2, 1, 4, 2, 2, 1],   # Deer
    [3, 3, 0, 2, 2, 3, 2, 2, 2, 1, 2, 4, 3, 2],   # Monkey
    [2, 2, 3, 0, 1, 2, 1, 2, 2, 2, 2, 3, 4, 2],   # Mongoose
    [1, 0, 1, 2, 1, 1, 2, 1, 1, 1, 1, 2, 2, 4],   # Lion
]
def yoni_points(a1: str, a2: str) -> float:
    return float(YONI_MATRIX[YONI_ANIMALS.index(a1)][YONI_ANIMALS.index(a2)])

# Planetary friendships (natural) for Graha Maitri
FRIENDS = {
    "Sun": {"Moon", "Mars", "Jupiter"},
    "Moon": {"Sun", "Mercury"},
    "Mars": {"Sun", "Moon", "Jupiter"},
    "Mercury": {"Sun", "Venus"},
    "Jupiter": {"Sun", "Moon", "Mars"},
    "Venus": {"Mercury", "Saturn"},
    "Saturn": {"Mercury", "Venus"},
}
ENEMIES = {
    "Sun": {"Venus", "Saturn"},
    "Moon": set(),
    "Mars": {"Mercury"},
    "Mercury": {"Moon"},
    "Jupiter": {"Mercury", "Venus"},
    "Venus": {"Sun", "Moon"},
    "Saturn": {"Sun", "Moon", "Mars"},
}
def relation(p1: str, p2: str) -> str:
    if p1 == p2:
        return "same"
    if p2 in FRIENDS[p1]:
        return "friend"
    if p2 in ENEMIES[p1]:
        return "enemy"
    return "neutral"

def graha_maitri_points(lord1: str, lord2: str) -> float:
    r1, r2 = relation(lord1, lord2), relation(lord2, lord1)
    pair = {r1, r2}
    if lord1 == lord2 or pair == {"friend"} or pair == {"same"}:
        return 5.0
    if pair == {"friend", "neutral"}:
        return 4.0
    if pair == {"neutral"}:
        return 3.0
    if pair == {"friend", "enemy"}:
        return 1.0
    if pair == {"neutral", "enemy"}:
        return 0.5
    return 0.0

# Gana by nakshatra index
GANA_MAP = {
    "Deva": [0, 4, 6, 7, 12, 14, 16, 21, 26],
    "Manushya": [1, 3, 5, 10, 11, 19, 20, 24, 25],
    "Rakshasa": [2, 8, 9, 13, 15, 17, 18, 22, 23],
}
GANA = [None] * 27
for g, idxs in GANA_MAP.items():
    for i in idxs:
        GANA[i] = g
def gana_points(g_groom: str, g_bride: str) -> float:
    if g_groom == g_bride:
        return 6.0
    pair = (g_groom, g_bride)
    table = {
        ("Deva", "Manushya"): 6.0, ("Manushya", "Deva"): 5.0,
        ("Deva", "Rakshasa"): 1.0, ("Rakshasa", "Deva"): 1.0,
        ("Manushya", "Rakshasa"): 0.0, ("Rakshasa", "Manushya"): 0.0,
    }
    return table[pair]

# Nadi by nakshatra index (Adi, Madhya, Antya repeating in classical order)
NADI_ORDER = ["Adi", "Madhya", "Antya", "Antya", "Madhya", "Adi",
              "Adi", "Madhya", "Antya", "Antya", "Madhya", "Adi",
              "Adi", "Madhya", "Antya", "Antya", "Madhya", "Adi",
              "Adi", "Madhya", "Antya", "Antya", "Madhya", "Adi",
              "Adi", "Madhya", "Antya"]

# --- South Indian (Porutham) tables ----------------------------------------

RAJJU = {
    "Pada":   [0, 8, 9, 17, 18, 26],
    "Kati":   [1, 7, 10, 16, 19, 25],
    "Nabhi":  [2, 6, 11, 15, 20, 24],
    "Kantha": [3, 5, 12, 14, 21, 23],
    "Sira":   [4, 13, 22],
}
RAJJU_OF = [None] * 27
for r, idxs in RAJJU.items():
    for i in idxs:
        RAJJU_OF[i] = r

VEDHA_PAIRS = [
    (0, 17), (1, 16), (2, 15), (3, 14), (4, 22), (5, 21), (6, 20),
    (7, 19), (8, 18), (9, 26), (10, 25), (11, 24), (12, 23),
]  # Chitra (13) exempt
VEDHA_SET = {frozenset(p) for p in VEDHA_PAIRS}

MAHENDRA_COUNTS = {4, 7, 10, 13, 16, 19, 22, 25}


# ---------------------------------------------------------------------------
# Astronomical core
# ---------------------------------------------------------------------------

def julian_day_ut(year: int, month: int, day: int,
                  hour: int, minute: int, tz_offset_hours: float) -> float:
    """Local birth time + timezone offset -> Julian Day in UT."""
    ut_hours = hour + minute / 60.0 - tz_offset_hours
    return swe.julday(year, month, day, ut_hours)


def sidereal_longitude(jd: float, planet_id: int) -> float:
    pos, _ = swe.calc_ut(jd, planet_id, FLAGS)
    return pos[0] % 360.0


def ascendant(jd: float, lat: float, lon: float) -> float:
    """Sidereal ascendant degree (Lahiri)."""
    _, ascmc = swe.houses_ex(jd, lat, lon, b'W', swe.FLG_SIDEREAL)
    return ascmc[0] % 360.0


def sign_of(deg: float) -> int:
    return int(deg // 30)  # 0 = Aries


def nakshatra_of(deg: float) -> tuple[int, int]:
    """Return (nakshatra_index 0-26, pada 1-4)."""
    span = 360.0 / 27.0
    idx = int(deg // span)
    pada = int((deg % span) // (span / 4)) + 1
    return idx, pada


def panchang(year: int, month: int, day: int, sun_deg: float, moon_deg: float) -> dict:
    """
    Basic Panchang for the birth moment: weekday, tithi (lunar day + paksha),
    and yoga. Derived from Sun/Moon sidereal longitudes already computed for
    the chart, so no extra ephemeris calls are needed.
    """
    weekday_name = WEEKDAYS[datetime.date(year, month, day).weekday()]

    tithi_num = int(((moon_deg - sun_deg) % 360.0) // 12.0) + 1  # 1-30
    if tithi_num <= 15:
        paksha = "Shukla"
        tithi_name = "Purnima" if tithi_num == 15 else TITHI_NAMES[tithi_num - 1]
    else:
        idx = tithi_num - 15
        paksha = "Krishna"
        tithi_name = "Amavasya" if idx == 15 else TITHI_NAMES[idx - 1]

    yoga_idx = int(((sun_deg + moon_deg) % 360.0) // (360.0 / 27.0))
    yoga_name = YOGAS[yoga_idx]

    return {
        "weekday": weekday_name,
        "paksha": paksha,
        "tithi_name": tithi_name,
        "tithi_number": tithi_num,
        "tithi": f"{paksha} {tithi_name}",
        "yoga": yoga_name,
    }


# ---------------------------------------------------------------------------
# Birth chart
# ---------------------------------------------------------------------------

@dataclass
class BirthChart:
    name: str
    year: int; month: int; day: int
    hour: int; minute: int
    tz_offset: float          # e.g. 5.5 for IST
    lat: float; lon: float
    gender: str = "unspecified"   # used for role in matching (groom/bride)

    jd: float = field(init=False)
    asc_deg: float = field(init=False)
    asc_sign: int = field(init=False)
    planets: dict = field(init=False)   # name -> {deg, sign, house, nakshatra, pada, retro}

    def __post_init__(self):
        # Swiss Ephemeris' sidereal-mode flag is process/thread state, not tied
        # to this Python module — the module-level swe.set_sid_mode() call at
        # import time only reliably applies to whichever thread ran the
        # import. ASGI servers (uvicorn/FastAPI) dispatch sync request
        # handlers onto a worker-thread pool, so a chart built while handling
        # a real HTTP request can silently run with swisseph's *default*
        # ayanamsa (Fagan-Bradley) instead of Lahiri if that worker thread
        # never itself called set_sid_mode. Re-asserting it here, on every
        # chart construction, guarantees the correct ayanamsa regardless of
        # which thread does the work.
        swe.set_sid_mode(swe.SIDM_LAHIRI)
        self.jd = julian_day_ut(self.year, self.month, self.day,
                                self.hour, self.minute, self.tz_offset)
        self.asc_deg = ascendant(self.jd, self.lat, self.lon)
        self.asc_sign = sign_of(self.asc_deg)
        self.planets = {}
        for pname, pid in PLANETS.items():
            pos, _ = swe.calc_ut(self.jd, pid, FLAGS)
            deg = pos[0] % 360.0
            self._add_planet(pname, deg, retro=pos[3] < 0)
        # Ketu = Rahu + 180
        ketu_deg = (self.planets["Rahu"]["deg"] + 180.0) % 360.0
        self._add_planet("Ketu", ketu_deg, retro=True)

    def _add_planet(self, pname: str, deg: float, retro: bool):
        s = sign_of(deg)
        nk, pada = nakshatra_of(deg)
        self.planets[pname] = {
            "deg": round(deg, 4),
            "deg_in_sign": round(deg % 30, 4),
            "sign": SIGNS[s],
            "sign_index": s,
            "house": (s - self.asc_sign) % 12 + 1,   # whole-sign
            "nakshatra": NAKSHATRAS[nk],
            "nakshatra_index": nk,
            "pada": pada,
            "retrograde": retro,
        }

    # -- key handles ---------------------------------------------------------

    @property
    def moon_sign(self) -> int:
        return self.planets["Moon"]["sign_index"]

    @property
    def moon_nakshatra(self) -> int:
        return self.planets["Moon"]["nakshatra_index"]

    # -- chart layouts -------------------------------------------------------

    def south_indian_chart(self) -> dict:
        """
        South Indian style: 12 FIXED boxes by sign (Aries always 2nd box of
        top row, moving clockwise). Returns sign -> occupants.
        Layout grid (4x4 with hollow middle), sign order clockwise from
        top-row second cell: Pisces Aries Taurus Gemini / Aquarius . . Cancer /
        Capricorn . . Leo / Sagittarius Scorpio Libra Virgo
        """
        boxes = {s: [] for s in SIGNS}
        boxes[SIGNS[self.asc_sign]].append("Asc")
        for pname, p in self.planets.items():
            boxes[p["sign"]].append(pname + ("(R)" if p["retrograde"] else ""))
        grid = [
            ["Pisces", "Aries", "Taurus", "Gemini"],
            ["Aquarius", None, None, "Cancer"],
            ["Capricorn", None, None, "Leo"],
            ["Sagittarius", "Scorpio", "Libra", "Virgo"],
        ]
        return {"style": "south_indian", "grid": grid, "boxes": boxes}

    def north_indian_chart(self) -> dict:
        """
        North Indian style: 12 FIXED houses (diamond), house 1 always the top
        center diamond; signs rotate. Returns house -> {sign, occupants}.
        """
        houses = {}
        for h in range(1, 13):
            s = (self.asc_sign + h - 1) % 12
            houses[h] = {"sign": SIGNS[s], "occupants": []}
        houses[1]["occupants"].append("Asc")
        for pname, p in self.planets.items():
            houses[p["house"]]["occupants"].append(
                pname + ("(R)" if p["retrograde"] else ""))
        return {"style": "north_indian", "houses": houses}

    # -- doshas --------------------------------------------------------------

    def manglik(self) -> dict:
        """
        Kuja/Manglik dosha: Mars in houses 1,4,7,8,12 from Lagna (North
        convention) — house 2 also counted in South Indian convention.
        Also checked from Moon (chandra manglik).
        """
        mars_house_lagna = self.planets["Mars"]["house"]
        mars_house_moon = (self.planets["Mars"]["sign_index"]
                           - self.moon_sign) % 12 + 1
        north_houses = {1, 4, 7, 8, 12}
        south_houses = {1, 2, 4, 7, 8, 12}
        return {
            "from_lagna_house": mars_house_lagna,
            "from_moon_house": mars_house_moon,
            "manglik_north": mars_house_lagna in north_houses,
            "manglik_south": mars_house_lagna in south_houses,
            "chandra_manglik": mars_house_moon in north_houses,
        }

    def summary(self) -> dict:
        return {
            "name": self.name,
            "ascendant": {"sign": SIGNS[self.asc_sign],
                          "degree": round(self.asc_deg % 30, 2)},
            "moon_sign": SIGNS[self.moon_sign],
            "moon_nakshatra": NAKSHATRAS[self.moon_nakshatra],
            "moon_pada": self.planets["Moon"]["pada"],
            "planets": self.planets,
            "manglik": self.manglik(),
            "panchang": panchang(self.year, self.month, self.day,
                                  self.planets["Sun"]["deg"],
                                  self.planets["Moon"]["deg"]),
        }


# ---------------------------------------------------------------------------
# North Indian matching: Ashtakoota (36 gunas)
# ---------------------------------------------------------------------------

def tara_points(nk_bride: int, nk_groom: int) -> float:
    def bad(count):  # count 1-27 -> remainder mod 9 in {3,5,7} inauspicious
        return (count % 9) in (3, 5, 7)
    c1 = (nk_groom - nk_bride) % 27 + 1   # bride -> groom
    c2 = (nk_bride - nk_groom) % 27 + 1   # groom -> bride
    return (0 if bad(c1) else 1.5) + (0 if bad(c2) else 1.5)


def bhakoot_points(sign_groom: int, sign_bride: int) -> float:
    d = (sign_bride - sign_groom) % 12 + 1  # position of bride from groom
    d2 = (sign_groom - sign_bride) % 12 + 1
    bad = {(2, 12), (12, 2), (6, 8), (8, 6), (5, 9), (9, 5)}
    return 0.0 if (d, d2) in bad else 7.0


def ashtakoota(groom: BirthChart, bride: BirthChart) -> dict:
    gs, bs = groom.moon_sign, bride.moon_sign
    gn, bn = groom.moon_nakshatra, bride.moon_nakshatra

    varna_g, varna_b = VARNA[gs % 4], VARNA[bs % 4]
    kootas = {
        "varna": {
            "max": 1, "groom": varna_g, "bride": varna_b,
            "points": 1.0 if VARNA_RANK[varna_g] >= VARNA_RANK[varna_b] else 0.0,
        },
        "vashya": {
            "max": 2, "groom": VASHYA[gs], "bride": VASHYA[bs],
            "points": vashya_points(VASHYA[gs], VASHYA[bs]),
        },
        "tara": {
            "max": 3, "points": tara_points(bn, gn),
        },
        "yoni": {
            "max": 4, "groom": YONI[gn], "bride": YONI[bn],
            "points": yoni_points(YONI[gn], YONI[bn]),
        },
        "graha_maitri": {
            "max": 5, "groom_lord": SIGN_LORDS[gs], "bride_lord": SIGN_LORDS[bs],
            "points": graha_maitri_points(SIGN_LORDS[gs], SIGN_LORDS[bs]),
        },
        "gana": {
            "max": 6, "groom": GANA[gn], "bride": GANA[bn],
            "points": gana_points(GANA[gn], GANA[bn]),
        },
        "bhakoot": {
            "max": 7, "points": bhakoot_points(gs, bs),
        },
        "nadi": {
            "max": 8, "groom": NADI_ORDER[gn], "bride": NADI_ORDER[bn],
            "points": 0.0 if NADI_ORDER[gn] == NADI_ORDER[bn] else 8.0,
        },
    }
    total = sum(k["points"] for k in kootas.values())
    if total >= 32:
        verdict = "Excellent"
    elif total >= 25:
        verdict = "Very Good"
    elif total >= 18:
        verdict = "Acceptable"
    else:
        verdict = "Below Threshold"

    doshas = []
    if kootas["nadi"]["points"] == 0:
        doshas.append("Nadi Dosha")
    if kootas["bhakoot"]["points"] == 0:
        doshas.append("Bhakoot Dosha")
    if kootas["gana"]["points"] == 0:
        doshas.append("Gana Dosha")
    gm, bm = groom.manglik(), bride.manglik()
    if gm["manglik_north"] != bm["manglik_north"]:
        doshas.append("Manglik Mismatch")

    return {"system": "ashtakoota", "kootas": kootas,
            "total": total, "max": 36, "verdict": verdict, "doshas": doshas}


# ---------------------------------------------------------------------------
# South Indian matching: Dasa Porutham (10 poruthams)
# ---------------------------------------------------------------------------

def porutham(groom: BirthChart, bride: BirthChart) -> dict:
    gn, bn = groom.moon_nakshatra, bride.moon_nakshatra
    gs, bs = groom.moon_sign, bride.moon_sign
    count_b_to_g = (gn - bn) % 27 + 1   # from bride's star to groom's

    results = {}

    # 1. Dina (day/health) — like Tara
    results["dina"] = (count_b_to_g % 9) not in (3, 5, 7)

    # 2. Gana (temperament)
    results["gana"] = gana_points(GANA[gn], GANA[bn]) >= 5

    # 3. Mahendra (progeny/protection)
    results["mahendra"] = count_b_to_g in MAHENDRA_COUNTS

    # 4. Stree Dirgha (well-being of bride)
    results["stree_dirgha"] = count_b_to_g > 13

    # 5. Yoni (intimacy)
    results["yoni"] = yoni_points(YONI[gn], YONI[bn]) >= 2

    # 6. Rasi (moon-sign relation)
    d = (gs - bs) % 12 + 1  # groom's rasi counted from bride's
    results["rasi"] = d not in (2, 6, 8, 12)

    # 7. Rasyadhipati (lords' friendship)
    results["rasyadhipati"] = graha_maitri_points(
        SIGN_LORDS[gs], SIGN_LORDS[bs]) >= 4

    # 8. Vashya (mutual regard)
    results["vashya"] = vashya_points(VASHYA[gs], VASHYA[bs]) >= 1

    # 9. Rajju (longevity of union) — same rajju is inauspicious
    results["rajju"] = RAJJU_OF[gn] != RAJJU_OF[bn]

    # 10. Vedha (obstruction) — vedha pair is inauspicious
    results["vedha"] = frozenset({gn, bn}) not in VEDHA_SET

    matched = sum(results.values())
    # Rajju & Vedha are considered essential in South tradition
    essential_ok = results["rajju"] and results["vedha"]
    if matched >= 8 and essential_ok:
        verdict = "Uttamam (Excellent)"
    elif matched >= 6 and essential_ok:
        verdict = "Madhyamam (Good)"
    elif essential_ok:
        verdict = "Adhamam (Weak)"
    else:
        verdict = "Not Recommended (Rajju/Vedha dosha)"

    return {"system": "dasa_porutham",
            "poruthams": results, "matched": matched, "max": 10,
            "essential_rajju_vedha_ok": essential_ok, "verdict": verdict,
            # Part 1 (10 Aug 2026): three-tier classical weighting. Rajju and
            # Vedha were already "essential" in this engine; this names the
            # remaining split the way South Indian practice treats them —
            # a presentation/classification layer over the same pass/fail
            # results above, not a change to any computation.
            "tiers": {
                "critical": ["rajju", "vedha"],
                "major": ["rasi", "rasyadhipati", "yoni", "stree_dirgha"],
                "supporting": ["dina", "gana", "mahendra", "vashya"],
            },
            "tier_counts": {
                "critical": sum(1 for k in ("rajju", "vedha") if results[k]),
                "major": sum(1 for k in ("rasi", "rasyadhipati", "yoni", "stree_dirgha") if results[k]),
                "supporting": sum(1 for k in ("dina", "gana", "mahendra", "vashya") if results[k]),
            }}


# ---------------------------------------------------------------------------
# Navamsa (D9) chart
# ---------------------------------------------------------------------------

def navamsa_sign(deg: float) -> int:
    """D9: each 3°20' of the zodiac maps to one sign, counted from Aries."""
    return int(deg / (360.0 / 108.0)) % 12


def navamsa_positions(chart: "BirthChart") -> dict:
    """Navamsa sign for ascendant and every planet."""
    out = {"Asc": {"sign": SIGNS[navamsa_sign(chart.asc_deg)],
                   "sign_index": navamsa_sign(chart.asc_deg)}}
    for pname, p in chart.planets.items():
        s = navamsa_sign(p["deg"])
        out[pname] = {"sign": SIGNS[s], "sign_index": s}
    return out


def navamsa_chart(chart: "BirthChart", style: str = "south") -> dict:
    """Navamsa rendered as a chart structure in either regional style."""
    nav = navamsa_positions(chart)
    nav_asc = nav["Asc"]["sign_index"]
    boxes = {s: [] for s in SIGNS}
    for name, info in nav.items():
        boxes[info["sign"]].append(name)
    if style == "south":
        grid = [
            ["Pisces", "Aries", "Taurus", "Gemini"],
            ["Aquarius", None, None, "Cancer"],
            ["Capricorn", None, None, "Leo"],
            ["Sagittarius", "Scorpio", "Libra", "Virgo"],
        ]
        return {"style": "south_indian_d9", "grid": grid, "boxes": boxes}
    houses = {}
    for h in range(1, 13):
        s = (nav_asc + h - 1) % 12
        houses[h] = {"sign": SIGNS[s], "occupants": boxes[SIGNS[s]]}
    return {"style": "north_indian_d9", "houses": houses}


# ---------------------------------------------------------------------------
# Vimshottari Dasha
# ---------------------------------------------------------------------------

DASHA_SEQUENCE = [("Ketu", 7), ("Venus", 20), ("Sun", 6), ("Moon", 10),
                  ("Mars", 7), ("Rahu", 18), ("Jupiter", 16),
                  ("Saturn", 19), ("Mercury", 17)]   # 120 years total
NAKSHATRA_LORD = [DASHA_SEQUENCE[i % 9][0] for i in range(27)]
YEAR_DAYS = 365.25


def _jd_to_date(jd: float) -> str:
    y, m, d, _ = swe.revjul(jd)
    return f"{y:04d}-{m:02d}-{int(d):02d}"


def vimshottari_dasha(chart: "BirthChart", n_periods: int = 9) -> list[dict]:
    """
    Mahadasha timeline from birth. Balance of first dasha comes from the
    Moon's fractional progress through its janma nakshatra.
    """
    moon_deg = chart.planets["Moon"]["deg"]
    span = 360.0 / 27.0
    nk = chart.moon_nakshatra
    frac_elapsed = (moon_deg % span) / span

    start_idx = nk % 9
    lord, years = DASHA_SEQUENCE[start_idx]
    balance_years = years * (1.0 - frac_elapsed)

    periods = []
    jd_cursor = chart.jd
    # first (partial) mahadasha
    end = jd_cursor + balance_years * YEAR_DAYS
    periods.append({"lord": lord, "years": round(balance_years, 2),
                    "start": _jd_to_date(jd_cursor), "end": _jd_to_date(end),
                    "start_jd": jd_cursor, "end_jd": end})
    jd_cursor = end
    # subsequent full mahadashas
    i = start_idx
    while len(periods) < n_periods:
        i = (i + 1) % 9
        lord, years = DASHA_SEQUENCE[i]
        end = jd_cursor + years * YEAR_DAYS
        periods.append({"lord": lord, "years": years,
                        "start": _jd_to_date(jd_cursor),
                        "end": _jd_to_date(end),
                        "start_jd": jd_cursor, "end_jd": end})
        jd_cursor = end
    return periods


def antardashas(maha_lord: str, maha_start_jd: float,
                maha_years: float) -> list[dict]:
    """Sub-periods within a mahadasha, starting from the mahadasha lord."""
    start_idx = next(i for i, (l, _) in enumerate(DASHA_SEQUENCE)
                     if l == maha_lord)
    subs = []
    jd_cursor = maha_start_jd
    for k in range(9):
        lord, years = DASHA_SEQUENCE[(start_idx + k) % 9]
        sub_years = maha_years * years / 120.0
        end = jd_cursor + sub_years * YEAR_DAYS
        subs.append({"lord": lord, "years": round(sub_years, 2),
                     "start": _jd_to_date(jd_cursor), "end": _jd_to_date(end),
                     "start_jd": jd_cursor, "end_jd": end})
        jd_cursor = end
    return subs


def current_dasha(chart: "BirthChart", on_jd: float | None = None) -> dict:
    """Mahadasha + antardasha active on a given date (default: today)."""
    if on_jd is None:
        import datetime
        t = datetime.datetime.now(datetime.timezone.utc)
        on_jd = swe.julday(t.year, t.month, t.day, t.hour + t.minute / 60)
    timeline = vimshottari_dasha(chart, n_periods=12)
    maha = next((p for p in timeline
                 if p["start_jd"] <= on_jd < p["end_jd"]), timeline[-1])
    subs = antardashas(maha["lord"], maha["start_jd"], maha["years"])
    antar = next((s for s in subs
                  if s["start_jd"] <= on_jd < s["end_jd"]), subs[-1])
    return {"mahadasha": {k: v for k, v in maha.items()
                          if not k.endswith("_jd")},
            "antardasha": {k: v for k, v in antar.items()
                           if not k.endswith("_jd")}}


# ---------------------------------------------------------------------------
# SVG chart rendering
# ---------------------------------------------------------------------------

def _abbrev(occupants: list[str]) -> list[str]:
    short = {"Sun": "Su", "Moon": "Mo", "Mars": "Ma", "Mercury": "Me",
             "Jupiter": "Ju", "Venus": "Ve", "Saturn": "Sa",
             "Rahu": "Ra", "Ketu": "Ke", "Asc": "Asc"}
    out = []
    for o in occupants:
        r = "(R)" if "(R)" in o else ""
        base = o.replace("(R)", "")
        out.append(short.get(base, base[:2]) + r)
    return out


def render_south_svg(chart_data: dict, title: str = "") -> str:
    """South Indian 4x4 fixed-sign grid as SVG."""
    cell = 110
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{cell*4+20}" '
           f'height="{cell*4+50}" font-family="sans-serif">',
           f'<text x="{(cell*4+20)//2}" y="20" text-anchor="middle" '
           f'font-size="14" font-weight="bold">{title}</text>']
    for r, row in enumerate(chart_data["grid"]):
        for c, sign in enumerate(row):
            x, y = 10 + c * cell, 30 + r * cell
            if sign is None:
                continue
            svg.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" '
                       f'fill="none" stroke="black"/>')
            svg.append(f'<text x="{x+4}" y="{y+14}" font-size="10" '
                       f'fill="gray">{sign[:3]}</text>')
            occ = _abbrev(chart_data["boxes"][sign])
            for i, o in enumerate(occ):
                svg.append(f'<text x="{x+8}" y="{y+30+i*14}" '
                           f'font-size="12">{o}</text>')
    # outer border for the hollow center block
    svg.append(f'<rect x="{10+cell}" y="{30+cell}" width="{cell*2}" '
               f'height="{cell*2}" fill="none" stroke="black"/>')
    svg.append("</svg>")
    return "".join(svg)


# North Indian diamond: text anchor coordinates per house (440x440 canvas)
_NORTH_POS = {1: (220, 120), 2: (110, 65), 3: (60, 120), 4: (110, 220),
              5: (60, 320), 6: (110, 380), 7: (220, 320), 8: (330, 380),
              9: (380, 320), 10: (330, 220), 11: (380, 120), 12: (330, 65)}


def render_north_svg(chart_data: dict, title: str = "") -> str:
    """North Indian fixed-house diamond as SVG."""
    S = 440
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{S}" '
           f'height="{S+30}" font-family="sans-serif">',
           f'<text x="{S//2}" y="18" text-anchor="middle" font-size="14" '
           f'font-weight="bold">{title}</text>',
           f'<g transform="translate(0,30)">',
           f'<rect x="20" y="20" width="{S-40}" height="{S-40}" '
           f'fill="none" stroke="black"/>',
           # diagonals
           f'<line x1="20" y1="20" x2="{S-20}" y2="{S-20}" stroke="black"/>',
           f'<line x1="{S-20}" y1="20" x2="20" y2="{S-20}" stroke="black"/>',
           # midpoint diamond
           f'<line x1="{S//2}" y1="20" x2="20" y2="{S//2}" stroke="black"/>',
           f'<line x1="20" y1="{S//2}" x2="{S//2}" y2="{S-20}" stroke="black"/>',
           f'<line x1="{S//2}" y1="{S-20}" x2="{S-20}" y2="{S//2}" stroke="black"/>',
           f'<line x1="{S-20}" y1="{S//2}" x2="{S//2}" y2="20" stroke="black"/>']
    for h, (x, y) in _NORTH_POS.items():
        info = chart_data["houses"][h]
        svg.append(f'<text x="{x}" y="{y-16}" text-anchor="middle" '
                   f'font-size="9" fill="gray">{h} {info["sign"][:3]}</text>')
        occ = _abbrev(info["occupants"])
        for i, o in enumerate(occ):
            svg.append(f'<text x="{x}" y="{y+i*13}" text-anchor="middle" '
                       f'font-size="11">{o}</text>')
    svg.append("</g></svg>")
    return "".join(svg)




# ---------------------------------------------------------------------------
# Combined report
# ---------------------------------------------------------------------------

def navamsa_compatibility(groom: BirthChart, bride: BirthChart) -> dict:
    """Supplementary D9 checks used by traditional matchmakers."""
    gnav, bnav = navamsa_positions(groom), navamsa_positions(bride)
    g_moon, b_moon = gnav["Moon"]["sign_index"], bnav["Moon"]["sign_index"]
    g_ven, b_ven = gnav["Venus"]["sign_index"], bnav["Venus"]["sign_index"]
    return {
        "groom_navamsa_moon": SIGNS[g_moon],
        "bride_navamsa_moon": SIGNS[b_moon],
        "navamsa_moon_bhakoot_ok": bhakoot_points(g_moon, b_moon) > 0,
        "navamsa_moon_lords_maitri": graha_maitri_points(
            SIGN_LORDS[g_moon], SIGN_LORDS[b_moon]),
        "venus_navamsa_relation": graha_maitri_points(
            SIGN_LORDS[g_ven], SIGN_LORDS[b_ven]),
    }


def dasha_compatibility(groom: BirthChart, bride: BirthChart) -> dict:
    """Current mahadasha lords of both partners and their mutual relation."""
    gd, bd = current_dasha(groom), current_dasha(bride)
    gl, bl = gd["mahadasha"]["lord"], bd["mahadasha"]["lord"]
    shadow = {"Rahu": "Saturn", "Ketu": "Mars"}   # nodes act like these lords
    gl_eff, bl_eff = shadow.get(gl, gl), shadow.get(bl, bl)
    return {
        "groom_current": gd, "bride_current": bd,
        "mahadasha_lords_relation_points": graha_maitri_points(gl_eff, bl_eff),
    }


# ---------------------------------------------------------------------------
# Marriage Analysis — Part 1: the classical, deterministic layer (10 Aug 2026)
# ---------------------------------------------------------------------------
# Everything below is textbook Parashari computation — dignity tables,
# combustion orbs, graha drishti, 7th-house/lord analysis, graded Mangal
# dosha with cancellation, and a D9 deep-dive. No invented scores: every
# output is a classical FACT (a dignity, an aspect, a placement), not a
# model rating. Model-scored layers (synastry weights, foundation scores,
# timing windows) are deliberately deferred to Part 2 where they will be
# labelled as HiJODI model analysis, not tradition.

# Exaltation sign (and deep-exaltation degree) per BPHS. Debilitation is the
# 7th sign from exaltation. Rahu/Ketu are excluded: classical sources
# disagree on nodal exaltation (Taurus/Scorpio vs Gemini/Sagittarius), so
# rather than pick a camp we report nodes as dignity-neutral.
EXALTATION = {  # planet -> (sign_index, deep_degree)
    "Sun": (0, 10), "Moon": (1, 3), "Mars": (9, 28), "Mercury": (5, 15),
    "Jupiter": (3, 5), "Venus": (11, 27), "Saturn": (6, 20),
}
# Moolatrikona: sign + degree range (BPHS standard ranges).
MOOLATRIKONA = {  # planet -> (sign_index, deg_from, deg_to)
    "Sun": (4, 0, 20), "Moon": (1, 3, 30), "Mars": (0, 0, 12),
    "Mercury": (5, 16, 20), "Jupiter": (8, 0, 10), "Venus": (6, 0, 15),
    "Saturn": (10, 0, 20),
}
OWN_SIGNS = {  # from SIGN_LORDS, inverted
    "Sun": [4], "Moon": [3], "Mars": [0, 7], "Mercury": [2, 5],
    "Jupiter": [8, 11], "Venus": [1, 6], "Saturn": [9, 10],
}
# Ordinal strength ladder (standard shastra ordering, 7 = strongest).
DIGNITY_RANK = {"exalted": 7, "moolatrikona": 6, "own": 5, "friend": 4,
                "neutral": 3, "enemy": 2, "debilitated": 1}

def dignity(planet: str, sign_index: int, deg_in_sign: float) -> dict:
    """Classical dignity of a planet in a sign (BPHS ladder)."""
    if planet in ("Rahu", "Ketu"):
        return {"status": "node", "rank": None,
                "note": "nodal dignity varies by tradition — not applied"}
    # Moolatrikona is degree-bounded and, for Moon (Taurus 3-30) and Mercury
    # (Virgo 16-20), shares a sign with the exaltation — so the MT range must
    # be tested BEFORE the sign-level exaltation test, giving the classical
    # degree partition (e.g. Mercury in Virgo: 0-15 exalted, 16-20 MT,
    # 20-30 own).
    mt = MOOLATRIKONA.get(planet)
    if mt and sign_index == mt[0] and mt[1] <= deg_in_sign <= mt[2]:
        return {"status": "moolatrikona", "rank": 6}
    ex = EXALTATION.get(planet)
    if ex and sign_index == ex[0]:
        # Moon and Mercury's exaltation shares its sign with their MT (and,
        # for Mercury, with own-sign Virgo): there the exaltation band runs
        # only up to the deep-exaltation degree (Moon 0-3 Taurus, Mercury
        # 0-15 Virgo); beyond it the MT/own checks decide. For all other
        # planets exaltation is the whole sign.
        shares_sign = mt is not None and mt[0] == ex[0]
        if not shares_sign or deg_in_sign <= ex[1]:
            return {"status": "exalted", "rank": 7,
                    "deep": abs(deg_in_sign - ex[1]) <= 1.0}
    if ex and sign_index == (ex[0] + 6) % 12:
        return {"status": "debilitated", "rank": 1,
                "deep": abs(deg_in_sign - ex[1]) <= 1.0}
    if sign_index in OWN_SIGNS.get(planet, []):
        return {"status": "own", "rank": 5}
    rel = relation(planet, SIGN_LORDS[sign_index])
    status = {"friend": "friend", "enemy": "enemy"}.get(rel, "neutral")
    return {"status": status, "rank": DIGNITY_RANK[status]}

# Combustion orbs (degrees of longitudinal separation from the Sun) —
# standard values; Mercury and Venus use tighter orbs when retrograde.
COMBUSTION_ORB = {"Moon": 12.0, "Mars": 17.0, "Mercury": 14.0,
                  "Jupiter": 11.0, "Venus": 10.0, "Saturn": 15.0}
COMBUSTION_ORB_RETRO = {"Mercury": 12.0, "Venus": 8.0}

def is_combust(chart: BirthChart, planet: str) -> bool:
    if planet in ("Sun", "Rahu", "Ketu") or planet not in COMBUSTION_ORB:
        return False
    p = chart.planets[planet]
    orb = (COMBUSTION_ORB_RETRO.get(planet) if p["retrograde"] else None) \
        or COMBUSTION_ORB[planet]
    diff = abs(chart.planets["Sun"]["deg"] - p["deg"]) % 360.0
    return min(diff, 360.0 - diff) <= orb

# Graha drishti (whole-sign Parashari aspects): every graha aspects the 7th
# sign from itself; Mars additionally the 4th and 8th; Jupiter the 5th and
# 9th; Saturn the 3rd and 10th. Nodal aspects vary by tradition (some give
# Rahu/Ketu 5/7/9) — excluded here for the same reason as nodal dignity.
SPECIAL_DRISHTI = {"Mars": (4, 8), "Jupiter": (5, 9), "Saturn": (3, 10)}

def aspects_on_sign(chart: BirthChart, target_sign: int) -> list:
    """Planets casting graha drishti onto a target sign (whole-sign)."""
    out = []
    for pname, p in chart.planets.items():
        if pname in ("Rahu", "Ketu"):
            continue
        offset = (target_sign - p["sign_index"]) % 12 + 1  # counted inclusively
        if offset == 7 or offset in SPECIAL_DRISHTI.get(pname, ()):
            out.append(pname)
    return out

# Natural benefics/malefics (simplified standard: Mercury and Moon counted
# benefic without the conditional rules — noted, deliberate simplification).
NATURAL_BENEFICS = {"Jupiter", "Venus", "Mercury", "Moon"}
NATURAL_MALEFICS = {"Sun", "Mars", "Saturn", "Rahu", "Ketu"}

def seventh_house_analysis(chart: BirthChart, ref: str) -> dict:
    """The marriage house read from a reference point: 'lagna'|'moon'|'venus'."""
    ref_sign = {"lagna": chart.asc_sign,
                "moon": chart.planets["Moon"]["sign_index"],
                "venus": chart.planets["Venus"]["sign_index"]}[ref]
    seventh = (ref_sign + 6) % 12
    occupants = [n for n, p in chart.planets.items() if p["sign_index"] == seventh]
    aspects = aspects_on_sign(chart, seventh)
    lord = SIGN_LORDS[seventh]
    lp = chart.planets[lord]
    influences = set(occupants) | set(aspects)
    return {
        "reference": ref, "seventh_sign": SIGNS[seventh],
        "occupants": occupants, "aspects_from": aspects,
        "benefic_influences": sorted(influences & NATURAL_BENEFICS),
        "malefic_influences": sorted(influences & NATURAL_MALEFICS),
        "lord": lord,
        "lord_placement": {
            "sign": lp["sign"],
            "house_from_reference": (lp["sign_index"] - ref_sign) % 12 + 1,
            "dignity": dignity(lord, lp["sign_index"], lp["deg_in_sign"]),
            "combust": is_combust(chart, lord),
            "retrograde": lp["retrograde"],
            "conjunct": [n for n, p in chart.planets.items()
                         if p["sign_index"] == lp["sign_index"] and n != lord],
        },
    }

def person_marriage_facts(chart: BirthChart) -> dict:
    """All Part-1 classical facts for one person's chart."""
    return {
        "dignities": {n: dignity(n, p["sign_index"], p["deg_in_sign"])
                      for n, p in chart.planets.items()},
        "combust": [n for n in chart.planets if is_combust(chart, n)],
        "seventh_house": {ref: seventh_house_analysis(chart, ref)
                          for ref in ("lagna", "moon", "venus")},
    }

def manglik_graded(groom: BirthChart, bride: BirthChart) -> dict:
    """
    Graded Mangal verdict instead of a binary yes/no.
    Person level: none / mild / significant / cancelled.
    Couple level: adds 'balanced' when both carry the dosha.
    Cancellation implemented conservatively — only the least-disputed rule:
    Mars in own sign (Aries/Scorpio) or exalted (Capricorn) neutralises the
    dosha. Wider cancellation lists (by sign-in-house, aspect, etc.) vary too
    much between classical sources to apply silently.
    """
    def grade(ch: BirthChart) -> dict:
        m = ch.manglik()
        refs = []
        if m["manglik_north"]:
            refs.append("lagna")
        if m["chandra_manglik"]:
            refs.append("moon")
        # Venus reference (same house sets as lagna, counted from Venus) —
        # part of the roadmap's triple-reference check.
        venus_house = (ch.planets["Mars"]["sign_index"]
                       - ch.planets["Venus"]["sign_index"]) % 12 + 1
        if venus_house in (1, 4, 7, 8, 12):
            refs.append("venus")
        mars_dig = dignity("Mars", ch.planets["Mars"]["sign_index"],
                           ch.planets["Mars"]["deg_in_sign"])
        cancelled = bool(refs) and mars_dig["status"] in ("own", "exalted", "moolatrikona")
        # Lagna-reference Mangal is the primary classical form; Moon (chandra)
        # and Venus references are secondary. "Significant" therefore requires
        # the lagna reference — secondary-only combinations stay "mild",
        # matching the product's fear-free, no-overclaiming stance.
        level = ("none" if not refs else
                 "cancelled" if cancelled else
                 "significant" if "lagna" in refs else
                 "mild")
        return {"references": refs, "south_convention_second_house": m["manglik_south"] and not m["manglik_north"],
                "mars_dignity": mars_dig, "level": level,
                "cancellation_reason": ("Mars in " + mars_dig["status"] + " sign") if cancelled else None}
    g, b = grade(groom), grade(bride)
    both_active = (g["level"] in ("mild", "significant")
                   and b["level"] in ("mild", "significant"))
    couple = ("balanced" if both_active else
              "one_sided" if (g["level"] in ("mild", "significant")) != (b["level"] in ("mild", "significant")) else
              "clear")
    return {"groom": g, "bride": b, "couple_verdict": couple,
            "note": ("Both charts carry Mangal dosha — classically read as mutually "
                     "balancing rather than doubly afflicted.") if both_active else None}

def d9_deep(groom: BirthChart, bride: BirthChart) -> dict:
    """D9 deep-dive: D9 lagna, D9 7th house/lord, vargottama, D1<->D9 confirmation."""
    def per(ch: BirthChart) -> dict:
        nav = navamsa_positions(ch)
        d9_asc = nav["Asc"]["sign_index"]
        d9_seventh = (d9_asc + 6) % 12
        d9_occupants = [n for n, v in nav.items()
                        if n != "Asc" and v["sign_index"] == d9_seventh]
        d9_lord = SIGN_LORDS[d9_seventh]
        # sign-level dignity in D9 (degree-based rungs don't apply in varga)
        def d9_dignity(pl: str) -> dict:
            return dignity(pl, nav[pl]["sign_index"], 15.0)
        vargottama = [n for n, p in ch.planets.items()
                      if p["sign_index"] == nav[n]["sign_index"]]
        if ch.asc_sign == d9_asc:
            vargottama.insert(0, "Asc")
        d1_seventh_lord = SIGN_LORDS[(ch.asc_sign + 6) % 12]
        return {
            "d9_lagna": SIGNS[d9_asc],
            "d9_seventh_sign": SIGNS[d9_seventh],
            "d9_seventh_occupants": d9_occupants,
            "d9_seventh_lord": d9_lord,
            "d9_seventh_lord_dignity": d9_dignity(d9_lord),
            "venus_d9": {"sign": nav["Venus"]["sign"], "dignity": d9_dignity("Venus")},
            "jupiter_d9": {"sign": nav["Jupiter"]["sign"], "dignity": d9_dignity("Jupiter")},
            "vargottama": vargottama,
            "d1_seventh_lord_in_d9": {"lord": d1_seventh_lord,
                                      "d9_sign": nav[d1_seventh_lord]["sign"],
                                      "dignity": d9_dignity(d1_seventh_lord)},
        }
    return {"groom": per(groom), "bride": per(bride)}

# ---------------------------------------------------------------------------
# Marriage Analysis — Part 2: the HiJODI MODEL layer (10 Aug 2026)
# ---------------------------------------------------------------------------
# Unlike Part 1 (pure classical facts), everything below combines classical
# primitives using weights/buckets HiJODI chose. It must always be presented
# in-report as "HiJODI model analysis", never as shastra. House rule
# preserved: NO single overall compatibility score is produced anywhere.

# Sign-distance buckets (counted inclusively, symmetric pairs). Grounded in
# the same distance lore the Rasi porutham/Bhakoot use (2/12, 6/8 adverse;
# trines easy; 7th the partnership axis) — but the three-bucket grouping is
# a HiJODI model choice, not a classical rule.
def _distance_bucket(sign_a: int, sign_b: int) -> tuple:
    d1 = (sign_b - sign_a) % 12 + 1
    d2 = (sign_a - sign_b) % 12 + 1
    d = min(d1, d2)  # symmetric pair (2/12 -> 2, 6/8 -> 6, etc.)
    if d1 == 1:
        return 1, "flowing"
    if d in (5, 7, 9) or d1 in (5, 7, 9):
        return d1, "flowing"
    if d in (3, 4) or d1 in (3, 4, 10, 11):
        return d1, "working"
    return d1, "friction"   # 2/12 and 6/8 axes

_SYNASTRY_PAIRS = [
    ("Moon", "Moon", "Emotional wavelength — how the two inner lives sit together"),
    ("Venus", "Mars", "Attraction — his Venus to her Mars"),
    ("Mars", "Venus", "Attraction — his Mars to her Venus"),
    ("Venus", "Venus", "Affection style — how each expresses love"),
    ("Mercury", "Mercury", "Communication — how the two minds exchange"),
    ("Jupiter", "Moon", "His Jupiter to her Moon — guidance, generosity, growth"),
    ("Moon", "Jupiter", "Her Jupiter to his Moon — guidance, generosity, growth"),
    ("Saturn", "Moon", "His Saturn to her Moon — structure or heaviness"),
    ("Moon", "Saturn", "Her Saturn to his Moon — structure or heaviness"),
    ("Saturn", "Venus", "His Saturn to her Venus — steadiness vs restraint in love"),
    ("Venus", "Saturn", "Her Saturn to his Venus — steadiness vs restraint in love"),
]

def synastry_matrix(groom: BirthChart, bride: BirthChart) -> list:
    """Cross-chart planet pairs, bucketed by classical sign distance."""
    out = []
    for pa, pb, theme in _SYNASTRY_PAIRS:
        sa = groom.planets[pa]["sign_index"]
        sb = bride.planets[pb]["sign_index"]
        dist, bucket = _distance_bucket(sa, sb)
        out.append({"groom_planet": pa, "bride_planet": pb, "theme": theme,
                    "groom_sign": SIGNS[sa], "bride_sign": SIGNS[sb],
                    "distance": dist, "read": bucket})
    return out

def karaka_profile(chart: BirthChart) -> dict:
    """Venus (affection), Jupiter (commitment/values), Saturn (structure) —
    per person, from Part-1 primitives. Saturn's read is contextual: strong
    and connected to the marriage zone = stabilising; afflicted and
    connected = heavier — the classical question, answered mechanically."""
    def basic(pl: str) -> dict:
        p = chart.planets[pl]
        return {"sign": p["sign"], "house": p["house"],
                "dignity": dignity(pl, p["sign_index"], p["deg_in_sign"]),
                "combust": is_combust(chart, pl), "retrograde": p["retrograde"]}
    seventh = (chart.asc_sign + 6) % 12
    sat = chart.planets["Saturn"]
    sat_touches_7th = (sat["sign_index"] == seventh
                       or "Saturn" in aspects_on_sign(chart, seventh))
    sat_moon = _distance_bucket(sat["sign_index"], chart.planets["Moon"]["sign_index"])[1]
    sat_dig = dignity("Saturn", sat["sign_index"], sat["deg_in_sign"])
    saturn_read = ("stabilising" if sat_touches_7th and (sat_dig["rank"] or 0) >= 4
                   else "heavy" if sat_touches_7th and (sat_dig["rank"] or 0) <= 2
                   else "background")
    return {"venus": basic("Venus"), "jupiter": basic("Jupiter"),
            "saturn": {**basic("Saturn"), "touches_7th": sat_touches_7th,
                       "to_own_moon": sat_moon, "model_read": saturn_read}}

def nodes_synastry(groom: BirthChart, bride: BirthChart) -> list:
    """Rahu/Ketu cross-chart contacts (same sign or opposition only) —
    flagged as intensity notes, deliberately not scored."""
    out = []
    for node in ("Rahu", "Ketu"):
        for target in ("Moon", "Venus"):
            for a, b, who in ((groom, bride, "groom"), (bride, groom, "bride")):
                ns = a.planets[node]["sign_index"]
                ts = b.planets[target]["sign_index"]
                d = (ts - ns) % 12 + 1
                if d in (1, 7):
                    out.append({
                        "node": node, "node_chart": who, "target": target,
                        "contact": "conjunction" if d == 1 else "opposition",
                        "note": f"{who.capitalize()}'s {node} {'with' if d == 1 else 'opposite'} the other's {target} — "
                                "classically read as magnetic, karmically charged intensity; energising when named, destabilising when unconscious."})
    return out

def _maha_lord_at(chart: BirthChart, jd: float) -> str:
    timeline = vimshottari_dasha(chart, n_periods=12)
    for d in timeline:
        if d["start_jd"] <= jd < d["end_jd"]:
            return d["lord"]
    return timeline[-1]["lord"]

def dasha_windows(groom: BirthChart, bride: BirthChart) -> list:
    """Mahadasha-lord relation across three forward windows. Model layer:
    the window buckets and signal thresholds are HiJODI choices; the lord
    relation itself is classical graha maitri (nodes read as Saturn/Mars)."""
    shadow = {"Rahu": "Saturn", "Ketu": "Mars"}
    now = datetime.datetime.now(datetime.timezone.utc)
    jd_now = swe.julday(now.year, now.month, now.day, 12.0)
    out = []
    for label, offset_years in (("Now — 1 year", 0.5), ("1 — 3 years", 2.0), ("3 — 5 years", 4.0)):
        jd = jd_now + offset_years * 365.25
        gl, bl = _maha_lord_at(groom, jd), _maha_lord_at(bride, jd)
        pts = graha_maitri_points(shadow.get(gl, gl), shadow.get(bl, bl))
        signal = "supportive" if pts >= 4 else "mixed" if pts >= 2.5 else "demanding"
        out.append({"window": label, "groom_lord": gl, "bride_lord": bl,
                    "maitri_points": pts, "signal": signal})
    return out

def transits_today(chart: BirthChart) -> dict:
    """Slow movers (Jupiter/Saturn/Rahu) from the natal Moon, today —
    including the standard sade-sati check (Saturn 12th/1st/2nd from Moon)."""
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    now = datetime.datetime.now(datetime.timezone.utc)
    jd = swe.julday(now.year, now.month, now.day, 12.0)
    moon_sign = chart.planets["Moon"]["sign_index"]
    out = {}
    for pl, pid in (("Jupiter", swe.JUPITER), ("Saturn", swe.SATURN), ("Rahu", swe.MEAN_NODE)):
        pos, _ = swe.calc_ut(jd, pid, FLAGS)
        s = sign_of(pos[0] % 360.0)
        out[pl.lower() + "_from_moon"] = (s - moon_sign) % 12 + 1
    h = out["saturn_from_moon"]
    out["sade_sati"] = ({12: "first phase", 1: "peak phase", 2: "closing phase"}.get(h)
                        if h in (12, 1, 2) else None)
    return out

_MATRIX_DIMS = [
    # (dimension, [synastry pair indexes], extra evidence fn)
    ("Emotional bond", [0], lambda ak, pr: [("Nadi clear", ak["kootas"]["nadi"]["points"] > 0)]),
    ("Attraction & romance", [1, 2, 3], lambda ak, pr: [("Yoni favourable", ak["kootas"]["yoni"]["points"] >= 2)]),
    ("Communication", [4], lambda ak, pr: [("Gana compatible", ak["kootas"]["gana"]["points"] >= 3)]),
    ("Growth & commitment", [5, 6], lambda ak, pr: [("Sign-lord friendship", ak["kootas"]["graha_maitri"]["points"] >= 4)]),
    ("Stability & structure", [7, 8, 9, 10], lambda ak, pr: [("Rajju clear", pr["poruthams"]["rajju"])]),
]

def relationship_matrix(syn: list, ak: dict, pr: dict) -> list:
    """The final per-dimension read — visible evidence, three-colour signal,
    and deliberately NO overall number (house rule)."""
    out = []
    for dim, idxs, extra_fn in _MATRIX_DIMS:
        reads = [syn[i]["read"] for i in idxs]
        extras = extra_fn(ak, pr)
        score = (sum({"flowing": 2, "working": 1, "friction": 0}[r] for r in reads)
                 + sum(2 if ok else 0 for _, ok in extras))
        max_score = 2 * len(reads) + 2 * len(extras)
        frac = score / max_score if max_score else 0
        signal = "green" if frac >= 0.65 else "amber" if frac >= 0.35 else "red"
        out.append({"dimension": dim, "signal": signal,
                    "synastry_evidence": [
                        {"pair": f"{syn[i]['groom_planet']}×{syn[i]['bride_planet']}",
                         "read": syn[i]["read"]} for i in idxs],
                    "classical_evidence": [{"check": n, "ok": ok} for n, ok in extras]})
    return out

def model_analysis(groom: BirthChart, bride: BirthChart, ak: dict, pr: dict) -> dict:
    syn = synastry_matrix(groom, bride)
    return {
        "label": "HiJODI model analysis — classical primitives, HiJODI weighting; not shastra, never a verdict",
        "synastry": syn,
        "karakas": {"groom": karaka_profile(groom), "bride": karaka_profile(bride)},
        "nodes": nodes_synastry(groom, bride),
        "dasha_windows": dasha_windows(groom, bride),
        "transits": {"groom": transits_today(groom), "bride": transits_today(bride)},
        "matrix": relationship_matrix(syn, ak, pr),
    }

def match_report(groom: BirthChart, bride: BirthChart) -> dict:
    ak, pr = ashtakoota(groom, bride), porutham(groom, bride)
    return {
        "groom": groom.summary(),
        "bride": bride.summary(),
        "north_indian_matching": ak,
        "south_indian_matching": pr,
        "navamsa_analysis": navamsa_compatibility(groom, bride),
        "dasha_analysis": dasha_compatibility(groom, bride),
        "reconciliation": north_south_reconciliation(ak, pr),
        "marriage_analysis": {
            "version": "part2-classical+model",
            "groom": person_marriage_facts(groom),
            "bride": person_marriage_facts(bride),
            "manglik_verdict": manglik_graded(groom, bride),
            "d9": d9_deep(groom, bride),
            # Part 2 — rides inside marriage_analysis so the worker's existing
            # wholesale pass-through carries it with no worker change.
            "model": model_analysis(groom, bride, ak, pr),
        },
    }


# ---------------------------------------------------------------------------
# North vs South reconciliation — same underlying chart, two independent
# classical scoring systems. Ashtakoota (North) and Dasa Porutham (South)
# share several factors that are the *same traditional concept* computed a
# different way (Tara~Dina, Nadi~Rajju, Bhakoot~Rasi, Gana~Gana, Vashya~Vashya,
# Yoni~Yoni, Graha Maitri~Rasyadhipati — the standard textbook correspondence
# between the two systems). This reads the two already-computed results side
# by side rather than computing anything new, so it can't disagree with the
# koota/porutham numbers above — it can only ever restate them differently.
# ---------------------------------------------------------------------------

# (concept, north koota key, south porutham key)
_RECONCILIATION_PAIRS = [
    ("Birth-star wellbeing", "tara", "dina"),
    ("Temperament nature", "gana", "gana"),
    ("Mutual amenability", "vashya", "vashya"),
    ("Instinctive/physical harmony", "yoni", "yoni"),
    ("Friendship of sign lords", "graha_maitri", "rasyadhipati"),
    ("Moon-sign placement", "bhakoot", "rasi"),
    ("Constitution / longevity (essential in both)", "nadi", "rajju"),
]


def _ashtakoota_signal(total: float) -> str:
    if total >= 25:
        return "strong"
    if total >= 18:
        return "mixed"
    return "review"


def _porutham_signal(pr: dict) -> str:
    # "review" is reserved for a failed essential (Rajju/Vedha) — tradition's
    # gravest objection. A passed-essential-but-low-count result is "weak",
    # not "review": less urgent, still worth naming honestly.
    if not pr["essential_rajju_vedha_ok"]:
        return "review"
    if pr["matched"] >= 8:
        return "strong"
    if pr["matched"] >= 6:
        return "mixed"
    return "weak"


def north_south_reconciliation(ak: dict, pr: dict) -> dict:
    pairs = []
    for concept, koota_key, porutham_key in _RECONCILIATION_PAIRS:
        k = ak["kootas"][koota_key]
        north_ok = (k["points"] / k["max"]) >= 0.5
        south_ok = bool(pr["poruthams"][porutham_key])
        pairs.append({
            "concept": concept, "north_factor": koota_key, "south_factor": porutham_key,
            "north_points": k["points"], "north_max": k["max"], "north_ok": north_ok,
            "south_ok": south_ok, "agree": north_ok == south_ok,
        })
    north_only = [k for k in ak["kootas"] if k not in dict((p["north_factor"], 1) for p in pairs)]
    south_only = [k for k in pr["poruthams"] if k not in dict((p["south_factor"], 1) for p in pairs)]
    agreements = [p for p in pairs if p["agree"]]
    disagreements = [p for p in pairs if not p["agree"]]
    return {
        "north_signal": _ashtakoota_signal(ak["total"]),
        "south_signal": _porutham_signal(pr),
        "pairs": pairs,
        "agreements": [p["concept"] for p in agreements],
        "disagreements": [p["concept"] for p in disagreements],
        "north_only_factors": north_only,
        "south_only_factors": south_only,
    }


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    groom = BirthChart(name="Aarav", year=1992, month=8, day=23,
                       hour=14, minute=30, tz_offset=5.5,
                       lat=28.6139, lon=77.2090, gender="male")     # Delhi
    bride = BirthChart(name="Priya", year=1994, month=12, day=4,
                       hour=6, minute=45, tz_offset=5.5,
                       lat=13.0827, lon=80.2707, gender="female")   # Chennai

    print("=== GROOM CHART SUMMARY ===")
    s = groom.summary()
    print(f"Asc: {s['ascendant']} | Moon: {s['moon_sign']} "
          f"({s['moon_nakshatra']} pada {s['moon_pada']})")
    for p, d in s["planets"].items():
        print(f"  {p:8s} {d['sign']:12s} {d['deg_in_sign']:6.2f}° "
              f"H{d['house']:<2d} {d['nakshatra']}-{d['pada']}"
              f"{' R' if d['retrograde'] else ''}")

    print("\n=== NORTH INDIAN CHART (groom) ===")
    ni = groom.north_indian_chart()
    for h, info in ni["houses"].items():
        occ = ", ".join(info["occupants"]) or "-"
        print(f"  House {h:2d} [{info['sign']:12s}]: {occ}")

    print("\n=== SOUTH INDIAN CHART (groom) ===")
    si = groom.south_indian_chart()
    for row in si["grid"]:
        cells = []
        for cell in row:
            if cell is None:
                cells.append(" " * 22)
            else:
                occ = ",".join(si["boxes"][cell]) or "-"
                cells.append(f"{cell[:3]}:{occ}"[:22].ljust(22))
        print("  " + " | ".join(cells))

    print("\n=== ASHTAKOOTA (North Indian, 36 gunas) ===")
    ak = ashtakoota(groom, bride)
    for k, v in ak["kootas"].items():
        print(f"  {k:14s}: {v['points']:4.1f} / {v['max']}")
    print(f"  TOTAL: {ak['total']} / 36 -> {ak['verdict']}")
    print(f"  Doshas: {ak['doshas'] or 'None'}")

    print("\n=== DASA PORUTHAM (South Indian) ===")
    pr = porutham(groom, bride)
    for k, ok in pr["poruthams"].items():
        print(f"  {k:14s}: {'✓' if ok else '✗'}")
    print(f"  MATCHED: {pr['matched']} / 10 -> {pr['verdict']}")

    print("\n=== MANGLIK ===")
    print(f"  Groom: {groom.manglik()}")
    print(f"  Bride: {bride.manglik()}")

    print("\n=== NAVAMSA (D9) — groom ===")
    for name, info in navamsa_positions(groom).items():
        print(f"  {name:8s} -> {info['sign']}")

    print("\n=== VIMSHOTTARI DASHA — groom (first 5 mahadashas) ===")
    for p in vimshottari_dasha(groom, n_periods=5):
        print(f"  {p['lord']:8s} {p['start']} -> {p['end']} ({p['years']}y)")
    cd = current_dasha(groom)
    print(f"  CURRENT: {cd['mahadasha']['lord']} mahadasha / "
          f"{cd['antardasha']['lord']} antardasha")

    print("\n=== NAVAMSA + DASHA COMPATIBILITY ===")
    print(f"  {navamsa_compatibility(groom, bride)}")
    dc = dasha_compatibility(groom, bride)
    print(f"  Mahadasha lords: {dc['groom_current']['mahadasha']['lord']} x "
          f"{dc['bride_current']['mahadasha']['lord']} -> "
          f"{dc['mahadasha_lords_relation_points']} maitri points")

    # SVG exports
    with open("north_chart_groom.svg", "w") as f:
        f.write(render_north_svg(groom.north_indian_chart(),
                                 "Aarav — Rasi (North Indian)"))
    with open("south_chart_groom.svg", "w") as f:
        f.write(render_south_svg(groom.south_indian_chart(),
                                 "Aarav — Rasi (South Indian)"))
    with open("south_chart_groom_d9.svg", "w") as f:
        f.write(render_south_svg(navamsa_chart(groom, "south"),
                                 "Aarav — Navamsa D9 (South Indian)"))
    print("\nSVG charts written: north_chart_groom.svg, "
          "south_chart_groom.svg, south_chart_groom_d9.svg")
