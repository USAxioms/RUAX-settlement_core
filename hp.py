"""High-precision integer kernels at scale P = 10**90 (72 guard digits beyond WAD18). Integer-only."""
SCALE = 10 ** 18
P = 10 ** 90
K = P // SCALE
_ONE = 10 ** 100
_DROP = _ONE // P


def _atanh_inv(n):
    x = _ONE // n
    n2 = n * n
    total = x
    k = 1
    while x:
        x //= n2
        total += x // (2 * k + 1)
        k += 1
    return total


LN2 = (2 * _atanh_inv(3)) // _DROP
LN10 = (6 * _atanh_inv(3) + 2 * _atanh_inv(9)) // _DROP


def ln(x):
    """Natural log of x > 0 (scale P) at scale P. P.bit_length()==299 => m in [0.509P, 1.0185P)."""
    k = x.bit_length() - P.bit_length()
    m = x >> k if k >= 0 else x << (-k)
    if m < P:
        m <<= 1
        k -= 1
    z = (m - P) * P // (m + P)
    z2 = z * z // P
    term = z
    total = 0
    n = 1
    while term:
        total += term // n
        term = term * z2 // P
        n += 2
    return 2 * total + k * LN2


def exp(x):
    """e^x for x (scale P), |x| <= ~130 ln2; result at scale P. Reduction x = k ln2 + r, |r| <= ln2/2."""
    k = (x + LN2 // 2) // LN2
    r = x - k * LN2
    term = P
    total = P
    n = 1
    while term:
        term = term * r // P // n
        total += term
        n += 1
    return total << k if k >= 0 else total >> (-k)
