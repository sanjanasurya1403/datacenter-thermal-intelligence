# MemSense — Memory-Aware Thermal Intelligence for Sustainable Data Centres

**Micron-Supported SOLVE Innovation Program (BITS Pilani), 2026 submission**
Focus areas: **#2 IoT & Connected Intelligent Systems**, **#6 AI Applications**, **#1 Semiconductor Technologies**

> Every DDR5 server memory module already carries **three temperature sensors**, and every NVMe SSD reports its own temperature.
> A single rack holds about **2,000** of these sensors, sitting exactly where the heat is, yet each one is only used to drive its own server's fans.
> **MemSense turns Micron memory into a room-wide thermal sensing network.** It adds a rugged low-cost sensor node for what memory cannot sense (humidity, dew point, dust, corrosive gas, airflow pressure, leaks) and edge AI that predicts hotspots.
> Operators can then **run cooling warmer, safely, using less energy and water**.

---

## The problem
- Cooling uses **~30–40%** of a data centre's energy. Indian facilities use **1.5–2.5 L of water per kWh**.
- Operators keep rooms at 20–22 °C even though ASHRAE recommends server inlets up to **27 °C**. They overcool because **they cannot see hotspots early**.
- Each +1 °C of safe warming saves roughly **2–5%** of energy.
- AI racks, liquid cooling, humid monsoons and polluted city air add new risks: condensation, corrosion and leaks.

Sources: [docs/01_research_notes.md](docs/01_research_notes.md)

## The idea (three layers)
| Layer | What | New hardware? |
|---|---|---|
| **1. Memory as a sensor** | DDR5 RDIMM (SPD hub + 2 sensors) and NVMe SSD temperatures, read out-of-band through the server BMC (Redfish) | **None** |
| **2. MemSense Node** | ESP32-S3 node with Micron industrial flash: inlet/outlet temperature and humidity, dew point, aisle pressure, PM2.5, Ag/Cu corrosion coupons, leak rope, pipe-surface temperature. PoE powered, no batteries | ~₹4.5k per rack / ~₹16k per row |
| **3. Edge AI** | 10-minute hotspot forecast, **Airflow Health Index**, sensor self-check, dew-point guard, safe bounded setpoint control (BACnet/Modbus to any cooling vendor) | Gateway per hall |

**Two new metrics:**
- **Memory Thermal Margin**: how far each server's DRAM is from its throttle / extended-refresh region.
- **Airflow Health Index (AHI)**: the DIMM-over-inlet temperature rise compared with the rise expected at the current load. It detects clogged or blocked airflow *inside* a server using only the memory's own sensors.

Full design: [docs/02_system_design.md](docs/02_system_design.md)

## Results (simulation)
A 20-rack, ~100 kW hall was simulated for one week. **Baseline and MemSense see identical weather, IT load and faults.**

![Setpoint and inlet](results/figures/01_setpoint_and_inlet.png)

| Bengaluru, November | Baseline (fixed 18 °C) | MemSense |
|---|---|---|
| Average supply air | 18.0 °C | 20.7 °C |
| Cooling energy | 6,593 kWh | 6,197 kWh (**−6.0%**) |
| Total facility energy | 24,141 kWh | 23,746 kWh (−1.6%) |
| PUE | 1.486 | 1.461 |
| Water | 39,067 L | 38,355 L (−1.8%) |
| Rack-minutes above 27 °C | 301 | 66 |
| Server-minutes with DRAM at throttle limit | 5 | 0 |
| Condensation on rear-door heat exchangers (humid day) | 710 min | **0 min** |
| False alarms | 0 | 0 |

**Cooler climate (Delhi, January):** cooling energy **−23%**, water **−22%**, total energy −5.3%, PUE 1.398 → 1.324. Warmer setpoints unlock many more free-cooling hours.

**Fault detection (time from fault start to alert):**

| Fault | Baseline | MemSense |
|---|---|---|
| Clogged airflow inside a server (fan alarms silent) | 31 h (when DIMM hit critical) | **2.8 h** (AHI) |
| Containment breach (blanking panels removed) | 2 h (manual round) | **2 min** (aisle pressure + gradient) |
| Coolant leak under rear-door heat exchanger | 1 h 50 min (manual round) | **< 1 min** (leak rope) |
| Node sensor drifting | never | 1.5 h (cross-check with server BMCs) |

**Hotspot forecaster** (10 min ahead, held-out data): mean error 0.12 °C vs 0.19 °C for a naive "no change" guess. During temperature transients it is **0.20 °C vs 0.76 °C**.

**Indicative annual impact per 1 MW of IT load** (linear extrapolation of the simulated week):

| | Bengaluru | Delhi (winter week) |
|---|---|---|
| Energy | 213 MWh | 645 MWh |
| Cost (₹8/kWh) | ₹17 lakh | ₹52 lakh |
| CO₂ (0.71 kg/kWh) | 151 t | 458 t |
| Water | 384 kL | 4,151 kL |

The Delhi row extrapolates a *winter* week, so it is an upper bound, not an annual average.

More charts: [airflow fault + AHI](results/figures/03_airflow_fault_ahi.png) · [humid day](results/figures/04_humid_day_dewpoint.png) · [rack heat map](results/figures/05_rack_heatmap_breach.png) · [KPIs](results/figures/02_kpis.png) · [scenarios](results/figures/06_facility_energy_scenarios.png)

## Run it yourself
Requires Python 3.9+.
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m sim.run_all          # ~9 min: trains models, runs all scenarios, writes results/
.venv/bin/streamlit run dashboard.py     # interactive dashboard in the browser
```

## Project structure
```
docs/
  01_research_notes.md       sourced facts (cooling, ASHRAE, DDR5 sensors, Micron)
  02_system_design.md        architecture, node hardware design + BOM, control loop, security
  03_submission_writeup.md   application write-up
sim/
  config.py                  every modelling assumption, in one place
  scenario.py                weather, IT load, fault schedule
  datacenter.py              hall physics ("ground truth") + what sensors report
  facility.py                chiller / economiser / water model
  memsense.py                AHI, sensor self-check, forecaster features, controllers
  runner.py                  runs one week, collects metrics
  train.py                   training week + forecaster / AHI calibration
  compare.py, run_all.py     scenarios, summary, figures
dashboard.py                 Streamlit dashboard
results/                     summary.json, CSVs, figures
```

## Honest limitations
- **Simplified physics, not CFD.** Lumped rack/server thermal model, synthetic weather and load, one week per scenario. It is built to compare control strategies fairly, not to predict a specific building.
- The forecaster and AHI are trained and tested on **simulated** data (separate seeds and fault sets). Real deployment needs calibration on site data.
- **Hardware is a paper design.** Prices are rough estimates; some part numbers and thresholds are marked **[VERIFY]** in the docs.
- Savings depend strongly on climate and on the worst rack in the room. Bengaluru gains are modest; cooler climates and hotspot remediation gain more.
- Annual figures are linear extrapolations of one week.
