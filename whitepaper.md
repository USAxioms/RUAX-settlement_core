# MARUSC-2026: A Deterministic WAD18 Settlement and Leverage-Control Reference Model
**Technical specification, capsule v3.0.0.** Integer-only double-entry settlement engine with an exact leverage cap, a circuit breaker, and a dual-path recompute-and-compare auditor.

**Document control.** Reference model and specification of behavior. Not investment, legal or accounting advice. Not audited, certified or reviewed by any third party; no endorsement or relationship with any institution is stated or implied. Every parameter not given in the originating directive is a **placeholder**.

## 1. Abstract
Institutional ledgers fail in a few recurring ways: arithmetic that differs between machines or runs, postings that do not balance, limit checks that are ambiguous at the boundary, a single faulty computation that is silently committed, and audit trails that cannot be reproduced. MARUSC-2026 is a small deterministic state machine built to remove those particular failure classes by construction and to prove, by test, that injected faults are trapped. It uses exact integer arithmetic at 10¹⁸ scale (WAD18), compares leverage by integer cross-multiplication (no rounding), and commits a block only after an independent second computation path agrees bit for bit.

## 2. Scope and non-claims
| In scope | Not in scope (stated explicitly) |
|---|---|
| Arithmetic, conservation, leverage-limit and state-machine behavior; fault trapping; reproducible audit chain | Valuation of the enterprise (EV is an **external input**; a wrong EV is accepted as given), credit, market, liquidity and legal risk |
| Single-process deterministic reference model | Air-gapped hardware, network settlement, multi-node consensus ("HALT" is a local terminal state), key management, access control |
| Detection of divergence between two code paths | Common-mode faults: the same wrong input or the same specification error reaching both paths |
The model does not execute or authorize real transfers. Nothing here is a statement about the enforceability of any settlement.

## 3. Mathematical invariants
Notation: WAD = 10¹⁸. Amounts and balances are Python `int`. EV is the enterprise value, D the senior debt outstanding (credit balance of `SENIOR_DEBT` summed over sub-ledgers). CAP = 0.45·WAD, BREAKER = 0.48·WAD. Baseline EV = 3 000 000 000·WAD.

**I1 Exactness.** Ledger state changes use only integer addition, subtraction and comparison. No rounding occurs anywhere in the ledger path. Inputs must satisfy `type(x) is int` and 0 < x ≤ 2¹²⁷−1; floats, `Decimal`, strings, booleans and `int` subclasses are rejected before any arithmetic (`NON_INTEGER_INPUT`, `BAD_AMOUNT`). Any balance with |v| > 2¹²⁷−1 is rejected (`OVERFLOW`); the ledger never saturates silently.

**I2 Conservation.** A transaction is accepted only if debits equal credits *within every sub-ledger it touches* (not merely globally). Hence, by induction over committed blocks, the net of each sub-ledger is 0 and the global net is 0. Marks and audits do not touch balances. The auditor re-checks conservation on both paths.

**I3 Non-negativity.** Asset accounts (`CASH`, `ACQUIRED_ASSETS`, `DUE_FROM`) never hold a credit balance, and `SENIOR_DEBT` never holds a debit balance (`NEGATIVE_ASSET`, `NEGATIVE_DEBT`).

**I4 Leverage cap (exact).** The test "D/EV > r" is evaluated as `D·WAD > r·EV` over integers, so there is no rounding at the boundary: D = 0.45·EV exactly is permitted, D = 0.45·EV + 1 ulp is not. For EV = 3·10⁹ the cap is D = 1 350 000 000·WAD. A second, independent decision path compares `⌈D·WAD/EV⌉ > r`, which is equivalent because r is an integer (tested at ±2 ulp around both thresholds for six EV values).
*Theorem 1 (transactions cannot breach the cap).* A committed transaction (or remediation) satisfies either D′·WAD ≤ CAP·EV′, or D′·EV ≤ D·EV′ (leverage not increased). *Proof.* The pre-commit control rejects any transaction with D′/EV′ > CAP that is not non-increasing in leverage (`CAP_BREACH`). ∎ Consequently leverage can exceed CAP only through an EV mark, never through a transaction, and while above CAP no transaction can increase it.

**I5 Circuit breaker.** After every commit the state is recomputed. If D·WAD > BREAKER·EV (strict) the state becomes `FROZEN`. Exactly 48.000000000000000000% does not trip; one ulp of EV below the exact-48% value does (tested). `FROZEN` is sticky: marks are recorded but cannot unfreeze; only an explicit `audit_unfreeze` can, and it requires a clean dual-path audit.

**I6 Dual-path audit soundness.** For every candidate block, path A applies the postings incrementally to the balance map; path B rebuilds the state from genesis by replaying the full journal with a different algorithm (separate debit/credit lists, sorted sums) and takes the debt from those lists; the leverage decision on path B uses the rounded-up ratio. The block is committed only if both paths agree on balances, EV, debt, decision and conservation, and all values are exact `int`. Any difference ⇒ state `HALTED` with reason `AUDIT:<code>`, and nothing is committed. *Rollback is by construction*: state is mutated only in the final commit step. The audit runs before policy decisions, so a corrupted path A cannot influence an admit/reject decision.
*Limit.* Two code paths written by one team share the specification and the input. I6 detects divergence (hardware faults, memory corruption, logic regressions in one path), not common-mode error.

