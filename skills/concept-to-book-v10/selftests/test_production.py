"""Portable real-export tests. Optional PDF dependencies/font skip explicitly."""
from __future__ import annotations
import copy
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
import build_reading_edition as reading
import audit_exports as auditor
import build_print_edition as printing


def test_font():
    explicit = os.environ.get("BOOK_TEST_FONT")
    if explicit:
        path = Path(explicit)
        return path if path.is_file() else None
    try:
        import reportlab
        path = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
        return path if path.is_file() else None
    except ImportError:
        return None


def create_fixture(root, font_path=None):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    def write(name, value):
        (root / name).write_bytes(reading.encoded(value))
    config = {"schema_version": 1, "edition_id": "harbor-proof", "metadata": {"title": "The Harbor Promise", "author": "Alex Example", "identifier": "urn:example:harbor-proof-001", "language": "en", "modified": "2026-10-31T00:00:00Z"}, "formats": ["html", "epub"], "assets": [{"id": "harbor-map", "path": "map.png", "role": "map", "alt": "A geometric blue harbor map"}], "sections": [{"id": "dedication", "part": "front", "kind": "dedication", "title": "For the Keepers", "source": "front.json"}, {"id": "chapter-one", "part": "body", "kind": "chapter", "title": "The Third Lantern", "source": "body.json"}, {"id": "afterword", "part": "back", "kind": "afterword", "title": "After the Crossing", "source": "back.json"}]}
    write("edition.json", config)
    write("front.json", {"blocks": [{"type": "paragraph", "text": "For everyone who has kept a light burning."}]})
    shutil.copyfile(SKILL / "selftests/fixtures/production/body.json", root / "body.json")
    write("back.json", {"blocks": [{"type": "paragraph", "text": "Some promises bring us home. Others teach us where home begins."}]})
    # A fixed 2:1 PNG made with standard library only; no image-generation dependency.
    import struct, zlib
    def chunk(kind, value):
        return struct.pack(">I", len(value)) + kind + value + struct.pack(">I", zlib.crc32(kind + value) & 0xffffffff)
    pixels = b"".join(b"\0" + bytes([35, 88, 132]) * 160 for _ in range(80))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 160, 80, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")
    (root / "map.png").write_bytes(png)
    if font_path:
        (root / "fonts").mkdir()
        shutil.copyfile(font_path, root / "fonts/proof.ttf")
        license_path = Path(font_path).with_name("bitstream-vera-license.txt")
        if license_path.exists():
            shutil.copyfile(license_path, root / "fonts/font-license.txt")
    settings = copy.deepcopy(printing.DEFAULTS)
    settings["font"] = {"path": "fonts/proof.ttf", "embedding_authorized": True}
    write("print-settings.json", settings)
    return config, settings


class ReadingAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "input"
        self.config, _ = create_fixture(self.source)
        self.out = self.base / "out"
        self.out.mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(reading.main(["--input-root", str(self.source), "--config", "edition.json", "--output-root", str(self.out), "--output-dir", "reading"]), 0)
        self.release = self.out / "reading"

    def test_real_html_epub_audit(self):
        report = auditor.audit(self.source, "edition.json", self.release)
        self.assertTrue(report["ok"], report["errors"])
        self.assertTrue(report["actual_outputs"])
        self.assertTrue(any("unsupported" in s for s in report["coverage"]))

    def test_actual_html_text_and_asset_tampering(self):
        html = self.release / "html/index.html"
        html.write_bytes(html.read_bytes().replace(b"Mara counted", b"Nora counted"))
        report = auditor.audit(self.source, "edition.json", self.release)
        self.assertFalse(report["ok"])
        self.assertTrue(any("section text" in s for s in report["errors"]))
        asset = self.release / "html/assets/harbor-map.png"
        asset.write_bytes(b"broken exported image")
        report = auditor.audit(self.source, "edition.json", self.release)
        self.assertTrue(any("harbor-map.png" in s for s in report["errors"]))

    def test_actual_epub_metadata_and_text_tampering(self):
        path = self.release / "harbor-proof.epub"
        with zipfile.ZipFile(path) as archive:
            entries = {n: archive.read(n) for n in archive.namelist()}
        entries["EPUB/package.opf"] = entries["EPUB/package.opf"].replace(b"urn:example:harbor-proof-001", b"urn:example:wrong-identifier")
        entries["EPUB/content/chapter-one.xhtml"] = entries["EPUB/content/chapter-one.xhtml"].replace(b"Mara counted", b"Nora counted")
        with zipfile.ZipFile(path, "w") as archive:
            for n, value in entries.items():
                archive.writestr(n, value)
        report = auditor.audit(self.source, "edition.json", self.release)
        self.assertFalse(report["ok"])
        self.assertTrue(any("identifier" in s for s in report["errors"]))

    def test_changed_current_source_and_corrupt_epub(self):
        body = self.source / "body.json"
        body.write_bytes(body.read_bytes().replace(b"Mara counted", b"Nora counted"))
        self.assertFalse(auditor.audit(self.source, "edition.json", self.release)["ok"])
        (self.release / "harbor-proof.epub").write_bytes(b"not zip")
        self.assertFalse(auditor.audit(self.source, "edition.json", self.release)["ok"])

    def test_auditor_cli_json_read_only(self):
        before = {str(p): p.read_bytes() for p in self.release.rglob("*") if p.is_file()}
        run = subprocess.run([sys.executable, str(SKILL / "scripts/audit_exports.py"), "--input-root", str(self.source), "--config", "edition.json", "--release-root", str(self.release)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(json.loads(run.stdout)["ok"])
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.release.rglob("*") if p.is_file()})


