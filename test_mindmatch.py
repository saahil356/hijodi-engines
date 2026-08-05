import sys; sys.path.insert(0, 'engines')
from mindmatch_engine import (PartnerDimAnswers, score_dimension, koota_signal,
    tradition_signal, convergence_cell, plan_priorities, validity_flags, to100)

ok = True
def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    ok = ok and cond

# --- Worked example from spec (Money): pos 78 vs 34 -> gap 44, imp avg 87.5 -> sev 53.9 FAULT_LINE
# construct answers chosen to average exactly: A: (4,5,4,5)->(75,100,75,100)=87.5? need 78...
# use direct positions matching spec via 1-5 mix: A avg 78 -> constructs [4.12]? use approx:
a = PartnerDimAnswers(positions={"P1":5,"P2":4,"P3":4,"P4":4}, importance=4,  # ->81.25? recompute below
                      perceptions={"P1":2})   # guesses partner low
b = PartnerDimAnswers(positions={"P1":2,"P2":3,"P3":2,"P4":2}, importance=5,
                      perceptions={"P1":4})
r = score_dimension("Money & finances", a, b)
# manual: A=(100+75+75+75)/4=81.25 B=(25+50+25+25)/4=31.25 gap=50 impavg=(75+100)/2=87.5
# factor=0.7+0.6*.875=1.225 sev=61.25 FAULT
check("money gap", abs(r.g_pos-50.0)<1e-6, r.g_pos)
check("money imp_avg", abs(r.imp_avg-87.5)<1e-6, r.imp_avg)
check("money severity", abs(r.severity-61.25)<1e-6, r.severity)
check("money state FAULT_LINE", r.state=="FAULT_LINE", r.state)
# perception: A guesses B on P1: guess=2->25 actual B P1=25 -> pg_ab=0; B guesses A: 4->75 vs A P1=100 -> 25
check("pg a->b zero", r.pg_a_to_b==0.0, r.pg_a_to_b)
check("pg b->a 25", r.pg_b_to_a==25.0, r.pg_b_to_a)
check("pg avg 12.5 no flag", r.pg==12.5 and not r.perception_flag, r.pg)

# --- Same gap, low importance -> DRIFTING (Couple 3 story)
c = PartnerDimAnswers(positions={"P1":5,"P2":4,"P3":4,"P4":4}, importance=2)
d = PartnerDimAnswers(positions={"P1":2,"P2":3,"P3":2,"P4":2}, importance=2)
r2 = score_dimension("Personal space", c, d)
# factor=0.7+0.6*0.25=0.85 sev=42.5 -> DRIFTING
check("low-imp severity 42.5", abs(r2.severity-42.5)<1e-6, r2.severity)
check("low-imp DRIFTING", r2.state=="DRIFTING", r2.state)

# --- Override: single construct 3+ apart, both imp>=75, small avg gap
e = PartnerDimAnswers(positions={"C1":5,"C2":3,"C3":3,"C4":3}, importance=5)
f = PartnerDimAnswers(positions={"C1":1,"C2":3,"C3":3,"C4":3}, importance=4)
r3 = score_dimension("Values & beliefs", e, f)
check("override fires", r3.override_fired and r3.state=="FAULT_LINE",
      f"{r3.override_fired}/{r3.state}/sev={r3.severity}")

# --- Reverse key handling
g = PartnerDimAnswers(positions={"R1":5}, importance=3)   # R1 reverse: 5 -> 1 -> 0
h = PartnerDimAnswers(positions={"R1":1}, importance=3)   # 1 -> 5 -> 100
r4 = score_dimension("Communication", g, h, reverse_keys={"R1"})
check("reverse flips both", r4.pos_a==0.0 and r4.pos_b==100.0, f"{r4.pos_a}/{r4.pos_b}")

# --- Aligned case
i = PartnerDimAnswers(positions={"P1":4,"P2":4}, importance=5)
j = PartnerDimAnswers(positions={"P1":4,"P2":5}, importance=5)
r5 = score_dimension("Communication", i, j)
check("aligned green", r5.state=="ALIGNED", f"{r5.state}/{r5.severity}")

# --- Validity
check("straightline flag", validity_flags([4]*14)==["low_variance"])
check("varied ok", validity_flags([1,5,2,4,3,5,1,4,2,5,3,4,1,5])==[])

# --- Convergence
check("bhakoot dosha challenging", koota_signal(0,7,dosha=True)=="CHALLENGING")
check("koota 5/5 supportive", koota_signal(5,5)=="SUPPORTIVE")
check("worse-of", tradition_signal(["CHALLENGING","SUPPORTIVE"])=="CHALLENGING")
check("converged concern", convergence_cell("CHALLENGING","FAULT_LINE")=="CONVERGED_CONCERN")
check("compensated", convergence_cell("CHALLENGING","ALIGNED")=="COMPENSATED")
top = plan_priorities([
  {"dimension":"Money","cell":"CONVERGED_CONCERN","severity":61.25},
  {"dimension":"Family","cell":"COMPENSATED","severity":10},
  {"dimension":"Career","cell":"MODERN_FAULT","severity":50},
  {"dimension":"Space","cell":"OPEN_QUESTION","severity":30},
  {"dimension":"Values","cell":"MODERN_FAULT","severity":55}])
check("plan order", [t["dimension"] for t in top]==["Money","Values","Career"],
      [t["dimension"] for t in top])

print("\n" + ("MINDMATCH ENGINE OK — all reproducibility checks green" if ok else "FAILURES PRESENT"))
sys.exit(0 if ok else 1)
