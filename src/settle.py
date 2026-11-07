"""MARUSC-2026 reference model: WAD18 double-entry settlement engine.
Integer-only. Single-process deterministic state machine. All parameters are PLACEHOLDERS except as given in the directive.
State changes only at commit; a rejected or halted block leaves state untouched (rollback by construction)."""
import hashlib
from wad18 import WAD, MAXV, div_up
import mathw

EV_BASELINE = 3000000000 * WAD
CAP = 450000000000000000
BREAKER = 480000000000000000
MAX_POSTINGS = 1024
CHART = {"CASH": "A", "ACQUIRED_ASSETS": "A", "DUE_FROM": "A",
         "SENIOR_DEBT": "L", "DUE_TO": "L", "EQUITY": "E"}
ACTIVE, RESTRICTED, FROZEN, HALTED = "ACTIVE", "RESTRICTED", "FROZEN", "HALTED"
GENESIS = "0" * 64


def is_ev(x):
    return type(x) is int and 0 < x <= MAXV


def exceeds(debt, ev, ratio):
    """Exact: debt/ev > ratio/WAD, by integer cross-multiplication. ev <= 0 is a breach (fail-safe)."""
    return ev <= 0 or debt * WAD > ratio * ev


def leverage_up(debt, ev):
    """Leverage as WAD ratio rounded up (display / second audit path)."""
    return MAXV if ev <= 0 else div_up(debt, ev)


def classify(debt, ev):
    if exceeds(debt, ev, BREAKER):
        return FROZEN
    if exceeds(debt, ev, CAP):
        return RESTRICTED
    return ACTIVE


def classify_b(debt, ev):
    """Independent decision path: compares the rounded-up ratio against the thresholds."""
    lev = leverage_up(debt, ev)
    if lev > BREAKER:
        return FROZEN
    if lev > CAP:
        return RESTRICTED
    return ACTIVE


def deleveraging(d0, e0, d1, e1):
    """d1/e1 <= d0/e0 exactly."""
    return d1 * e0 <= d0 * e1


def parse_postings(postings):
    """Returns (clean tuple, None) or (None, reason). Only exact ints are accepted as amounts."""
    if type(postings) not in (list, tuple) or not postings or len(postings) > MAX_POSTINGS:
        return None, "BAD_STRUCTURE"
    out = []
    for p in postings:
        if type(p) not in (list, tuple) or len(p) != 4:
            return None, "BAD_STRUCTURE"
        side, sub, acct, amt = p
        if type(side) is not str or side not in ("D", "C"):
            return None, "BAD_STRUCTURE"
        if type(sub) is not str or not sub or type(acct) is not str:
            return None, "BAD_STRUCTURE"
        if acct not in CHART:
            return None, "UNKNOWN_ACCOUNT"
        if type(amt) is not int:
            return None, "NON_INTEGER_INPUT"
        if not 0 < amt <= MAXV:
            return None, "BAD_AMOUNT"
        out.append((side, sub, acct, amt))
    return tuple(out), None


def unbalanced_sub(postings):
    net = {}
    for side, sub, acct, amt in postings:
        net[sub] = net.get(sub, 0) + (amt if side == "D" else -amt)
    for sub in sorted(net):
        if net[sub] != 0:
            return sub
    return None


def debt_of(bal):
    return -sum(v for (sub, acct), v in bal.items() if acct == "SENIOR_DEBT")


def well_formed(bal):
    return (type(bal) is dict and all(type(k) is tuple and len(k) == 2 and type(v) is int
                                       for k, v in bal.items()))


def invariant_reason(bal):
    for (sub, acct), v in sorted(bal.items()):
        if abs(v) > MAXV:
            return "OVERFLOW"
        if CHART[acct] == "A" and v < 0:
            return "NEGATIVE_ASSET"
        if acct == "SENIOR_DEBT" and v > 0:
            return "NEGATIVE_DEBT"
    return None


