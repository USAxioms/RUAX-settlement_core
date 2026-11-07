import ast, os, sys, unittest
from math import isqrt
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "src")
sys.path.insert(0, SRC)
from wad18 import *

W = from_int


class TestWad(unittest.TestCase):
    def test_rounding_directions(self):
        self.assertEqual(mul_down(1, 1), 0)
        self.assertEqual(mul_up(1, 1), 1)
        self.assertEqual(div_down(WAD, 3 * WAD), 333333333333333333)
        self.assertEqual(div_up(WAD, 3 * WAD), 333333333333333334)
        self.assertEqual(mul_down(-1, 1), -1)
        self.assertEqual(mul_up(-1, 1), 0)

    def test_limits(self):
        self.assertEqual(MAXV, 2 ** 127 - 1)
        self.assertEqual(MINV, -(2 ** 127 - 1))
        self.assertEqual((SCALE, WAD), (10 ** 18, 10 ** 18))

    def test_round_div(self):
        self.assertEqual(round_div(5, 2), 3)
        self.assertEqual(round_div(-5, 2), -2)
        self.assertEqual(round_div(7, 2), 4)
        self.assertEqual(round_div(1, 3), 0)
        self.assertEqual(round_div(2, 3), 1)
        self.assertEqual(round_div(-2, 3), -1)
        self.assertEqual(round_div(-1, 3), 0)
        self.assertEqual(round_div(0, 7), 0)

    def test_totality(self):
        self.assertEqual(div_down(0, 0), MAXV)
        self.assertEqual(div_up(0, 0), MAXV)
        self.assertEqual(div_down(5, 0), MAXV)
        self.assertEqual(div_down(-5, 0), MINV)
        self.assertEqual(div_up(5, 0), MAXV)
        self.assertEqual(div_up(-5, 0), MINV)
        self.assertEqual(sqrt_down(-1), 0)
        self.assertEqual(sqrt_up(-1), 0)
        self.assertEqual(sat(MAXV + 1), MAXV)
        self.assertEqual(sat(MINV - 1), MINV)
        self.assertEqual(sat(MAXV), MAXV)
        self.assertEqual(sat(MINV), MINV)
        self.assertEqual(mul_down(MAXV, MAXV), MAXV)
        self.assertEqual(mul_up(MAXV, MAXV), MAXV)
        self.assertEqual(div_down(MAXV, 1), MAXV)
        self.assertEqual(div_up(MAXV, 1), MAXV)
        self.assertEqual(from_int(MAXV), MAXV)

    def test_newton_matches_isqrt(self):
        ns = list(range(0, 3000)) + [-5]
        for k in (6, 18, 36, 54, 100, 300):
            for d in (-2, -1, 0, 1, 2):
                ns.append(10 ** k + d)
        for r in (1, 2, 3, 10 ** 9, 10 ** 18 + 7, 2 ** 63 - 1, 2 ** 150 + 3, 3 ** 200):
            ns += [r * r - 1, r * r, r * r + 1]
        ns += [2 ** 1000, 2 ** 1000 - 1, 2 ** 1001 + 5]
        for n in ns:
            self.assertEqual(isqrt_newton(n), isqrt(n) if n > 0 else 0, n)

    def test_sqrt_wad(self):
        self.assertEqual(sqrt_down(W(4)), W(2))
        self.assertEqual(sqrt_down(W(2)), 1414213562373095048)
        self.assertEqual(sqrt_down(0), 0)
        self.assertEqual(sqrt_down(1), 10 ** 9)
        self.assertEqual(sqrt_up(W(4)), W(2))
        self.assertEqual(sqrt_up(W(2)), 1414213562373095049)
        self.assertEqual(sqrt_up(0), 0)
        self.assertEqual(sqrt_up(1), 10 ** 9)
        self.assertEqual(sqrt_up(2), 1414213563)
        for x in (3, 10 ** 17 + 1, W(7) + 5, 12345678901234567890123):
            self.assertLessEqual(sqrt_up(x) - sqrt_down(x), 1)
            self.assertGreaterEqual(sqrt_up(x) ** 2, x * SCALE)
            self.assertLessEqual(sqrt_down(x) ** 2, x * SCALE)

    def test_decimal(self):
        self.assertEqual(from_decimal("9.80665"), (9806650000000000000, True))
        self.assertEqual(from_decimal("-0.5"), (-WAD // 2, True))
        self.assertEqual(from_decimal("+2"), (W(2), True))
        self.assertEqual(from_decimal(".5"), (WAD // 2, True))
        self.assertEqual(from_decimal("7."), (W(7), True))
        self.assertEqual(from_decimal("1.0000000000000000019"), (WAD + 1, True))
        for bad in ["", "-", "+", ".", "1.2.3", "abc", "1e5", None, 5, "-.", "1 2"]:
            self.assertEqual(from_decimal(bad), (0, False))
        self.assertEqual(to_decimal(-WAD // 2), "-0.500000000000000000")
        self.assertEqual(to_decimal(W(12) + 5), "12.000000000000000005")
        self.assertEqual(to_decimal(0), "0.000000000000000000")

    def test_clamp(self):
        self.assertEqual(clamp(5, 0, 3), 3)
        self.assertEqual(clamp(-5, 0, 3), 0)
        self.assertEqual(clamp(2, 0, 3), 2)
        self.assertEqual(clamp(0, 0, 3), 0)
        self.assertEqual(clamp(3, 0, 3), 3)

    def test_no_floats_static(self):
        for fn in ["wad18.py", "hp.py", "mathw.py", "settle.py", "ledger.py"]:
            with open(os.path.join(SRC, fn)) as fh:
                tree = ast.parse(fh.read())
            for n in ast.walk(tree):
                if isinstance(n, ast.Constant):
                    self.assertNotIsInstance(n.value, float, fn)
                if isinstance(n, ast.BinOp):
                    self.assertNotIsInstance(n.op, ast.Div, fn)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                    self.assertNotIn(n.func.id, ("float", "isqrt"), fn)
                if isinstance(n, (ast.Import, ast.ImportFrom)):
                    mods = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module]
                    for m in mods:
                        self.assertNotIn(m, ("math", "decimal", "fractions", "random", "numpy"), fn)


if __name__ == "__main__":
    unittest.main()
