"""
MemSense analytics + controllers.

  * FeatureBuilder  - per-rack features for the 10-minute hotspot forecaster
  * AirflowHealth   - Airflow Health Index (AHI) from DIMM vs inlet temperature
  * SensorHealth    - flags drifting node sensors by cross-checking server BMC inlets
  * MemSenseController / BaselineController / RandomWalkController
"""
from collections import deque
import numpy as np
from . import config as C

FEATURES = ["m0", "d5", "d10", "u_mean", "du10", "t_sup", "sp_gap", "hsin", "hcos", "hd"]


def util_from_power(power_w, hd):
    """Estimate utilisation from BMC-reported power (fan power ignored, small)."""
    p_idle = np.where(hd, C.HD_P_IDLE_W, C.P_IDLE_W)
    p_max = np.where(hd, C.HD_P_MAX_W, C.P_MAX_W)
    return np.clip((power_w - p_idle) / (p_max - p_idle), 0, 1)


class SensorHealth:
    """Node inlet sensors must agree with the server BMC inlet at the same height."""

    def __init__(self, threshold=1.5, alpha=1 / 15):
        self.thr, self.alpha = threshold, alpha
        self.ewma = np.zeros(C.N_RACKS)
        self.suspect = np.zeros(C.N_RACKS, bool)

    def update(self, s):
        resid = s["node_in_top"] - s["bmc_inlet"][:, -1]
        self.ewma += self.alpha * (resid - self.ewma)
        newly = (np.abs(self.ewma) > self.thr) & ~self.suspect
        self.suspect |= np.abs(self.ewma) > self.thr
        return np.flatnonzero(newly)

    def clear(self, rack):
        self.suspect[rack] = False
        self.ewma[rack] = 0.0


class AirflowHealth:
    """
    AHI = measured DIMM-over-inlet rise (normalised for fan speed) / expected rise for this load.
    1.0 = healthy. Expected rise comes from a linear fit learned on healthy training data.
    """

    def __init__(self, coef, threshold=1.3, persist_min=10, alpha=1 / 10):
        self.coef = coef            # {False: (a, b), True: (a, b)} for standard / high-density servers
        self.thr, self.persist, self.alpha = threshold, persist_min, alpha
        self.ewma = None
        self.count = None
        self.flagged = None
        self.n = 0

    WARMUP_MIN = 60

    def update(self, s, hd):
        u = util_from_power(s["bmc_power_w"], hd)
        rise = (s["bmc_dimm"] - s["bmc_inlet"]) * s["bmc_fan_speed"] ** C.FAN_SPEED_EXP
        a = np.where(hd, self.coef[True][0], self.coef[False][0])
        b = np.where(hd, self.coef[True][1], self.coef[False][1])
        ahi = rise / (a + b * u)
        if self.ewma is None:
            self.ewma = ahi.copy()
            self.count = np.zeros(ahi.shape, int)
            self.flagged = np.zeros(ahi.shape, bool)
        self.ewma += self.alpha * (ahi - self.ewma)
        self.n += 1
        if self.n < self.WARMUP_MIN:
            return self.ewma, []
        self.count = np.where(self.ewma > self.thr, self.count + 1, 0)
        newly = (self.count >= self.persist) & ~self.flagged
        self.flagged |= newly
        return self.ewma, list(zip(*np.nonzero(newly)))

    def clear(self, rack, server):
        self.flagged[rack, server] = False
        self.count[rack, server] = 0
        self.ewma[rack, server] = 1.0


def fit_ahi_coefficients(rises, utils, hds):
    """Least-squares fit rise = a + b*u separately for standard and high-density servers."""
    coef = {}
    for flag in (False, True):
        m = hds == flag
        A = np.vstack([np.ones(m.sum()), utils[m]]).T
        coef[flag] = tuple(np.linalg.lstsq(A, rises[m], rcond=None)[0])
    return coef


