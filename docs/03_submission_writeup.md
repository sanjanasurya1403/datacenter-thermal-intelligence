# MemSense: Memory-Aware Thermal Intelligence for Sustainable Data Centres
### Application write-up: Micron-Supported SOLVE Innovation Program, BITS Pilani

Sections are self-contained so they can be copied into the application form.

**Applicant / team:** Bachina Baby Sanjana Surya, ECE, BITS Hyderabad

**Focus areas:** #2 IoT & Connected Intelligent Systems (primary) · #6 AI Applications · #1 Semiconductor Technologies
**Repository:** https://github.com/sanjanasurya1403/datacenter-thermal-intelligence

---

## 1. Abstract (~150 words)
Data centres spend 30–40% of their energy on cooling. Most keep rooms colder than necessary because operators cannot see hotspots early.
Yet every DDR5 RDIMM (server memory module) already contains three temperature sensors, and every NVMe SSD reports its own temperature. A full rack of 40 dual-socket servers with 16 RDIMMs each holds about 2,000 such sensors, used today only to drive each server's own fans.
**MemSense** fuses this existing Micron in-silicon telemetry with a low-cost, PoE-powered environmental sensor node (humidity, dew point, aisle pressure, particulates, corrosive gas, leaks) and edge AI that forecasts hotspots 10 minutes ahead. Operators can then raise cooling setpoints safely.
In a week-long simulation of a 100 kW hall, MemSense:
- cut cooling energy by 6% (Bengaluru) to 23% (Delhi winter);
- cut water by up to 22%;
- kept rear-door heat exchangers dry on a humid day using measured coil temperature and a shared room dew point;
- in a simulated slow-clogging event, flagged the server 2.8 h after onset using memory sensors alone, long before its DRAM approached 85 °C (a BMC critical-only alarm needed 31 h).

## 2. Problem statement
- **Energy:** cooling is the largest non-IT load in a data centre (~30–40% of facility energy in Indian guidance). India's data-centre capacity is growing rapidly with AI workloads.
- **Water:** Indian facilities typically consume 1.5–2.5 litres of water per kWh of IT load. A 100 MW evaporative-cooled site can use around 2 million litres a day.
- **Overcooling:** operators run at 20–22 °C although ASHRAE recommends server inlets up to 27 °C. Each unnecessary degree wastes roughly 2–5% of energy. They overcool because a hall has only a handful of wall sensors, and hotspots (recirculation, blocked airflow, open containment) form *between* them.
- **New risks:** AI racks bring liquid cooling (rear-door heat exchangers, direct-to-chip CDUs). That adds condensation and leak risks, and India's humid monsoons and polluted urban air add corrosion risk to electronics.
- **Memory pays the price:** above 85 °C, DDR5 must refresh twice as often (Micron 16Gb DDR5 datasheet), which costs bandwidth and power. Servers may also throttle memory through their own firmware policies.

## 3. Proposed solution
**MemSense** is a three-layer, vendor-neutral system:

1. **Memory as a sensor (zero added hardware).** Read DDR5 RDIMM temperatures (SPD5 hub + two JEDEC sensors per module) and NVMe SSD temperatures out-of-band through the server BMC (DMTF Redfish, read-only). No software is installed on customer servers.
2. **MemSense Node (IoT).** An ESP32-S3-based node with Micron industrial flash memory, powered by PoE (no batteries). It measures:
   - inlet/outlet temperature and humidity, and dew point;
   - cold-to-hot-aisle pressure difference (containment leaks);
   - PM2.5;
   - silver/copper corrosion coupons, a low-cost estimate of the ANSI/ISA-71.04 severity class;
   - rope leak detection;
   - pipe-surface temperature on liquid-cooling lines.
   
   It comes in two tiers: Node-R (~₹4.5k, every rack) and Node-X (~₹16k, one per row).
3. **Edge AI gateway.** On-site; data never leaves the facility.
   - Fuses both layers into a per-rack, per-height thermal map.
   - Forecasts the hottest inlet 10 minutes ahead (gradient-boosted model).
   - Computes the **Airflow Health Index** and **Memory Thermal Margin**.
   - Cross-checks sensors to catch drift.
   - Guards against condensation.
   - Adjusts cooling setpoints within operator-defined hard limits through BACnet/Modbus, so it works with Vertiv, Schneider or any other plant.

