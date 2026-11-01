"""Actual semantic import/export and adversarial auditing; synthetic fixtures only."""
import contextlib
import copy
import io
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
import import_manuscript as importer
import build_reading_edition as reading
import build_print_edition as printing
import audit_exports as auditor

META = {"title": "Semantic Lantern", "author": "Test Author", "identifier": "urn:test:semantic", "language": "en", "modified": "2026-10-31T00:00:00Z"}
MARKDOWN = "# First **Lantern**\n\nBefore *soft words*, **strong words**, and ***both words*** after.\n\n## Nested *Heading*\n\nA & B remain literal.\n\n***\n\n### Deeper Heading\n\nFinal paragraph.\n\n# Second\n\nLast words.\n"
W = importer.W


def copy_font_family(destination):
    """Synthetic checksum-rebuilt Bitstream Vera copies; no installed font modified.

    destination is the fonts directory. Return print-settings font declaration
    using paths relative to its parent edition root. Preserve bundled license.
    """
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    import reportlab
    import struct
    from reportlab.pdfbase.ttfonts import TTFontMaker
    fonts = Path(reportlab.__file__).parent / "fonts"
    for name in ("Vera.ttf", "VeraIt.ttf", "VeraBd.ttf", "VeraBI.ttf"):
        original = (fonts / name).read_bytes()
        maker = TTFontMaker()
        for index in range(struct.unpack_from(">H", original, 4)[0]):
            tag, _, offset, size = struct.unpack_from(">4sIII", original, 12 + 16 * index)
            maker.add(tag.decode("ascii"), original[offset:offset+size])
        (destination / name).write_bytes(maker.makeStream())
    license_path = fonts / "bitstream-vera-license.txt"
    if not license_path.is_file():
        raise RuntimeError("Bundled Bitstream Vera license missing")
    shutil.copyfile(license_path, destination / license_path.name)
    (destination / "fixture-font-provenance.txt").write_text("Synthetic fixture font copies from ReportLab bundled Bitstream Vera. TTF table directory checksums rebuilt with ReportLab TTFontMaker; glyph outlines and face semantics retained. Original installed fonts unchanged. See bitstream-vera-license.txt.\n", encoding="utf-8")
    prefix = destination.name + "/"
    return {"path": prefix + "Vera.ttf", "embedding_authorized": True, "variants": {"italic": prefix + "VeraIt.ttf", "bold": prefix + "VeraBd.ttf", "bold_italic": prefix + "VeraBI.ttf"}}


def fixture(base):
    source, out = Path(base) / "source", Path(base) / "out"
    source.mkdir(parents=True)
    out.mkdir()
    (source / "book.md").write_text(MARKDOWN, encoding="utf-8")
    (source / "metadata.json").write_bytes(reading.encoded(META))
    args = ["--input-root", str(source), "--input", "book.md", "--metadata", "metadata.json", "--output-root", str(out), "--output-dir", "imported"]
    with contextlib.redirect_stdout(io.StringIO()):
        assert importer.main(args) == 0
    imported = out / "imported"
    family = copy_font_family(imported / "fonts")
    settings = copy.deepcopy(printing.DEFAULTS)
    settings["font"] = family
    (imported / "print-settings.json").write_bytes(reading.encoded(settings))
    with contextlib.redirect_stdout(io.StringIO()):
        assert reading.main(["--input-root", str(imported), "--config", "edition.json", "--output-root", str(out), "--output-dir", "reading"]) == 0
    printing.build(imported, "edition.json", "print-settings.json", out, "print")
    return source, imported, out, settings


def semantic_fixture_skip_reason():
    missing = [name for name in ("reportlab", "pypdf", "PIL") if importlib.util.find_spec(name) is None]
    if missing:
        return "Optional semantic PDF dependencies unavailable: " + ", ".join(missing)
    import reportlab
    fonts = Path(reportlab.__file__).parent / "fonts"
    required = ("Vera.ttf", "VeraIt.ttf", "VeraBd.ttf", "VeraBI.ttf", "bitstream-vera-license.txt")
    absent = [name for name in required if not (fonts / name).is_file()]
    if absent:
        return "Optional bundled Vera fixture family/license unavailable: " + ", ".join(absent)
    return None


SEMANTIC_SKIP_REASON = semantic_fixture_skip_reason()