class FeatureBuilder:
    def __init__(self, hd_rack):
        self.hist_m = deque(maxlen=11)
        self.hist_u = deque(maxlen=11)
        self.hd = hd_rack.astype(float)
        self.sm_bmc = None

    SMOOTH = 0.2

    def rack_max_inlet(self, s, trusted_top):
        """Hottest inlet per rack, from smoothed BMC inlets (integer-rounded) and node sensors."""
        if self.sm_bmc is None:
            self.sm_bmc = s["bmc_inlet"].astype(float)
            self.sm_bot, self.sm_top = s["node_in_bottom"].copy(), s["node_in_top"].copy()
        a = self.SMOOTH
        self.sm_bmc += a * (s["bmc_inlet"] - self.sm_bmc)
        self.sm_bot += a * (s["node_in_bottom"] - self.sm_bot)
        self.sm_top += a * (s["node_in_top"] - self.sm_top)
        node_top = np.where(trusted_top, self.sm_top, -np.inf)
        return np.maximum.reduce([self.sm_bmc.max(axis=1), self.sm_bot, node_top])

    def build(self, minute, s, setpoint, trusted_top, hd_server):
        m0 = self.rack_max_inlet(s, trusted_top)
        u = util_from_power(s["bmc_power_w"], hd_server).mean(axis=1)
        self.hist_m.append(m0)
        self.hist_u.append(u)
        m5 = self.hist_m[-6] if len(self.hist_m) >= 6 else self.hist_m[0]
        m10 = self.hist_m[0]
        u10 = self.hist_u[0]
        h = (minute / 60.0) % 24
        n = len(m0)
        X = np.column_stack([
            m0, m0 - m5, m0 - m10, u, u - u10,
            np.full(n, s["supply_air"]), np.full(n, setpoint - s["supply_air"]),
            np.full(n, np.sin(2 * np.pi * h / 24)), np.full(n, np.cos(2 * np.pi * h / 24)), self.hd,
        ])
        return X, m0


# ======================================================================= controllers
class BaselineController:
    """Conventional practice: fixed conservative setpoint, BMC critical alarms, manual rounds."""
    name = "baseline"

    def __init__(self, hall_hd):
        self.setpoint = C.BASELINE_SUPPLY_C
        self.hot = np.zeros(hall_hd.shape, int)
        self.breach_visible = None      # set by the runner: what a person walking the aisle would see

    def decide(self, minute, s):
        detections = []
        # BMC raises a critical alarm only when a DIMM is already at the throttle limit for 5 min
        self.hot = np.where(s["bmc_dimm"] >= C.DRAM_THROTTLE_C, self.hot + 1, 0)
        for r, h in zip(*np.nonzero(self.hot == 5)):
            detections.append(("airflow", int(r), int(h), "BMC DIMM critical alarm"))
        # manual walk-through every 4 h finds visible leaks
        if minute % C.MANUAL_ROUND_INTERVAL_MIN == 0:
            for r in np.flatnonzero(s["node_leak"]):
                detections.append(("leak", int(r), -1, "found on manual round"))
            if self.breach_visible is not None:
                for r in np.flatnonzero(self.breach_visible):
                    detections.append(("breach", int(r), -1, "found on manual round"))
        rdhx_water = self.setpoint - C.CHW_APPROACH_C
        return self.setpoint, rdhx_water, detections

    def on_repair(self, fault):
        pass


class RandomWalkController(BaselineController):
    """Used only to generate training data: setpoint wanders 17-25 degC."""
    name = "random_walk"

    def __init__(self, hall_hd, rng):
        super().__init__(hall_hd)
        self.rng = rng
        self.next_change = 0

    def decide(self, minute, s):
        if minute >= self.next_change:
            self.setpoint = float(np.clip(self.setpoint + self.rng.choice([-2, -1, -0.5, 0.5, 1, 2]), 17, 25))
            self.next_change = minute + int(self.rng.integers(20, 120))
        return self.setpoint, self.setpoint - C.CHW_APPROACH_C, []