**Safety by design:**
- Warming is slow (+0.5 °C, at most every 15 minutes); cooling is fast (−1 °C immediately).
- If MemSense goes silent, the cooling units revert to their defaults.
- Deployment starts in advisory-only mode.

## 4. Innovation: what is new
1. **Repurposing memory telemetry as facility infrastructure.** DIMM/SSD sensors are dense, factory-calibrated, already paid for and located at the heat source. Today they never leave the server's fan loop. MemSense makes them a room-scale sensor network.
2. **Airflow Health Index.** It compares a DIMM's temperature rise over inlet with the rise expected at its current load, and detects clogged filters, blocked intakes or recirculation *inside* a server that fan-tachometer alarms miss. In a simulated slow-clogging event, AHI flagged the server 2.8 h after onset, long before its DRAM approached 85 °C. A BMC critical-only alarm needed 31 h.
3. **Measured dew-point margin for liquid cooling.** Commercial CDUs already control water temperature to avoid condensation. What is new here is that the margin uses a *measured* coil/pipe surface temperature and a room dew point shared across racks, rather than a fixed setpoint offset. (In simulation, a baseline with fixed 15 °C water and no dew-point control saw 710 minutes of condensation on a humid day; MemSense saw 0. That shows the size of the risk, not a gain over a well-controlled CDU.)
4. **Self-verifying sensing.** Node sensors are continuously cross-checked against server BMC readings at the same height. A drifting sensor was isolated in 90 minutes. Without this check, the drift caused 91 kWh/week of needless cooling.
5. **A sub-₹1,000 corrosion monitor** concept (Ag/Cu thin-film coupons + 24-bit ADC). Commercial gaseous-contamination monitors cost far more. This targets India's urban air.

## 5. Relevance to Micron
- **Makes Micron memory more valuable in the data centre.** The same DIMMs and SSDs customers already buy become part of the cooling system. Micron could showcase "memory that helps cool the data centre".
- **Protects Micron products in the field.** Keeping DRAM below 85 °C avoids the 2× refresh region, which preserves bandwidth, performance per watt and reliability. Simulated server-minutes with DRAM above 85 °C fell from 5 to 0.
- **Uses Micron industrial memory** in the node (e.MMC/NOR) for store-and-forward buffering and secure A/B firmware.
- **Aligns with Micron's sustainability goals:** water reuse targets, net-zero operations by 2050, and low-power product leadership (HBM3E, LPDDR5X, 6600 ION).
- **Applies to Micron's own sites.** The Node-X measures exactly what cleanrooms and test floors care about (temperature, humidity, particles, corrosive gas), so it could be piloted at the **Sanand, Gujarat** assembly and test facility. It also scales to the data rooms of any Micron site.

## 6. Current status and results
**Done (in the repository):**
- Research with cited sources.
- Full system and hardware design on paper: architecture, BOM, block diagram, control logic, security.
- A working Python simulation with an ML forecaster, the AHI detector, the sensor self-check and an interactive dashboard.

**Simulation setup:** a 20-rack (~100 kW) hall, including 4 high-density racks with rear-door heat exchangers, over one week. Four faults are injected: clogged server airflow, removed blanking panels, coolant leak and sensor drift, plus a humid day. Baseline and MemSense see identical conditions.

| Result | Baseline | MemSense |
|---|---|---|
| Cooling energy (Bengaluru, Nov) | 6,593 kWh | 6,197 kWh (−6.0%) |
| Cooling energy (Delhi, Jan) | — | −23% (water −22%) |
| PUE (Bengaluru / Delhi) | 1.486 / 1.398 | 1.461 / 1.324 |
| Rack-minutes above 27 °C | 301 | 66 |
| Condensation minutes (baseline: fixed 15 °C water, no dew-point control) | 710 | 0 |
| Slow-clogging airflow flagged after (BMC critical-only alarm vs AHI) | 31 h | 2.8 h |
| Containment breach detected after (manual round vs aisle pressure sensor) | 2 h | 2 min |
| Leak detected after (manual round vs leak rope) | 110 min | < 1 min |
| False alarms | 0 | 0 |

Each detection result is a single simulated event. The leak and breach results come from the leak rope and the aisle pressure sensor, not from the AI.