class PrintProductionTests(unittest.TestCase):
    def setUp(self):
        try:
            printing.dependencies()
        except reading.BuildError as exc:
            self.skipTest(str(exc))
        font = test_font()
        if not font:
            self.skipTest("No explicit BOOK_TEST_FONT or ReportLab Vera.ttf fixture available")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "input"
        self.config, self.settings = create_fixture(self.source, font)
        self.out = self.base / "out"
        self.out.mkdir()

    def build(self, name="print", preflight=False):
        return printing.build(self.source, "edition.json", "print-settings.json", self.out, name, preflight)

    def write_settings(self):
        (self.source / "print-settings.json").write_bytes(reading.encoded(self.settings))

    def test_real_pdf_text_metadata_geometry_font_image(self):
        report = self.build()
        audited = auditor.audit(self.source, "edition.json", self.out / "print", "print-settings.json")
        self.assertTrue(audited["ok"], audited["errors"])
        self.assertEqual(report["page_count"], 3)
        image = report["image_placements"][0]
        self.assertAlmostEqual(image["width_pt"] / image["height_pt"], 2)
        self.assertEqual(report["reading_order"], ["dedication", "chapter-one", "afterword"])

    def test_preflight_determinism_originals_overwrite(self):
        before = {p.relative_to(self.source): p.read_bytes() for p in self.source.rglob("*") if p.is_file()}
        report = self.build("dry", True)
        self.assertFalse((self.out / "dry").exists())
        self.assertEqual(report["status"], "preflight_passed_no_outputs_written")
        self.build("one")
        self.build("two")
        self.assertEqual((self.out / "one/harbor-proof.pdf").read_bytes(), (self.out / "two/harbor-proof.pdf").read_bytes())
        self.assertEqual(before, {p.relative_to(self.source): p.read_bytes() for p in self.source.rglob("*") if p.is_file()})
        with self.assertRaises(reading.BuildError):
            self.build("one")

    def test_actual_pdf_metadata_corruption_and_changed_source(self):
        self.build()
        target = self.out / "print/harbor-proof.pdf"
        from pypdf import PdfReader, PdfWriter
        writer = PdfWriter()
        writer.clone_document_from_reader(PdfReader(target))
        writer.add_metadata({"/Title": "Wrong title", "/Subject": "Wrong identifier"})
        writer.write(target)
        audited = auditor.audit(self.source, "edition.json", self.out / "print", "print-settings.json")
        self.assertFalse(audited["ok"])
        self.assertTrue(any("/Title" in s for s in audited["errors"]))
        target.write_bytes(b"broken PDF")
        self.assertFalse(auditor.audit(self.source, "edition.json", self.out / "print", "print-settings.json")["ok"])
        self.build("clean")
        body = self.source / "body.json"
        body.write_bytes(body.read_bytes().replace(b"Mara counted", b"Nora counted"))
        report = auditor.audit(self.source, "edition.json", self.out / "clean", "print-settings.json")
        self.assertTrue(any("extracted text" in s for s in report["errors"]))

    def test_distinct_layout_recto_and_flow(self):
        a = self.build("a")
        self.settings["trim_inches"] = [5, 8]
        self.settings["section_start"] = "recto"
        self.write_settings()
        b = self.build("b")
        self.assertEqual([x["start_page"] for x in b["section_placements"]], [1, 3, 5])
        self.assertNotEqual(a["outputs"][0]["sha256"], b["outputs"][0]["sha256"])
        self.assertTrue(auditor.audit(self.source, "edition.json", self.out / "b", "print-settings.json")["ok"])
        self.assertFalse(auditor.audit(self.source, "edition.json", self.out / "a", "print-settings.json")["ok"])

    def test_actual_pdf_removed_text_geometry_and_repeated_images(self):
        body = json.loads((self.source / "body.json").read_bytes())
        body["blocks"].append({"type": "image", "asset_id": "harbor-map"})
        (self.source / "body.json").write_bytes(reading.encoded(body))
        self.build()
        self.assertTrue(auditor.audit(self.source, "edition.json", self.out / "print", "print-settings.json")["ok"])
        from pypdf import PdfReader, PdfWriter
        target = self.out / "print/harbor-proof.pdf"
        writer = PdfWriter()
        writer.clone_document_from_reader(PdfReader(target))
        writer.remove_text()
        writer.pages[0].mediabox.upper_right = (400, 600)
        writer.write(target)
        report = auditor.audit(self.source, "edition.json", self.out / "print", "print-settings.json")
        self.assertFalse(report["ok"])
        self.assertTrue(any("extracted text" in s for s in report["errors"]))
        self.assertTrue(any("MediaBox" in s for s in report["errors"]))

    def test_long_text_paginates_and_audits(self):
        cfg = copy.deepcopy(self.config)
        cfg["assets"] = []
        (self.source / "edition.json").write_bytes(reading.encoded(cfg))
        (self.source / "body.json").write_bytes(reading.encoded({"blocks": [{"type": "paragraph", "text": "A lantern waits beside the water. " * 600}]}))
        self.settings["footer"]["page_numbers"] = False
        self.settings["section_start"] = "continuous"
        self.write_settings()
        report = self.build()
        self.assertGreater(report["page_count"], 3)
        audit = auditor.audit(self.source, "edition.json", self.out / "print", "print-settings.json")
        self.assertTrue(audit["ok"], audit["errors"])

    def test_distinct_edition_identity(self):
        first = self.build("first")
        other = copy.deepcopy(self.config)
        other["edition_id"] = "harbor-second"
        other["metadata"]["identifier"] = "urn:example:harbor-second-002"
        other["metadata"]["title"] = "The Harbor Promise: Second Edition"
        (self.source / "second.json").write_bytes(reading.encoded(other))
        second = printing.build(self.source, "second.json", "print-settings.json", self.out, "second")
        self.assertNotEqual(first["outputs"][0]["sha256"], second["outputs"][0]["sha256"])
        self.assertTrue(auditor.audit(self.source, "second.json", self.out / "second", "print-settings.json")["ok"])
        self.assertFalse(auditor.audit(self.source, "edition.json", self.out / "second", "print-settings.json")["ok"])

    def test_actual_font_cmap_notdef_is_refused(self):
        # Construct a checksummed real TTF whose cmap explicitly maps A to .notdef.
        # Mere membership in charToGlyph used to falsely pass this font.
        import struct
        from reportlab.pdfbase.ttfonts import TTFont, TTFontMaker
        path = self.source / "fonts/proof.ttf"
        original = path.read_bytes()
        face = TTFont("RegressionOriginal", io.BytesIO(original), validate=1).face
        mapping = {c: g for c, g in face.charToGlyph.items() if c < 65535}
        mapping[65] = 0
        mapping[65535] = 0
        codes = sorted(mapping)
        n = len(codes)
        self.assertLess(n, 8190, "Regression fixture needs a bounded Latin TrueType cmap")
        power = 2 ** (n.bit_length() - 1)
        words = lambda values: struct.pack(">" + str(n) + "H", *values)
        fmt = struct.pack(">7H", 4, 16 + 8*n, 0, 2*n, 2*power, power.bit_length()-1, 2*n-2*power) + words(codes) + b"\0\0" + words(codes) + words([(mapping[c]-c) % 65536 for c in codes]) + b"\0\0"*n
        cmap = struct.pack(">HHHHI", 0, 1, 3, 1, 12) + fmt
        maker = TTFontMaker()
        count = struct.unpack_from(">H", original, 4)[0]
        for i in range(count):
            tag, _, offset, size = struct.unpack_from(">4sIII", original, 12+16*i)
            maker.add(tag.decode("ascii"), cmap if tag == b"cmap" else original[offset:offset+size])
        damaged = maker.makeStream()
        self.assertEqual(TTFont("RegressionNotdef", io.BytesIO(damaged), validate=1).face.charToGlyph[65], 0)
        path.write_bytes(damaged)
        with self.assertRaisesRegex(reading.BuildError, "U\\+0041.*notdef"):
            self.build("missing-glyph")
        self.assertFalse((self.out / "missing-glyph").exists())

    def test_refuse_negative_frame_glyph_asset_and_overflow(self):
        self.settings["margins_inches"]["inner"] = 5
        self.write_settings()
        with self.assertRaises(reading.BuildError):
            self.build("badframe")
        self.settings["margins_inches"]["inner"] = .7
        self.write_settings()
        body = self.source / "body.json"
        original = body.read_bytes()
        for text in ("漢字", "a" * 5000):
            body.write_bytes(reading.encoded({"blocks": [{"type": "paragraph", "text": text}]}))
            # Remove now-unused map reference so validation reaches text/layout.
            cfg = copy.deepcopy(self.config)
            cfg["assets"] = []
            (self.source / "edition.json").write_bytes(reading.encoded(cfg))
            with self.assertRaises(reading.BuildError):
                self.build("badtext")
        body.write_bytes(original)
        (self.source / "edition.json").write_bytes(reading.encoded(self.config))
        (self.source / "map.png").write_bytes(b"broken")
        with self.assertRaises(reading.BuildError):
            self.build("badimage")
        self.assertEqual(list(self.out.iterdir()), [])

    def test_cli_preflight_json_and_path_boundary(self):
        run = subprocess.run([sys.executable, str(SKILL / "scripts/build_print_edition.py"), "--input-root", str(self.source), "--config", "edition.json", "--settings", "print-settings.json", "--output-root", str(self.out), "--output-dir", "dry", "--preflight"], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["page_count"], 3)
        with self.assertRaises(reading.BuildError):
            printing.build(self.source, "edition.json", "print-settings.json", self.source, "inside")
        with self.assertRaises(reading.BuildError):
            printing.build(self.source, "edition.json", "../print-settings.json", self.out, "escape")


if __name__ == "__main__":
    unittest.main()
