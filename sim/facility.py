"""Cooling plant energy and water for one minute."""
import numpy as np
from . import config as C


def plant_minute(it_kw, t_sup, t_db, t_wb):
    t_chw = t_sup - C.CHW_APPROACH_C
    free = float(np.clip((t_chw - (t_wb + C.ECON_APPROACH_C)) / C.ECON_RAMP_C, 0, 1))
    cop = C.COP_REF * (1 + C.COP_GAIN_PER_C * (t_chw - 15.0)) * (1 - C.COP_LOSS_PER_C_WB * (t_wb - 20.0))
    chiller_kw = it_kw * (1 - free) / cop
    aux_kw = it_kw * (C.PUMP_TOWER_FRAC + C.CRAH_FAN_FRAC)
    other_kw = it_kw * C.OTHER_LOSS_FRAC
    dry = float(np.clip((t_chw - (t_db + C.DRY_APPROACH_C)) / C.DRY_RAMP_C, 0, 1))
    heat_kw = it_kw + chiller_kw
    water_l = heat_kw * (C.DT_MIN / 60.0) * C.WATER_L_PER_KWH_HEAT * (1 - dry)
    return {
        "t_chw": t_chw, "free_frac": free, "cop": cop, "chiller_kw": chiller_kw,
        "cooling_kw": chiller_kw + aux_kw, "other_kw": other_kw,
        "facility_kw": it_kw + chiller_kw + aux_kw + other_kw, "water_l": water_l,
    }
