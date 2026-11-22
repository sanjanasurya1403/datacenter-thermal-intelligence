"""
Run every scenario, save results + figures.

    .venv/bin/python -m sim.run_all          (about 10 minutes)

Scenarios
  1. Bengaluru (Nov): baseline vs MemSense, same weather/load/faults
  2. Ablation: MemSense without the sensor self-check (shows why it matters)
  3. MemSense + hotspot fixes: blanking panels fitted on the chronic hot racks MemSense reports
  4. Delhi (Jan): cooler climate -> more free-cooling hours
"""
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from . import config as C
from .compare import load_models, run_climate, summarise, kpis, TEST_SEED
from .datacenter import DataHall
from .memsense import MemSenseController
from .runner import run_week
from .scenario import make_weather, make_load, test_week_faults
from .train import MODEL_PATH, train

OUT = Path(__file__).resolve().parent.parent / "results"
FIG = OUT / "figures"
BLUE, ORANGE = "#2a78d6", "#eb6834"          # MemSense = slot 1, Baseline = slot 2
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def style(ax, title=None, ylabel=None):
    ax.set_facecolor("#fcfcfb")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, loc="left", fontsize=11, color=INK, fontweight="bold")
    if ylabel:
        ax.set_ylabel(ylabel, color=MUTED, fontsize=9)


def days(ts):
    return ts["minute"] / 1440.0


def hotspot_report(ts, top=4):
    share = ts["hottest_rack"].value_counts(normalize=True)
    return [int(r) for r in share.index[:top]], share


