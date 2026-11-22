"""Run baseline vs MemSense on the same week (same weather, load, faults) and summarise."""
import json
import pickle
import numpy as np
from . import config as C
from .datacenter import DataHall
from .memsense import BaselineController, MemSenseController
from .runner import run_week
from .scenario import make_weather, make_load, test_week_faults
from .train import MODEL_PATH

TEST_SEED = 7


def load_models():
    with open(MODEL_PATH, "rb") as fh:
        return pickle.load(fh)


def run_climate(climate, models, ablation=False, verbose=True):
    weather = make_weather(climate)
    load = make_load(np.random.default_rng(TEST_SEED + 1000))
    hd = DataHall(np.random.default_rng(0)).hd
    ctrls = [BaselineController(hd), MemSenseController(hd, models["model"], models["ahi_coef"])]
    if ablation:
        c = MemSenseController(hd, models["model"], models["ahi_coef"], use_sensor_health=False)
        c.name = "memsense_no_sensor_check"
        ctrls.append(c)
    res = {}
    for c in ctrls:
        if verbose:
            print(f"[{climate}] running {c.name} ...")
        res[c.name] = run_week(c, test_week_faults(), weather=weather, load=load, seed=TEST_SEED)
    return res


def kpis(r):
    a = r["acc"]
    ts = r["ts"]
    return {
        "facility_kwh": a["facility_kwh"], "it_kwh": a["it_kwh"], "cooling_kwh": a["cooling_kwh"],
        "chiller_kwh": a["chiller_kwh"], "water_l": a["water_l"],
        "pue": a["facility_kwh"] / a["it_kwh"], "wue_l_per_kwh": a["water_l"] / a["it_kwh"],
        "avg_supply_c": float(ts["t_sup"].mean()), "avg_max_inlet_c": float(ts["max_inlet"].mean()),
        "peak_inlet_c": float(ts["max_inlet"].max()), "peak_dimm_c": float(ts["max_dimm"].max()),
        "exceed27_rack_min": a["exceed27_rack_min"], "exceed32_rack_min": a["exceed32_rack_min"],
        "dimm_over85_server_min": a["dimm_over85_server_min"],
        "condensation_min": a["condensation_min"], "dew_risk_min": a["dew_risk_min"],
        "false_alarms": int(len(r["false_alarms"])),
        "free_cooling_hours": float(ts["free_frac"].sum() / 60.0),
    }


def summarise(res):
    b, m = kpis(res["baseline"]), kpis(res["memsense"])
    saved_kwh = b["facility_kwh"] - m["facility_kwh"]
    avg_it_kw = b["it_kwh"] / (C.STEPS / 60.0)
    per_mw_year = 1000.0 / avg_it_kw * C.WEEKS_PER_YEAR
    out = {
        "baseline": b, "memsense": m,
        "savings": {
            "facility_energy_pct": 100 * saved_kwh / b["facility_kwh"],
            "cooling_energy_pct": 100 * (b["cooling_kwh"] - m["cooling_kwh"]) / b["cooling_kwh"],
            "water_pct": 100 * (b["water_l"] - m["water_l"]) / b["water_l"],
            "pue_delta": m["pue"] - b["pue"],
            "it_energy_change_pct": 100 * (m["it_kwh"] - b["it_kwh"]) / b["it_kwh"],
            "week_kwh": saved_kwh, "week_water_l": b["water_l"] - m["water_l"],
        },
        "annual_per_mw_it": {
            "note": "Linear extrapolation of the simulated week to 1 MW IT load for 52 weeks. Indicative only.",
            "energy_mwh": saved_kwh * per_mw_year / 1000.0,
            "cost_inr_lakh": saved_kwh * per_mw_year * C.TARIFF_INR_PER_KWH / 1e5,
            "co2_tonnes": saved_kwh * per_mw_year * C.GRID_KG_CO2_PER_KWH / 1000.0,
            "water_kl": (b["water_l"] - m["water_l"]) * per_mw_year / 1000.0,
        },
        "hall_avg_it_kw": avg_it_kw,
    }
    if "memsense_no_sensor_check" in res:
        out["ablation_no_sensor_check"] = kpis(res["memsense_no_sensor_check"])
    ev = {}
    for name in res:
        e = res[name]["events"]
        ev[name] = e[e.kind != "humid"][["kind", "rack", "server", "detect_delay_min", "note"]].to_dict("records")
    out["fault_detection"] = ev
    return out
