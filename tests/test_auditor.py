"""State Auditor Test Oracle: injects float drift, rounding errors, boundary violations and path faults,
and asserts every one is trapped (rejected or halted) with the engine state untouched."""
import os, sys, unittest
from decimal import Decimal
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from wad18 import *
import settle as S

W = lambda n: n * WAD
CASH, DEBT, EQ, ASSET = "CASH", "SENIOR_DEBT", "EQUITY", "ACQUIRED_ASSETS"


def snap(e):
    return (dict(e.bal), e.ev, e.height, e.head, list(e.journal), list(e.chain), e.state)


def fault_at(stage, fn):
    return lambda s, v: fn(v) if s == stage else v


def base(equity=2000000000, debt=0):
    e = S.Engine()
    e.post([("D", "SL1", CASH, W(equity)), ("C", "SL1", EQ, W(equity))])
    if debt:
        e.post([("D", "SL1", CASH, W(debt)), ("C", "SL1", DEBT, W(debt))])
    return e


TX_SMALL = [("D", "SL1", ASSET, W(5)), ("C", "SL1", CASH, W(5))]


class MyInt(int):
    pass


class TestFaultInjection(unittest.TestCase):
    def assert_halts(self, e, action, why):
        before = snap(e)
        r = action(e)
        self.assertEqual((r["status"], r["reason"], r["state"]), ("HALTED", "AUDIT:" + why, S.HALTED))
        self.assertEqual(e.halt_reason, "AUDIT:" + why)
        after = snap(e)
        self.assertEqual(after[:6], before[:6])  # rolled back: nothing committed
        self.assertEqual(e.post(TX_SMALL)["reason"], "HALTED")
        self.assertEqual(e.mark_ev(W(1))["reason"], "HALTED")
        self.assertEqual(e.audit_unfreeze()["reason"], "HALTED")
        self.assertEqual(snap(e)[:6], before[:6])
        self.assertTrue(S.verify_chain(e))

    def test_one_ulp_balance_corruption(self):
        e = base()
        e.fault = fault_at("A_BAL", lambda b: {**b, ("SL1", CASH): b[("SL1", CASH)] + 1})
        self.assert_halts(e, lambda x: x.post(TX_SMALL), "BALANCE_MISMATCH")

    def test_corruption_hits_every_entry_kind(self):
        for act in (lambda x: x.mark_ev(W(2900000000)),):
            e = base(debt=1000000000)
            e.fault = fault_at("A_BAL", lambda b: {**b, ("SL1", CASH): b[("SL1", CASH)] - 1})
            self.assert_halts(e, act, "BALANCE_MISMATCH")
        e = base(debt=1000000000)
        e.state = S.FROZEN
        e.fault = fault_at("A_BAL", lambda b: {**b, ("SL1", CASH): b[("SL1", CASH)] - 1})
        self.assert_halts(e, lambda x: x.audit_unfreeze(), "BALANCE_MISMATCH")

    def test_exactly_representable_float_is_still_trapped(self):
        e = S.Engine()
        e.post([("D", "SL1", CASH, 2 ** 60), ("C", "SL1", EQ, 2 ** 60)])
        e.fault = fault_at("A_BAL", lambda b: {k: float(v) for k, v in b.items()})
        self.assertEqual(float(2 ** 59), 2 ** 59)
        self.assert_halts(e, lambda x: x.post([("D", "SL1", ASSET, 2 ** 59), ("C", "SL1", CASH, 2 ** 59)]), "NON_INTEGER_STATE")

    def test_float_roundtrip_drift_is_trapped(self):
        e = base(equity=2000000000)
        e.fault = fault_at("A_BAL", lambda b: {k: int(float(v)) for k, v in b.items()})
        self.assert_halts(e, lambda x: x.post([("D", "SL1", ASSET, W(5) + 7), ("C", "SL1", CASH, W(5) + 7)]), "BALANCE_MISMATCH")

    def test_ev_faults(self):
        e = base(debt=1000000000)
        e.fault = fault_at("A_EV", lambda v: v + 1)
        self.assert_halts(e, lambda x: x.mark_ev(W(2900000000)), "EV_MISMATCH")
        e = base(debt=1000000000)
        e.fault = fault_at("A_EV", lambda v: float(v))
        self.assert_halts(e, lambda x: x.mark_ev(W(2900000000)), "NON_INTEGER_STATE")
        e = base(debt=1000000000)
        e.fault = fault_at("A_EV", lambda v: int(float(v)))
        self.assert_halts(e, lambda x: x.mark_ev(W(2900000000) + 1), "EV_MISMATCH")

    def test_debt_faults_hide_cap_breach(self):
        e = base(debt=1350000000)
        self.assertEqual(e.post([("D", "SL1", CASH, 1), ("C", "SL1", DEBT, 1)])["reason"], "CAP_BREACH")
        e.fault = fault_at("A_DEBT", lambda d: d - 1)
        self.assert_halts(e, lambda x: x.post([("D", "SL1", CASH, 1), ("C", "SL1", DEBT, 1)]), "DEBT_MISMATCH")
        e = base(debt=1350000000)
        e.fault = fault_at("A_DEBT", lambda d: float(d))
        self.assert_halts(e, lambda x: x.post(TX_SMALL), "NON_INTEGER_STATE")

    def test_balance_fault_hiding_breach(self):
        e = base(debt=1350000000)
        e.fault = fault_at("A_BAL", lambda b: dict(e.bal))
        self.assert_halts(e, lambda x: x.post([("D", "SL1", CASH, 1), ("C", "SL1", DEBT, 1)]), "BALANCE_MISMATCH")

    def test_decision_fault(self):
        e = base(debt=1350000000)
        e.fault = fault_at("A_CLASS", lambda c: S.ACTIVE)
        self.assert_halts(e, lambda x: x.mark_ev(W(2800000000)), "DECISION_MISMATCH")
        e = base(debt=1350000000)
        e.fault = fault_at("A_CLASS", lambda c: 5)
        self.assert_halts(e, lambda x: x.mark_ev(W(2800000000)), "DECISION_MISMATCH")

    def test_garbage_from_fault_hook_is_total(self):
        for stage, junk in (("A_BAL", None), ("A_BAL", [1]), ("A_DEBT", None), ("A_EV", "x")):
            e = base()
            e.fault = fault_at(stage, lambda v, j=junk: j)
            self.assert_halts(e, lambda x: x.post(TX_SMALL), "NON_INTEGER_STATE")

    def test_non_integer_key(self):
        e = base()
        e.fault = fault_at("A_BAL", lambda b: {**b, "weird": 5})
        self.assert_halts(e, lambda x: x.post(TX_SMALL), "NON_INTEGER_STATE")

    def test_conservation_defense_in_depth(self):
        e = base()
        entry = ("TX", (("D", "SL1", CASH, 5),), None)
        bal = dict(e.bal)
        bal[("SL1", CASH)] += 5
        self.assertEqual(e._audit(entry, bal, e.ev, e.debt, S.ACTIVE), "CONSERVATION_VIOLATION")
        self.assertIsNone(e._audit(("AUDIT",), dict(e.bal), e.ev, e.debt, S.ACTIVE))

    def test_clean_run_never_halts(self):
        e = base(debt=1000000000)
        e.fault = lambda s, v: v
        for i in range(5):
            self.assertEqual(e.post(TX_SMALL)["status"], "COMMITTED")
        self.assertEqual(e.state, S.ACTIVE)


