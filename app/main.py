"""HiJodi Engine Service — AstroJodi + NumeroJodi behind FastAPI.
Called ONLY by the API worker (rule 1). Outputs stored by caller with engine_version.
The engine modules are the validated project files, verbatim."""
import sys, os, hashlib, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engines'))
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from astrology_engine import BirthChart, match_report, current_dasha, render_north_svg, render_south_svg
from numerology_engine import Profile, CompatibilityEngine

ENGINE_VERSIONS = {"astrojodi": "1.0.0", "numerojodi": "1.0.0"}
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

@app.post("/v1/astrojodi/match")
def astro_match(inp: AstroMatchIn):
    try:
        g, b = _chart(inp.groom), _chart(inp.bride)
        rep = match_report(g, b)
        rep["dashas"] = {"groom": current_dasha(g), "bride": current_dasha(b)}
        # EM-001 T15: propagate birth-time confidence so every surface can qualify lagna factors
        rep["birth_time_confidence"] = {"groom": inp.groom.birth_time_confidence,
                                        "bride": inp.bride.birth_time_confidence}
        if inp.include_charts:
            rep["charts"] = {
                "groom_north": render_north_svg(g), "groom_south": render_south_svg(g),
                "bride_north": render_north_svg(b), "bride_south": render_south_svg(b),
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
