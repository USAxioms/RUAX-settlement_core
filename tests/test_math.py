import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fractions import Fraction as Fr
from wad18 import *
import hp, mathw as M
import oracle as O

SCALE = 10 ** 18
W = from_int
FACT = [1]
for _i in range(1, 100):
    FACT.append(FACT[-1] * _i)
D = lambda s: from_decimal(s)[0]


class TestConstants(unittest.TestCase):
    def test_ln_constants(self):
        self.assertEqual(hp.LN2 // 10 ** 50, int("6931471805599453094172321214581765680755"))
        self.assertEqual(hp.LN10 // 10 ** 50, int("23025850929940456840179914546843642076011"))
        self.assertEqual((hp.P, hp.K), (10 ** 90, 10 ** 72))

    def test_ln_normalization_assumption(self):
        self.assertEqual(hp.P.bit_length(), 299)
        self.assertTrue(2 ** 298 * 2 > hp.P > 2 ** 298)


class TestLog(unittest.TestCase):
    def test_known(self):
        self.assertEqual(M.ln_wad(WAD), 0)
        self.assertEqual(M.log10_wad(W(10)), WAD)
        self.assertEqual(M.log10_wad(W(100)), W(2))
        self.assertEqual(M.log10_wad(WAD // 10), -WAD)
        self.assertEqual(M.ln_wad(W(2)), 693147180559945309)
        self.assertEqual(M.log10_wad(1), -18 * WAD)

    def test_vs_oracle(self):
        for a in ["0.5", "0.77", "1.0000000000000001", "1.3", "1.99", "2"]:
            w = D(a)
            self.assertEqual(M.ln_wad(w), O.rnd(O.ln(Fr(w, SCALE))), a)
        for k in (-5, -1, 1, 7, 60):
            w = W(1) * 2 ** k if k >= 0 else WAD // 2 ** (-k)
            self.assertEqual(M.ln_wad(w), O.rnd(k * O.ln(Fr(2))), k)
        self.assertEqual(M.ln_wad(1), O.rnd(-18 * (3 * O.ln(Fr(2)) + O.ln(Fr(5, 4)))))

    def test_totality(self):
        for x in (0, -1, MINV):
            self.assertEqual(M.ln_wad(x), MINV)
            self.assertEqual(M.log10_wad(x), MINV)


class TestExp(unittest.TestCase):
    def test_known(self):
        self.assertEqual(M.exp_wad(0), WAD)
        self.assertEqual(M.exp_wad(WAD), 2718281828459045235)
        self.assertEqual(M.exp_wad(-45 * WAD), 0)
        self.assertEqual(M.exp_wad(-1000 * WAD), 0)
        self.assertEqual(M.exp_wad(47 * WAD), MAXV)
        self.assertEqual(M.exp_wad(D("46.6")), MAXV)
        self.assertEqual(M.exp_wad(MAXV), MAXV)
        self.assertEqual(M.exp_wad(MINV), 0)

    def test_vs_independent_oracle(self):
        for a in ["1", "-1", "0.5", "-0.5", "2.7", "-7.3", "10", "-20", "30.5", "-40", "46", "-44.9",
                  "0.000000000000000001", "-0.000000000000000001", "0.693147180559945309", "-0.693147180559945309"]:
            w = D(a)
            self.assertEqual(M.exp_wad(w), O.exp_round(w), a)

    def test_ln_exp_roundtrip(self):
        for a in ["0.5", "1.3", "7.7", "100"]:
            w = D(a)
            self.assertLessEqual(abs(M.exp_wad(M.ln_wad(w)) - w) // (w // 10 ** 12 + 1), 2)


class TestStress(unittest.TestCase):
    def test_identities(self):
        ev = 3000000000 * WAD
        self.assertEqual(M.stress_ev(ev, 0, D("0.2"), W(1)), ev)
        self.assertEqual(M.stress_ev(ev, W(2), 0, W(1)), ev)
        self.assertEqual(M.stress_ev(ev, W(2), D("0.2"), 0), ev)
        for bad in ((0, W(2), WAD, WAD), (-1, W(2), WAD, WAD), (ev, -1, WAD, WAD), (ev, W(2), -1, WAD), (ev, W(2), WAD, -1)):
            self.assertEqual(M.stress_ev(*bad), 0)
        self.assertEqual(M.stress_ev(ev, W(100), W(1), W(1)), 0)
        self.assertEqual(M.stress_ev(ev, W(90), W(1), W(1)), 0)
        self.assertGreater(M.stress_ev(ev, W(60), W(1), W(1)), 0)
        self.assertEqual(M.stress_ev(ev, W(65), W(1), W(1)), 0)
        self.assertGreater(M.stress_ev(MAXV, W(88), W(1), W(1)), 0)

    def test_one_ulp_ev(self):
        self.assertEqual(M.stress_ev(1, 0, D("0.2"), W(1)), 1)
        self.assertEqual(M.stress_ev(1, W(1), W(1), W(1)), 0)
        self.assertEqual(M.stress_ev(5, 0, 0, 0), 5)

    def test_value_and_bias(self):
        ev = 3000000000 * WAD
        got = M.stress_ev(ev, W(2), D("0.2"), W(1))
        exact = ev * O.exp_scaled(-D("0.4")) // 10 ** 140
        self.assertEqual(got, exact)
        got = M.stress_ev(ev, W(2), D("0.2"), W(2))
        # exact exponent 0.4*sqrt(2); computed value must be <= exact and within 5e-18 relative
        xe = Fr(2, 5) * Fr(1414213562373095048801688724, 10 ** 27)
        ex = ev * (Fr(1) / sum(xe ** n / FACT[n] for n in range(80)))
        self.assertLessEqual(got, int(ex))
        self.assertLessEqual((int(ex) - got) * 10 ** 18, 5 * int(ex))

    def test_monotone(self):
        ev = 3000000000 * WAD
        a = M.stress_ev(ev, W(2), D("0.2"), W(1))
        b = M.stress_ev(ev, W(2), D("0.3"), W(1))
        c = M.stress_ev(ev, W(3), D("0.3"), W(1))
        d = M.stress_ev(ev, W(3), D("0.3"), W(2))
        self.assertTrue(ev > a > b > c > d > 0)


if __name__ == "__main__":
    unittest.main()