class MemSenseController:
    name = "memsense"

    def __init__(self, hall_hd, model, ahi_coef, use_sensor_health=True):
        self.hd = hall_hd
        self.model = model
        self.ahi = AirflowHealth(ahi_coef)
        self.health = SensorHealth()
        self.use_health = use_sensor_health
        self.fb = FeatureBuilder(hall_hd[:, 0])
        self.setpoint = C.BASELINE_SUPPLY_C
        self.last_raise = -10_000
        self.last_lower = -10_000
        self.dp_low = np.zeros(C.N_RACKS, int)
        self.reported_breach = np.zeros(C.N_RACKS, bool)
        self.grad_norm = None
        self.reported_leak = np.zeros(C.N_RACKS, bool)
        self.dew_alerted = False
        self.last_pred = None
        self.last_ahi = None

    def decide(self, minute, s):
        det = []
        # ---- sensor self-check
        for r in self.health.update(s):
            if self.use_health:
                det.append(("drift", int(r), -1, "node sensor disagrees with server BMC inlets"))
        trusted_top = ~self.health.suspect if self.use_health else np.ones(C.N_RACKS, bool)
        # ---- airflow faults inside servers (memory-as-a-sensor)
        ahi, newly = self.ahi.update(s, self.hd)
        self.last_ahi = ahi
        for r, h in newly:
            det.append(("airflow", int(r), int(h), f"AHI {ahi[r, h]:.2f} > {self.ahi.thr}"))
        # ---- containment breach from aisle pressure
        # A low cold/hot-aisle pressure difference says "this row's containment is open".
        # Localise to racks whose top-to-bottom inlet gradient rose above their own learned normal.
        grad = s["bmc_inlet"][:, -1] - s["bmc_inlet"][:, 0]
        dp_ok = s["node_dp_pa"] >= 2.5
        if self.grad_norm is None:
            self.grad_norm = grad.astype(float)
        self.grad_norm = np.where(dp_ok, self.grad_norm + (grad - self.grad_norm) / 240.0, self.grad_norm)
        self.dp_low = np.where(dp_ok, 0, self.dp_low + 1)
        row = np.arange(C.N_RACKS) // C.RACKS_PER_ROW
        anomaly = grad - self.grad_norm
        for rw in np.unique(row[self.dp_low >= 3]):
            cand = np.flatnonzero((row == rw) & (anomaly > 2.5) & ~self.reported_breach)
            for r in cand:
                det.append(("breach", int(r), -1,
                            f"row {rw} aisle dP {s['node_dp_pa'][r]:.1f} Pa; rack gradient +{anomaly[r]:.1f} C vs normal"))
                self.reported_breach[r] = True
        # ---- leaks (rope sensor, hardware interrupt)
        for r in np.flatnonzero(s["node_leak"] & ~self.reported_leak):
            det.append(("leak", int(r), -1, "leak rope triggered"))
            self.reported_leak[r] = True
        # ---- forecast and bounded setpoint control
        X, m0 = self.fb.build(minute, s, self.setpoint, trusted_top, self.hd)
        pred = m0 + self.model.predict(X)
        self.last_pred = pred
        limit = C.ASHRAE_REC_MAX_C - C.INLET_MARGIN_C
        healthy = ~self.ahi.flagged
        mtm = C.DRAM_THROTTLE_C - np.where(healthy, s["bmc_dimm"], -np.inf).max()
        hall_pred, hall_now = pred.max(), m0.max()
        if (hall_pred > limit or hall_now > limit + 0.5 or mtm < C.MTM_GUARD_C) and \
                minute - self.last_lower >= C.LOWER_HOLD_MIN:
            self.setpoint -= C.LOWER_STEP_C
            self.last_lower = minute
        elif (hall_pred + C.RAISE_STEP_C <= limit - 0.25 and hall_now <= limit - 0.5 and mtm > C.MTM_GUARD_C + 3
              and minute - self.last_raise >= C.RAISE_HOLD_MIN and minute - self.last_lower >= C.RAISE_HOLD_MIN
              and abs(self.setpoint - s["supply_air"]) < 0.3):
            self.setpoint += C.RAISE_STEP_C
            self.last_raise = minute
        self.setpoint = float(np.clip(self.setpoint, C.MEMSENSE_MIN_SUPPLY_C, C.MEMSENSE_MAX_SUPPLY_C))
        # ---- dew-point guard for rear-door heat exchangers
        td = float(np.median(s["node_dewpoint"]))
        chw = self.setpoint - C.CHW_APPROACH_C
        rdhx_water = max(chw, td + C.DEW_MARGIN_C)
        if rdhx_water > chw + 0.01 and not self.dew_alerted:
            det.append(("humid", -1, -1, f"dew point {td:.1f} C: RDHx water raised to {rdhx_water:.1f} C"))
            self.dew_alerted = True
        return self.setpoint, rdhx_water, det

    def on_repair(self, fault):
        if fault.kind == "airflow":
            self.ahi.clear(fault.rack, fault.server)
        elif fault.kind == "drift":
            self.health.clear(fault.rack)
        elif fault.kind == "breach":
            self.reported_breach[:] = False
            self.dp_low[:] = 0
        elif fault.kind == "leak":
            self.reported_leak[fault.rack] = False
