"""
MemSense interactive dashboard.

    .venv/bin/streamlit run dashboard.py

Reads the results produced by `python -m sim.run_all`.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st

RES = Path(__file__).parent / "results"
BLUE, ORANGE, GREY = "#2a78d6", "#eb6834", "#8a8984"

st.set_page_config(page_title="MemSense", layout="wide")

if not (RES / "summary.json").exists():
    st.error("No results yet. Run:  .venv/bin/python -m sim.run_all")
    st.stop()


@st.cache_data
def load():
    s = json.loads((RES / "summary.json").read_text())
    ts = {n: pd.read_csv(RES / f"timeseries_{n}.csv") for n in ("baseline", "memsense", "memsense_with_fixes")}
    ev = {n: pd.read_csv(RES / f"events_{n}.csv") for n in ("baseline", "memsense")}
    snaps = dict(np.load(RES / "snapshots.npz"))
    for d in ts.values():
        d["day"] = d["minute"] / 1440
    return s, ts, ev, snaps


S, TS, EV, SNAP = load()
b, m = TS["baseline"], TS["memsense"]
sv = S["savings"]

st.title("MemSense — Memory-Aware Thermal Intelligence")
st.caption("Simulated 20-rack (~100 kW) data hall, one week, Bengaluru November climate. "
           "Baseline and MemSense see identical weather, IT load and faults.")

c = st.columns(5)
c[0].metric("Cooling energy", f"{S['memsense']['cooling_kwh']:,.0f} kWh", f"{-sv['cooling_energy_pct']:.1f}%", delta_color="inverse")
c[1].metric("PUE", f"{S['memsense']['pue']:.3f}", f"{sv['pue_delta']:+.3f}", delta_color="inverse")
c[2].metric("Water", f"{S['memsense']['water_l']:,.0f} L", f"{-sv['water_pct']:.1f}%", delta_color="inverse")
c[3].metric("Inlet > 27 °C", f"{S['memsense']['exceed27_rack_min']} rack-min",
            f"{S['memsense']['exceed27_rack_min'] - S['baseline']['exceed27_rack_min']:+d}", delta_color="inverse")
c[4].metric("RDHx condensation", f"{S['memsense']['condensation_min']} min",
            f"{S['memsense']['condensation_min'] - S['baseline']['condensation_min']:+d}", delta_color="inverse")

tabs = st.tabs(["Thermal", "Memory as a sensor", "Faults detected", "Humidity", "Rack map", "Impact", "Assumptions"])

with tabs[0]:
    st.subheader("Supply-air setpoint")
    st.line_chart(pd.DataFrame({"day": b["day"], "Baseline": b["t_sup"], "MemSense": m["t_sup"]}).set_index("day"),
                  color=[ORANGE, BLUE], y_label="°C")
    st.subheader("Hottest server inlet in the hall")
    st.line_chart(pd.DataFrame({"day": b["day"], "Baseline": b["max_inlet"], "MemSense": m["max_inlet"],
                                "ASHRAE limit": 27.0}).set_index("day"), color=[ORANGE, GREY, BLUE], y_label="°C")
    st.caption("MemSense raises the setpoint in 0.5 °C steps only when the 10-minute forecast stays below 25.5 °C, "
               "and drops it by 1 °C immediately when a hotspot is predicted.")

with tabs[1]:
    st.subheader("Rack 7 / server 8 — airflow slowly clogs (BMC fan alarms stay silent)")
    st.line_chart(pd.DataFrame({"day": b["day"], "Baseline DIMM": b["watch_dimm"], "MemSense DIMM": m["watch_dimm"],
                                "Throttle limit": 85.0}).set_index("day"), color=[ORANGE, BLUE, GREY], y_label="°C")
    st.subheader("Airflow Health Index (MemSense)")
    st.line_chart(pd.DataFrame({"day": m["day"], "AHI": m["watch_ahi"], "Alert threshold": 1.3}).set_index("day"),
                  color=[BLUE, GREY])
    st.markdown("**AHI** = DIMM-over-inlet temperature rise (fan-speed corrected) ÷ expected rise at this load. "
                "Every DDR5 RDIMM already has 3 temperature sensors; MemSense uses them to see airflow problems "
                "*inside* the server with no extra hardware.")

with tabs[2]:
    rows = []
    for kind, label in [("airflow", "Clogged server airflow"), ("breach", "Containment breach (panels removed)"),
                        ("leak", "Coolant leak under RDHx"), ("drift", "Node sensor drift")]:
        eb = EV["baseline"].set_index("kind").loc[kind]
        em = EV["memsense"].set_index("kind").loc[kind]
        fmt = lambda d: "not detected" if pd.isna(d) else f"{d:.0f} min"
        rows.append({"Fault": label, "Baseline": fmt(eb.detect_delay_min), "How (baseline)": eb.note,
                     "MemSense": fmt(em.detect_delay_min), "How (MemSense)": em.note})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption(f"MemSense false alarms in the week: {S['memsense']['false_alarms']}.  "
               f"Without the sensor self-check, the drifting sensor costs "
               f"{S['ablation_no_sensor_check']['cooling_kwh'] - S['memsense']['cooling_kwh']:+.0f} kWh of cooling.")

with tabs[3]:
    d = (b["day"] >= 2.8) & (b["day"] <= 4.3)
    st.line_chart(pd.DataFrame({"day": b["day"][d], "Room dew point": b["td_room"][d],
                                "Baseline coil": b["rdhx_water"][d] + 0.5,
                                "MemSense coil": m["rdhx_water"][d] + 0.5}).set_index("day"),
                  color=[ORANGE, BLUE, GREY], y_label="°C")
    st.caption("When the coil surface is colder than the dew point, water condenses on the rear-door heat exchanger. "
               "MemSense keeps the coil at least 2.5 °C above the measured dew point.")

with tabs[4]:
    which = st.radio("Run", ["baseline", "memsense"], horizontal=True)
    k = st.slider("Time (5-minute steps)", 0, SNAP[f"{which}_inlet"].shape[0] - 1, int(2 * 288 + 14 * 12 + 2))
    st.caption(f"Day {k * 5 / 1440:.2f}")
    grid = pd.DataFrame(SNAP[f"{which}_inlet"][k].T[::-1], index=[f"U{i}" for i in range(9, -1, -1)],
                        columns=[f"R{r}" for r in range(SNAP[f"{which}_inlet"].shape[1])])
    st.dataframe(grid.style.background_gradient(cmap="Blues", vmin=18, vmax=28).format("{:.1f}"),
                 width="stretch")

with tabs[5]:
    a = S["annual_per_mw_it"]
    st.subheader("Per 1 MW of IT load, per year (linear extrapolation, indicative)")
    c = st.columns(4)
    c[0].metric("Energy saved", f"{a['energy_mwh']:,.0f} MWh")
    c[1].metric("Cost saved", f"₹{a['cost_inr_lakh']:,.1f} lakh")
    c[2].metric("CO₂ avoided", f"{a['co2_tonnes']:,.0f} t")
    c[3].metric("Water saved", f"{a['water_kl']:,.0f} kL")
    fx = S["memsense_with_fixes"]
    st.subheader("Scenarios")
    st.dataframe(pd.DataFrame([
        {"Scenario": "Bengaluru — MemSense", "Facility energy saving %": round(sv["facility_energy_pct"], 2),
         "Water saving %": round(sv["water_pct"], 2)},
        {"Scenario": f"Bengaluru — MemSense + fixes on racks {fx['fixed_racks']}",
         "Facility energy saving %": round(fx["facility_energy_saving_pct"], 2),
         "Water saving %": round(fx["water_saving_pct"], 2)},
        {"Scenario": "Delhi (January) — MemSense", "Facility energy saving %": round(S["delhi_jan"]["savings"]["facility_energy_pct"], 2),
         "Water saving %": round(S["delhi_jan"]["savings"]["water_pct"], 2)},
    ]), hide_index=True, width="stretch")

with tabs[6]:
    st.markdown("All modelling assumptions are in `sim/config.py`; sources in `docs/01_research_notes.md`. "
                "This is a simplified physics model for comparing control strategies, not a CFD model.")
    st.json({"forecaster": S["forecaster"]})
