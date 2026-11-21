"""Generate a training week (different seed, random setpoints, random faults) and fit the models."""
import pickle
from pathlib import Path
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
from . import config as C
from .memsense import RandomWalkController, fit_ahi_coefficients, FEATURES
from .runner import run_week
from .scenario import random_faults
from .datacenter import DataHall

MODEL_PATH = Path(__file__).parent / "models" / "memsense_models.pkl"


def train(seed=101, climate="bengaluru_nov"):
    rng = np.random.default_rng(seed)
    hd = DataHall(np.random.default_rng(0)).hd
    ctrl = RandomWalkController(hd, rng)
    print("Simulating training week (random setpoints + random faults)...")
    out = run_week(ctrl, random_faults(rng), climate=climate, seed=seed, collect_training=True)
    X, m = out["train_X"], out["train_m"]
    H = C.FORECAST_HORIZON_MIN
    sp = out["ts"]["setpoint"].to_numpy()
    T = len(sp)
    # Target: "what will the hottest inlet be in 10 min if the setpoint is held?"
    # Keep only windows where the setpoint did not change during the horizon.
    idx = np.array([t for t in range(20, T - H) if np.all(sp[t:t + H + 1] == sp[t])])
    Xs = X[idx].reshape(-1, X.shape[2])
    y = (m[idx + H] - m[idx]).reshape(-1)
    split = int(len(idx) * 0.8) * X.shape[1]      # time-ordered split: last 20% of the week held out
    model = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.08, max_leaf_nodes=31, random_state=0)
    model.fit(Xs[:split], y[:split])
    yt, pred = y[split:], model.predict(Xs[split:])
    mae = mean_absolute_error(yt, pred)
    mae_persist = mean_absolute_error(yt, np.zeros_like(pred))
    big = np.abs(yt) > 0.5
    mae_tr = mean_absolute_error(yt[big], pred[big])
    mae_tr_naive = mean_absolute_error(yt[big], np.zeros(big.sum()))
    print(f"Forecaster (10-min-ahead rack max inlet), held-out data:")
    print(f"  all samples  : MAE {mae:.3f} C  vs naive 'no change' {mae_persist:.3f} C")
    print(f"  transients   : MAE {mae_tr:.3f} C  vs naive {mae_tr_naive:.3f} C  ({big.mean()*100:.1f}% of samples)")
    model.fit(Xs, y)
    coef = fit_ahi_coefficients(*out["ahi"])
    print(f"AHI expected-rise fit: standard a={coef[False][0]:.2f} b={coef[False][1]:.2f}; "
          f"high-density a={coef[True][0]:.2f} b={coef[True][1]:.2f}")
    MODEL_PATH.parent.mkdir(exist_ok=True)
    with open(MODEL_PATH, "wb") as fh:
        pickle.dump({"model": model, "ahi_coef": coef, "features": FEATURES,
                     "mae": mae, "mae_naive": mae_persist,
                     "mae_transient": mae_tr, "mae_transient_naive": mae_tr_naive}, fh)
    return {"mae": mae, "mae_naive": mae_persist}


if __name__ == "__main__":
    train()