**I7 Atomicity and determinism.** There is no clock, randomness, floating point or I/O in the state transition. The same input sequence yields the same commit chain: each commit hash is SHA-256 over (previous hash, canonical block text, state digest). The reference scenario's head is pinned by a golden test and reproduced in `demo_expected.txt`. `verify_chain` recomputes the chain and final state from the journal and fails on any edit to a block, a hash, EV, height, head, or balances (tamper tests for each).

**I8 Totality.** Every public method returns a result record for any input; malformed input yields a `REJECTED` record with a reason code, and an invalid genesis yields `HALTED(BAD_GENESIS)`. Even malformed state returned by the fault-injection seam is trapped (a defect of exactly this kind was found by the injection suite and fixed).

## 4. State machine topology
```
          lev > 45%                 lev > 48%
 ACTIVE ─────────────▶ RESTRICTED ─────────────▶ FROZEN (sticky)
   ▲  ◀───── lev ≤ 45% ──────┘                      │
   │      (after any commit)                         │ audit_unfreeze: clean audit and
   │                                                 │ lev ≤ 48% ⇒ RESTRICTED, lev ≤ 45% ⇒ ACTIVE
   └─────────────────────────────────────────────────┘
 ACTIVE ──(mark makes lev > 48%)──▶ FROZEN      any state ──(audit divergence | bad genesis)──▶ HALTED (terminal)
```
| State | `post` (transaction) | `mark_ev` | `audit_unfreeze` |
|---|---|---|---|
| ACTIVE | admitted if post-leverage ≤ 45% | admitted | rejected (`NOT_FROZEN`) |
| RESTRICTED | admitted only if leverage does not increase | admitted | rejected |
| FROZEN | rejected (`FROZEN`) | admitted, stays FROZEN | optional remediation (must not increase leverage); commits an audit record |
| HALTED | rejected | rejected | rejected |
**Placeholder policy choices (not given in the directive):** the RESTRICTED band between 45% and 48%, deleveraging-only admission there, the sticky freeze, unfreeze at ≤ 48% (to RESTRICTED), and strict `>` triggers. They are one-line changes in `classify` and are covered by boundary tests.

## 5. Arithmetic primitives
- **Square root.** `isqrt_newton(n)`: integer Newton-Raphson from the upper bound 2^⌈bits/2⌉. For x > ⌊√n⌋ the update y = ⌊(x + ⌊n/x⌋)/2⌋ satisfies ⌊√n⌋ ≤ y < x, so the sequence strictly decreases and stops exactly at ⌊√n⌋. Tested equal to `math.isqrt` (used only as a test oracle) on more than 3 000 values including 10^k±2, r²±1 and 2^1000-scale inputs. `sqrt_down` / `sqrt_up` give directed WAD results.
- **ln, exp.** Computed at 10⁻⁹⁰ with integer series (ln: atanh form after normalization to [P, 2P); exp: reduction by ln 2) and rounded once to 10⁻¹⁸. **Deviation from the directive:** this replaces CORDIC; a CORDIC 1-ulp guarantee would need the same guard-digit analysis, and the series form is simpler to verify. Result error ≤ 0.5 ulp plus < 10⁻⁵⁰ ulp (hand analysis: series truncation < 100 units of 10⁻⁹⁰, reduction error k·10⁻⁹⁰ with k ≤ 130). Tested against exact-rational oracles (ln) and an independent unreduced-Taylor integer oracle at 10⁻¹⁴⁰ (exp) on 16 inputs spanning ±46, plus 40 + 6 golden 90-digit vectors.
- **Stress valuation.** EV_stress = ⌊EV·exp(−⌈z·σ⌉·⌈√t⌉)⌋ with exponent rounded up and result floored (biased low, i.e. conservative). It is advisory (`stress_report`) and does not change state. Each primitive meets its stated bound; the composite carries a relative error ≤ 5·10⁻¹⁸ against the exact formula (tested), i.e. about 10⁻⁹ currency units on a 3·10⁹ EV.
"Strict 1-ulp" therefore holds per primitive (exact for sums, comparisons and square-root floor; ≤ 0.5 ulp + ε for ln/exp), not as a blanket statement about every composite quantity.