def figures(res, fixed_ts, summary):
    FIG.mkdir(parents=True, exist_ok=True)
    b, m = res["baseline"]["ts"], res["memsense"]["ts"]

    # 1. setpoint and hottest inlet over the week
    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True)
    ax = axes[0]
    ax.plot(days(b), b["t_sup"], color=ORANGE, lw=2, label="Baseline (fixed 18 °C)")
    ax.plot(days(m), m["t_sup"], color=BLUE, lw=2, label="MemSense (adaptive)")
    style(ax, "Supply-air temperature: MemSense runs warmer when it is safe", "°C")
    ax.legend(frameon=False, fontsize=9, loc="center right")
    ax = axes[1]
    ax.plot(days(b), b["max_inlet"].rolling(10).mean(), color=ORANGE, lw=1.5, label="Baseline")
    ax.plot(days(m), m["max_inlet"].rolling(10).mean(), color=BLUE, lw=1.5, label="MemSense")
    ax.axhline(C.ASHRAE_REC_MAX_C, color=MUTED, lw=1, ls="--")
    ax.text(0.02, C.ASHRAE_REC_MAX_C + 0.15, "ASHRAE recommended limit 27 °C", color=MUTED, fontsize=8)
    for f in res["memsense"]["events"].itertuples():
        if f.kind in ("airflow", "breach", "leak", "drift"):
            ax.axvline(f.minute / 1440, color=GRID, lw=1)
            ax.text(f.minute / 1440 + 0.02, 0.97, f.kind, color=MUTED, fontsize=8, va="top",
                    transform=ax.get_xaxis_transform())
    style(ax, "Hottest server inlet in the hall (10-min mean)", "°C")
    ax.set_xlabel("Day of simulated week", color=MUTED, fontsize=9)
    ax.legend(frameon=False, fontsize=9, loc="center right")
    fig.tight_layout()
    fig.savefig(FIG / "01_setpoint_and_inlet.png", dpi=160)
    plt.close(fig)

    # 2. KPI bars (separate panels: different units, never dual axis)
    sb, sm = summary["baseline"], summary["memsense"]
    items = [("Cooling energy (kWh / week)", "cooling_kwh"), ("PUE", "pue"),
             ("Water (litres / week)", "water_l"), ("Inlet > 27 °C (rack-minutes)", "exceed27_rack_min"),
             ("DRAM above 85 °C, 2× refresh (server-min)", "dimm_over85_server_min"),
             ("RDHx condensation (minutes)", "condensation_min")]
    fig, axes = plt.subplots(2, 3, figsize=(11, 5.5))
    for ax, (label, key) in zip(axes.flat, items):
        vals = [sb[key], sm[key]]
        bars = ax.bar(["Baseline", "MemSense"], vals, color=[ORANGE, BLUE], width=0.55, edgecolor="#fcfcfb", linewidth=2)
        for bar, v in zip(bars, vals):
            txt = f"{v:.2f}" if key == "pue" else f"{v:,.0f}"
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), txt, ha="center", va="bottom", fontsize=9, color=INK)
        style(ax, label)
        ax.title.set_fontsize(9.5)
        if key == "pue":
            ax.set_ylim(1.0, max(vals) * 1.05)
    fig.suptitle("One simulated week, same weather, load and faults (Bengaluru, November)", x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(FIG / "02_kpis.png", dpi=160)
    plt.close(fig)

    # 3. airflow fault: memory-as-a-sensor
    ev_b = res["baseline"]["events"].set_index("kind").loc["airflow"]
    ev_m = res["memsense"]["events"].set_index("kind").loc["airflow"]
    lo, hi = int(ev_b.minute) - 120, int(ev_b.minute) + 2400
    fig, axes = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
    ax = axes[0]
    sl_b, sl_m = b.iloc[lo:hi], m.iloc[lo:hi]
    ax.plot(days(sl_b), sl_b["watch_dimm"], color=ORANGE, lw=1.5, label="Baseline")
    ax.plot(days(sl_m), sl_m["watch_dimm"], color=BLUE, lw=1.5, label="MemSense")
    ax.axhline(C.DRAM_2X_REFRESH_C, color=MUTED, ls="--", lw=1)
    ax.text(days(sl_b).iloc[-1], C.DRAM_2X_REFRESH_C + 0.8, "85 °C: DDR5 2× refresh region", color=MUTED,
            fontsize=8, ha="right")
    for ev, col, name in ((ev_b, ORANGE, "BMC critical-only alarm"), (ev_m, BLUE, "AHI alert")):
        if ev.detected_at >= 0:
            ax.axvline(ev.detected_at / 1440, color=col, lw=1, ls=":")
            ax.text(ev.detected_at / 1440 + 0.01, 50, f"{name}\n+{ev.detect_delay_min / 60:.1f} h", color=INK, fontsize=8)
    style(ax, "Rack 7 / server 8: clogged airflow, hottest DIMM temperature", "°C")
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    ax = axes[1]
    ax.plot(days(sl_m), sl_m["watch_ahi"], color=BLUE, lw=1.5)
    ax.axhline(1.3, color=MUTED, ls="--", lw=1)
    ax.text(days(sl_m).iloc[-1], 1.32, "alert threshold 1.3", color=MUTED, fontsize=8, ha="right")
    style(ax, "Airflow Health Index (1.0 = healthy), computed only from memory + inlet sensors", "AHI")
    ax.set_xlabel("Day", color=MUTED, fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG / "03_airflow_fault_ahi.png", dpi=160)
    plt.close(fig)

    # 4. humid day: condensation guard
    lo, hi = C.HUMID_DAY * 1440, (C.HUMID_DAY + 1) * 1440 + 360
    fig, ax = plt.subplots(figsize=(11, 4))
    sl_b, sl_m = b.iloc[lo:hi], m.iloc[lo:hi]
    ax.plot(days(sl_b), sl_b["td_room"], color=MUTED, lw=2, label="Room dew point")
    ax.plot(days(sl_b), sl_b["rdhx_water"] + 0.5, color=ORANGE, lw=2, label="Baseline coil surface (fixed 15 °C water, no dew-point control)")
    ax.plot(days(sl_m), sl_m["rdhx_water"] + 0.5, color=BLUE, lw=2, label="MemSense RDHx coil surface")
    ax.fill_between(days(sl_b), sl_b["rdhx_water"] + 0.5, sl_b["td_room"],
                    where=sl_b["td_room"] >= sl_b["rdhx_water"] + 0.5, color=ORANGE, alpha=0.15, label="Condensation on baseline coil")
    style(ax, "Humid day: measured coil temperature vs shared room dew point", "°C")
    ax.set_ylim(top=ax.get_ylim()[1] + 3)
    ax.legend(frameon=False, fontsize=9, loc="upper left", ncol=2)
    ax.set_xlabel("Day", color=MUTED, fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG / "04_humid_day_dewpoint.png", dpi=160)
    plt.close(fig)

    # 5. rack heat map at breach onset (what MemSense sees)
    ev = res["memsense"]["events"].set_index("kind").loc["breach"]
    k = (int(ev.minute) + 10) // 5
    snap = res["baseline"]["snaps_in"][k]
    fig, ax = plt.subplots(figsize=(11, 3.6))
    im = ax.imshow(snap.T, origin="lower", aspect="auto", cmap="Blues", vmin=18, vmax=27)
    ax.set_xticks(range(C.N_RACKS))
    ax.set_xticklabels([f"R{r}" for r in range(C.N_RACKS)], fontsize=8, color=MUTED)
    ax.set_yticks([0, C.SERVERS_PER_RACK - 1])
    ax.set_yticklabels(["bottom", "top"], fontsize=8, color=MUTED)
    cb = fig.colorbar(im, ax=ax, pad=0.01)
    cb.set_label("Server inlet °C", color=MUTED, fontsize=9)
    ax.set_title("Server inlet temperature by rack and height, 10 min after blanking panels were removed on R12-R13",
                 loc="left", fontsize=10.5, color=INK, fontweight="bold")
    fig.tight_layout()
    fig.savefig(FIG / "05_rack_heatmap_breach.png", dpi=160)
    plt.close(fig)

    # 6. energy waterfall-style comparison incl. fixes scenario
    sf = kpis({"acc": summary["_fixed_acc"], "ts": fixed_ts, "false_alarms": []})
    fig, ax = plt.subplots(figsize=(8, 4))
    names = ["Baseline", "MemSense", "MemSense +\nhotspot fixes"]
    kwh = [sb["facility_kwh"], sm["facility_kwh"], sf["facility_kwh"]]
    vals = [100 * (kwh[0] - v) / kwh[0] for v in kwh]          # % saving vs baseline; axis starts at zero
    bars = ax.bar(names, vals, color=[ORANGE, BLUE, "#1c5cab"], width=0.55, edgecolor="#fcfcfb", linewidth=2)
    for bar, v, e in zip(bars, vals, kwh):
        ax.text(bar.get_x() + bar.get_width() / 2, v, f"{v:.1f}%\n({e:,.0f} kWh)",
                ha="center", va="bottom", fontsize=9, color=INK)
    ax.set_ylim(0, max(vals) * 1.6)
    style(ax, "Total facility energy saved vs baseline, one week (Bengaluru)", "% saved")
    fig.tight_layout()
    fig.savefig(FIG / "06_facility_energy_scenarios.png", dpi=160)
    plt.close(fig)


def main():
    t0 = time.time()
    OUT.mkdir(exist_ok=True)
    print("Training models (forecaster + AHI calibration)...")
    train_stats = train()
    models = load_models()

    res = run_climate("bengaluru_nov", models, ablation=True)
    summary = summarise(res)
    summary["forecaster"] = {k: float(models[k]) for k in ("mae", "mae_naive", "mae_transient", "mae_transient_naive")}

    hot_racks, share = hotspot_report(res["memsense"]["ts"])
    print(f"MemSense hotspot report: chronic hottest racks {hot_racks}")
    hd = DataHall(np.random.default_rng(0)).hd
    ctrl = MemSenseController(hd, models["model"], models["ahi_coef"])
    ctrl.name = "memsense_with_fixes"
    weather, load = make_weather("bengaluru_nov"), make_load(np.random.default_rng(TEST_SEED + 1000))
    print("[bengaluru_nov] running memsense with hotspot fixes ...")
    fixed = run_week(ctrl, test_week_faults(), weather=weather, load=load, seed=TEST_SEED, fixed_racks=hot_racks)
    fk = kpis(fixed)
    bk = summary["baseline"]
    summary["memsense_with_fixes"] = fk
    summary["memsense_with_fixes"]["fixed_racks"] = hot_racks
    summary["memsense_with_fixes"]["facility_energy_saving_pct"] = 100 * (bk["facility_kwh"] - fk["facility_kwh"]) / bk["facility_kwh"]
    summary["memsense_with_fixes"]["water_saving_pct"] = 100 * (bk["water_l"] - fk["water_l"]) / bk["water_l"]
    summary["hotspot_share"] = {f"R{int(r)}": float(v) for r, v in share.items()}
    summary["_fixed_acc"] = fixed["acc"]

    res_delhi = run_climate("delhi_jan", models)
    summary["delhi_jan"] = summarise(res_delhi)

    figures(res, fixed["ts"], summary)
    summary.pop("_fixed_acc")
    summary["delhi_jan"].pop("fault_detection", None)

    # save data
    for name, r in res.items():
        r["ts"].iloc[::5].to_csv(OUT / f"timeseries_{name}.csv", index=False)
        r["events"].to_csv(OUT / f"events_{name}.csv", index=False)
        r["false_alarms"].to_csv(OUT / f"false_alarms_{name}.csv", index=False)
    fixed["ts"].iloc[::5].to_csv(OUT / "timeseries_memsense_with_fixes.csv", index=False)
    for name, r in res_delhi.items():
        r["ts"].iloc[::5].to_csv(OUT / f"timeseries_delhi_{name}.csv", index=False)
    np.savez_compressed(OUT / "snapshots.npz",
                        baseline_inlet=res["baseline"]["snaps_in"], memsense_inlet=res["memsense"]["snaps_in"],
                        baseline_dimm=res["baseline"]["snaps_dimm"], memsense_dimm=res["memsense"]["snaps_dimm"])
    with open(OUT / "summary.json", "w") as fh:
        json.dump(summary, fh, indent=2, default=lambda o: None if (isinstance(o, float) and np.isnan(o)) else float(o))
    print(f"Done in {(time.time() - t0) / 60:.1f} min. Results in {OUT}")


if __name__ == "__main__":
    main()
