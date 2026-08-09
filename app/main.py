"""HiJodi Engine Service — AstroJodi + NumeroJodi behind FastAPI.
Called ONLY by the API worker (rule 1). Outputs stored by caller with engine_version.
The engine modules are the validated project files, verbatim."""
import sys, os, hashlib, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engines'))
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from astrology_engine import (BirthChart, match_report, current_dasha, render_north_svg,
    render_south_svg, SIGNS, vimshottari_dasha, navamsa_chart, antardashas)
from numerology_engine import Profile, CompatibilityEngine

ENGINE_VERSIONS = {"astrojodi": "1.0.0", "numerojodi": "1.0.0", "mindmatch": "1.0.0"}
_DATA = os.path.join(os.path.dirname(__file__), '..', 'engines', 'compatibility-engine-data.json')
_numero = CompatibilityEngine(_DATA)

app = FastAPI(title="HiJodi Engines", version="1.0.0")

class Birth(BaseModel):
    name: str
    year: int; month: int; day: int
    hour: int = 12; minute: int = 0
    tz_offset: float = 5.5
    lat: float; lon: float
    gender: str = "unknown"
    birth_time_confidence: str = Field("exact", pattern="^(exact|approximate|unknown)$")

class AstroMatchIn(BaseModel):
    groom: Birth
    bride: Birth
    include_charts: bool = False

class NumeroPerson(BaseModel):
    full_name: str          # name as per records
    day: int; month: int; year: int

class NumeroMatchIn(BaseModel):
    a: NumeroPerson
    b: NumeroPerson
    system: str = Field("chaldean", pattern="^(chaldean|pythagorean)$")

def _chart(b: Birth) -> BirthChart:
    return BirthChart(name=b.name, year=b.year, month=b.month, day=b.day,
                      hour=b.hour, minute=b.minute, tz_offset=b.tz_offset,
                      lat=b.lat, lon=b.lon, gender=b.gender)

@app.get("/health")
def health():
    return {"ok": True, "versions": ENGINE_VERSIONS}

def _strip_jd(period: dict) -> dict:
    return {k: v for k, v in period.items() if not k.endswith("_jd")}

def _dasha_bundle(chart: BirthChart, n_periods: int = 9) -> dict:
    """Full mahadasha timeline + antardashas of the currently-running mahadasha."""
    cur = current_dasha(chart)
    timeline = [_strip_jd(p) for p in vimshottari_dasha(chart, n_periods=n_periods)]
    # Recompute the current mahadasha's raw (with _jd) period so antardashas can be derived
    raw_timeline = vimshottari_dasha(chart, n_periods=max(n_periods, 12))
    maha_lord = cur["mahadasha"]["lord"]
    raw_maha = next((p for p in raw_timeline if p["lord"] == maha_lord
                     and p["start"] == cur["mahadasha"]["start"]), raw_timeline[0])
    subs = [_strip_jd(s) for s in
            antardashas(raw_maha["lord"], raw_maha["start_jd"], raw_maha["years"])]
    return {"current": cur, "timeline": timeline, "antardashas_current": subs}

@app.post("/v1/astrojodi/match")
def astro_match(inp: AstroMatchIn):
    try:
        g, b = _chart(inp.groom), _chart(inp.bride)
        rep = match_report(g, b)
        rep["dashas"] = {"groom": _dasha_bundle(g), "bride": _dasha_bundle(b)}
        # EM-001 T15: propagate birth-time confidence so every surface can qualify lagna factors
        rep["birth_time_confidence"] = {"groom": inp.groom.birth_time_confidence,
                                        "bride": inp.bride.birth_time_confidence}
        if inp.include_charts:
            rep["charts"] = {
                "groom_north": render_north_svg(g.north_indian_chart(), title=g.name),
                "groom_south": render_south_svg(g.south_indian_chart(), title=g.name),
                "groom_navamsa": render_south_svg(navamsa_chart(g, style="south"),
                                                  title=f"{g.name} — Navamsa D9"),
                "bride_north": render_north_svg(b.north_indian_chart(), title=b.name),
                "bride_south": render_south_svg(b.south_indian_chart(), title=b.name),
                "bride_navamsa": render_south_svg(navamsa_chart(b, style="south"),
                                                  title=f"{b.name} — Navamsa D9"),
            }
        return {"engine": "astrojodi", "engine_version": ENGINE_VERSIONS["astrojodi"],
                "input_hash": hashlib.sha256(inp.model_dump_json().encode()).hexdigest()[:16],
                "output": rep}
    except Exception as e:
        raise HTTPException(422, detail=f"astro computation failed: {e}")

