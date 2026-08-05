"""
MindMatch scoring engine — deterministic, config-driven.
Implements HiJodi-Scoring-Algorithms.md Part A (dimension scoring) + Part B (convergence).
Ground rules: no composite total; importance shapes severity, never the gap;
astro/numero never modify MindMatch; scenarios unscored.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from statistics import mean, pstdev

ENGINE_VERSION = "1.0.0"

DEFAULT_CONFIG = {
    "k_low": 0.70, "k_span": 0.60,
    "t_aligned": 22.0, "t_fault": 45.0,
    "t_pg": 35.0,
    "override_con_gap": 3,      # construct gap (1-5 scale units)
    "override_imp": 75.0,       # both importances >= this
    "straightline_sd": 0.30,
    "scale_min": 1, "scale_max": 5,
}

DIMENSIONS = ["Communication", "Money & finances", "Intimacy", "Parenting plans",
              "Family & in-laws", "Sharing the load", "Personal space",
              "Future & career", "Values & beliefs"]

def to100(r: float, cfg=DEFAULT_CONFIG) -> float:
    lo, hi = cfg["scale_min"], cfg["scale_max"]
    return (r - lo) / (hi - lo) * 100.0

def apply_reverse(r: int, cfg=DEFAULT_CONFIG) -> int:
    return cfg["scale_min"] + cfg["scale_max"] - r

@dataclass
class PartnerDimAnswers:
    positions: dict[str, int]            # construct_id -> raw 1-5
    importance: int                      # raw 1-5
    perceptions: dict[str, int] = field(default_factory=dict)  # construct_id -> guess of PARTNER

@dataclass
class DimensionResult:
    dimension: str
    state: str                           # ALIGNED | DRIFTING | FAULT_LINE
    severity: float
    g_pos: float
    pos_a: float
    pos_b: float
    imp_avg: float
    pg: float | None
    pg_a_to_b: float | None
    pg_b_to_a: float | None
    perception_flag: bool
    top_drivers: list[dict]
    override_fired: bool

def _norm_positions(ans: PartnerDimAnswers, reverse_keys: set[str], cfg) -> dict[str, float]:
    out = {}
    for c, r in ans.positions.items():
        rr = apply_reverse(r, cfg) if c in reverse_keys else r
        out[c] = to100(rr, cfg)
    return out

def score_dimension(dim: str, a: PartnerDimAnswers, b: PartnerDimAnswers,
                    reverse_keys: set[str] | None = None,
                    cfg: dict | None = None) -> DimensionResult:
    cfg = {**DEFAULT_CONFIG, **(cfg or {})}
    rk = reverse_keys or set()
    pa, pb = _norm_positions(a, rk, cfg), _norm_positions(b, rk, cfg)
    shared = sorted(set(pa) & set(pb))
    if not shared:
        raise ValueError(f"no shared constructs for {dim}")
    pos_a, pos_b = mean(pa[c] for c in shared), mean(pb[c] for c in shared)
    g_pos = abs(pos_a - pos_b)
    imp_a, imp_b = to100(a.importance, cfg), to100(b.importance, cfg)
    imp_avg = (imp_a + imp_b) / 2
    factor = cfg["k_low"] + cfg["k_span"] * imp_avg / 100.0
    severity = g_pos * factor

    # construct-level drivers (raw 1-5 gap for override; both stances for narrative)
    drivers = []
    for c in shared:
        ra = apply_reverse(a.positions[c], cfg) if c in rk else a.positions[c]
        rb = apply_reverse(b.positions[c], cfg) if c in rk else b.positions[c]
        drivers.append({"construct": c, "gap_raw": abs(ra - rb),
                        "a": pa[c], "b": pb[c]})
    drivers.sort(key=lambda x: -x["gap_raw"])

    override = any(d["gap_raw"] >= cfg["override_con_gap"] for d in drivers) \
               and imp_a >= cfg["override_imp"] and imp_b >= cfg["override_imp"]

    if severity >= cfg["t_fault"] or override:
        state = "FAULT_LINE"
    elif severity >= cfg["t_aligned"]:
        state = "DRIFTING"
    else:
        state = "ALIGNED"

    # perception gaps: guess_p(c) vs actual_q(c), both normalized 0-100
    def pg(guesser: PartnerDimAnswers, target_norm: dict[str, float]):
        pairs = [(to100(apply_reverse(g, cfg) if c in rk else g, cfg), target_norm[c])
                 for c, g in guesser.perceptions.items() if c in target_norm]
        return mean(abs(g - t) for g, t in pairs) if pairs else None
    pg_ab, pg_ba = pg(a, pb), pg(b, pa)
    pgs = [x for x in (pg_ab, pg_ba) if x is not None]
    pg_avg = mean(pgs) if pgs else None
    flag = pg_avg is not None and pg_avg >= cfg["t_pg"]

    return DimensionResult(dim, state, round(severity, 2), round(g_pos, 2),
                           round(pos_a, 2), round(pos_b, 2), round(imp_avg, 2),
                           None if pg_avg is None else round(pg_avg, 2),
                           None if pg_ab is None else round(pg_ab, 2),
                           None if pg_ba is None else round(pg_ba, 2),
                           flag, drivers[:2], override)

def validity_flags(all_raw: list[int], cfg: dict | None = None) -> list[str]:
    cfg = {**DEFAULT_CONFIG, **(cfg or {})}
    flags = []
    if len(all_raw) >= 8 and pstdev(all_raw) < cfg["straightline_sd"]:
        flags.append("low_variance")
    return flags

# ---------------- Part B: Convergence ----------------
TRAD_ORDER = {"CHALLENGING": 0, "NEUTRAL": 1, "SUPPORTIVE": 2}
CELL = {  # (tradition, mindmatch) -> cell
    ("SUPPORTIVE", "ALIGNED"): "CONFIRMED_STRENGTH",
    ("SUPPORTIVE", "DRIFTING"): "EARLY_WHISPER",
    ("SUPPORTIVE", "FAULT_LINE"): "HIDDEN_TENSION",
    ("NEUTRAL", "ALIGNED"): "QUIET_STRENGTH",
    ("NEUTRAL", "DRIFTING"): "OPEN_QUESTION",
    ("NEUTRAL", "FAULT_LINE"): "MODERN_FAULT",
    ("CHALLENGING", "ALIGNED"): "COMPENSATED",
    ("CHALLENGING", "DRIFTING"): "ECHOED_CAUTION",
    ("CHALLENGING", "FAULT_LINE"): "CONVERGED_CONCERN",
}
PRIORITY = ["CONVERGED_CONCERN", "MODERN_FAULT", "HIDDEN_TENSION",
            "ECHOED_CAUTION", "OPEN_QUESTION", "EARLY_WHISPER"]

def koota_signal(points: float, maximum: float, dosha: bool = False) -> str:
    if dosha:
        return "CHALLENGING"
    frac = points / maximum if maximum else 0
    return "SUPPORTIVE" if frac >= 0.66 else "NEUTRAL" if frac >= 0.33 else "CHALLENGING"

def tradition_signal(signals: list[str]) -> str:
    return min(signals, key=lambda s: TRAD_ORDER[s]) if signals else "NEUTRAL"

def convergence_cell(tradition: str, mm_state: str) -> str:
    return CELL[(tradition, mm_state)]

def plan_priorities(rows: list[dict]) -> list[dict]:
    """rows: [{dimension, cell, severity}] -> top-3 for Act 5."""
    def key(r):
        return (PRIORITY.index(r["cell"]) if r["cell"] in PRIORITY else 99, -r["severity"])
    ranked = sorted((r for r in rows if r["cell"] in PRIORITY), key=key)
    return ranked[:3]