@unittest.skipIf(SEMANTIC_SKIP_REASON is not None, SEMANTIC_SKIP_REASON or "")
class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source, self.imported, self.out, self.settings = fixture(self.temp.name)

    def test_actual_markdown_json_html_epub_pdf_preservation(self):
        cfg = json.loads((self.imported / "edition.json").read_bytes())
        self.assertEqual([s["title"] for s in cfg["sections"]], ["First Lantern", "Second"])
        first = json.loads((self.imported / cfg["sections"][0]["source"]).read_bytes())
        self.assertEqual([b["type"] for b in first["blocks"]], ["paragraph", "heading", "paragraph", "scene_break", "heading", "paragraph"])
        self.assertEqual([b["level"] for b in first["blocks"] if b["type"] == "heading"], [2, 3])
        self.assertTrue(any(r["emphasis"] and r["strong"] for r in first["blocks"][0]["runs"]))
        data = (self.out / "reading/html/index.html").read_bytes()
        self.assertIn(b"<strong><em>both words</em></strong>", data)
        self.assertIn(b"A &amp; B", data)
        self.assertIn(b'<hr class="scene-break" />', data)
        for release, settings in (("reading", None), ("print", "print-settings.json")):
            report = auditor.audit(self.imported, "edition.json", self.out / release, settings)
            self.assertTrue(report["ok"], report["errors"])
        report = auditor.audit(self.imported, "edition.json", self.out / "print", "print-settings.json")
        self.assertTrue(any("semantic font faces" in c["check"] and c["passed"] for c in report["checks"]))

    def test_plain_docx_matches_markdown_structured_content(self):
        def run(text, props=""):
            return f'<w:r>{"<w:rPr>" + props + "</w:rPr>" if props else ""}<w:t xml:space="preserve">{text}</w:t></w:r>'
        def p(value, level=None):
            return '<w:p>' + (f'<w:pPr><w:pStyle w:val="Heading{level}"/></w:pPr>' if level else '') + value + '</w:p>'
        body = p(run("First ") + run("Lantern", "<w:b/>"), 1) + p(run("Before ") + run("soft words", "<w:i/>") + run(", ") + run("strong words", "<w:b/>") + run(", and ") + run("both words", "<w:b/><w:i/>") + run(" after.")) + p(run("Nested ") + run("Heading", "<w:i/>"), 2) + p(run("A &amp; B remain literal.")) + p(run("***")) + p(run("Deeper Heading"), 3) + p(run("Final paragraph.")) + p(run("Second"), 1) + p(run("Last words."))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name in ("[Content_Types].xml", "_rels/.rels"):
                archive.writestr(name, "<root/>")
            archive.writestr("word/document.xml", f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>')
        md, issues, _ = importer.markdown(MARKDOWN.encode())
        doc, doc_issues, _ = importer.docx(buffer.getvalue())
        self.assertEqual(issues, [])
        self.assertEqual(doc_issues, [])
        self.assertEqual(importer.convert(md)[0], importer.convert(doc)[0])
        # Exercise actual DOCX CLI->JSON->HTML/EPUB/PDF, not just parser equivalence.
        (self.source / "book.docx").write_bytes(buffer.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(importer.main(["--input-root", str(self.source), "--input", "book.docx", "--metadata", "metadata.json", "--output-root", str(self.out), "--output-dir", "docx-import"]), 0)
        docroot = self.out / "docx-import"
        shutil.copytree(self.imported / "fonts", docroot / "fonts")
        shutil.copyfile(self.imported / "print-settings.json", docroot / "print-settings.json")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(reading.main(["--input-root", str(docroot), "--config", "edition.json", "--output-root", str(self.out), "--output-dir", "docx-reading"]), 0)
        printing.build(docroot, "edition.json", "print-settings.json", self.out, "docx-print")
        for release, settings in (("docx-reading", None), ("docx-print", "print-settings.json")):
            report = auditor.audit(docroot, "edition.json", self.out / release, settings)
            self.assertTrue(report["ok"], report["errors"])
        self.assertEqual((self.out / "print/imported-edition.pdf").read_bytes(), (self.out / "docx-print/imported-edition.pdf").read_bytes())

    def test_missing_or_fake_font_variants_and_malformed_runs_refused(self):
        settings_path = self.imported / "print-settings.json"
        for variants in ({}, {"bold": "fonts/Vera.ttf", "italic": "fonts/VeraIt.ttf", "bold_italic": "fonts/VeraBI.ttf"}):
            settings = copy.deepcopy(self.settings)
            settings["font"]["variants"] = variants
            settings_path.write_bytes(reading.encoded(settings))
            with self.assertRaises(reading.BuildError):
                printing.build(self.imported, "edition.json", "print-settings.json", self.out, "refused")
            self.assertFalse((self.out / "refused").exists())
        path = self.imported / "sections/section-0001.json"
        data = json.loads(path.read_bytes())
        data["blocks"][0]["runs"][0]["text"] = "silently wrong"
        path.write_bytes(reading.encoded(data))
        with self.assertRaisesRegex(reading.BuildError, "concatenation"):
            reading.prepare(reading.Inputs(self.imported), "edition.json")

    def test_actual_semantic_tampering_detected_independently(self):
        path = self.out / "reading/html/index.html"
        path.write_bytes(path.read_bytes().replace(b"<em>soft words</em>", b"<strong>soft words</strong>"))
        report = auditor.audit(self.imported, "edition.json", self.out / "reading")
        self.assertTrue(any("actual HTML semantic" in e for e in report["errors"]))
        path = self.out / "print/imported-edition.pdf"
        from pypdf import PdfReader, PdfWriter
        reader = PdfReader(path)
        writer = PdfWriter()
        writer.clone_document_from_reader(reader)
        page = writer.pages[0]
        # Change actual Tf operations to the regular face; visible text survives.
        fonts = page["/Resources"]["/Font"]
        regular = next(key for key, value in fonts.items() if "Roman" in str(value.get_object().get("/BaseFont", "")))
        stream = page.get_contents()
        for operands, operator in stream.operations:
            if operator == b"Tf":
                operands[0] = regular
        page.replace_contents(stream)
        writer.write(path)
        report = auditor.audit(self.imported, "edition.json", self.out / "print", "print-settings.json")
        self.assertTrue(any("painted character order, supplied semantic font faces" in e for e in report["errors"]), report["errors"])

    def test_wrapped_nested_heading_keeps_first_following_line(self):
        from pypdf import PdfReader
        config = json.loads((self.imported / "edition.json").read_bytes())
        config["sections"] = config["sections"][:1]
        config["sections"][0]["title"] = "Section"
        config["sections"][0].pop("title_runs", None)
        (self.imported / "edition.json").write_bytes(reading.encoded(config))
        heading = {"type": "heading", "level": 2, "text": "Measured heading using real bold and italic variants across lines", "runs": [
            {"text": "Measured heading using ", "emphasis": False, "strong": False},
            {"text": "real bold", "emphasis": False, "strong": True},
            {"text": " and ", "emphasis": False, "strong": False},
            {"text": "italic variants", "emphasis": True, "strong": False},
            {"text": " across lines", "emphasis": False, "strong": False}]}
        blocks = [{"type": "paragraph", "text": f"Filler {n}."} for n in range(6)] + [heading, {"type": "paragraph", "text": "Following body starts here and continues after the measured heading."}]
        (self.imported / config["sections"][0]["source"]).write_bytes(reading.encoded({"blocks": blocks}))
        settings = copy.deepcopy(self.settings)
        settings["trim_inches"] = [3, 4]
        settings["margins_inches"] = {name: .4 for name in ("top", "bottom", "inner", "outer")}
        settings["footer"]["page_numbers"] = False
        (self.imported / "print-settings.json").write_bytes(reading.encoded(settings))
        printing.build(self.imported, "edition.json", "print-settings.json", self.out, "heading-flow")
        pages = [page.extract_text() for page in PdfReader(self.out / "heading-flow/imported-edition.pdf").pages]
        self.assertGreaterEqual(len(pages), 2)
        self.assertIn("Filler 5.", pages[0])
        self.assertNotIn("Measured heading", pages[0])
        self.assertIn("Measured heading", pages[1])
        self.assertIn("Following body starts", pages[1])
        self.assertIn(heading["text"], printing.normalize(pages[1]))
        heading_lines = pages[1].split("Following body", 1)[0].splitlines()
        self.assertGreaterEqual(len(heading_lines), 3, "Regression must exercise an actually wrapped heading")
        report = auditor.audit(self.imported, "edition.json", self.out / "heading-flow", "print-settings.json")
        self.assertTrue(report["ok"], report["errors"])

    def test_unsupported_features_and_heading_context(self):
        for text in ("[^bad note]", "<em>raw</em>", "**outer *nested***", "*unbalanced", "a*b*c"):
            _, issues, _ = importer.markdown(("# One\n\n" + text).encode())
            self.assertTrue(issues, text)
        units, issues, _ = importer.markdown(b"## First\n\nParagraph.\n\n### Nested\n\nParagraph.\n\n## Second\n\nEnd.")
        sections, _ = importer.convert(units)
        self.assertEqual([s["heading_level"] for s in sections], [2, 2])
        self.assertEqual(sections[0]["blocks"][1]["level"], 3)


if __name__ == "__main__":
    unittest.main()
