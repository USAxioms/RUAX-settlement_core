"""WAD18 ln/log10/exp and stress valuation. Results are the 10^-18 rounding of a 10^-90 computation."""
from wad18 import WAD, MAXV, MINV, sat, round_div, mul_up, sqrt_up
import hp

K = hp.K


def ln_wad(x):
    if x <= 0:
        return MINV
    return sat(round_div(hp.ln(x * K), K))


def log10_wad(x):
    if x <= 0:
        return MINV
    return sat(round_div(hp.ln(x * K) * hp.P // hp.LN10, K))


def exp_wad(x):
    if x >= 47 * WAD:
        return MAXV
    if x <= -45 * WAD:
        return 0
    return sat(round_div(hp.exp(x * K), K))


def stress_ev(ev, z, sigma, t):
    """EV * exp(-z * sigma * sqrt(t)). Exponent rounded UP, result floored: biased low (conservative).
    Invalid (non-positive ev, negative parameter) returns 0, the most conservative value."""
    if ev <= 0 or z < 0 or sigma < 0 or t < 0:
        return 0
    x = mul_up(mul_up(z, sigma), sqrt_up(t))
    if x >= 90 * WAD:
        return 0
    return sat(ev * hp.exp(-x * K) // hp.P)
