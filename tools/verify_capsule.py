"""Verify the capsule. Fast by default; --full adds the (~4 min) mutation suite."""
import hashlib, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import ledger as L


def sh(args):
    env = dict(os.environ, PYTHONWARNINGS="ignore", PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable] + args, cwd=ROOT, capture_output=True, text=True, env=env)


def main():
    ok = True
    r = L.verify(os.path.join(ROOT, "ledger", "ledger.jsonl"))
    print("ledger chain:", "OK" if r else "FAIL"); ok = ok and r
    t = sh(["-m", "unittest", "discover", "-s", "tests", "-q"])
    print("unit tests:", "OK" if t.returncode == 0 else "FAIL"); ok = ok and t.returncode == 0
    d = sh(["demo.py"])
    with open(os.path.join(ROOT, "demo_expected.txt")) as f:
        same = d.stdout == f.read()
    print("demo parity:", "OK" if same else "FAIL"); ok = ok and same
    mf = os.path.join(ROOT, "MANIFEST.sha256")
    if os.path.exists(mf):
        bad = 0
        with open(mf) as f:
            for line in f:
                h, _, p = line.rstrip("\n").partition("  ")
                with open(os.path.join(ROOT, p), "rb") as g:
                    bad += hashlib.sha256(g.read()).hexdigest() != h
        print("manifest:", "OK" if bad == 0 else "FAIL (%d)" % bad); ok = ok and bad == 0
    if "--full" in sys.argv:
        m = sh(["tools/mutants.py"])
        print("mutation:", m.stdout.strip().splitlines()[-1]); ok = ok and m.returncode == 0
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
