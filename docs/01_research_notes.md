# Research Notes — MemSense

Background research behind the MemSense design. Every number below has a source.
Items marked **[VERIFY]** need a primary-source check before they go into the final submission.

---

## 1. Why cooling is the problem to solve

| Fact | Value | Source |
|---|---|---|
| Cooling's share of data-centre energy | ~30–40% (BEE/CII guidance cites ~40%); ~25% in one AI-facility breakdown | [tele.net.in](https://tele.net.in/smart-energy-management-role-of-technology-and-green-policy-mandates-in-building-sustainable-data-centres/), [Takshashila](https://takshashila.org.in/content/publications/20251029-Building-Indias-Data-Centres.html) |
| Water use (WUE) in Indian data centres | typically 1.5–2.5 L/kWh of IT load; evaporative towers 1.8–9.5 L/kWh | [netsolwater](https://www.netsolwater.com/water-requirement-for-data-centers-in-india.php?blog=7289), [DownToEarth](https://www.downtoearth.org.in/science-technology/indias-digital-thirst-what-data-centre-giants-arent-saying-about-their-water-use) |
| IGBC certification WUE target | < 2.2 L/kWh; no national WUE policy yet | same as above |
| A 100 MW evaporative-cooled facility | ~2 million litres of water per day | [CEEW](https://www.ceew.in/blogs/why-is-water-based-cooling-a-big-issue-for-ai-data-centres-in-india) |
| Typical operating setpoint | 20–22 °C, even though ASHRAE recommends up to 27 °C | [R&D World / U. Toronto](https://www.rdworldonline.com/hotter-might-be-better-at-energy-intensive-data-centers) |
| Saving from raising inlet temperature | ~2–5% of energy per +1 °C (academic); ENERGY STAR says 4–5% per +1 °F (an industry figure, higher) | [R&D World](https://www.rdworldonline.com/hotter-might-be-better-at-energy-intensive-data-centers), [ENERGY STAR](https://www.energystar.gov/products/data_center_equipment/5-simple-ways-avoid-energy-waste-your-data-center/raise-temperature) |
| New India BIS data-centre standards (2026) | affect cooling and efficiency requirements **[VERIFY: read the details]** | [Schneider blog](https://blog.se.com/datacenter/2026/08/13/what-indias-new-bis-data-centre-standards-mean-for-cooling-and-efficiency/), [India Briefing](https://www.india-briefing.com/news/india-bis-standards-data-centres-46991.html/) |

**Core insight:** operators **overcool** because they cannot see hotspots early.
Raising the setpoint saves energy, but it creates hotspot risk. Mixing of hot and cold air means the inlet temperature at each server is unknown.
*Better, denser sensing plus prediction makes it safe to run warmer.* This is the gap MemSense fills.

We will use **3% per °C** in the simulation, a conservative value inside the 2–5% academic range.

## 2. ASHRAE thermal envelope (the safe operating zone)

- Recommended server inlet temperature: **18–27 °C** ([Araner blog](https://www.araner.com/blog/data-center-cooling-how-it-works-and-why-it-is-the-future), [greencalculus](https://greencalculus.com/standards/ashrae-tc-9-9-thermal-guidelines/)).
- Recommended humidity: upper limit **60% RH**, **dew point up to 15 °C**. The 2022 update added a lower dew-point bound of about 5.5 °C. Whichever RH or dew-point limit is stricter applies. ([ASHRAE Journal May 2022](https://nxtbook.com/nxtbooks/ashrae/ashraejournal_REMKLS/index.php?startid=56))
- Allowable class A1 is roughly 15–32 °C **[VERIFY: ASHRAE Thermal Guidelines 5th ed.]**.
- Three thresholds: *reliability* (long-term), *functional* (runs, but data integrity is not guaranteed), *damage*. ([Araner](https://www.araner.com/blog/data-center-cooling-how-it-works-and-why-it-is-the-future))
- Air quality: **ISO 14644-1 Class 8** particulates; **ANSI/ISA-71.04-2013 severity G1** for gaseous contamination (sulphur and chlorine compounds corrode copper and silver on boards). This matters in Indian cities with high pollution. ([Araner](https://www.araner.com/blog/data-center-cooling-how-it-works-and-why-it-is-the-future))

**Implication for the sensor:** it must measure temperature, RH, **dew point** (computed), **particulates** and ideally **corrosive gas**, not only temperature.

## 3. Cooling technologies we must work with (Vertiv / Araner)

Note: vertiv.com blocked automated reading (HTTP 403), so Vertiv facts come from search results of its product pages.

- **Air:** CRAC/CRAH units, raised floors, hot/cold aisle containment.
- **Chilled-water plants:** water-, air- or seawater-cooled chillers, cooling towers, dry coolers.
- **Free cooling (economisers):** use outside air or water when the climate allows. ENERGY STAR notes that sites with economisers or variable-speed fans gain the most from smarter setpoints.
- **Thermal energy storage:** make chilled water off-peak and use it at peak.
- **Liquid cooling (AI era):**
  - Vertiv **CoolChip CDU** (successor to Liebert XDU): rear-door and direct-to-chip cooling. Liquid-to-air units up to 70 kW work *without facility water*; liquid-to-liquid units go up to 1,368 kW. The CDU provides temperature and flow control and coolant filtration.
  - Vertiv **CoolLoop RDHx** rear-door heat exchanger: up to 80 kW per rack, launched March 2025.
  - Vertiv says the CDU helps keep water temperature accurate to **avoid condensation**, which is a dew-point problem.
  - Vertiv warns that the room's air cooling must handle the rack's heat when a rear door is open for service.
  - Sources: [Vertiv CoolChip CDU](https://www.vertiv.com/en-us/products-catalog/thermal-management/high-density-solutions/vertiv-coolchip-cdu/), [CoolLoop RDHx launch](https://www.vertiv.com/en-us/about/news-and-insights/corporate-news/vertiv-announces-global-launch-of-chilled-water-rear-door-heat-exchanger-for-ai-and-hpc-applications/), [Liquid cooling options](https://www.vertiv.com/en-us/insights/articles/liquid-cooling-options-for-data-centers/)
- Rising rack densities and AI workloads are pushing data centres to liquid and hybrid cooling ([Araner](https://www.araner.com/blog/data-center-cooling-how-it-works-and-why-it-is-the-future)).

**Implication:** MemSense must be **cooling-agnostic**. It should send setpoint advice to any CRAH, CDU or economiser through standard protocols (BACnet, Modbus, Redfish), and add **leak detection** and **dew-point/condensation protection** for liquid-cooled racks.

## 4. The Micron link: memory is already a sensor

- A **DDR5 RDIMM has 3 temperature sensors**: an SPD Hub with a built-in sensor plus 2 discrete sensor ICs (TS0/TS1). Readings go to the server's BMC, which uses them for **fan speed, DRAM refresh rate and bandwidth throttling**. ([Rambus SPD Hub](https://www.rambus.com/memory-interface-chips/ddr5-dimm-chipset/ddr5-spd-hub-with-internal-temperature-sensor/), [Rambus DDR5 blog](https://www.rambus.com/blogs/ddr5-delivers-more-bandwidth-and-capacity-with-a-smarter-dimm))
- The JEDEC sensor (e.g. Renesas TS5111) is accurate to about **±0.5 °C in the 75–95 °C range** and has programmable warning flags. ([Embedded Computing](https://embeddedcomputing.com/technology/iot/wireless-sensor-networks/renesas-introduces-jedec-compliant-precision-temperature-sensor-for-ddr5-memory-modules))
- **NVMe SSDs** report a *Composite Temperature* plus *Warning* and *Critical* thresholds (WCTEMP/CCTEMP) in the standard SMART/Health log. This is part of the NVMe specification. **[VERIFY: cite the NVMe Base Spec]**
- Hot DRAM has to be **refreshed more often**, which costs power and bandwidth, and it gets **throttled**. Heat directly reduces the performance of Micron's own products. (The exact refresh-trigger temperature is in JEDEC JESD79-5 / JESD300-5. **[VERIFY]**: commonly ~85 °C for 2× refresh.)
- **Scale argument:** a 2-socket server with 16 RDIMMs = **48 memory temperature sensors**, plus around 8 SSD sensors. A 40-server rack has about **2,000 built-in sensors** that sit exactly where the heat is. Today they are used only *inside one server's fan loop* and are never combined at room level.

## 5. Micron context (why they will care)

- **Products:** HBM3E (~30% lower power than competitors, per Micron), LPDDR5X, LPCAMM2, and the 245 TB 6600 ION SSD (~30 W, about half the power of a comparable HDD deployment, per Micron). ([Nasdaq press release](https://www.nasdaq.com/press-release/micron-releases-2024-sustainability-report-highlighting-progress-and-long-term-vision), [Micron 6600 ION](https://micron.gcs-web.com/node/50436))
- **Sustainability:** 66% water reuse, recycling and restoration (2023, up from 50% in 2020); scope 1 emissions down 11% against the 2020 baseline; net-zero operations target by 2050. Singapore site: >150 million kWh saved since 2021. ([Nasdaq](https://www.nasdaq.com/press-release/micron-releases-2024-sustainability-report-highlighting-progress-and-long-term-vision), [EDB Singapore](https://www.edb.gov.sg/en/news-and-insights/micron-moves-the-needle-on-energy-savings))
- **India:** Micron's **Sanand, Gujarat** assembly and test facility opened in early 2026. It is India's first commercial semiconductor chip production site (about $2.75B total investment, 500,000+ sq ft of cleanroom). It packages DRAM and NAND into finished memory and storage products. ([Computer Weekly](https://www.computerweekly.com/news/366639653/Micron-opens-275bn-chip-assembly-plant-in-India), [HPCwire](https://www.hpcwire.com/off-the-wire/micron-celebrates-opening-of-indias-1st-semiconductor-assembly-and-test-facility/))
  - Tie-in: the same sensing node also applies to **cleanrooms and test floors**. Test floors run burn-in ovens, cleanrooms need strict temperature, RH and particle control, and Sanand is in a hot, dusty climate.
- **Industrial memory for the node:** Micron sells industrial-temperature e.MMC/NOR/LPDDR for edge devices **[VERIFY: pick an exact part number]**.

## 6. Real-world difficulties the sensor must survive

1. **Air mixing and hot-air recirculation** cause hotspots between sparse wall sensors.
2. **Humidity:** too high leads to condensation (especially on liquid-cooled pipes) and corrosion; too low leads to static discharge (ESD).
3. **Dust and corrosive gas** (Indian urban air) corrode silver and copper on boards; ISA-71.04 G1 is the target.
4. **Containment leaks** are visible as a small cold-to-hot-aisle pressure difference (a few pascals).
5. **Liquid cooling leaks** cause catastrophic damage, so they need fast detection.
6. **Sensor drift, failure and EMI** in a noisy RF and electrical environment, so the system needs self-checking.
7. **Retrofit constraint:** no rewiring and no downtime, so mounting and power must be simple.
8. **Cyber-security:** sensors must not become an attack path into the operator's network.
9. **The sensors' own footprint:** they must consume very little power and avoid throwaway batteries.

## 7. Open items to verify before final submission
- ASHRAE A1 allowable limits (5th edition table).
- NVMe spec section for WCTEMP/CCTEMP.
- JEDEC DDR5 refresh-rate temperature threshold.
- Exact Micron industrial part numbers for the node BOM.
- BIS 2026 data-centre standard details.
