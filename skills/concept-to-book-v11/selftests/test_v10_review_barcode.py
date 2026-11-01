"""Real Poppler batches >200 pages and independently encoded ReportLab EAN bars."""
import copy
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import aggregate_reviews as aggregate
import build_reading_edition as reading
import render_review as render
import verify_barcode as barcode

DEPS = all(importlib.util.find_spec(name) for name in ("pypdf", "reportlab", "PIL"))
RENDERER = os.environ.get("BOOK_TEST_PDFTOPPM") or shutil.which("pdftoppm")


def write(path, value):
    path.write_bytes(reading.encoded(value))
    return path


def real_pdf(path, count=1, label="Synthetic batch review fixture"):
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path), pagesize=(144, 144), invariant=1)
    for page in range(1, count + 1):
        c.drawString(5, 100, f"{label} {page}")
        c.showPage()
    c.save()


def root_dir(name):
    evidence = os.environ.get("BOOK_V10_EVIDENCE_DIR")
    if evidence:
        root = Path(evidence) / name
        root.mkdir(parents=True, exist_ok=False)
        return root, None
    temp = tempfile.TemporaryDirectory()
    return Path(temp.name), temp


@unittest.skipUnless(DEPS and RENDERER, "Actual batch tests need ReportLab, pypdf, Pillow and existing pdftoppm")
class AggregateBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root, cls.temp = root_dir("aggregate-201-pages")
        cls.inputs = cls.root / "inputs"
        cls.inputs.mkdir()
        real_pdf(cls.inputs / "book.pdf", 201)
        cls.pdfbytes = (cls.inputs / "book.pdf").read_bytes()
        cls.packets, cls.explicit = [], []
        for n, pages in enumerate((list(range(1, 201)), [201])):
            cfg = write(cls.inputs / f"render-{n}.json", {"schema_version": 1, "pdf": "book.pdf", "renderer": RENDERER, "pages": pages, "dpi": 36})
            packet = cls.root / f"packet-{n}"
            result = render.render_review(cfg, packet)
            path = packet / "manifest.json"
            digest = reading.sha(path.read_bytes())
            cls.packets.append({"path": str(path), "sha256": digest})
            for preview in result["previews"]:
                cls.explicit.append({"packet_sha256": digest, "page": preview["page"], "preview_sha256": preview["sha256"], "status": "accepted", "reviewer": "Synthetic automated test fixture, not real human review", "note": "Explicit simulated disposition for test coverage only"})
        cls.counter = 0

    @classmethod
    def tearDownClass(cls):
        if cls.temp:
            cls.temp.cleanup()

    def run_aggregate(self, dispositions, packets=None):
        type(self).counter += 1
        n = type(self).counter
        cfg = write(self.inputs / f"aggregate-{n}.json", {"schema_version": 1, "pdf": "book.pdf", "packets": packets or self.packets, "dispositions": dispositions})
        output = self.root / f"aggregate-{n}"
        return aggregate.aggregate_reviews(cfg, output), output

    def test_201_actual_pages_full_explicit_coverage_and_relocation(self):
        before = {p: reading.sha(p.read_bytes()) for p in self.inputs.iterdir()}
        result, output = self.run_aggregate(self.explicit)
        self.assertEqual(result["review_state"], "accepted")
        self.assertEqual(len(result["reviewed_pages"]), 201)
        self.assertEqual(result["pending_pages"], [])
        aggregate.validate_aggregate(output / "manifest.json")
        relocated = self.root / "relocated-packet"
        shutil.copytree(Path(self.packets[0]["path"]).parent, relocated)
        aggregate.validate_aggregate(output / "manifest.json", pdf_path=self.inputs / "book.pdf", packet_paths={self.packets[0]["sha256"]: str(relocated / "manifest.json")})
        self.assertTrue(all(reading.sha(p.read_bytes()) == digest for p, digest in before.items()))

    def test_previews_alone_and_one_gap_remain_pending(self):
        result, _ = self.run_aggregate([])
        self.assertEqual(result["review_state"], "pending")
        self.assertEqual(len(result["pending_pages"]), 201)
        result, _ = self.run_aggregate(self.explicit[:-1])
        self.assertEqual(result["pending_pages"], [201])
        self.assertEqual(result["review_state"], "pending")
        changed = copy.deepcopy(self.explicit[:-1])
        changed[0]["status"] = "changes-required"
        result, _ = self.run_aggregate(changed)
        self.assertEqual(result["review_state"], "pending")
        self.assertEqual(result["changes_required_pages"], [1])
        self.assertEqual(result["pending_pages"], [201])

    def test_changes_conflicts_and_wrong_preview_hash(self):
        changed = copy.deepcopy(self.explicit)
        changed[-1]["status"] = "changes-required"
        result, _ = self.run_aggregate(changed)
        self.assertEqual(result["review_state"], "changes-required")
        # A separately pinned packet with an opposed explicit disposition conflicts.
        original = Path(self.packets[1]["path"])
        packet = json.loads(original.read_text())
        packet["dispositions"] = [{"page": 201, "status": "changes-required", "note": "Synthetic opposed test decision"}]
        packet["disposition_pdf_sha256"] = packet["pdf"]["sha256"]
        opposed = original.parent / "opposed.json"
        write(opposed, packet)
        packets = self.packets + [{"path": str(opposed), "sha256": reading.sha(opposed.read_bytes())}]
        with self.assertRaisesRegex(reading.BuildError, "Conflicting"):
            self.run_aggregate(self.explicit, packets)
        bad = copy.deepcopy(self.explicit)
        bad[0]["preview_sha256"] = "0" * 64
        with self.assertRaisesRegex(reading.BuildError, "preview identity"):
            self.run_aggregate(bad)

    def test_packet_preview_and_pdf_tampering_rejected(self):
        result, output = self.run_aggregate(self.explicit)
        path = Path(self.packets[0]["path"])
        original = path.read_bytes()
        try:
            path.write_bytes(original + b" ")
            with self.assertRaisesRegex(reading.BuildError, "Packet changed"):
                aggregate.validate_aggregate(output / "manifest.json")
        finally:
            path.write_bytes(original)
        preview = path.parent / "page-0001.png"
        original_preview = preview.read_bytes()
        try:
            preview.write_bytes(original_preview + b"tampered")
            with self.assertRaisesRegex(reading.BuildError, "preview missing or changed"):
                aggregate.validate_aggregate(output / "manifest.json")
        finally:
            preview.write_bytes(original_preview)
        try:
            real_pdf(self.inputs / "book.pdf", 201, "Same count changed bytes")
            with self.assertRaisesRegex(reading.BuildError, "PDF hash/page identity changed"):
                aggregate.validate_aggregate(output / "manifest.json")
        finally:
            (self.inputs / "book.pdf").write_bytes(self.pdfbytes)