def digest(bal, ev, height):
    body = "EV=%d;H=%d;" % (ev, height) + ";".join(
        "%s/%s=%d" % (sub, acct, v) for (sub, acct), v in sorted(bal.items()))
    return hashlib.sha256(body.encode("ascii")).hexdigest()


def canon(entry):
    if entry[0] == "TX":
        body = ",".join("%s.%s.%s.%d" % p for p in entry[1])
        return "TX:%s:ev=%s" % (body, "-" if entry[2] is None else str(entry[2]))
    if entry[0] == "MARK":
        return "MARK:%d" % entry[1]
    return "AUDIT"


def replay(journal, ev0):
    """Path B: rebuild state from genesis with a different algorithm (separate debit/credit lists, sorted sums)."""
    debits, credits = {}, {}
    ev = ev0
    for entry in journal:
        if entry[0] == "TX":
            for side, sub, acct, amt in entry[1]:
                (debits if side == "D" else credits).setdefault((sub, acct), []).append(amt)
            if entry[2] is not None:
                ev = entry[2]
        elif entry[0] == "MARK":
            ev = entry[1]
    bal = {}
    for k in set(debits) | set(credits):
        v = sum(sorted(debits.get(k, []))) - sum(sorted(credits.get(k, [])))
        if v != 0:
            bal[k] = v
    return bal, ev


def conserved(bal):
    per = {}
    for (sub, acct), v in bal.items():
        per[sub] = per.get(sub, 0) + v
    return all(v == 0 for v in per.values()) and sum(bal.values()) == 0


def chain_step(prev, entry, dig):
    return hashlib.sha256(("%s|%s|%s" % (prev, canon(entry), dig)).encode("ascii")).hexdigest()


def verify_chain(e):
    """Recompute the full commit chain and final state from the journal; True iff identical."""
    prev = GENESIS
    for i, entry in enumerate(e.journal):
        bal, ev = replay(e.journal[:i + 1], e.ev0)
        prev = chain_step(prev, entry, digest(bal, ev, i + 1))
        if i < len(e.chain) and e.chain[i] != prev:
            return False
    bal, ev = replay(e.journal, e.ev0)
    return (len(e.chain) == len(e.journal) and bal == e.bal and ev == e.ev
            and e.height == len(e.journal) and (e.head == (e.chain[-1] if e.chain else GENESIS)))