class TestInputNeutralization(unittest.TestCase):
    def test_non_integer_amounts(self):
        bad = [0.1, 1e18, 1e27, 5.0, -0.0, float("nan"), float("inf"), -float("inf"), Decimal("5"), "5", b"5",
               True, False, None, [5], (5,), 5j, MyInt(5)]
        for b in bad:
            e = base()
            before = snap(e)
            r = e.post([("D", "SL1", CASH, b), ("C", "SL1", EQ, 5)])
            self.assertEqual((r["status"], r["reason"]), ("REJECTED", "NON_INTEGER_INPUT"), repr(b))
            self.assertEqual(snap(e), before)
            r = e.post([("D", "SL1", CASH, 5), ("C", "SL1", EQ, b)])
            self.assertEqual(r["reason"], "NON_INTEGER_INPUT", repr(b))
            self.assertEqual(snap(e), before)
            self.assertEqual(e.log[-1][:2], ("REJECT", "NON_INTEGER_INPUT"))

    def test_out_of_range_integers(self):
        for b in (0, -1, -(10 ** 30), MAXV + 1, 10 ** 60):
            e = base()
            before = snap(e)
            self.assertEqual(e.post([("D", "SL1", CASH, b), ("C", "SL1", EQ, 5)])["reason"], "BAD_AMOUNT", b)
            self.assertEqual(snap(e), before)

    def test_ev_inputs(self):
        for b in (0.5, 3e27, Decimal(5), "5", True, MyInt(5), -1, 0, MAXV + 1):
            e = base()
            before = snap(e)
            self.assertEqual(e.mark_ev(b)["reason"], "EV_INVALID", repr(b))
            self.assertEqual(e.post(TX_SMALL, ev=b)["reason"], "EV_INVALID", repr(b))
            self.assertEqual(snap(e), before)

    def test_float_hazards_documented(self):
        self.assertNotEqual(0.1 + 0.2, 0.3)
        acc = 0.0
        for _ in range(10):
            acc += 0.1
        self.assertNotEqual(acc, 1.0)
        self.assertNotEqual(int(float(WAD + 1)), WAD + 1)
        self.assertEqual(3 * WAD // 10, WAD // 10 + 2 * WAD // 10)
        cap = W(1350000000)
        self.assertEqual(float(cap), float(cap + 10 ** 9))
        e = base(debt=1350000000)
        before = snap(e)
        r = e.post([("D", "SL1", CASH, 10 ** 9), ("C", "SL1", DEBT, 10 ** 9)])
        self.assertEqual(r["reason"], "CAP_BREACH")
        self.assertEqual(snap(e), before)

    def test_float_state_never_reaches_ledger(self):
        e = base(debt=1000000000)
        e.mark_ev(W(2900000000))
        for v in list(e.bal.values()) + [e.ev, e.debt, e.height]:
            self.assertIs(type(v), int)


class Lcg:
    def __init__(self, seed):
        self.s = seed

    def next(self, n):
        self.s = (self.s * 6364136223846793005 + 1442695040888963407) % (1 << 64)
        return (self.s >> 33) % n


EVS = [W(2000000000), W(2500000000), W(2800000000), W(3000000000), W(3500000000)]


def fuzz_op(e, r):
    op = r.next(11)
    amt = W(1 + r.next(600000000))
    if op == 0:
        return "TX", e.post([("D", "SL1", CASH, amt // 3), ("C", "SL1", EQ, amt // 3)])
    if op == 1:
        return "TX", e.post([("D", "SL1", CASH, amt), ("C", "SL1", DEBT, amt)])
    if op == 2:
        return "TX", e.post([("D", "SL1", DEBT, amt), ("C", "SL1", CASH, amt)])
    if op == 3:
        return "TX", e.post([("D", "SL1", ASSET, amt), ("C", "SL1", CASH, amt)])
    if op == 4:
        return "TX", e.post([("D", "SL1", CASH, amt), ("C", "SL1", ASSET, amt)])
    if op in (5, 6):
        return "MARK", e.mark_ev(EVS[r.next(5)])
    if op == 7:
        return "TX", e.post([("D", "SL1", "DUE_FROM", amt), ("C", "SL1", CASH, amt),
                             ("D", "SL2", CASH, amt), ("C", "SL2", "DUE_TO", amt)])
    if op == 8:
        if r.next(2):
            return "AUD", e.audit_unfreeze()
        return "AUD", e.audit_unfreeze([("D", "SL1", DEBT, amt // 4), ("C", "SL1", CASH, amt // 4)])
    if op == 9:
        return "TX", e.post([("D", "SL1", ASSET, amt), ("C", "SL1", CASH, amt)], ev=EVS[r.next(5)])
    bad = [0.5, "x", None, -1, True][r.next(5)]
    return "BAD", e.post([("D", "SL1", CASH, bad), ("C", "SL1", EQ, 1)])


class TestFuzz(unittest.TestCase):
    def run_seed(self, seed, n=500):
        e = S.Engine()
        e.post([("D", "SL1", CASH, W(2500000000)), ("C", "SL1", EQ, W(2500000000))])
        r = Lcg(seed)
        seen_states, commits, rejects, unfrozen = set(), 0, 0, 0
        for i in range(n):
            before = snap(e)
            pre_debt, pre_ev, pre_state = e.debt, e.ev, e.state
            kind, res = fuzz_op(e, r)
            self.assertNotEqual(e.state, S.HALTED)
            self.assertTrue(S.conserved(e.bal))
            self.assertIsNone(S.invariant_reason(e.bal))
            seen_states.add(e.state)
            if res["status"] == "REJECTED":
                rejects += 1
                self.assertEqual(snap(e), before)
            else:
                commits += 1
                if res["status"] == "UNFROZEN":
                    unfrozen += 1
                if kind == "TX" and pre_state == S.RESTRICTED:
                    self.assertTrue(S.deleveraging(pre_debt, pre_ev, e.debt, e.ev))
            if e.state == S.ACTIVE:
                self.assertFalse(S.exceeds(e.debt, e.ev, S.CAP))
            elif e.state == S.RESTRICTED:
                self.assertTrue(S.exceeds(e.debt, e.ev, S.CAP))
                self.assertFalse(S.exceeds(e.debt, e.ev, S.BREAKER))
            if i % 50 == 0:
                self.assertTrue(S.verify_chain(e))
        self.assertTrue(S.verify_chain(e))
        return seen_states, commits, rejects, unfrozen, e

    def test_campaign(self):
        allstates, uf = set(), 0
        for seed in (1, 2, 3):
            st, commits, rejects, unfrozen, e = self.run_seed(seed)
            allstates |= st
            uf += unfrozen
            self.assertGreater(commits, 60)
            self.assertGreater(rejects, 60)
        self.assertEqual(allstates, {S.ACTIVE, S.RESTRICTED, S.FROZEN})
        self.assertGreater(uf, 0)

    def test_campaign_deterministic(self):
        a = self.run_seed(7, 200)[4]
        b = self.run_seed(7, 200)[4]
        self.assertEqual((a.head, a.log_head), (b.head, b.log_head))


if __name__ == "__main__":
    unittest.main()
