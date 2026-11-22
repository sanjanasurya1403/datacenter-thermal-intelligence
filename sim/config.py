"""
Every modelling assumption lives in this file.

Values are simplified but physically sensible. They are chosen to be
*conservative* (understating MemSense savings rather than overstating them).
Sources are in docs/01_research_notes.md.
"""

# ---------------------------------------------------------------- time
DT_MIN = 1.0                      # simulation step (minutes)
SIM_DAYS = 7
STEPS = int(SIM_DAYS * 24 * 60)

# ---------------------------------------------------------------- hall layout
N_RACKS = 20                      # two rows of 10 racks
RACKS_PER_ROW = 10
SERVERS_PER_RACK = 10
HIGH_DENSITY_RACKS = [16, 17, 18, 19]   # AI/HPC racks, fitted with rear-door heat exchangers (RDHx)
END_OF_ROW_RACKS = [0, 9, 10, 19]       # end-of-row racks suffer more hot-air wrap-around

# ---------------------------------------------------------------- servers
P_IDLE_W, P_MAX_W = 200.0, 600.0        # standard 2-socket server
HD_P_IDLE_W, HD_P_MAX_W = 350.0, 1100.0 # high-density server
FAN_BASE_W, HD_FAN_BASE_W = 15.0, 30.0  # server fan power at speed 1.0 (fan power ~ speed^3)
AIRFLOW_M3S, HD_AIRFLOW_M3S = 0.028, 0.060   # nominal server airflow (~60 / ~130 CFM)
FAN_RAMP_START_C = 25.0           # server firmware speeds fans up above this inlet temperature
FAN_RAMP_PER_C = 0.06             # +6% fan speed per degC above the ramp start
FAN_DIMM_RAMP_START_C = 75.0      # fans also react to hot DIMMs
FAN_DIMM_RAMP_PER_C = 0.03
FAN_MAX_SPEED = 2.0
RHO_AIR, CP_AIR = 1.2, 1005.0     # kg/m3, J/(kg K)

# ---------------------------------------------------------------- memory / storage thermal model
DIMM_BASE_RISE_C, DIMM_LOAD_RISE_C = 10.0, 28.0         # DIMM temp rise over inlet at speed 1.0
HD_DIMM_BASE_RISE_C, HD_DIMM_LOAD_RISE_C = 12.0, 32.0
AIRFLOW_HEALTH_EXP = 0.8          # DIMM rise scales with 1 / health^0.8
FAN_SPEED_EXP = 0.6               # DIMM rise scales with 1 / speed^0.6
TAU_DIMM_MIN = 5.0                # DIMM thermal time constant
SSD_BASE_RISE_C, SSD_LOAD_RISE_C = 12.0, 15.0
DRAM_2X_REFRESH_C = 85.0          # above this DDR5 must refresh 2x as often (32 ms window up to 85 degC, 16 ms 85-95 degC; Micron 16Gb DDR5 datasheet). Throttling is a separate server-firmware policy.
MTM_GUARD_C = 10.0                # MemSense keeps >= 10 degC Memory Thermal Margin

# ---------------------------------------------------------------- air distribution
MIX_OFFSET_C = 1.0                # supply-to-cold-aisle mixing gain
RACK_OFFSET_MAX_C = 1.2           # rack-to-rack placement variation (random, fixed per hall)
RECIRC_BOTTOM, RECIRC_TOP = 0.01, 0.10   # share of exhaust air recirculating to inlet
END_OF_ROW_RECIRC_FACTOR = 1.5
BREACH_RECIRC_EXTRA = 0.35        # extra recirculation at the top of a rack with containment breached
TAU_SUPPLY_MIN = 10.0             # CRAH supply-air response time
DP_NOMINAL_PA, DP_BREACH_DROP_PA = 5.0, 3.0   # cold-to-hot aisle pressure difference

# ---------------------------------------------------------------- humidity
DEHUMID_OFFSET_C = 4.0            # room dew point sits ~4 degC below outdoor dew point (CRAH dehumidifying)
TAU_HUMIDITY_MIN = 240.0          # room humidity follows outdoor with ~4 h lag
DEW_MARGIN_C = 2.5                # MemSense keeps RDHx coil >= dew point + 2.5 degC

# ---------------------------------------------------------------- cooling plant
CHW_APPROACH_C = 3.0              # chilled water is ~3 degC below supply air
COP_REF = 3.0                     # chiller plant COP at 15 degC CHW, 20 degC wet bulb; calibrated so the
                                  # baseline PUE ~1.5 and cooling ~30% of energy (typical India) [VERIFY]
COP_GAIN_PER_C = 0.03             # +3% COP per degC warmer chilled water (conservative; research: 2-5%)
COP_LOSS_PER_C_WB = 0.02          # -2% COP per degC hotter outdoor wet bulb
ECON_APPROACH_C = 4.5             # water-side economiser: tower + heat-exchanger approach
ECON_RAMP_C = 4.0                 # partial free cooling across this band
DRY_APPROACH_C = 6.0              # hybrid cooler can reject heat without water below this
DRY_RAMP_C = 4.0
PUMP_TOWER_FRAC = 0.03            # pumps + tower fans, fraction of heat load
CRAH_FAN_FRAC = 0.04              # CRAH fans, fraction of heat load
OTHER_LOSS_FRAC = 0.08            # UPS / distribution / lighting losses, fraction of IT power
WATER_L_PER_KWH_HEAT = 1.8        # evaporation + blowdown per kWh heat rejected in wet mode

# ---------------------------------------------------------------- controllers
BASELINE_SUPPLY_C = 18.0          # conventional fixed, conservative setpoint
MEMSENSE_MIN_SUPPLY_C = 18.0
MEMSENSE_MAX_SUPPLY_C = 25.0      # hard cap set by the operator
ASHRAE_REC_MAX_C = 27.0           # recommended inlet upper limit
ASHRAE_ALLOW_MAX_C = 32.0         # A1 allowable upper limit [VERIFY]
INLET_MARGIN_C = 1.5              # MemSense targets predicted max inlet <= 25.5 degC
RAISE_STEP_C, LOWER_STEP_C = 0.5, 1.0
RAISE_HOLD_MIN = 15               # wait at least 15 min between raises (warming is slow)
LOWER_HOLD_MIN = 2                # cooling is fast
FORECAST_HORIZON_MIN = 10

# ---------------------------------------------------------------- operations
REPAIR_DELAY_MIN = {              # time from detection to fix
    "airflow": 60, "breach": 30, "leak": 20, "drift": 120,
}
MANUAL_ROUND_INTERVAL_MIN = 240   # baseline: walk-through every 4 h finds leaks / open panels

# ---------------------------------------------------------------- reporting
TARIFF_INR_PER_KWH = 8.0          # commercial tariff [VERIFY local]
GRID_KG_CO2_PER_KWH = 0.71        # India grid emission factor (CEA) [VERIFY latest]
WEEKS_PER_YEAR = 52.14

CLIMATES = {
    # name: (mean dry bulb, diurnal amplitude, normal outdoor dew point)
    "bengaluru_nov": (22.0, 5.0, 15.0),
    "delhi_jan": (14.0, 6.5, 7.0),
}
HUMID_DAY = 3                     # day index of the rain / monsoon-like humid day
HUMID_DAY_DEWPOINT_C = 23.0
