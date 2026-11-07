"""CLI for the ledger: python3 tools/ledger_cli.py verify | append KIND JSON  (run from capsule root)."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import ledger

PATH = "ledger/ledger.jsonl"
if len(sys.argv) == 2 and sys.argv[1] == "verify":
    print("OK" if ledger.verify(PATH) else "CORRUPT")
elif len(sys.argv) == 4 and sys.argv[1] == "append":
    e = ledger.append(PATH, sys.argv[2], json.loads(sys.argv[3]))
    print(e["hash"] if e else "REJECTED")