@app.post("/v1/numerojodi/match")
def numero_match(inp: NumeroMatchIn):
    try:
        pa = Profile(name=inp.a.full_name, day=inp.a.day, month=inp.a.month, year=inp.a.year, system=inp.system)
        pb = Profile(name=inp.b.full_name, day=inp.b.day, month=inp.b.month, year=inp.b.year, system=inp.system)
        res = _numero.compare(pa, pb)
        res["profiles"] = {
            "a": {**pa.numbers(), "compound": pa.compound},
            "b": {**pb.numbers(), "compound": pb.compound},
        }
        return {"engine": "numerojodi", "engine_version": ENGINE_VERSIONS["numerojodi"],
                "system": inp.system,
                "input_hash": hashlib.sha256(inp.model_dump_json().encode()).hexdigest()[:16],
                "output": res}
    except Exception as e:
        raise HTTPException(422, detail=f"numero computation failed: {e}")

@app.post("/v1/astrojodi/prospect-check")
def prospect_check(inp: AstroMatchIn):
    """Teaser payload for step-4 prospect flow: category + counts only (details paywalled)."""
    full = astro_match(inp)["output"]
    ak = full["north_indian_matching"]
    return {"teaser": {
        "verdict": ak["verdict"],
        "doshas_to_review": len(ak.get("doshas", [])),
        "essential_pass": full["south_indian_matching"]["essential_rajju_vedha_ok"],
    }}

# ---------------- MindMatch (Build 2) ----------------
from mindmatch_engine import (PartnerDimAnswers, score_dimension, koota_signal,
    tradition_signal, convergence_cell, plan_priorities, validity_flags,
    ENGINE_VERSION as MM_VERSION)

class MMPartnerDim(BaseModel):
    positions: dict[str, int]
    importance: int
    perceptions: dict[str, int] = {}

class MMScoreIn(BaseModel):
    partner_a: dict[str, MMPartnerDim]          # dimension -> answers
    partner_b: dict[str, MMPartnerDim]
    reverse_keys: list[str] = []
    tradition: dict[str, list[str]] = {}        # dimension -> ["SUPPORTIVE"|"NEUTRAL"|"CHALLENGING", ...]
    config: dict | None = None

@app.post("/v1/mindmatch/score")
def mindmatch_score(inp: MMScoreIn):
    try:
        rk = set(inp.reverse_keys)
        dims = sorted(set(inp.partner_a) & set(inp.partner_b))
        if not dims:
            raise HTTPException(422, "no shared dimensions")
        results, conv_rows, raw_a, raw_b = [], [], [], []
        for d in dims:
            a, b = inp.partner_a[d], inp.partner_b[d]
            raw_a += list(a.positions.values()) + [a.importance]
            raw_b += list(b.positions.values()) + [b.importance]
            r = score_dimension(d,
                PartnerDimAnswers(a.positions, a.importance, a.perceptions),
                PartnerDimAnswers(b.positions, b.importance, b.perceptions),
                reverse_keys=rk, cfg=inp.config)
            row = r.__dict__.copy()
            trad = tradition_signal(inp.tradition.get(d, []))
            cell = convergence_cell(trad, r.state)
            row.update(tradition=trad, convergence=cell)
            results.append(row)
            conv_rows.append({"dimension": d, "cell": cell, "severity": r.severity})
        return {"engine_version": MM_VERSION, "output": {
            "dimensions": results,
            "plan_priorities": plan_priorities(conv_rows),
            "validity": {"partner_a": validity_flags(raw_a),
                         "partner_b": validity_flags(raw_b)},
        }}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(422, f"mindmatch computation failed: {e}")