@unittest.skipUnless(DEPS and RENDERER, "Actual barcode tests need ReportLab, pypdf, Pillow and existing pdftoppm")
class BarcodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root, cls.temp = root_dir("barcode-real-ean13")

    @classmethod
    def tearDownClass(cls):
        if cls.temp:
            cls.temp.cleanup()

    def setUp(self):
        self.case = self.root / self._testMethodName
        self.case.mkdir()
        self.inputs = self.case / "inputs"
        self.inputs.mkdir()
        self.expected = "9780306406157"
        self.wrong = "9780140328721"
        self.image("source.png", self.expected)
        self.cover("source.png")

    def image(self, name, value):
        # Encode through independent ReportLab implementation; decoder tables are
        # never imported to manufacture passing fixtures.
        from reportlab.graphics.barcode.eanbc import Ean13BarcodeWidget
        from PIL import Image, ImageDraw
        widget = Ean13BarcodeWidget(value=value[:12], humanReadable=False, barWidth=4, barHeight=140)
        group = widget.draw()
        # ReportLab supplies nine quiet modules each side; add two on the left
        # to satisfy EAN-13's eleven-module left quiet zone.
        image = Image.new("RGB", (round(widget.width) + 8, 160), "white")
        draw = ImageDraw.Draw(image)
        for shape in group.contents:
            if getattr(shape, "fillColor", None) is not None:
                x, y, w, h = shape.x + 8, shape.y, shape.width, shape.height
                draw.rectangle((round(x), round(150-y-h), round(x+w)-1, round(150-y)-1), fill="black")
        image.save(self.inputs / name)

    def cover(self, image_name):
        from reportlab.pdfgen import canvas
        from PIL import Image
        with Image.open(self.inputs / image_name) as image:
            self.region = [20, 20, image.width * .3, image.height * .3]
        c = canvas.Canvas(str(self.inputs / "cover.pdf"), pagesize=(300, 200), invariant=1)
        c.drawImage(str(self.inputs / image_name), *self.region)
        c.showPage()
        c.save()

    def run_verify(self, name="proof", **changes):
        cfg = {"schema_version": 1, "edition_identifier": self.expected, "source_barcode": "source.png", "source_barcode_sha256": reading.sha((self.inputs / "source.png").read_bytes()), "cover_pdf": "cover.pdf", "cover_pdf_sha256": reading.sha((self.inputs / "cover.pdf").read_bytes()), "barcode_region_pt": self.region, "renderer": RENDERER}
        cfg.update(changes)
        path = write(self.inputs / f"{name}.json", cfg)
        before = {p: reading.sha(p.read_bytes()) for p in self.inputs.iterdir()}
        output = self.case / name
        result = barcode.verify_barcode(path, output)
        self.assertEqual(before, {p: reading.sha(p.read_bytes()) for p in self.inputs.iterdir()})
        return result, output

    def test_decodes_real_supplied_and_actual_rendered_and_preserves_sources(self):
        result, output = self.run_verify()
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["source_decode"]["value"], self.expected)
        self.assertEqual(result["rendered_decode"]["value"], self.expected)
        self.assertEqual(result["physical_print_scanner_acceptance"], "not-assessed")
        barcode.validate_barcode(output / "manifest.json")
        (self.inputs / "cover.pdf").write_bytes((self.inputs / "cover.pdf").read_bytes() + b"changed")
        with self.assertRaisesRegex(reading.BuildError, "cover_pdf changed"):
            barcode.validate_barcode(output / "manifest.json")

    def test_wrong_source_edition_and_wrong_rendered_edition_fail(self):
        result, _ = self.run_verify("wrong-edition", edition_identifier=self.wrong)
        self.assertEqual(result["status"], "failed")
        self.image("wrong.png", self.wrong)
        self.cover("wrong.png")
        result, _ = self.run_verify("wrong-render")
        self.assertEqual(result["source_decode"]["value"], self.expected)
        self.assertEqual(result["rendered_decode"]["value"], self.wrong)
        self.assertEqual(result["status"], "failed")

    def test_damaged_clipped_and_unreadable_bars_fail(self):
        from PIL import Image, ImageDraw
        with Image.open(self.inputs / "source.png") as image:
            image = image.copy()
            ImageDraw.Draw(image).rectangle((100, 0, 125, image.height), fill="white")
            image.save(self.inputs / "damage.png")
        self.cover("damage.png")
        result, _ = self.run_verify("damaged")
        self.assertEqual(result["rendered_decode"]["status"], "unreadable")
        self.assertEqual(result["status"], "failed")
        self.cover("source.png")
        clipped = [self.region[0] + 12, self.region[1], self.region[2] - 12, self.region[3]]
        result, _ = self.run_verify("clipped", barcode_region_pt=clipped)
        self.assertEqual(result["status"], "failed")
        Image.new("RGB", (452, 160), "white").save(self.inputs / "source.png")
        result, _ = self.run_verify("unreadable")
        self.assertEqual(result["source_decode"]["status"], "unreadable")
        self.assertEqual(result["status"], "failed")

    def test_missing_renderer_is_explicit_and_hashes_fail_closed(self):
        result, _ = self.run_verify("missing-renderer", renderer="nonexistent-v10-renderer-9d207")
        self.assertEqual(result["status"], "capability-missing")
        self.assertEqual(result["source_decode"]["value"], self.expected)
        with self.assertRaisesRegex(reading.BuildError, "Supplied barcode SHA-256"):
            self.run_verify("bad-source-hash", source_barcode_sha256="0" * 64)

    def test_actual_helpers_support_long_input_and_output_paths(self):
        # The real native renderer must read AND write from a short workspace;
        # merely passing relative arguments still fails on affected Windows builds.
        parent = self.case
        while len(str(parent / "inputs" / "cover.pdf")) <= 310:
            parent = parent / ("long-render-path-" + "x" * 24)
        try:
            parent.mkdir(parents=True)
            shutil.copytree(self.inputs, parent / "inputs")
        except OSError as exc:
            if getattr(exc, "winerror", None) == 206 or exc.errno == 36:
                self.skipTest("Platform cannot create long-path regression fixture: " + str(exc))
            raise
        self.inputs = parent / "inputs"
        self.assertGreater(len(str(self.inputs / "cover.pdf")), 260)
        before = {p.name: reading.sha(p.read_bytes()) for p in self.inputs.iterdir()}
        config = write(self.inputs / "render.json", {"schema_version": 1, "pdf": "cover.pdf", "renderer": RENDERER, "dpi": 36})
        rendered = render.render_review(config, parent / "render-output")
        self.assertGreater(len(str(parent / "render-output" / "page-0001.png")), 260)
        self.assertTrue((parent / "render-output" / "page-0001.png").is_file())
        # Exercise actual barcode-region rendering with the same long inputs,
        # with output on another long branch (not a shortened test destination).
        old_case = self.case
        self.case = parent
        result, output = self.run_verify("barcode-output")
        self.case = old_case
        self.assertEqual(result["status"], "verified")
        self.assertGreater(len(str(output / "rendered-barcode.png")), 260)
        self.assertTrue(all(reading.sha((self.inputs / name).read_bytes()) == digest for name, digest in before.items()))
        render.validate_review(parent / "render-output" / "manifest.json")
        barcode.validate_barcode(output / "manifest.json")
        for renderer_record, expected_hash, output_root in ((rendered["renderer"], rendered["pdf"]["sha256"], parent / "render-output"), (result["renderer"], result["cover_pdf"]["sha256"], output)):
            for invocation in renderer_record["invocations"]:
                self.assertEqual(invocation["returncode"], 0)
                self.assertEqual(invocation["staged_pdf_sha256"], expected_hash)
                self.assertEqual(invocation["output_sha256"], reading.sha((output_root / invocation["output_path"]).read_bytes()))
                self.assertTrue(invocation["temporary_workspace"])
                self.assertEqual(invocation["arguments"][-2], "document.pdf")
                self.assertFalse(Path(invocation["arguments"][-1]).is_absolute())
                self.assertLess(len(str(Path(invocation["cwd"]) / "document.pdf")), 240)
                self.assertFalse(Path(invocation["cwd"]).exists())


if __name__ == "__main__":
    unittest.main()