**Where the Bengaluru saving comes from:** no free-cooling hours occur in either Bengaluru run, so the saving comes from the assumed chiller COP gain per °C. Across the 2–5% per °C range in the literature, it is 4.1–9.5% of cooling energy (6.0% at our 3%).

The forecaster's held-out error is 0.20 °C during temperature transients, against 0.76 °C for a naive forecast.

**Indicative annual impact per MW of IT load:** about 213 MWh, ₹17 lakh, 151 t CO₂ and 384 kL of water (Bengaluru). The figures are higher in cooler climates. They are linear extrapolations of one simulated week.

**Being upfront:** this is a simplified physics model, not CFD, and the hardware is not yet built. All assumptions are listed in `sim/config.py`, and limitations are stated in the README.

## 7. Sustainability impact
- **Energy and CO₂:** lower chiller load from safe warmer setpoints, and more free-cooling hours.
- **Water:** warmer chilled water means less evaporative heat rejection (up to −22% in simulation).
- **Hardware life:** less condensation, corrosion and thermal stress means fewer failures and less e-waste.
- **The node itself:** PoE-powered with no batteries, ~2 W, modular and repairable sensor boards. The research option of a thermoelectric harvester keeps the leak alarm alive during power loss.
- **No rip-and-replace:** retrofits existing halls and works with existing cooling equipment.

## 8. Plan and budget (if selected)
| Month | Milestone |
|---|---|
| 0–2 | Build 5 Node-R + 1 Node-X. Lab test bench: read DDR5 SPD-hub temperatures via Linux `hwmon` / BMC Redfish. Validate AHI with controlled airflow blockage. |
| 3–5 | Pilot in a campus server room in advisory mode; record baseline vs. recommendations. |
| 6–9 | Closed-loop pilot within safe bounds. Validate corrosion coupons against a reference. Write up results. |
| 9–12 | Report and demo to Micron; explore a pilot at a Micron facility. |

**Indicative prototype budget** (estimates, to be confirmed with quotes; total ≈ ₹2.2 lakh, or ≈ ₹1.45 lakh with campus DDR5 server access):

| Item | ₹ |
|---|---|
| 5 × Node-R + 1 × Node-X components | ~40,000 |
| PCB fabrication, enclosures, cabling, PoE switch | ~25,000 |
| Edge gateway (mini PC) | ~40,000 |
| DDR5 test platform: desktop with DDR5 modules + NVMe SSD (DDR5 SPD-hub sensors are readable via Linux `spd5118`); not needed if campus DDR5 servers are available | ~75,000 |
| Reference instruments: calibrated temperature/RH logger, handheld differential manometer, commercial Ag/Cu reactivity coupons + lab analysis | ~40,000 |

**Support requested from Micron / SIRE:**
- Mentorship on DDR5 SPD-hub/thermal-sensor behaviour and DRAM thermal thresholds.
- Access to a few DDR5 servers or RDIMMs and Micron industrial flash samples.
- Guidance on a pilot site.

## 9. Risks and mitigations
| Risk | Mitigation |
|---|---|
| BMCs differ in which memory sensors Redfish exposes | IPMI and in-band `hwmon`/`nvme` fallbacks; vendor survey in month 1 |
| Operators distrust automated setpoint changes | Advisory mode first, hard limits, fail-safe revert, explainable alerts |
| Simulation results don't transfer to a real room | Calibrate on campus pilot data before closed-loop control |
| Low-cost corrosion coupon accuracy | Treated as a research element; validated against a commercial reference |
| Security of sensors on the operator's network | Wired, separate VLAN, outbound-only mTLS, signed firmware, read-only BMC accounts |
| In colocation, the operator does not own tenants' servers and cannot read their BMCs | Layer 1 needs tenant consent there, so target enterprise, campus and hyperscale halls first; in colocation, Layers 2 and 3 still work alone |

## 10. Why this team
As an Electronics & Communication Engineering student, I bring together the hardware and software this project needs: I designed the MemSense sensor node (component selection, bill of materials, block diagram, security) and built a working Python simulation of a 20-rack data hall with physics-based thermal, cooling and water models, machine-learning hotspot forecasting, fault detection and an interactive Streamlit dashboard. All of it is public in the repository above. I validated the results honestly: I fixed a forecaster that initially did worse than a naive baseline, made the baseline comparison fair, and documented every assumption and limitation.
