# WAD18 MARUSC-2026 Settlement Capsule v3.0.0 (reference model)
`python3 tools/verify_capsule.py [--full]` (Python 3.9+, stdlib only). `python3 demo.py` prints the deterministic scenario. See `docs/whitepaper.md`.
Layout: `src/` (wad18, hp, mathw, settle, ledger), `tests/` (incl. `test_auditor.py`, the State Auditor Test Oracle), `tools/` (mutants, build, verify, ledger_cli), `ledger/ledger.jsonl`, `demo.py` + `demo_expected.txt`, `MANIFEST.sha256`.
Reference model only: not air-gapped, not certified, not financial or legal advice. EV is an external input; chart of accounts and state policy are placeholders.
