"""Portable tests for advisory impact and review packet helpers."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,HERE/"scripts"/path); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
changes=load("plan_changes","plan_changes.py")
packets=load("make_review_packet","make_review_packet.py")

class ChangeImpactTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)/"project"; self.root.mkdir()
        for path,data in {"source.txt":"source one","decision.json":"{}","chapter.md":"chapter","unrelated.md":"same"}.items():
            p=self.root/path; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(data,encoding="utf-8")
        self.graph={"schema_version":1,"artifacts":[{"id":"source","path":"source.txt"},{"id":"decision","path":"decision.json","depends_on":["source"]},{"id":"chapter","path":"chapter.md","depends_on":["decision"]},{"id":"unrelated","path":"unrelated.md"}],"checks":[{"id":"source-check","inputs":["source"],"status":"done","reviewed_sha256":{}},{"id":"chapter-check","inputs":["chapter"],"status":"done","reviewed_sha256":{}},{"id":"other-check","inputs":["unrelated"],"status":"done","reviewed_sha256":{}},{"id":"incomplete","inputs":["ghost"],"status":"pending"}]}
    def tearDown(self): self.tmp.cleanup()
    def test_stale_transitive_unrelated_unknown_and_reusable_baseline(self):
        first=changes.build_report(self.root,self.graph)
        self.graph["checks"][0]["reviewed_sha256"]={"source":first["artifacts"]["source"]["sha256"]}
        self.graph["checks"][1]["reviewed_sha256"]={"chapter":first["artifacts"]["chapter"]["sha256"]}
        self.graph["checks"][2]["reviewed_sha256"]={"unrelated":first["artifacts"]["unrelated"]["sha256"]}
        # Baseline is an ordinary in-memory emitted report; no report file becomes an artifact.
        (self.root/"source.txt").write_text("source two",encoding="utf-8")
        now=changes.build_report(self.root,self.graph,first)
        rows={r["artifact_id"]:r for r in now["changes"]}
        self.assertEqual(rows["source"]["direct_reasons"],["content_changed"])
        self.assertTrue(rows["decision"]["transitive"]); self.assertTrue(rows["chapter"]["transitive"])
        self.assertNotIn("unrelated",rows)
        checks={r["check_id"]:r for r in now["checks"]}
        self.assertTrue(checks["source-check"]["reconsider"])
        self.assertTrue(checks["chapter-check"]["reconsider"])
        self.assertFalse(checks["other-check"]["reconsider"])
        self.assertEqual(checks["incomplete"]["missing_inputs"],["ghost"])
        self.assertNotIn("report",now["artifacts"])
    def test_stale_check_without_artifact_change_and_missing_artifact_propagates(self):
        baseline=changes.build_report(self.root,self.graph)
        self.graph["checks"][1]["reviewed_sha256"]={"chapter":"0"*64}
        stale=changes.build_report(self.root,self.graph,baseline)
        self.assertTrue(next(c for c in stale["checks"] if c["check_id"]=="chapter-check")["reconsider"])
        (self.root/"decision.json").unlink()
        missing=changes.build_report(self.root,self.graph,baseline)
        self.assertEqual(missing["missing_artifacts"],["decision"])
        self.assertTrue(next(c for c in missing["checks"] if c["check_id"]=="chapter-check")["reconsider"])
        self.assertIn("chapter",{r["artifact_id"] for r in missing["changes"]})
    def test_rolling_baseline_keeps_unreviewed_closure_until_digest_is_updated(self):
        initial=changes.build_report(self.root,self.graph)
        chapter_check=next(c for c in initial["checks"] if c["check_id"]=="chapter-check")
        self.graph["checks"][1]["reviewed_sha256"]={"chapter":initial["artifacts"]["chapter"]["sha256"]}
        self.graph["checks"][1]["reviewed_state_sha256"]=chapter_check["current_state_sha256"]
        initial=changes.build_report(self.root,self.graph)
        (self.root/"source.txt").write_text("source changed",encoding="utf-8")
        changed=changes.build_report(self.root,self.graph,initial)
        changed_check=next(c for c in changed["checks"] if c["check_id"]=="chapter-check")
        self.assertTrue(changed_check["reconsider"])
        quiet=changes.build_report(self.root,self.graph,changed)
        self.assertEqual(quiet["changes"],[])
        quiet_check=next(c for c in quiet["checks"] if c["check_id"]=="chapter-check")
        self.assertTrue(quiet_check["reconsider"])
        self.assertEqual(quiet_check["current_state_sha256"],changed_check["current_state_sha256"])
        self.graph["checks"][1]["reviewed_state_sha256"]=quiet_check["current_state_sha256"]
        resolved=changes.build_report(self.root,self.graph,quiet)
        resolved_check=next(c for c in resolved["checks"] if c["check_id"]=="chapter-check")
        self.assertFalse(resolved_check["reconsider"])
    def test_dependency_topology_change_changes_review_state_without_byte_change(self):
        baseline=changes.build_report(self.root,self.graph)
        row=next(c for c in baseline["checks"] if c["check_id"]=="chapter-check")
        self.graph["checks"][1]["reviewed_state_sha256"]=row["current_state_sha256"]
        baseline=changes.build_report(self.root,self.graph)
        before=baseline["artifacts"]["chapter"]["sha256"]
        self.graph["artifacts"][1]["depends_on"]=[]
        result=changes.build_report(self.root,self.graph,baseline)
        current=next(c for c in result["checks"] if c["check_id"]=="chapter-check")
        self.assertEqual(before,result["artifacts"]["chapter"]["sha256"])
        self.assertNotEqual(row["current_state_sha256"],current["current_state_sha256"])
        self.assertTrue(current["reconsider"])
    def test_review_requirement_survives_removal_of_final_edge(self):
        baseline=changes.build_report(self.root,self.graph)
        row=next(c for c in baseline["checks"] if c["check_id"]=="chapter-check")
        self.graph["checks"][1]["reviewed_sha256"]={"chapter":baseline["artifacts"]["chapter"]["sha256"]}
        self.graph["checks"][1]["reviewed_state_sha256"]=row["current_state_sha256"]
        baseline=changes.build_report(self.root,self.graph)
        self.graph["artifacts"][2]["depends_on"]=[]
        changed=changes.build_report(self.root,self.graph,baseline)
        changed_row=next(c for c in changed["checks"] if c["check_id"]=="chapter-check")
        self.assertTrue(changed_row["state_required"]); self.assertTrue(changed_row["reconsider"])
        quiet=changes.build_report(self.root,self.graph,changed)
        quiet_row=next(c for c in quiet["checks"] if c["check_id"]=="chapter-check")
        self.assertEqual(quiet["changes"],[]); self.assertTrue(quiet_row["state_required"]); self.assertTrue(quiet_row["reconsider"])
        self.graph["checks"][1]["reviewed_state_sha256"]=quiet_row["current_state_sha256"]
        resolved=changes.build_report(self.root,self.graph,quiet)
        resolved_row=next(c for c in resolved["checks"] if c["check_id"]=="chapter-check")
        self.assertTrue(resolved_row["state_required"]); self.assertFalse(resolved_row["reconsider"])
    def test_mixed_old_and_new_edges_reach_fixed_point(self):
        baseline=changes.build_report(self.root,self.graph)
        baseline["dependencies"]={"source":[],"decision":[],"chapter":[],"unrelated":["source"],"bridge":["source"]}
        # Current edge is visited before the old edge. The bridge becomes impacted
        # via the old edge, and the union fixed-point must then reach current child.
        graph={"schema_version":1,"artifacts":[{"id":"child","path":"chapter.md","depends_on":["bridge"]},{"id":"bridge","path":"decision.json","depends_on":[]},{"id":"source","path":"source.txt"},{"id":"unrelated","path":"unrelated.md"}],"checks":[]}
        baseline["artifacts"]["child"]={"path":"chapter.md","sha256":changes.sha(self.root/"chapter.md")}
        baseline["dependencies"]["child"]=["bridge"]
        result=changes.build_report(self.root,graph,baseline)
        rows={r["artifact_id"]:r for r in result["changes"]}
        self.assertIn("dependencies_changed",rows["bridge"]["direct_reasons"])
        self.assertTrue(rows["child"]["transitive"])
    def test_new_removed_dependency_and_cycle_validation(self):
        old=changes.build_report(self.root,self.graph)
        (self.root/"unrelated.md").unlink()
        graph=dict(self.graph); graph["artifacts"]=self.graph["artifacts"][:3]
        report=changes.build_report(self.root,graph,old)
        self.assertIn("removed",next(r for r in report["changes"] if r["artifact_id"]=="unrelated")["direct_reasons"])
        bad={"schema_version":1,"artifacts":[{"id":"a","path":"source.txt","depends_on":["b"]},{"id":"b","path":"decision.json","depends_on":["a"]}]}
        with self.assertRaises(changes.InputError): changes.build_report(self.root,bad)
    def test_strict_fields_and_duplicate_json_keys(self):
        bad={**self.graph,"typo":True}
        with self.assertRaises(changes.InputError): changes.build_report(self.root,bad)
        dup=self.root/"duplicate.json"; dup.write_text('{"schema_version":1,"schema_version":1}',encoding="utf-8")
        with self.assertRaises(changes.InputError): changes.read_json(dup)
        report=changes.build_report(self.root,self.graph)
        report["checks"][0]["state_required"]="yes"
        with self.assertRaises(changes.InputError): changes.build_report(self.root,self.graph,report)

class ReviewPacketTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.base=Path(self.tmp.name); self.root=self.base/"project"; self.root.mkdir(); self.out=self.base/"validation"; self.out.mkdir()
        (self.root/"current.md").write_text('<script>alert("x")</script>\nnew line',encoding="utf-8")
        (self.root/"old.md").write_text("old line",encoding="utf-8"); (self.root/"context.txt").write_text("source note",encoding="utf-8")
        (self.root/"page.png").write_bytes(b"fake-png-test-fixture")
        self.manifest={"schema_version":1,"title":"Packet <script>","criteria":["Keep <safe>"],"items":[{"id":"ch1","label":"Chapter <one>","current":"current.md","previous":"old.md","context":["context.txt"],"previews":["page.png"]}]}
    def tearDown(self): self.tmp.cleanup()
    def test_creation_escape_diff_assets_provenance_and_pending(self):
        dest=packets.build(self.root,self.manifest,self.out,"packet")
        doc=(dest/"index.html").read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;",doc); self.assertNotIn('<script>alert',doc); self.assertIn("Text diff",doc); self.assertIn("Provided image",doc); self.assertIn("PENDING",doc)
        prov=json.loads((dest/"provenance.json").read_text(encoding="utf-8")); roles={x["role"] for x in prov["sources"]}
        self.assertEqual(roles,{"current","previous","context","provided_page_preview"}); self.assertEqual(prov["review_scope"]["status"],"pending")
        for row in prov["sources"]: self.assertEqual(len(row["sha256"]),64); self.assertTrue((dest/row["packet_path"]).is_file())
        with self.assertRaises(packets.InputError): packets.build(self.root,self.manifest,self.out,"packet")
    def test_copied_asset_links_are_url_encoded(self):
        source=self.root/"Chapter #1 %.md"; source.write_text("text",encoding="utf-8")
        manifest={**self.manifest,"items":[{**self.manifest["items"][0],"current":"Chapter #1 %.md","previews":[]} ]}
        dest=packets.build(self.root,manifest,self.out,"encoded")
        doc=(dest/"index.html").read_text(encoding="utf-8")
        self.assertIn("items/ch1/current/Chapter%20%231%20%25.md",doc)
    def test_reject_unsafe_path_and_output_inside_root(self):
        bad={**self.manifest,"items":[{**self.manifest["items"][0],"current":"../outside.md"}]}
        with self.assertRaises(packets.InputError): packets.build(self.root,bad,self.out,"bad")
        with self.assertRaises(packets.InputError): packets.build(self.root,self.manifest,self.root,"inside")
        for unsafe in ("C:relative", "folder/file.", "CON.txt", "folder/a:b"):
            with self.assertRaises(packets.InputError): packets.safe_file(self.root,unsafe)
        bad={**self.manifest,"items":[{**self.manifest["items"][0],"id":"chapter:1"}]}
        with self.assertRaises(packets.InputError): packets.build(self.root,bad,self.out,"bad-id")
        typo={**self.manifest,"criteria":[],"criterai":[]}
        with self.assertRaises(packets.InputError): packets.build(self.root,typo,self.out,"bad-schema")
        with self.assertRaises(packets.InputError): packets.read_json(self._write_duplicate())
    def _write_duplicate(self):
        p=self.root/"duplicate.json"; p.write_text('{"title":"x","title":"y"}',encoding="utf-8"); return p

if __name__=="__main__": unittest.main()
