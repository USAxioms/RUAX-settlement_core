import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import ledger as L


class TestLedger(unittest.TestCase):
    def test_chain(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "l.jsonl")
            self.assertTrue(L.verify(p))
            e0 = L.append(p, "A", {"x": "1"})
            e1 = L.append(p, "B", {"y": ["2"]})
            e2 = L.append(p, "C", {"z": "3"})
            self.assertEqual(e2["prev"], e1["hash"])
            self.assertEqual(e2["seq"], 2)
            self.assertEqual(e0["prev"], "0" * 64)
            self.assertEqual(e1["prev"], e0["hash"])
            self.assertEqual((e0["seq"], e1["seq"]), (0, 1))
            self.assertTrue(L.verify(p))
            self.assertEqual(len(L.query(p)), 3)
            self.assertEqual([e["kind"] for e in L.query(p, "B")], ["B"])
            self.assertEqual([e["kind"] for e in L.query(p, "C")], ["C"])
            self.assertIsNone(L.append(p, "C", {"f": 1.5}))
            self.assertIsNone(L.append(p, "C", {"f": [1.5]}))
            data = open(p).read()
            open(p, "w").write(data.replace('"x":"1"', '"x":"2"'))
            self.assertFalse(L.verify(p))
            self.assertIsNone(L.append(p, "D", {}))
            open(p, "w").write("not json\n")
            self.assertFalse(L.verify(p))
            open(p, "w").write("{}\n")
            self.assertFalse(L.verify(p))

    def test_field_tamper_and_key_order(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "l.jsonl")
            L.append(p, "A", {}); L.append(p, "B", {})
            rows = [json.loads(x) for x in open(p).read().splitlines()]
            for field, val in (("prev", "f" * 64), ("seq", 7)):
                bad = [dict(r) for r in rows]
                bad[1][field] = val
                with open(p, "w") as fh:
                    fh.write("\n".join(json.dumps(r) for r in bad) + "\n")
                self.assertFalse(L.verify(p), field)
            p1, p2 = os.path.join(d, "1"), os.path.join(d, "2")
            e1 = L.append(p1, "K", {"a": "1", "b": "2"})
            e2 = L.append(p2, "K", {"b": "2", "a": "1"})
            self.assertEqual(e1["hash"], e2["hash"])

    def test_non_ascii_payload_is_total(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "l.jsonl")
            e = L.append(p, "K", {"x": "caf\u00e9 \u2713"})
            self.assertIsNotNone(e)
            self.assertTrue(L.verify(p))
            self.assertEqual(L.query(p, "K")[0]["payload"], {"x": "caf\u00e9 \u2713"})

    def test_reorder_detected(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "l.jsonl")
            L.append(p, "A", {}); L.append(p, "B", {})
            lines = open(p).read().splitlines()
            open(p, "w").write("\n".join(reversed(lines)) + "\n")
            self.assertFalse(L.verify(p))


if __name__ == "__main__":
    unittest.main()
