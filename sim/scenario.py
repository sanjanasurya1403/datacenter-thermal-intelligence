"""Weather, IT load and fault schedule for one simulated week."""
from dataclasses import dataclass, field
import numpy as np
from . import config as C


def make_weather(climate: str, steps: int = C.STEPS, humid_day: bool = True):
    """Outdoor dry bulb, dew point and wet bulb per minute (degC)."""
    mean, amp, td_normal = C.CLIMATES[climate]
    t = np.arange(steps) * C.DT_MIN / 60.0                     # hours
    t_db = mean + amp * np.sin(2 * np.pi * (t - 9) / 24)        # coolest ~03:00, warmest ~15:00
    td = np.full(steps, td_normal)
    if humid_day:
        day_h = t - 24 * C.HUMID_DAY
        bump = np.clip(np.minimum(day_h - 6, 22 - day_h) / 3, 0, 1)  # 06:00-22:00 with 3 h ramps
        td = td + bump * (C.HUMID_DAY_DEWPOINT_C - td_normal)
        t_db = np.maximum(t_db, td + 1.0)                       # rain: air near saturation
    td = np.minimum(td, t_db)
    t_wb = t_db - (t_db - td) / 3.0                             # "one-third rule" approximation
    return {"t_db": t_db, "td": td, "t_wb": t_wb}


def make_load(rng, steps: int = C.STEPS):
    """Per-server CPU utilisation u in [0.05, 0.98], shape (steps, racks, servers)."""
    R, H = C.N_RACKS, C.SERVERS_PER_RACK
    t = np.arange(steps) * C.DT_MIN / 60.0
    diurnal = 0.45 + 0.20 * np.sin(2 * np.pi * (t - 8) / 24)    # peak ~14:00
    base = np.broadcast_to(diurnal[:, None, None], (steps, R, H)).copy()
    base[:, C.HIGH_DENSITY_RACKS, :] += 0.15                    # AI racks run hotter
    # AR(1) per-server noise
    noise = np.zeros((steps, R, H))
    eps = rng.normal(0, 0.03, (steps, R, H))
    for k in range(1, steps):
        noise[k] = 0.97 * noise[k - 1] + eps[k]
    # batch jobs: random 1-3 h bursts on random racks
    for _ in range(25):
        r = rng.integers(R)
        s = rng.integers(steps - 200)
        d = rng.integers(60, 180)
        base[s:s + d, r, :] += 0.25
    return np.clip(base + noise, 0.05, 0.98)


@dataclass
class Fault:
    kind: str            # airflow | breach | leak | drift | humid
    start: int           # minute index
    rack: int
    server: int = -1     # -1 = rack/row level
    params: dict = field(default_factory=dict)
    detected_at: int = -1
    repaired_at: int = -1

    @property
    def active(self):
        return self.repaired_at < 0


def day_min(day, hour, minute=0):
    return int(day * 1440 + hour * 60 + minute)


def test_week_faults():
    """Scripted faults for the evaluation week (same for every controller)."""
    return [
        # Dust-clogged bezel / cable blocking airflow: health falls 1.0 -> 0.35 over 6 h.
        # BMC fan tach looks normal, so no standard alarm fires.
        Fault("airflow", day_min(1, 9), rack=7, server=8, params={"min_health": 0.35, "ramp_min": 360}),
        # Blanking panels left out after maintenance on two racks.
        Fault("breach", day_min(2, 14), rack=12, params={"racks": [12, 13]}),
        # Coolant leak under a rear-door heat exchanger manifold at 02:10.
        Fault("leak", day_min(4, 2, 10), rack=18),
        # Node inlet-top sensor on rack 5 drifts +0.02 degC/min.
        Fault("drift", day_min(5, 8), rack=5, params={"rate": 0.02}),
    ]


def random_faults(rng):
    """Random faults for the training week (forecaster must see disturbances)."""
    faults = []
    for _ in range(3):
        faults.append(Fault("airflow", int(rng.integers(500, C.STEPS - 1000)), rack=int(rng.integers(C.N_RACKS)),
                            server=int(rng.integers(C.SERVERS_PER_RACK)),
                            params={"min_health": float(rng.uniform(0.3, 0.6)), "ramp_min": int(rng.integers(60, 400))}))
    for _ in range(3):
        r = int(rng.integers(C.N_RACKS - 1))
        faults.append(Fault("breach", int(rng.integers(500, C.STEPS - 1000)), rack=r, params={"racks": [r, r + 1]}))
    return faults