class Engine:
    def __init__(self, ev=EV_BASELINE, fault=None):
        self.ev0 = ev
        self.ev = ev
        self.bal = {}
        self.journal = []
        self.chain = []
        self.head = GENESIS
        self.height = 0
        self.log = []
        self.log_head = GENESIS
        self.fault = fault
        self.state = ACTIVE
        self.halt_reason = None
        if not is_ev(ev):
            self._halt("BAD_GENESIS")

    @property
    def debt(self):
        return debt_of(self.bal)

    def _note(self, kind, detail):
        self.log_head = hashlib.sha256(("%s|%s|%s" % (self.log_head, kind, detail)).encode("ascii")).hexdigest()
        self.log.append((kind, detail, self.log_head))

    def _result(self, status, reason):
        return {"status": status, "reason": reason, "state": self.state, "height": self.height}

    def _reject(self, reason):
        self._note("REJECT", reason)
        return self._result("REJECTED", reason)

    def _halt(self, reason):
        self.state = HALTED
        self.halt_reason = reason
        self._note("HALT", reason)

    def _f(self, stage, value):
        return self.fault(stage, value) if self.fault is not None else value

    def _audit(self, entry, bal_a, ev_a, debt_a, cls_a):
        """Dual-path audit of the candidate. Returns None if clean, else a discrepancy code."""
        if not well_formed(bal_a) or type(ev_a) is not int or type(debt_a) is not int:
            return "NON_INTEGER_STATE"
        bal_b, ev_b = replay(self.journal + [entry], self.ev0)
        if bal_a != bal_b:
            return "BALANCE_MISMATCH"
        if ev_a != ev_b:
            return "EV_MISMATCH"
        debt_b = -sum(v for (sub, acct), v in bal_b.items() if acct == "SENIOR_DEBT")
        if debt_a != debt_b:
            return "DEBT_MISMATCH"
        if cls_a != classify_b(debt_b, ev_b):
            return "DECISION_MISMATCH"
        if not conserved(bal_a) or not conserved(bal_b):
            return "CONSERVATION_VIOLATION"
        return None

    def _process(self, entry, postings, ev1, kind):
        bal_a = dict(self.bal)
        for side, sub, acct, amt in postings:
            k = (sub, acct)
            bal_a[k] = bal_a.get(k, 0) + (amt if side == "D" else -amt)
        bal_a = {k: v for k, v in bal_a.items() if v != 0}
        bal_a = self._f("A_BAL", bal_a)
        ev_a = self._f("A_EV", ev1)
        debt_a = self._f("A_DEBT", debt_of(bal_a) if well_formed(bal_a) else 0)
        cls_a = self._f("A_CLASS", classify(debt_a, ev_a) if type(debt_a) is int and type(ev_a) is int else FROZEN)
        why = self._audit(entry, bal_a, ev_a, debt_a, cls_a)
        if why is not None:
            self._halt("AUDIT:" + why)
            return self._result("HALTED", "AUDIT:" + why)
        why = invariant_reason(bal_a)
        if why is not None:
            return self._reject(why)
        if kind in ("TX", "REMEDY") and exceeds(debt_a, ev_a, CAP) \
                and not deleveraging(self.debt, self.ev, debt_a, ev_a):
            return self._reject("CAP_BREACH")
        self.journal.append(entry)
        self.bal = bal_a
        self.ev = ev_a
        self.height += 1
        self.head = chain_step(self.head, entry, digest(bal_a, ev_a, self.height))
        self.chain.append(self.head)
        prior = self.state
        new = cls_a
        if prior == FROZEN:
            new = FROZEN
        self.state = new
        self._note("COMMIT", "%s h=%d %s->%s" % (kind, self.height, prior, new))
        return self._result("COMMITTED", kind)

    def post(self, postings, ev=None):
        if self.state == HALTED:
            return self._reject("HALTED")
        if self.state == FROZEN:
            return self._reject("FROZEN")
        clean, why = parse_postings(postings)
        if why is not None:
            return self._reject(why)
        if ev is not None and not is_ev(ev):
            return self._reject("EV_INVALID")
        if unbalanced_sub(clean) is not None:
            return self._reject("UNBALANCED")
        return self._process(("TX", clean, ev), clean, self.ev if ev is None else ev, "TX")

    def mark_ev(self, ev):
        if self.state == HALTED:
            return self._reject("HALTED")
        if not is_ev(ev):
            return self._reject("EV_INVALID")
        return self._process(("MARK", ev), (), ev, "MARK")

    def audit_unfreeze(self, postings=None):
        if self.state == HALTED:
            return self._reject("HALTED")
        if self.state != FROZEN:
            return self._reject("NOT_FROZEN")
        if postings is None:
            res = self._process(("AUDIT",), (), self.ev, "AUDIT")
        else:
            clean, why = parse_postings(postings)
            if why is not None:
                return self._reject(why)
            if unbalanced_sub(clean) is not None:
                return self._reject("UNBALANCED")
            res = self._process(("TX", clean, None), clean, self.ev, "REMEDY")
        if res["status"] != "COMMITTED":
            return res
        new = classify(self.debt, self.ev)
        if new == FROZEN:
            self.state = FROZEN
            self._note("STILL_FROZEN", "h=%d" % self.height)
            return self._result("STILL_FROZEN", res["reason"])
        self.state = new
        self._note("UNFROZEN", "h=%d ->%s" % (self.height, new))
        return self._result("UNFROZEN", res["reason"])

    def stress_report(self, z, sigma, t):
        """Advisory only: does not change state."""
        s = mathw.stress_ev(self.ev, z, sigma, t)
        return {"stressed_ev": s, "stressed_leverage_up": leverage_up(self.debt, s),
                "breaker_exceeded": exceeds(self.debt, s, BREAKER)}