# ---------------- Solo lenses (Aaina rollout) ----------------
SIGN_TRAITS = {
  "Aries":"initiative and fire","Taurus":"steadiness and loyalty","Gemini":"curiosity and words",
  "Cancer":"care and memory","Leo":"warmth and pride","Virgo":"precision and service",
  "Libra":"balance and partnership","Scorpio":"depth and intensity","Sagittarius":"faith and freedom",
  "Capricorn":"duty and patience","Aquarius":"ideals and independence","Pisces":"empathy and imagination"}
NUM_MEANING = {1:"leadership and self-drive",2:"partnership and sensitivity",3:"expression and joy",
  4:"discipline and building",5:"freedom and change",6:"care, home and responsibility",
  7:"reflection and depth",8:"ambition and material mastery",9:"compassion and completion",
  11:"intuition and inspiration",22:"master builder energy"}

class SoloPerson(BaseModel):
    name: str
    year: int; month: int; day: int
    hour: int = 12; minute: int = 0
    tz_offset: float = 5.5
    lat: float = 28.61; lon: float = 77.21
    gender: str = "unspecified"

@app.post("/v1/astro/solo")
def astro_solo(p: SoloPerson):
    try:
        ch = BirthChart(name=p.name, year=p.year, month=p.month, day=p.day,
                        hour=p.hour, minute=p.minute, tz_offset=p.tz_offset,
                        lat=p.lat, lon=p.lon, gender=p.gender)
        moon = ch.planets["Moon"]; venus = ch.planets["Venus"]; mars = ch.planets["Mars"]
        seventh_sign = SIGNS[(ch.asc_sign + 6) % 12]
        dasha = vimshottari_dasha(ch, n_periods=3)
        return {"engine": "astrojodi", "engine_version": ENGINE_VERSIONS["astrojodi"], "output": {
            "lagna": SIGNS[ch.asc_sign], "lagna_traits": SIGN_TRAITS[SIGNS[ch.asc_sign]],
            "moon_sign": moon["sign"], "moon_nakshatra": moon["nakshatra"],
            "moon_traits": SIGN_TRAITS[moon["sign"]],
            "venus": {"sign": venus["sign"], "house": venus["house"]},
            "mars": {"sign": mars["sign"], "house": mars["house"]},
            "seventh_house_sign": seventh_sign,
            "seventh_traits": SIGN_TRAITS[seventh_sign],
            "current_dasha": dasha[0], "next_dasha": dasha[1] if len(dasha) > 1 else None,
        }}
    except Exception as e:
        raise HTTPException(422, f"astro solo failed: {e}")

class SoloNumIn(BaseModel):
    name: str
    year: int; month: int; day: int
    system: str = "chaldean"

@app.post("/v1/numero/solo")
def numero_solo(p: SoloNumIn):
    try:
        pr = Profile(name=p.name, day=p.day, month=p.month, year=p.year, system=p.system)
        def m(n): return NUM_MEANING.get(n, "a rare master vibration")
        return {"engine": "numerojodi", "engine_version": ENGINE_VERSIONS["numerojodi"], "output": {
            "system": p.system,
            "life_path": {"n": pr.life_path, "meaning": m(pr.life_path)},
            "destiny": {"n": pr.destiny, "compound": pr.compound, "meaning": m(pr.destiny)},
            "soul_urge": {"n": pr.soul_urge, "meaning": m(pr.soul_urge)},
            "personality": {"n": pr.personality, "meaning": m(pr.personality)},
            "birth_day": {"n": pr.birth_day, "meaning": m(pr.birth_day)},
        }}
    except Exception as e:
        raise HTTPException(422, f"numero solo failed: {e}")