## 6. State Auditor Test Oracle
`tests/test_auditor.py` injects faults and asserts each is trapped with the engine state untouched.
| Injection | Expected trap |
|---|---|
| ±1 ulp on a path-A balance, on mark / transaction / remediation | `HALTED AUDIT:BALANCE_MISMATCH`, no commit |
| Path-A values converted to `float` (exactly representable, e.g. 2⁵⁹, so `==` would pass) | `NON_INTEGER_STATE` (type check, not value check) |
| Float round-trip drift `int(float(v))` on balances or EV | `BALANCE_MISMATCH` / `EV_MISMATCH` |
| Debt reduced by 1 ulp to hide a cap breach; balance replaced to hide it | `DEBT_MISMATCH` / `BALANCE_MISMATCH` instead of a silent commit |
| Forced decision `ACTIVE` when the true class is `FROZEN` | `DECISION_MISMATCH` |
| Garbage or malformed path-A state (None, list, odd keys) | `NON_INTEGER_STATE`, no exception |
| Float, NaN, ±inf, Decimal, str, bytes, bool, None, complex, `int` subclass as amounts or EV | `NON_INTEGER_INPUT` / `EV_INVALID`, state byte-identical |
| 0, negative, > 2¹²⁷−1 amounts; unknown account; unbalanced per sub-ledger (globally balanced) | `BAD_AMOUNT`, `UNKNOWN_ACCOUNT`, `UNBALANCED` |
| Boundary: debt = cap ⇒ accepted; cap + 1 ulp (an amount floats cannot distinguish) ⇒ rejected; exact 48% no freeze; 48% + 1 ulp freeze | exact |
| Edits to journal, hash, EV, height, head, balances | `verify_chain` false |
| Deterministic fuzz: 3 seeds × 500 operations mixing valid, invalid, marks and unfreezes | conservation, non-negativity, state/classification consistency, no leverage increase while RESTRICTED, rejected ⇒ byte-identical state, chain verifies; ACTIVE, RESTRICTED and FROZEN are all visited |
The float hazards are shown, not asserted from folklore: `0.1+0.2 ≠ 0.3`, ten additions of 0.1 ≠ 1.0, `int(float(WAD+1)) ≠ WAD+1`, and `float(cap) == float(cap + 10⁹ ulp)` while the engine rejects that amount.

## 7. Systemic risk reduction model
The contribution is narrow and checkable: it removes specific failure classes from the settlement path and makes the remaining ones visible.
| Failure class | Control | Evidence | Residual risk |
|---|---|---|---|
| F1 Platform- or run-dependent arithmetic | Integer-only, no floats, no clock/randomness | static AST test; golden chain head | Python semantics assumed correct |
| F2 Unbalanced or partial postings | Per-sub-ledger Dr = Cr; atomic commit | I2 tests; fuzz | Chart of accounts is a placeholder |
| F3 Ambiguous limit at the boundary | Exact cross-multiplication; strict thresholds | boundary tests ±1 ulp | Threshold policy is an input |
| F4 Single-path computation fault committed silently | Dual-path audit before decision and commit; HALT | injection suite | Common-mode faults and bad inputs |
| F5 Contaminated inputs (floats, subclasses, out-of-range) | Exact-type gate | input tests | Upstream data quality (EV, amounts) |
| F6 Unreproducible audit trail | SHA-256 commit chain; full replay verification | tamper tests; golden head | Hash chain gives consistency, not authenticity: signatures and key custody are out of scope |
| F7 Leverage creep during stress | RESTRICTED admits deleveraging only; FROZEN halts flow | Theorem 1; state tests | Cap and breaker values are policy; EV marks are exogenous |
Not addressed: valuation error, counterparty and credit risk, liquidity, legal and regulatory treatment, operational security. No statistical risk-reduction figure is claimed; the evidence is test-based.

## 8. Verification evidence
- 76 unit and oracle tests (≈0.3 s). Independent oracles share no code with the implementation.
- AST mutation engine over all source modules: **518 mutants, 484 killed, 34 equivalent (each justified in `tools/equivalent_mutants.json`), 0 survivors.** First run left 45 survivors; analysis closed real test gaps (division-by-zero saturation, 1-ulp stress inputs, zero-balance invariants, cross-sub-ledger conservation, a discriminating `exp` reduction vector) and classified the rest as equivalent (boundary-equal returns, sign-symmetric zero tests, Newton initial-guess variants that change only iteration count, saturation guards whose cutoffs cannot change a result). Mutation testing shows sensitivity to those mutation classes; it does not prove correctness against reality.
- Development ledger: a hash-chained record (`ledger/ledger.jsonl`) carries the ground check, pre-execution plans and results from capsules v1–v3.

## 9. Reproduction
`python3 tools/verify_capsule.py [--full]`; `python3 demo.py` must equal `demo_expected.txt`; `python3 tools/build_capsule.py out.zip` rebuilds a byte-identical ZIP. The demo's final commit-chain head is `496b2d8a…921c` after 9 committed entries.

## 10. Open items
Real chart of accounts and sub-ledger topology; EV provenance and attestation; policy sign-off on RESTRICTED/FROZEN behavior; signatures, key custody and an independent second implementation to reduce common-mode risk; multi-node consensus and an actual air-gapped deployment path; machine-checked proofs of Theorem 1 and the audit-soundness argument; independent security and financial review before any use with real assets.
