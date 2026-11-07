import hashlib, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from wad18 import *
import settle as S

W = lambda n: n * WAD
CASH, DEBT, EQ, ASSET = "CASH", "SENIOR_DEBT", "EQUITY", "ACQUIRED_ASSETS"


def snap(e):
    return (dict(e.bal), e.ev, e.height, e.head, list(e.journal), list(e.chain), e.state)


def cap_up(e, equity=2000000000):
    return e.post([("D", "SL1", CASH, W(equity)), ("C", "SL1", EQ, W(equity))])


def borrow(e, amt):
    return e.post([("D", "SL1", CASH, amt), ("C", "SL1", DEBT, amt)])


def repay(e, amt):
    return e.post([("D", "SL1", DEBT, amt), ("C", "SL1", CASH, amt)])


class TestConstantsAndMath(unittest.TestCase):
    def test_parameters(self):
        self.assertEqual(S.EV_BASELINE, 3000000000 * 10 ** 18)
        self.assertEqual(S.CAP, 450000000000000000)
        self.assertEqual(S.BREAKER, 480000000000000000)
        self.assertEqual(S.MAX_POSTINGS, 1024)
        self.assertEqual((S.ACTIVE, S.RESTRICTED, S.FROZEN, S.HALTED), ("ACTIVE", "RESTRICTED", "FROZEN", "HALTED"))
        self.assertEqual(S.CHART["SENIOR_DEBT"], "L")

    def test_classify_boundaries_baseline(self):
        ev = S.EV_BASELINE
        cap, brk = W(1350000000), W(1440000000)
        self.assertEqual(S.classify(cap, ev), S.ACTIVE)
        self.assertEqual(S.classify(cap + 1, ev), S.RESTRICTED)
        self.assertEqual(S.classify(brk, ev), S.RESTRICTED)
        self.assertEqual(S.classify(brk + 1, ev), S.FROZEN)
        self.assertEqual(S.classify(0, ev), S.ACTIVE)

    def test_two_decision_paths_agree_at_boundaries(self):
        for ev in (3000000000 * WAD, 3000000000 * WAD - 1, 7, 10 ** 18, 999999999999999999, 123456789012345678901):
            for ratio in (S.CAP, S.BREAKER):
                b = ratio * ev // WAD
                for debt in (b - 2, b - 1, b, b + 1, b + 2, 0, ev):
                    if debt < 0:
                        continue
                    self.assertEqual(S.classify(debt, ev), S.classify_b(debt, ev), (ev, ratio, debt))

    def test_leverage_helpers(self):
        self.assertEqual(S.leverage_up(1, 3), 333333333333333334)
        self.assertEqual(S.leverage_up(0, 5), 0)
        self.assertEqual(S.leverage_up(1, 0), MAXV)
        self.assertEqual(S.leverage_up(-5, 0), MAXV)
        self.assertEqual(S.leverage_up(0, 0), MAXV)
        self.assertEqual(S.leverage_up(1, -1), MAXV)
        self.assertTrue(S.exceeds(0, 0, S.CAP))
        self.assertTrue(S.exceeds(0, -1, S.CAP))
        self.assertFalse(S.exceeds(0, 1, S.CAP))
        self.assertFalse(S.exceeds(45, 100, 450000000000000000))
        self.assertTrue(S.exceeds(46, 100, 450000000000000000))
        self.assertFalse(S.exceeds(45, 100, 450000000000000000))

    def test_deleveraging(self):
        self.assertTrue(S.deleveraging(45, 100, 45, 100))
        self.assertTrue(S.deleveraging(45, 100, 90, 200))
        self.assertTrue(S.deleveraging(45, 100, 44, 100))
        self.assertTrue(S.deleveraging(45, 100, 45, 101))
        self.assertFalse(S.deleveraging(45, 100, 46, 100))
        self.assertFalse(S.deleveraging(45, 100, 45, 99))
        self.assertFalse(S.deleveraging(450000000000000001, 10 ** 18, 450000000000000002, 10 ** 18))


