"""Deterministic capsule builder: writes MANIFEST.sha256 and a byte-reproducible ZIP."""
import hashlib, os, sys, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "wad18_marusc_2026_capsule_v3.0.0"


def files():
    out = []
    for d, dirs, fs in os.walk(ROOT):
        dirs[:] = sorted(x for x in dirs if x != "__pycache__")
        for f in sorted(fs):
            p = os.path.relpath(os.path.join(d, f), ROOT).replace(os.sep, "/")
            if p != "MANIFEST.sha256" and not p.endswith(".pyc") and not p.endswith(".zip"):
                out.append(p)
    return sorted(out)


def main(dest):
    fl = files()
    with open(os.path.join(ROOT, "MANIFEST.sha256"), "w", newline="\n") as m:
        for p in fl:
            with open(os.path.join(ROOT, p), "rb") as f:
                m.write("%s  %s\n" % (hashlib.sha256(f.read()).hexdigest(), p))
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in fl + ["MANIFEST.sha256"]:
            zi = zipfile.ZipInfo("%s/%s" % (NAME, p), date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            with open(os.path.join(ROOT, p), "rb") as f:
                z.writestr(zi, f.read())
    with open(dest, "rb") as f:
        print(hashlib.sha256(f.read()).hexdigest())


if __name__ == "__main__":
    main(sys.argv[1])
