"""V10 bounded hyperlinks/endnotes and measured paragraph/figure pagination.

All fixtures are synthetic and reusable by external validation. No private vault
content, network access, or committed generated production files are required.
"""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import import_manuscript as importer
import build_reading_edition as reading
import build_print_edition as printing
import semantic_content as semantic
import audit_exports as audit
from selftests.test_semantics import copy_font_family, META

MARKDOWN = "# Evidence\n\nRead [the record](https://example.invalid/record?a=1&b=2) and keep this claim[^record] in context.\n\n[^record]: The source note preserves **these words** exactly.\n"
PRINT_AVAILABLE = all(importlib.util.find_spec(name) is not None for name in ("reportlab", "pypdf", "PIL"))


def docx_fixture(note_kind="endnote"):
    """Minimal actual zipped WordprocessingML with a native note and hyperlink."""
    w = importer.W
    r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    body = '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Evidence</w:t></w:r></w:p>'
    body += '<w:p><w:r><w:t xml:space="preserve">Read </w:t></w:r><w:hyperlink r:id="rLink"><w:r><w:t>the record</w:t></w:r></w:hyperlink><w:r><w:t xml:space="preserve"> and keep this claim</w:t></w:r>'
    body += f'<w:r><w:rPr><w:rStyle w:val="{note_kind.title()}Reference"/></w:rPr><w:{note_kind}Reference w:id="1"/></w:r><w:r><w:t xml:space="preserve"> in context.</w:t></w:r></w:p>'
    note = f'<w:{note_kind}s xmlns:w="{w}"><w:{note_kind} w:id="1"><w:p><w:r><w:{note_kind}Ref/></w:r><w:r><w:t xml:space="preserve">The source note preserves </w:t></w:r><w:r><w:rPr><w:b/></w:rPr><w:t>these words</w:t></w:r><w:r><w:t xml:space="preserve"> exactly.</w:t></w:r></w:p></w:{note_kind}></w:{note_kind}s>'
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("_rels/.rels", "<Relationships/>")
        z.writestr("word/document.xml", f'<w:document xmlns:w="{w}" xmlns:r="{r}"><w:body>{body}</w:body></w:document>')
        z.writestr("word/_rels/document.xml.rels", '<Relationships><Relationship Id="rLink" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.invalid/record?a=1&amp;b=2" TargetMode="External"/></Relationships>')
        z.writestr(f"word/{note_kind}s.xml", note)
    return data.getvalue()


def fixture(base, source_bytes=None, suffix=".md", with_print=True):
    base = Path(base)
    source, out = base / "source", base / "out"
    source.mkdir(parents=True)
    out.mkdir()
    source_bytes = MARKDOWN.encode() if source_bytes is None else source_bytes
    (source / ("book" + suffix)).write_bytes(source_bytes)
    (source / "metadata.json").write_bytes(reading.encoded(META))
    with contextlib.redirect_stdout(io.StringIO()):
        code = importer.main(["--input-root", str(source), "--input", "book" + suffix, "--metadata", "metadata.json", "--output-root", str(out), "--output-dir", "imported"])
    if code:
        raise AssertionError("Synthetic import failed")
    imported = out / "imported"
    with contextlib.redirect_stdout(io.StringIO()):
        code = reading.main(["--input-root", str(imported), "--config", "edition.json", "--output-root", str(out), "--output-dir", "reading"])
    if code:
        raise AssertionError("Synthetic reading build failed")
    if with_print:
        settings = copy.deepcopy(printing.DEFAULTS)
        settings["font"] = copy_font_family(imported / "fonts")
        (imported / "print-settings.json").write_bytes(reading.encoded(settings))
        printing.build(imported, "edition.json", "print-settings.json", out, "print")
    return source, imported, out


