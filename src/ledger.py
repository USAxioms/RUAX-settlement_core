"""Cognitive State Ledger: append-only SHA-256 hash chain. No floats, no wall clock."""
import hashlib
import json
import os

GENESIS = "0" * 64


def _canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash(seq, kind, payload, prev):
    body = _canon({"seq": seq, "kind": kind, "payload": payload, "prev": prev})
    return hashlib.sha256(body.encode("ascii")).hexdigest()


def _has_float(o):
    if isinstance(o, float):
        return True
    if isinstance(o, dict):
        return any(_has_float(v) for v in o.values())
    if isinstance(o, (list, tuple)):
        return any(_has_float(v) for v in o)
    return False


def read(path):
    if not os.path.exists(path):
        return []
    out = []
    try:
        with open(path, "r", encoding="ascii") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    except ValueError:
        return None
    return out


def verify(path):
    entries = read(path)
    if entries is None:
        return False
    prev = GENESIS
    for i, e in enumerate(entries):
        try:
            if e["seq"] != i or e["prev"] != prev:
                return False
            if _hash(i, e["kind"], e["payload"], prev) != e["hash"]:
                return False
        except (KeyError, TypeError):
            return False
        prev = e["hash"]
    return True


def append(path, kind, payload):
    """Returns the new entry, or None if the ledger is corrupt or payload has floats."""
    if _has_float(payload) or not verify(path):
        return None
    entries = read(path)
    prev = entries[-1]["hash"] if entries else GENESIS
    seq = len(entries)
    entry = {"seq": seq, "kind": kind, "payload": payload, "prev": prev,
             "hash": _hash(seq, kind, payload, prev)}
    with open(path, "a", encoding="ascii", newline="\n") as f:
        f.write(_canon(entry) + "\n")
    return entry


def query(path, kind=None):
    entries = read(path) or []
    return [e for e in entries if kind is None or e["kind"] == kind]
