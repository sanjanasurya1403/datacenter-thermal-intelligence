"""Run one simulated week with a given controller and collect metrics."""
import numpy as np
import pandas as pd
from . import config as C
from .datacenter import DataHall, read_sensors
from .facility import plant_minute
from .memsense import FeatureBuilder, util_from_power

WATCH = (7, 8)          # (rack, server) traced in detail: the airflow-fault server
DRIFT_RACK = 5


def apply_faults(minute, faults, hall, drift, leak):
    drift[:] = 0
    leak[:] = False
    hall.breach[:] = 0
    hall.health[:] = 1.0
    for f in faults:
        if minute < f.start or not f.active:
            continue
        el = minute - f.start
        if f.kind == "airflow":
            mh, ramp = f.params["min_health"], f.params["ramp_min"]
            hall.health[f.rack, f.server] = max(mh, 1 - (1 - mh) * el / ramp)
        elif f.kind == "breach":
            hall.breach[f.params["racks"]] = C.BREACH_RECIRC_EXTRA
        elif f.kind == "leak":
            leak[f.rack] = True
        elif f.kind == "drift":
            drift[f.rack] = f.params["rate"] * el


def match(det, faults, minute):
    kind, r, h, msg = det
    for f in faults:
        if f.kind != kind or minute < f.start or not f.active or f.detected_at >= 0:
            continue
        if kind == "airflow" and (f.rack, f.server) != (r, h):
            continue
        if kind == "breach" and r not in f.params["racks"]:
            continue
        if kind in ("leak", "drift") and f.rack != r:
            continue
        f.detected_at = minute
        f.params["repair_due"] = minute + C.REPAIR_DELAY_MIN[kind]
        f.params["how"] = msg
        return True
    # same incident already reported (e.g. 2nd rack of one breach) -> not a false alarm
    for f in faults:
        if f.kind == kind and minute >= f.start and f.active and f.detected_at >= 0:
            if kind == "breach" and r in f.params["racks"]:
                return True
    return False