class TestPredicates(unittest.TestCase):
    def test_invariant_reason(self):
        self.assertIsNone(S.invariant_reason({}))
        self.assertIsNone(S.invariant_reason({("S", CASH): 0, ("S", DEBT): 0}))
        self.assertIsNone(S.invariant_reason({("S", CASH): 5, ("S", DEBT): -5, ("S", EQ): -1}))
        self.assertEqual(S.invariant_reason({("S", CASH): -1}), "NEGATIVE_ASSET")
        self.assertEqual(S.invariant_reason({("S", "DUE_FROM"): -1}), "NEGATIVE_ASSET")
        self.assertEqual(S.invariant_reason({("S", DEBT): 1}), "NEGATIVE_DEBT")
        self.assertEqual(S.invariant_reason({("S", EQ): -5, ("S", "DUE_TO"): 3}), None)
        self.assertEqual(S.invariant_reason({("S", CASH): MAXV + 1}), "OVERFLOW")
        self.assertEqual(S.invariant_reason({("S", EQ): -MAXV - 1}), "OVERFLOW")
        self.assertIsNone(S.invariant_reason({("S", CASH): MAXV}))

    def test_conserved(self):
        self.assertTrue(S.conserved({}))
        self.assertTrue(S.conserved({("A", CASH): 5, ("A", EQ): -5, ("B", CASH): 2, ("B", DEBT): -2}))
        self.assertFalse(S.conserved({("A", CASH): 5, ("B", EQ): -5}))
        self.assertFalse(S.conserved({("A", CASH): 5, ("A", EQ): -4}))
        self.assertFalse(S.conserved({("A", CASH): 5}))
        self.assertFalse(S.conserved({("A", CASH): 5, ("A", EQ): -5, ("B", CASH): 1, ("C", EQ): -1}))

    def test_well_formed_and_debt(self):
        self.assertTrue(S.well_formed({}))
        self.assertTrue(S.well_formed({("A", CASH): 1}))
        for bad in (None, [], {"x": 1}, {("A",): 1}, {("A", "B", "C"): 1}, {("A", CASH): 1.0}, {("A", CASH): True}):
            self.assertFalse(S.well_formed(bad), repr(bad))
        self.assertEqual(S.debt_of({("A", DEBT): -7, ("B", DEBT): -3, ("A", CASH): 10}), 10)
        self.assertEqual(S.debt_of({}), 0)


class TestParsing(unittest.TestCase):
    def test_reasons(self):
        ok = ("D", "SL1", CASH, 5)
        self.assertEqual(S.parse_postings([ok]), ((ok,), None))
        self.assertEqual(S.parse_postings((list(ok),)), ((ok,), None))
        self.assertEqual(S.parse_postings([("D", "SL1", CASH, MAXV)])[1], None)
        cases = [
            (None, "BAD_STRUCTURE"), ("x", "BAD_STRUCTURE"), ([], "BAD_STRUCTURE"), ({}, "BAD_STRUCTURE"),
            ([ok] * 1025, "BAD_STRUCTURE"), ([5], "BAD_STRUCTURE"), (["abcd"], "BAD_STRUCTURE"),
            ([("D", "SL1", CASH)], "BAD_STRUCTURE"), ([("D", "SL1", CASH, 5, 6)], "BAD_STRUCTURE"),
            ([("X", "SL1", CASH, 5)], "BAD_STRUCTURE"), ([(1, "SL1", CASH, 5)], "BAD_STRUCTURE"),
            ([("D", "", CASH, 5)], "BAD_STRUCTURE"), ([("D", 7, CASH, 5)], "BAD_STRUCTURE"),
            ([("D", "SL1", 9, 5)], "BAD_STRUCTURE"), ([("D", "SL1", "NOPE", 5)], "UNKNOWN_ACCOUNT"),
            ([("D", "SL1", CASH, 0)], "BAD_AMOUNT"), ([("D", "SL1", CASH, -1)], "BAD_AMOUNT"),
            ([("D", "SL1", CASH, MAXV + 1)], "BAD_AMOUNT"), ([("D", "SL1", CASH, 5.0)], "NON_INTEGER_INPUT"),
            ([("D", "SL1", CASH, True)], "NON_INTEGER_INPUT"), ([("D", "SL1", CASH, "5")], "NON_INTEGER_INPUT"),
        ]
        for post, why in cases:
            self.assertEqual(S.parse_postings(post), (None, why), repr(post))
        self.assertEqual(S.parse_postings([ok] * 1024)[1], None)

    def test_first_error_wins(self):
        self.assertEqual(S.parse_postings([("D", "SL1", CASH, 5), ("D", "SL1", "NOPE", 5.5)])[1], "UNKNOWN_ACCOUNT")

    def test_unbalanced_sub(self):
        self.assertIsNone(S.unbalanced_sub([("D", "A", CASH, 5), ("C", "A", EQ, 5)]))
        self.assertEqual(S.unbalanced_sub([("D", "A", CASH, 5), ("C", "B", EQ, 5)]), "A")
        self.assertEqual(S.unbalanced_sub([("D", "B", CASH, 5), ("C", "A", EQ, 5)]), "A")
        self.assertEqual(S.unbalanced_sub([("D", "A", CASH, 5), ("C", "A", EQ, 4)]), "A")
        self.assertIsNone(S.unbalanced_sub([("D", "A", CASH, 5), ("D", "A", CASH, 5), ("C", "A", EQ, 10)]))


