"""Physics of the simulated data hall (the 'ground truth') and what sensors report."""
import numpy as np
from . import config as C


class DataHall:
    def __init__(self, rng, init_supply=C.BASELINE_SUPPLY_C, td_room=11.0):
        R, H = C.N_RACKS, C.SERVERS_PER_RACK
        self.rng = rng
        hd = np.zeros((R, H), bool)
        hd[C.HIGH_DENSITY_RACKS, :] = True
        self.hd = hd
        self.p_idle = np.where(hd, C.HD_P_IDLE_W, C.P_IDLE_W)
        self.p_max = np.where(hd, C.HD_P_MAX_W, C.P_MAX_W)
        self.v0 = np.where(hd, C.HD_AIRFLOW_M3S, C.AIRFLOW_M3S)
        self.fan_base = np.where(hd, C.HD_FAN_BASE_W, C.FAN_BASE_W)
        self.dimm_base = np.where(hd, C.HD_DIMM_BASE_RISE_C, C.DIMM_BASE_RISE_C)
        self.dimm_load = np.where(hd, C.HD_DIMM_LOAD_RISE_C, C.DIMM_LOAD_RISE_C)
        self.hpos = (np.arange(H) / (H - 1))[None, :]          # 0 = bottom, 1 = top
        end = np.ones(R)
        end[C.END_OF_ROW_RACKS] = C.END_OF_ROW_RECIRC_FACTOR
        self.recirc_base = (C.RECIRC_BOTTOM + (C.RECIRC_TOP - C.RECIRC_BOTTOM) * self.hpos ** 2) * end[:, None]
        self.rack_offset = rng.uniform(0, C.RACK_OFFSET_MAX_C, R)[:, None]
        # dynamic state
        self.health = np.ones((R, H))          # airflow health (1 = clean)
        self.breach = np.zeros(R)              # extra recirculation from containment breach
        self.t_sup = init_supply
        self.t_exh = np.full(R, init_supply + 14.0)
        self.t_dimm = init_supply + C.MIX_OFFSET_C + self.dimm_base + self.dimm_load * 0.45
        self.speed = np.ones((R, H))
        self.td_room = td_room

    def step(self, u, setpoint, td_out):
        """Advance one minute. Returns the true physical state."""
        dt = C.DT_MIN
        self.t_sup += (setpoint - self.t_sup) * dt / C.TAU_SUPPLY_MIN
        recirc = self.recirc_base + self.breach[:, None] * self.hpos
        t_in = (self.t_sup + C.MIX_OFFSET_C + self.rack_offset
                + recirc * (self.t_exh[:, None] - self.t_sup)
                + self.rng.normal(0, 0.1, u.shape))
        # server fan control reacts to inlet and DIMM temperature
        speed = (1.0 + C.FAN_RAMP_PER_C * np.clip(t_in - C.FAN_RAMP_START_C, 0, None)
                 + C.FAN_DIMM_RAMP_PER_C * np.clip(self.t_dimm - C.FAN_DIMM_RAMP_START_C, 0, None))
        speed = np.minimum(speed, C.FAN_MAX_SPEED)
        p_it = self.p_idle + (self.p_max - self.p_idle) * u
        p_fan = self.fan_base * speed ** 3
        airflow = self.v0 * speed * self.health
        t_out = t_in + (p_it + p_fan) / (C.RHO_AIR * C.CP_AIR * airflow)
        self.t_exh = t_out.mean(axis=1)
        dimm_ss = t_in + (self.dimm_base + self.dimm_load * u) / (
            self.health ** C.AIRFLOW_HEALTH_EXP * speed ** C.FAN_SPEED_EXP)
        self.t_dimm += (dimm_ss - self.t_dimm) * dt / C.TAU_DIMM_MIN
        t_ssd = t_in + (C.SSD_BASE_RISE_C + C.SSD_LOAD_RISE_C * u) / speed ** C.FAN_SPEED_EXP
        self.td_room += (td_out - C.DEHUMID_OFFSET_C - self.td_room) * dt / C.TAU_HUMIDITY_MIN
        self.speed = speed
        rows = np.arange(C.N_RACKS) // C.RACKS_PER_ROW
        row_breach = np.array([self.breach[rows == k].max() > 0 for k in range(rows.max() + 1)])
        dp = C.DP_NOMINAL_PA - C.DP_BREACH_DROP_PA * row_breach[rows]
        return {
            "t_sup": self.t_sup, "t_in": t_in, "t_out": t_out, "t_dimm": self.t_dimm.copy(),
            "t_ssd": t_ssd, "p_it_w": p_it, "p_fan_w": p_fan, "speed": speed,
            "td_room": self.td_room, "dp_rack": dp,
        }


def read_sensors(truth, rng, drift_offset, leak_racks):
    """What the monitoring system can actually see (noise, rounding, drift)."""
    t_in = truth["t_in"]
    R = t_in.shape[0]
    return {
        # --- Layer 1: server BMC via Redfish (integer inlet, 0.25 degC DIMM resolution)
        "bmc_inlet": np.round(t_in + rng.normal(0, 0.3, t_in.shape)),
        "bmc_dimm": np.round((truth["t_dimm"] + rng.normal(0, 0.2, t_in.shape)) * 4) / 4,
        "bmc_ssd": np.round(truth["t_ssd"]),
        "bmc_power_w": truth["p_it_w"] + truth["p_fan_w"],
        "bmc_fan_speed": truth["speed"],
        # --- Layer 2: MemSense nodes
        "node_in_bottom": t_in[:, 0] + rng.normal(0, 0.1, R),
        "node_in_top": t_in[:, -1] + rng.normal(0, 0.1, R) + drift_offset,
        "node_out": truth["t_out"].mean(axis=1) + rng.normal(0, 0.1, R),
        "node_dewpoint": truth["td_room"] + rng.normal(0, 0.2, R),
        "node_dp_pa": truth["dp_rack"] + rng.normal(0, 0.2, R),
        "node_leak": leak_racks.copy(),
        # --- cooling plant
        "supply_air": truth["t_sup"] + rng.normal(0, 0.1),
    }