def run_week(controller, faults, climate="bengaluru_nov", seed=0, weather=None, load=None,
             collect_training=False, verbose=False, fixed_racks=None):
    rng = np.random.default_rng(seed)
    from .scenario import make_weather, make_load
    weather = weather or make_weather(climate)
    load = make_load(np.random.default_rng(seed + 1000)) if load is None else load
    hall = DataHall(rng, td_room=weather["td"][0] - C.DEHUMID_OFFSET_C)
    hd_rack = hall.hd[:, 0]
    if fixed_racks:
        # MemSense hotspot report acted on: blanking panels / brush grommets on chronic hot racks
        hall.recirc_base[fixed_racks] = (C.RECIRC_BOTTOM + (C.RECIRC_TOP - C.RECIRC_BOTTOM) * hall.hpos ** 2)[0]
        hall.rack_offset[fixed_racks] = 0.3
    drift = np.zeros(C.N_RACKS)
    leak = np.zeros(C.N_RACKS, bool)
    setpoint = C.BASELINE_SUPPLY_C
    rdhx_water = setpoint - C.CHW_APPROACH_C

    rows, snaps_in, snaps_dimm, events, false_alarms = [], [], [], [], []
    train_X, train_m = [], []
    ahi_rise, ahi_u, ahi_hd = [], [], []
    fb = FeatureBuilder(hd_rack) if collect_training else None
    acc = dict(it_kwh=0.0, cooling_kwh=0.0, chiller_kwh=0.0, facility_kwh=0.0, water_l=0.0,
               exceed27_rack_min=0, exceed32_rack_min=0, dimm_over85_server_min=0,
               condensation_min=0, dew_risk_min=0)

    for k in range(C.STEPS):
        apply_faults(k, faults, hall, drift, leak)
        if hasattr(controller, "breach_visible"):
            controller.breach_visible = hall.breach > 0
        truth = hall.step(load[k], setpoint, weather["td"][k])
        s = read_sensors(truth, rng, drift, leak)

        setpoint, rdhx_water, dets = controller.decide(k, s)
        for d in dets:
            if d[0] == "humid":
                events.append({"minute": k, "kind": "humid", "rack": -1, "server": -1, "note": d[3]})
            elif not match(d, faults, k):
                false_alarms.append({"minute": k, "kind": d[0], "rack": d[1], "server": d[2], "note": d[3]})
        for f in faults:
            if f.active and f.detected_at >= 0 and k >= f.params["repair_due"]:
                f.repaired_at = k
                controller.on_repair(f)

        # ---- metrics
        it_kw = (truth["p_it_w"].sum() + truth["p_fan_w"].sum()) / 1000.0
        p = plant_minute(it_kw, truth["t_sup"], weather["t_db"][k], weather["t_wb"][k])
        h = C.DT_MIN / 60.0
        acc["it_kwh"] += it_kw * h
        acc["cooling_kwh"] += p["cooling_kw"] * h
        acc["chiller_kwh"] += p["chiller_kw"] * h
        acc["facility_kwh"] += p["facility_kw"] * h
        acc["water_l"] += p["water_l"]
        rack_max = truth["t_in"].max(axis=1)
        acc["exceed27_rack_min"] += int((rack_max > C.ASHRAE_REC_MAX_C).sum())
        acc["exceed32_rack_min"] += int((rack_max > C.ASHRAE_ALLOW_MAX_C).sum())
        acc["dimm_over85_server_min"] += int((truth["t_dimm"] >= C.DRAM_2X_REFRESH_C).sum())
        coil = rdhx_water + 0.5
        acc["condensation_min"] += int(coil <= truth["td_room"])
        acc["dew_risk_min"] += int(coil < truth["td_room"] + 2.0)

        wr, ws = WATCH
        ahi_watch = getattr(controller, "last_ahi", None)
        pred = getattr(controller, "last_pred", None)
        rows.append({
            "minute": k, "setpoint": setpoint, "t_sup": truth["t_sup"],
            "max_inlet": rack_max.max(), "mean_inlet": truth["t_in"].mean(), "hottest_rack": int(rack_max.argmax()),
            "max_dimm": truth["t_dimm"].max(), "mean_dimm": truth["t_dimm"].mean(),
            "watch_dimm": truth["t_dimm"][wr, ws], "watch_inlet": truth["t_in"][wr, ws],
            "watch_ahi": float(ahi_watch[wr, ws]) if ahi_watch is not None else np.nan,
            "pred_max_inlet": float(pred.max()) if pred is not None else np.nan,
            "drift_node_top": s["node_in_top"][DRIFT_RACK], "drift_true_top": truth["t_in"][DRIFT_RACK, -1],
            "it_kw": it_kw, "cooling_kw": p["cooling_kw"], "facility_kw": p["facility_kw"],
            "pue": p["facility_kw"] / it_kw, "water_l": p["water_l"], "free_frac": p["free_frac"],
            "cop": p["cop"], "td_room": truth["td_room"], "rdhx_water": rdhx_water,
            "t_db": weather["t_db"][k], "t_wb": weather["t_wb"][k],
        })
        if k % 5 == 0:
            snaps_in.append(truth["t_in"].astype(np.float32))
            snaps_dimm.append(truth["t_dimm"].astype(np.float32))

        if collect_training:
            X, m0 = fb.build(k, s, setpoint, np.ones(C.N_RACKS, bool), hall.hd)
            train_X.append(X)
            train_m.append(m0)
            if k % 10 == 0 and k > 60:
                ok = hall.health == 1.0
                rise = (s["bmc_dimm"] - s["bmc_inlet"]) * s["bmc_fan_speed"] ** C.FAN_SPEED_EXP
                ahi_rise.append(rise[ok])
                ahi_u.append(util_from_power(s["bmc_power_w"], hall.hd)[ok])
                ahi_hd.append(hall.hd[ok])
        if verbose and k % 1440 == 0:
            print(f"  day {k // 1440}: setpoint {setpoint:.1f} C, max inlet {rack_max.max():.1f} C")

    for f in faults:
        events.append({
            "minute": f.start, "kind": f.kind, "rack": f.rack, "server": f.server,
            "detected_at": f.detected_at, "repaired_at": f.repaired_at,
            "detect_delay_min": (f.detected_at - f.start) if f.detected_at >= 0 else None,
            "note": f.params.get("how", "not detected"),
        })
    ts = pd.DataFrame(rows)
    out = {
        "name": controller.name, "acc": acc, "ts": ts, "events": pd.DataFrame(events),
        "false_alarms": pd.DataFrame(false_alarms),
        "snaps_in": np.stack(snaps_in), "snaps_dimm": np.stack(snaps_dimm),
    }
    if collect_training:
        out["train_X"] = np.stack(train_X)          # (steps, racks, features)
        out["train_m"] = np.stack(train_m)          # (steps, racks)
        out["ahi"] = (np.concatenate(ahi_rise), np.concatenate(ahi_u), np.concatenate(ahi_hd))
    return out