class SemanticContentTests(unittest.TestCase):
    def test_markdown_text_links_notes_and_definition_order(self):
        units, issues, _ = importer.markdown(MARKDOWN.encode())
        self.assertEqual(issues, [])
        sections, coverage = importer.convert(units)
        self.assertEqual(sections[0]["blocks"][0]["text"], "Read the record and keep this claim[record] in context.")
        self.assertEqual(sections[1]["blocks"][0]["text"], "[record] The source note preserves these words exactly.")
        self.assertEqual(sections[1]["part"], "back")
        self.assertEqual(sections[1]["kind"], "endnotes")
        self.assertEqual(sum(c["characters"] for c in coverage), sum(len(u["text"]) for u in units))
        self.assertEqual(semantic.note_map(sections, reading.need)["record"]["note_section"], "section-0002")

    def test_missing_duplicate_or_nested_note_graph_refused(self):
        for text in ("# A\n\nMissing[^lost].", "# A\n\nNo reference.\n\n[^lost]: Lost.", "# A\n\nTwice[^a][^a].\n\n[^a]: One.", "# A\n\nOnce[^a].\n\n[^a]: One.\n[^a]: Duplicate.", "# A\n\nOnce[^a].\n\n[^a]: Nested[^b].\n[^b]: Two."):
            units, issues, _ = importer.markdown(text.encode())
            self.assertFalse(issues)
            with self.assertRaises(importer.Refusal):
                importer.convert(units)

    def test_uri_and_markup_refusals(self):
        for uri in ("javascript:alert", "file:///c:/private", "data:text/plain,abc", "../local", "https://user:secret@example.invalid", "https://example.invalid/a b"):
            self.assertFalse(semantic.safe_href(uri), uri)
        for text in ("[bad](javascript:evil)", "[label **nested**](https://example.invalid)", "[^Upper]", "![image](https://example.invalid/image.png)"):
            _, issues, _ = importer.markdown(("# A\n\n" + text).encode())
            self.assertTrue(issues, text)

    def test_docx_native_hyperlinks_and_notes(self):
        for kind, prefix in (("endnote", "en-"), ("footnote", "fn-")):
            units, issues, counts = importer.docx(docx_fixture(kind))
            self.assertFalse(issues, issues)
            sections, _ = importer.convert(units)
            self.assertEqual(sections[0]["blocks"][0]["text"], f"Read the record and keep this claim[{prefix}1] in context.")
            self.assertEqual(sections[1]["blocks"][0]["text"], f"[{prefix}1] The source note preserves these words exactly.")
            self.assertIn("never page footnotes", counts["note_treatment"])

    def test_docx_missing_duplicate_and_complex_notes_refused(self):
        original = docx_fixture()
        with zipfile.ZipFile(io.BytesIO(original)) as z:
            members = {name: z.read(name) for name in z.namelist()}
        for change in ("missing", "duplicate", "complex", "unsafe-link", "separator-text"):
            edited = dict(members)
            if change == "missing":
                del edited["word/endnotes.xml"]
            elif change == "duplicate":
                edited["word/document.xml"] = edited["word/document.xml"].replace(b'<w:endnoteReference w:id="1"/>', b'<w:endnoteReference w:id="1"/><w:endnoteReference w:id="1"/>')
            elif change == "complex":
                edited["word/endnotes.xml"] = edited["word/endnotes.xml"].replace(b'</w:endnote>', b'<w:p><w:r><w:t>Second paragraph.</w:t></w:r></w:p></w:endnote>')
            elif change == "unsafe-link":
                edited["word/_rels/document.xml.rels"] = edited["word/_rels/document.xml.rels"].replace(b'https://example.invalid/record?a=1&amp;b=2', b'file:///c:/private')
            else:
                edited["word/endnotes.xml"] = edited["word/endnotes.xml"].replace(b'</w:endnotes>', b'<w:endnote w:id="-1" w:type="separator"><w:p><w:r><w:t>Must not lose this text.</w:t></w:r></w:p></w:endnote></w:endnotes>')
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as z:
                for name, blob in edited.items():
                    z.writestr(name, blob)
            try:
                units, issues, _ = importer.docx(stream.getvalue())
                if not issues:
                    importer.convert(units)
            except importer.Refusal:
                continue
            self.assertTrue(issues, change)

    def test_research_source_records_do_not_become_citations(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, imported, _ = fixture(tmp, with_print=False)
            ledger = imported / "source-use.json"
            ledger.write_bytes(b'{"records":[{"id":"research-only","note":"Not a reader citation"}]}')
            inputs = reading.Inputs(imported)
            _, _, _, sections = reading.prepare(inputs, "edition.json")
            self.assertNotIn("source-use.json", inputs.files)
            self.assertEqual(set(semantic.note_map(sections, reading.need)), {"record"})
            self.assertEqual(ledger.read_bytes(), b'{"records":[{"id":"research-only","note":"Not a reader citation"}]}')

    def test_actual_reading_note_links_and_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, imported, out = fixture(tmp, with_print=False)
            self.assertEqual((source / "book.md").read_bytes(), MARKDOWN.encode())
            report = audit.audit(imported, "edition.json", out / "reading")
            self.assertTrue(report["ok"], report["errors"])
            path = out / "reading/html/index.html"
            original = path.read_bytes()
            root = ET.fromstring(original)
            group = root.find(f".//{{{reading.XHTML}}}section[@role='doc-endnotes']")
            self.assertIsNotNone(group)
            self.assertEqual(group.get("aria-label"), "Endnotes")
            self.assertIsNotNone(group.find(f"{{{reading.XHTML}}}ol/{{{reading.XHTML}}}li[@id='note-record']"))
            self.assertNotIn(b'role="doc-endnote"', original)
            for bad in (original.replace(b'#note-record', b'#note-missing'), original.replace(b'id="note-record"', b'id="note-missing"'), original.replace(b'id="note-record"', b'id="ref-record"'), original.replace(b'#ref-record', b'#note-record')):
                path.write_bytes(bad)
                report = audit.audit(imported, "edition.json", out / "reading")
                self.assertFalse(report["ok"])
                self.assertTrue(any("exported" in e or "endnote return" in e for e in report["errors"]), report["errors"])
            path.write_bytes(original)
            with zipfile.ZipFile(out / "reading/imported-edition.epub") as z:
                first = ET.fromstring(z.read("EPUB/content/section-0001.xhtml"))
                self.assertEqual(first.find(f".//{{{reading.XHTML}}}a[@role='doc-noteref']").get("href"), "section-0002.xhtml#note-record")
                notes = ET.fromstring(z.read("EPUB/content/section-0002.xhtml"))
                self.assertIsNotNone(notes.find(f".//{{{reading.XHTML}}}section[@role='doc-endnotes'][@{{{reading.EPUB}}}type='endnotes']/{{{reading.XHTML}}}ol/{{{reading.XHTML}}}li[@id='note-record']"))
                self.assertNotIn(b'epub:type="endnote"', z.read("EPUB/content/section-0002.xhtml"))
                self.assertEqual(notes.find(f".//{{{reading.XHTML}}}a[@class='note-back']").get("href"), "section-0001.xhtml#ref-record")


@unittest.skipUnless(PRINT_AVAILABLE, "ReportLab, pypdf or Pillow genuinely absent")
class PrintContentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        _, self.imported, self.out = fixture(self.tmp.name)

    def edit(self, blocks, **settings):
        cfg = json.loads((self.imported / "edition.json").read_bytes())
        cfg["sections"] = cfg["sections"][:1]
        (self.imported / "edition.json").write_bytes(reading.encoded(cfg))
        (self.imported / cfg["sections"][0]["source"]).write_bytes(reading.encoded({"blocks": blocks}))
        opts = json.loads((self.imported / "print-settings.json").read_bytes())
        opts.update(trim_inches=[3, 4], margins_inches={k: .4 for k in ("top", "bottom", "inner", "outer")}, footer={"page_numbers": False, "font_size_pt": 9, "offset_pt": 20}, **settings)
        (self.imported / "print-settings.json").write_bytes(reading.encoded(opts))

    def build(self, name):
        return printing.build(self.imported, "edition.json", "print-settings.json", self.out, name)

    def test_actual_pdf_endnote_links_text_and_annotation_tampering(self):
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import TextStringObject, NameObject
        report = audit.audit(self.imported, "edition.json", self.out / "print", "print-settings.json")
        self.assertTrue(report["ok"], report["errors"])
        path = self.out / "print/imported-edition.pdf"
        reader = PdfReader(path)
        text = printing.normalize(" ".join(p.extract_text() for p in reader.pages))
        self.assertIn("Read the record and keep this claim[record] in context.", text)
        self.assertIn("[record] The source note preserves these words exactly.", text)
        manifest = json.loads((self.out / "print/build-manifest.json").read_bytes())
        self.assertEqual({l["kind"] for l in manifest["link_placements"]}, {"uri", "note", "return"})
        writer = PdfWriter()
        writer.clone_document_from_reader(reader)
        first = writer.pages[0]["/Annots"][0].get_object()
        first["/A"][NameObject("/URI")] = TextStringObject("https://example.invalid/wrong")
        writer.write(path)
        report = audit.audit(self.imported, "edition.json", self.out / "print", "print-settings.json")
        self.assertTrue(any("hyperlink rectangles" in e for e in report["errors"]), report["errors"])

    def test_docx_to_all_three_outputs(self):
        _, imported, out = fixture(Path(self.tmp.name) / "docx", docx_fixture(), ".docx")
        for name, settings in (("reading", None), ("print", "print-settings.json")):
            report = audit.audit(imported, "edition.json", out / name, settings)
            self.assertTrue(report["ok"], report["errors"])

    def test_paragraph_minimums_and_legacy_defaults(self):
        blocks = [{"type": "paragraph", "text": "Filler."} for _ in range(5)] + [{"type": "paragraph", "text": " ".join("word" + str(i) for i in range(80))}]
        self.edit(blocks, widow_lines=2, orphan_lines=2)
        report = self.build("balanced")
        fragments = report["text_placements"][-1]["fragments"]
        self.assertGreater(len(fragments), 1)
        self.assertTrue(all(f["lines"] >= 2 for f in fragments), fragments)
        checked = audit.audit(self.imported, "edition.json", self.out / "balanced", "print-settings.json")
        self.assertTrue(checked["ok"], checked["errors"])
        path = self.imported / "print-settings.json"
        settings = json.loads(path.read_bytes())
        for key in ("widow_lines", "orphan_lines", "keep_image_caption"):
            settings.pop(key)
        path.write_bytes(reading.encoded(settings))
        old = self.build("implicit")
        settings.update(widow_lines=1, orphan_lines=1, keep_image_caption=False)
        path.write_bytes(reading.encoded(settings))
        explicit = self.build("explicit")
        self.assertEqual(old["outputs"], explicit["outputs"])

    def test_impossible_paragraph_constraints_refused_before_writes(self):
        self.edit([{"type": "paragraph", "text": " ".join(["long paragraph"] * 180)}], widow_lines=10, orphan_lines=10, leading_pt=30)
        with self.assertRaisesRegex(reading.BuildError, "Widow/orphan|widow/orphan"):
            self.build("impossible")
        self.assertFalse((self.out / "impossible").exists())

    def test_caption_group_moves_together_and_impossible_refused(self):
        from PIL import Image
        from pypdf import PdfReader
        Image.new("RGB", (100, 90), "navy").save(self.imported / "art.png")
        blocks = [{"type": "paragraph", "text": "Filler."} for _ in range(4)] + [{"type": "image", "asset_id": "art", "caption": "Caption wording stays beside its picture and remains intact."}]
        self.edit(blocks, keep_image_caption=True)
        path = self.imported / "edition.json"
        cfg = json.loads(path.read_bytes())
        cfg["assets"] = [{"id": "art", "path": "art.png", "role": "illustration", "alt": "Synthetic navy rectangle"}]
        path.write_bytes(reading.encoded(cfg))
        report = self.build("grouped")
        self.assertGreater(report["image_placements"][0]["page"], 1)
        self.assertEqual(report["image_placements"][0]["page"], report["text_placements"][-1]["fragments"][0]["page"])
        self.assertEqual(len(report["text_placements"][-1]["fragments"]), 1)
        reader = PdfReader(self.out / "grouped/imported-edition.pdf")
        self.assertIn("Caption wording", reader.pages[report["image_placements"][0]["page"] - 1].extract_text())
        section_path = self.imported / cfg["sections"][0]["source"]
        blocks[-1]["caption"] = " ".join(["Caption too long for a complete image group."] * 100)
        section_path.write_bytes(reading.encoded({"blocks": blocks}))
        with self.assertRaisesRegex(reading.BuildError, "complete caption"):
            self.build("impossible-caption")
        self.assertFalse((self.out / "impossible-caption").exists())


if __name__ == "__main__":
    unittest.main()
