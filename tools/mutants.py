"""AST mutation suite. Systematically mutates comparison/arithmetic/boolean operators, integer
constants and booleans in src/*.py (one mutation at a time) and requires the test suite to fail.
Usage: mutants.py [--list] [--only FILE] ; exit 0 iff every non-equivalent mutant is killed."""
import ast, json, os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ["wad18.py", "hp.py", "mathw.py", "settle.py", "ledger.py"]
CMP = {ast.Lt: (ast.LtE, ast.Gt), ast.LtE: (ast.Lt, ast.Gt), ast.Gt: (ast.GtE, ast.Lt),
       ast.GtE: (ast.Gt, ast.Lt), ast.Eq: (ast.NotEq,), ast.NotEq: (ast.Eq,),
       ast.Is: (ast.IsNot,), ast.IsNot: (ast.Is,), ast.In: (ast.NotIn,), ast.NotIn: (ast.In,)}
BIN = {ast.Add: (ast.Sub,), ast.Sub: (ast.Add,), ast.Mult: (ast.Add,), ast.FloorDiv: (ast.Mult,),
       ast.Mod: (ast.Mult,), ast.Pow: (ast.Mult,), ast.LShift: (ast.RShift,), ast.RShift: (ast.LShift,)}


class Mutator(ast.NodeTransformer):
    def __init__(self, target):
        self.target, self.i, self.desc = target, -1, None

    def _hit(self, node, text):
        self.i += 1
        if self.i == self.target:
            self.desc = "L%d %s" % (node.lineno, text)
            return True
        return False

    def visit_Compare(self, node):
        self.generic_visit(node)
        for k, op in enumerate(node.ops):
            for new in CMP.get(type(op), ()):
                if self._hit(node, "%s->%s" % (type(op).__name__, new.__name__)):
                    node.ops[k] = new()
                    return node
        return node

    def visit_BinOp(self, node):
        self.generic_visit(node)
        for new in BIN.get(type(node.op), ()):
            if self._hit(node, "%s->%s" % (type(node.op).__name__, new.__name__)):
                node.op = new()
                return node
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        new = ast.Or if isinstance(node.op, ast.And) else ast.And
        if self._hit(node, "%s->%s" % (type(node.op).__name__, new.__name__)):
            node.op = new()
        return node

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        if isinstance(node.op, (ast.USub, ast.Not)) and self._hit(node, "drop %s" % type(node.op).__name__):
            return node.operand
        return node

    def visit_Constant(self, node):
        v = node.value
        if isinstance(v, bool):
            if self._hit(node, "%s->%s" % (v, not v)):
                node.value = not v
        elif isinstance(v, int):
            for nv in ([v + 1] + ([v - 1] if v > 0 else [])):
                if self._hit(node, "const %d->%d" % (v, nv)):
                    node.value = nv
                    return node
        return node


def count(fn):
    with open(os.path.join(ROOT, "src", fn)) as f:
        tree = ast.parse(f.read())
    m = Mutator(-1)
    m.visit(tree)
    return m.i + 1


def mutate(fn, idx):
    with open(os.path.join(ROOT, "src", fn)) as f:
        tree = ast.parse(f.read())
    m = Mutator(idx)
    tree = m.visit(tree)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n", m.desc


def killed(tmp, code, fn):
    with open(os.path.join(tmp, "src", fn), "w") as f:
        f.write(code)
    env = dict(os.environ, PYTHONWARNINGS="ignore", PYTHONDONTWRITEBYTECODE="1")
    try:
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-f", "-q"],
                           cwd=tmp, capture_output=True, text=True, timeout=3, env=env)
        return r.returncode != 0
    except subprocess.TimeoutExpired:
        return True


def load_equiv():
    p = os.path.join(ROOT, "tools", "equivalent_mutants.json")
    if not os.path.exists(p):
        return {}
    with open(p) as f:
        return json.load(f)


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    import time
    only = arg("--only")
    state_path = arg("--state")
    budget = int(arg("--budget", "0"))
    retest = "--retest" in sys.argv
    t0 = time.time()
    state = {}
    if state_path and os.path.exists(state_path):
        with open(state_path) as f:
            state = json.load(f)
    equiv = load_equiv()
    total = kills = 0
    survivors, documented = [], []
    incomplete = False
    with tempfile.TemporaryDirectory() as tmp:
        for d in ("src", "tests"):
            shutil.copytree(os.path.join(ROOT, d), os.path.join(tmp, d), ignore=shutil.ignore_patterns("__pycache__"))
        for fn in FILES:
            if only and fn != only:
                continue
            with open(os.path.join(ROOT, "src", fn)) as f:
                orig = f.read()
            for idx in range(count(fn)):
                code, desc = mutate(fn, idx)
                key = "%s #%03d %s" % (fn, idx, desc)
                total += 1
                if "--list" in sys.argv:
                    print(key)
                    continue
                prev = state.get(key)
                if prev == "killed" or (prev == "survived" and not retest):
                    res = prev
                elif budget and time.time() - t0 > budget:
                    incomplete = True
                    continue
                else:
                    res = "killed" if killed(tmp, code, fn) else "survived"
                    state[key] = res
                    if state_path:
                        with open(state_path, "w") as f:
                            json.dump(state, f)
                if res == "killed":
                    kills += 1
                elif key.split(" L")[0] in equiv:
                    documented.append(key)
                else:
                    survivors.append(key)
            with open(os.path.join(tmp, "src", fn), "w") as f:
                f.write(orig)
    for k in survivors:
        print("SURVIVED:", k)
    print("mutants=%d killed=%d equivalent_documented=%d survivors=%d%s" % (
        total, kills, len(documented), len(survivors), " INCOMPLETE" if incomplete else ""))
    return 2 if incomplete else (0 if not survivors else 1)


if __name__ == "__main__":
    sys.exit(main())