class TestEngine(unittest.TestCase):
    def test_cap_boundary_exact(self):
        e = S.Engine()
        self.assertEqual(cap_up(e)["status"], "COMMITTED")
        self.assertEqual(borrow(e, W(1350000000))["status"], "COMMITTED")
        self.assertEqual(e.state, S.ACTIVE)
        before = snap(e)
        r = borrow(e, 1)
        self.assertEqual((r["status"], r["reason"]), ("REJECTED", "CAP_BREACH"))
        self.assertEqual(snap(e), before)
        self.assertEqual(e.debt, W(1350000000))

    def test_restricted_semantics(self):
        e = S.Engine()
        cap_up(e); borrow(e, W(1350000000))
        self.assertEqual(e.mark_ev(W(2900000000))["status"], "COMMITTED")
        self.assertEqual(e.state, S.RESTRICTED)
        self.assertEqual(borrow(e, 1)["reason"], "CAP_BREACH")
        r = e.post([("D", "SL1", ASSET, W(100)), ("C", "SL1", CASH, W(100))])
        self.assertEqual((r["status"], e.state), ("COMMITTED", S.RESTRICTED))
        r = repay(e, W(20000000))
        self.assertEqual((r["status"], e.state), ("COMMITTED", S.RESTRICTED))
        self.assertEqual(repay(e, W(40000000))["status"], "COMMITTED")
        self.assertEqual(e.state, S.ACTIVE)

    def test_ev_raising_acquisition_is_deleveraging(self):
        e = S.Engine()
        cap_up(e); borrow(e, W(1350000000)); e.mark_ev(W(2900000000))
        self.assertEqual(e.state, S.RESTRICTED)
        r = e.post([("D", "SL1", ASSET, W(100)), ("C", "SL1", CASH, W(100))], ev=W(3100000000))
        self.assertEqual((r["status"], e.state, e.ev), ("COMMITTED", S.ACTIVE, W(3100000000)))

    def test_breaker_exact_48(self):
        e = S.Engine()
        cap_up(e); borrow(e, W(1200000000))
        self.assertEqual(e.mark_ev(W(2500000000))["status"], "COMMITTED")
        self.assertEqual(e.state, S.RESTRICTED)
        e.mark_ev(W(2500000000) - 1)
        self.assertEqual(e.state, S.FROZEN)

    def test_frozen_semantics(self):
        e = S.Engine()
        cap_up(e); borrow(e, W(1350000000)); e.mark_ev(W(2800000000))
        self.assertEqual(e.state, S.FROZEN)
        before = snap(e)
        self.assertEqual(borrow(e, 1)["reason"], "FROZEN")
        self.assertEqual(snap(e), before)
        r = e.mark_ev(W(10000000000))
        self.assertEqual((r["status"], e.state), ("COMMITTED", S.FROZEN))
        r = e.audit_unfreeze()
        self.assertEqual((r["status"], e.state), ("UNFROZEN", S.ACTIVE))
        self.assertEqual(e.audit_unfreeze()["reason"], "NOT_FROZEN")

    def test_still_frozen_paths(self):
        e = S.Engine()
        cap_up(e); borrow(e, W(1350000000)); e.mark_ev(W(2800000000))
        h = e.height
        r = e.audit_unfreeze()
        self.assertEqual((r["status"], r["reason"], e.state, e.height), ("STILL_FROZEN", "AUDIT", S.FROZEN, h + 1))
        r = e.audit_unfreeze([("D", "SL1", DEBT, 1), ("C", "SL1", CASH, 1)])
        self.assertEqual((r["status"], r["reason"], e.state), ("STILL_FROZEN", "REMEDY", S.FROZEN))
        r = e.audit_unfreeze([("D", "SL1", DEBT, W(40000000)), ("C", "SL1", CASH, W(40000000))])
        self.assertEqual((r["status"], e.state), ("UNFROZEN", S.RESTRICTED))

    def test_remediation_rejections(self):
        e = S.Engine()
        cap_up(e); borrow(e, W(1350000000)); e.mark_ev(W(2800000000))
        before = snap(e)
        self.assertEqual(e.audit_unfreeze([("D", "SL1", CASH, 1), ("C", "SL1", DEBT, 1)])["reason"], "CAP_BREACH")
        self.assertEqual(e.audit_unfreeze([("D", "SL1", DEBT, 5), ("C", "SL2", CASH, 5)])["reason"], "UNBALANCED")
        self.assertEqual(e.audit_unfreeze([("D", "SL1", DEBT, 5.0), ("C", "SL1", CASH, 5)])["reason"], "NON_INTEGER_INPUT")
        self.assertEqual(e.audit_unfreeze("junk")["reason"], "BAD_STRUCTURE")
        self.assertEqual(snap(e), before)
        self.assertEqual(e.state, S.FROZEN)

    def test_invariant_rejections(self):
        e = S.Engine()
        cap_up(e, 10)
        before = snap(e)
        r = e.post([("D", "SL1", ASSET, W(11)), ("C", "SL1", CASH, W(11))])
        self.assertEqual(r["reason"], "NEGATIVE_ASSET")
        r = repay(e, 1)
        self.assertEqual(r["reason"], "NEGATIVE_DEBT")
        self.assertEqual(snap(e), before)
        e2 = S.Engine()
        e2.post([("D", "SL1", CASH, MAXV), ("C", "SL1", EQ, MAXV)])
        r = e2.post([("D", "SL1", CASH, 1), ("C", "SL1", EQ, 1)])
        self.assertEqual(r["reason"], "OVERFLOW")

    def test_ev_validation(self):
        e = S.Engine()
        cap_up(e)
        for bad in (0, -1, True, 1.5, "3", None, MAXV + 1):
            r = e.post([("D", "SL1", CASH, 5), ("C", "SL1", EQ, 5)], ev=bad) if bad is not None else None
            if r is not None:
                self.assertEqual(r["reason"], "EV_INVALID", repr(bad))
            self.assertEqual(e.mark_ev(bad)["reason"], "EV_INVALID", repr(bad))
        self.assertEqual(e.mark_ev(MAXV)["status"], "COMMITTED")
        self.assertEqual(e.mark_ev(1)["status"], "COMMITTED")

    def test_sub_ledger_conservation(self):
        e = S.Engine()
        cap_up(e)
        before = snap(e)
        r = e.post([("D", "SL1", "DUE_FROM", 5), ("C", "SL2", "DUE_TO", 5)])
        self.assertEqual(r["reason"], "UNBALANCED")
        self.assertEqual(snap(e), before)
        r = e.post([("D", "SL1", "DUE_FROM", W(5)), ("C", "SL1", CASH, W(5)), ("D", "SL2", CASH, W(5)), ("C", "SL2", "DUE_TO", W(5))])
        self.assertEqual(r["status"], "COMMITTED")
        self.assertTrue(S.conserved(e.bal))
        self.assertEqual(e.bal[("SL2", CASH)], W(5))

    def test_zero_balances_dropped(self):
        e = S.Engine()
        cap_up(e)
        e.post([("D", "SL1", ASSET, W(1)), ("C", "SL1", CASH, W(1))])
        e.post([("D", "SL1", CASH, W(1)), ("C", "SL1", ASSET, W(1))])
        self.assertNotIn(("SL1", ASSET), e.bal)

    def test_invalid_genesis(self):
        for bad in (0, -1, 1.0, True, MAXV + 1):
            e = S.Engine(ev=bad)
            self.assertEqual((e.state, e.halt_reason), (S.HALTED, "BAD_GENESIS"))
            self.assertEqual(cap_up(e)["reason"], "HALTED")
            self.assertEqual(e.mark_ev(W(1))["reason"], "HALTED")
            self.assertEqual(e.audit_unfreeze()["reason"], "HALTED")
        self.assertEqual(S.Engine(ev=1).state, S.ACTIVE)
        self.assertEqual(S.Engine(ev=MAXV).state, S.ACTIVE)

    def test_stress_report_is_advisory(self):
        e = S.Engine()
        cap_up(e); borrow(e, W(500000000))
        before = snap(e)
        r = e.stress_report(W(2), W(1) // 5, W(1))
        self.assertEqual(snap(e), before)
        self.assertLess(r["stressed_ev"], e.ev)
        self.assertEqual(r["stressed_leverage_up"], S.leverage_up(e.debt, r["stressed_ev"]))
        self.assertFalse(r["breaker_exceeded"])
        r = e.stress_report(W(5), W(1) // 2, W(4))
        self.assertTrue(r["breaker_exceeded"])
        r = e.stress_report(-1, 0, 0)
        self.assertEqual(r["stressed_ev"], 0)
        self.assertTrue(r["breaker_exceeded"])


class TestChainAndLog(unittest.TestCase):
    def build(self):
        e = S.Engine()
        cap_up(e); borrow(e, W(1000000000)); e.mark_ev(W(2900000000))
        e.post([("D", "SL1", ASSET, W(5)), ("C", "SL1", CASH, W(5))])
        return e

    def test_canon_and_digest(self):
        self.assertEqual(S.canon(("TX", (("D", "SL1", CASH, 5),), None)), "TX:D.SL1.CASH.5:ev=-")
        self.assertEqual(S.canon(("TX", (("D", "SL1", CASH, 5), ("C", "SL1", EQ, 5)), 7)), "TX:D.SL1.CASH.5,C.SL1.EQUITY.5:ev=7")
        self.assertEqual(S.canon(("MARK", 9)), "MARK:9")
        self.assertEqual(S.canon(("AUDIT",)), "AUDIT")
        self.assertEqual(S.digest({}, 5, 0), hashlib.sha256(b"EV=5;H=0;").hexdigest())
        self.assertEqual(S.digest({("B", CASH): 2, ("A", EQ): -2}, 5, 3),
                         hashlib.sha256(b"EV=5;H=3;A/EQUITY=-2;B/CASH=2").hexdigest())
        g = "0" * 64
        self.assertEqual(S.chain_step(g, ("AUDIT",), "d"), hashlib.sha256(("%s|AUDIT|d" % g).encode()).hexdigest())

    def test_verify_chain_and_tamper(self):
        e = self.build()
        self.assertTrue(S.verify_chain(e))
        self.assertEqual(len(e.chain), 4)
        self.assertEqual(e.head, e.chain[-1])
        import copy
        for mutate in (
            lambda x: x.journal.__setitem__(0, ("TX", (("D", "SL1", CASH, W(2000000000) + 1), ("C", "SL1", EQ, W(2000000000) + 1)), None)),
            lambda x: x.chain.__setitem__(1, "f" * 64),
            lambda x: setattr(x, "ev", x.ev + 1),
            lambda x: x.chain.pop(),
            lambda x: setattr(x, "height", x.height + 1),
            lambda x: setattr(x, "head", "e" * 64),
            lambda x: x.bal.__setitem__(("SL1", CASH), x.bal[("SL1", CASH)] + 1),
            lambda x: x.journal.append(("AUDIT",)),
        ):
            t = copy.deepcopy(e)
            mutate(t)
            self.assertFalse(S.verify_chain(t))
        self.assertTrue(S.verify_chain(S.Engine()))

    def test_log(self):
        e = S.Engine()
        h0 = e.log_head
        cap_up(e)
        borrow(e, W(1350000000))
        borrow(e, 1)
        kinds = [k for k, d, h in e.log]
        self.assertEqual(kinds, ["COMMIT", "COMMIT", "REJECT"])
        self.assertEqual(e.log[2][1], "CAP_BREACH")
        self.assertEqual(e.log[0][1], "TX h=1 ACTIVE->ACTIVE")
        self.assertNotEqual(e.log_head, h0)
        self.assertEqual(e.log[-1][2], e.log_head)
        exp = hashlib.sha256(("%s|REJECT|CAP_BREACH" % e.log[1][2]).encode()).hexdigest()
        self.assertEqual(e.log[2][2], exp)

    def test_determinism(self):
        a, b = self.build(), self.build()
        self.assertEqual((a.head, a.log_head, a.bal), (b.head, b.log_head, b.bal))


if __name__ == "__main__":
    unittest.main()
