"""Deterministic MARUSC-2026 demo (PLACEHOLDER scenario). Output must be byte-identical on every platform."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from wad18 import WAD, to_decimal
import settle as S

W = lambda n: n * WAD
CASH, DEBT, EQ, ASSET = "CASH", "SENIOR_DEBT", "EQUITY", "ACQUIRED_ASSETS"


def line(o, label, e, r):
    lev = to_decimal(S.leverage_up(e.debt, e.ev))
    o.append("  %-34s -> %-10s %-22s state=%-10s h=%d lev=%s" % (label, r["status"], r["reason"], e.state, e.height, lev))


def main():
    o = ["[parameters] EV=%s CAP=%s BREAKER=%s" % (to_decimal(S.EV_BASELINE), to_decimal(S.CAP), to_decimal(S.BREAKER))]
    e = S.Engine()
    o.append("[settlement scenario]")
    line(o, "capitalize 2.0B equity", e, e.post([("D", "SL1", CASH, W(2000000000)), ("C", "SL1", EQ, W(2000000000))]))
    line(o, "borrow 1.2B senior debt", e, e.post([("D", "SL1", CASH, W(1200000000)), ("C", "SL1", DEBT, W(1200000000))]))
    line(o, "acquire 3.0B assets", e, e.post([("D", "SL1", ASSET, W(3000000000)), ("C", "SL1", CASH, W(3000000000))]))
    line(o, "intercompany SL1->SL2 100M", e, e.post([("D", "SL1", "DUE_FROM", W(100000000)), ("C", "SL1", CASH, W(100000000)),
                                                    ("D", "SL2", CASH, W(100000000)), ("C", "SL2", "DUE_TO", W(100000000))]))
    line(o, "borrow 150M (debt = 45.000...%)", e, e.post([("D", "SL1", CASH, W(150000000)), ("C", "SL1", DEBT, W(150000000))]))
    line(o, "borrow +1 ulp", e, e.post([("D", "SL1", CASH, 1), ("C", "SL1", DEBT, 1)]))
    line(o, "float amount 1350000000.5", e, e.post([("D", "SL1", CASH, 1350000000.5), ("C", "SL1", DEBT, 1350000000.5)]))
    line(o, "unbalanced across sub-ledgers", e, e.post([("D", "SL1", CASH, 5), ("C", "SL2", EQ, 5)]))
    line(o, "overspend cash", e, e.post([("D", "SL1", ASSET, W(9000000000)), ("C", "SL1", CASH, W(9000000000))]))
    line(o, "mark EV 2.9B", e, e.mark_ev(W(2900000000)))
    line(o, "borrow +1 ulp while restricted", e, e.post([("D", "SL1", CASH, 1), ("C", "SL1", DEBT, 1)]))
    line(o, "mark EV 2.8B (breaker)", e, e.mark_ev(W(2800000000)))
    line(o, "post while frozen", e, e.post([("D", "SL1", CASH, 1), ("C", "SL1", EQ, 1)]))
    line(o, "audit_unfreeze (no remediation)", e, e.audit_unfreeze())
    line(o, "audit_unfreeze + repay 200M", e, e.audit_unfreeze([("D", "SL1", DEBT, W(200000000)), ("C", "SL1", CASH, W(200000000))]))
    st = e.stress_report(W(2), W(1) // 5, W(1))
    o.append("[stress] z=2 sigma=0.2 t=1: stressed_ev=%s stressed_lev=%s breaker_exceeded=%s" % (
        to_decimal(st["stressed_ev"]), to_decimal(st["stressed_leverage_up"]), st["breaker_exceeded"]))
    o.append("[ledger] height=%d chain_ok=%s conserved=%s" % (e.height, S.verify_chain(e), S.conserved(e.bal)))
    o.append("  head=%s" % e.head)
    o.append("  log_head=%s" % e.log_head)
    o.append("[fault injection] path-A balance +1 ulp during a valid block")
    f = S.Engine()
    f.post([("D", "SL1", CASH, W(10)), ("C", "SL1", EQ, W(10))])
    snapshot = (dict(f.bal), f.height, f.head)
    f.fault = lambda stage, v: ({**v, ("SL1", CASH): v[("SL1", CASH)] + 1} if stage == "A_BAL" else v)
    r = f.post([("D", "SL1", ASSET, W(1)), ("C", "SL1", CASH, W(1))])
    o.append("  result=%s reason=%s state=%s rolled_back=%s" % (r["status"], r["reason"], f.state, snapshot == (f.bal, f.height, f.head)))
    r = f.post([("D", "SL1", ASSET, W(1)), ("C", "SL1", CASH, W(1))])
    o.append("  next block: %s %s" % (r["status"], r["reason"]))
    return "\n".join(o) + "\n"


if __name__ == "__main__":
    sys.stdout.write(main())