# ---------------- Narration relay (no time limits here) ----------------
import urllib.request, json as _json

class NarrateIn(BaseModel):
    system: str
    user: str
    max_tokens: int = 8000
    anthropic_key: str
    supabase_url: str
    supabase_key: str
    table: str                      # 'aaina_reports' | 'reports'
    match: dict                     # for reports: {"purchase_id": "..."}; for aaina: row body extras
    mode: str = "insert"            # 'insert' | 'patch'
    target_column: str = "narrative"   # column written in patch mode


def _log_err(p, source, detail):
    """Best-effort: surface narrate failures in the admin Logs tab."""
    try:
        hd = {"apikey": p.supabase_key, "Authorization": f"Bearer {p.supabase_key}",
              "Content-Type": "application/json"}
        rq = urllib.request.Request(f"{p.supabase_url}/rest/v1/ai_errors",
            data=_json.dumps({"source": source, "detail": detail[:800]}).encode(),
            headers=hd, method="POST")
        urllib.request.urlopen(rq, timeout=10)
    except Exception:
        pass

@app.post("/v1/narrate")
def narrate(p: NarrateIn):
    # Hard clamps — protect credits no matter who calls or what future code sends
    p.max_tokens = min(max(p.max_tokens, 256), 9000)
    if len(p.system) + len(p.user) > 60000:
        raise HTTPException(413, "narration payload too large")
    body = _json.dumps({"model": "claude-sonnet-4-5", "max_tokens": p.max_tokens,
        "system": p.system, "messages": [{"role": "user", "content": p.user}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": p.anthropic_key, "anthropic-version": "2023-06-01",
        "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=280) as r:
            data = _json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:400]
        print(f"NARRATE anthropic {e.code}: {body}", flush=True)
        _log_err(p, f"anthropic:{p.table}", f"{e.code}: {body}")
        raise HTTPException(502, f"anthropic {e.code}: {body[:180]}")
    txt = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    txt = txt.replace("```json", "").replace("```", "").strip()
    try:
        narrative = _json.loads(txt)
    except Exception as pe:
        print(f"NARRATE parse: {pe}", flush=True)
        _log_err(p, f"parse:{p.table}", f"{pe} | tail: {txt[-300:]}")
        raise HTTPException(502, "narrative parse failed")

    hdrs = {"apikey": p.supabase_key, "Authorization": f"Bearer {p.supabase_key}",
            "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"} if p.mode != "patch" else {"apikey": p.supabase_key, "Authorization": f"Bearer {p.supabase_key}", "Content-Type": "application/json"}
    if p.mode == "patch":
        qs = "&".join(f"{k}=eq.{v}" for k, v in p.match.items())
        u = f"{p.supabase_url}/rest/v1/{p.table}?{qs}"
        rq = urllib.request.Request(u, data=_json.dumps({p.target_column: narrative, "narrated_at": __import__("datetime").datetime.utcnow().isoformat()+"Z"} if p.table=="reveal_narratives" else {p.target_column: narrative}).encode(),
                                    headers=hdrs, method="PATCH")
    else:
        row = dict(p.match); row["payload"] = narrative; row["model"] = "claude-sonnet-4-5"
        u = f"{p.supabase_url}/rest/v1/{p.table}"
        rq = urllib.request.Request(u, data=_json.dumps(row).encode(), headers=hdrs, method="POST")
    try:
        urllib.request.urlopen(rq, timeout=30)
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:400]
        print(f"NARRATE supabase {e.code}: {body}", flush=True)
        _log_err(p, f"supabase:{p.table}", f"{e.code}: {body}")
        raise HTTPException(502, f"supabase {e.code}: {body[:180]}")
    return {"ok": True}

