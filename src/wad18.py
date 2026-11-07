"""WAD18: exact 18-decimal fixed point on Python ints. No floats. All functions total."""
SCALE = 10 ** 18
WAD = SCALE
MAXV = (1 << 127) - 1
MINV = -MAXV


def sat(x):
    if x > MAXV:
        return MAXV
    if x < MINV:
        return MINV
    return x


def clamp(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def from_int(n):
    return sat(n * SCALE)


def from_decimal(s):
    """Parse a decimal string exactly (truncating past 18 places). Returns (value, ok)."""
    if not isinstance(s, str) or not s:
        return (0, False)
    neg = s[0] == "-"
    t = s[1:] if s[0] in "+-" else s
    if not t:
        return (0, False)
    ip, _, fp = t.partition(".")
    digits = ip + fp
    if not digits or any(c not in "0123456789" for c in digits):
        return (0, False)
    fp = (fp + "0" * 18)[:18]
    v = sat(int(ip or "0") * SCALE + int(fp))
    return (-v if neg else v, True)


def to_decimal(x):
    sign = "-" if x < 0 else ""
    a = -x if x < 0 else x
    return "%s%d.%018d" % (sign, a // SCALE, a % SCALE)


def mul_down(a, b):
    return sat((a * b) // SCALE)


def mul_up(a, b):
    return sat(-((-a * b) // SCALE))


def div_down(a, b):
    if b == 0:
        return MAXV if a >= 0 else MINV
    return sat((a * SCALE) // b)


def div_up(a, b):
    if b == 0:
        return MAXV if a >= 0 else MINV
    return sat(-((-a * SCALE) // b))


def isqrt_newton(n):
    """floor(sqrt(n)) by Newton-Raphson from an upper bound; strictly decreasing, hence terminating."""
    if n <= 0:
        return 0
    x = 1 << ((n.bit_length() + 1) // 2)
    while True:
        y = (x + n // x) // 2
        if y >= x:
            return x
        x = y


def sqrt_down(x):
    if x <= 0:
        return 0
    return isqrt_newton(x * SCALE)


def sqrt_up(x):
    if x <= 0:
        return 0
    n = x * SCALE
    r = isqrt_newton(n)
    return r if r * r == n else r + 1


def round_div(a, d):
    """Round-to-nearest (ties toward +inf) integer division, d > 0."""
    return (2 * a + d) // (2 * d)
