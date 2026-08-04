"""CI guard: engines must reproduce EM-001 known-good results exactly.
If this fails, an engine changed behaviour — version bump + re-validation required."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'engines'))
from astrology_engine import BirthChart, match_report
from numerology_engine import Profile, CompatibilityEngine

g = BirthChart(name="Rohan", year=1995, month=11, day=11, hour=6, minute=40,
               tz_offset=5.5, lat=28.6139, lon=77.2090, gender="male")
b = BirthChart(name="Ananya", year=1997, month=5, day=3, hour=18, minute=0,
               tz_offset=5.5, lat=26.8467, lon=80.9462, gender="female")
rep = match_report(g, b)
ak = rep["north_indian_matching"]
assert abs(ak["total"] - 16.5) < 1e-9, ak["total"]
assert ak["verdict"] == "Below Threshold"
assert "Nadi Dosha" in ak["doshas"]
assert ak["kootas"]["gana"]["points"] == 6.0
assert ak["kootas"]["bhakoot"]["points"] == 7.0
assert rep["south_indian_matching"]["essential_rajju_vedha_ok"] is True

eng = CompatibilityEngine(os.path.join(os.path.dirname(__file__), 'engines', 'compatibility-engine-data.json'))
res = eng.compare(Profile(name="Rohan Khanna", day=11, month=11, year=1995),
                  Profile(name="Ananya Sharma", day=3, month=5, year=1997))
assert abs(res["final_score"] - 79.8) < 1e-9, res["final_score"]
assert res["band"] == "Highly Compatible"
print("REPRODUCIBILITY OK — engines match EM-001 known-goods")
