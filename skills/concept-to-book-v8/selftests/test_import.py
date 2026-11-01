"""Portable CLI integration tests; synthetic public-domain text only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "import_manuscript.py"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
META = {"title": "Synthetic Lantern", "author": "Test Author", "identifier": "urn:test:lantern", "language": "en", "modified": "2026-01-01T00:00:00Z"}


class ManuscriptImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "input"
        self.output = self.base / "output"
        self.source.mkdir()
        self.output.mkdir()
        (self.source / "metadata.json").write_text(json.dumps(META), encoding="utf-8")

    def cli(self, name="book.md", output="imported", extra=(), success=True):
        command = [sys.executable, "-B", str(SCRIPT), "--input-root", str(self.source), "--input", name, "--metadata", "metadata.json", "--output-root", str(self.output), "--output-dir", output, *extra]
        result = subprocess.run(command, capture_output=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(result.returncode, 0 if success else 2, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def md(self, text="# First\n\n“Café”—Ω…\nA second line.\n\n## Second\n\n終わり。\n"):
        (self.source / "book.md").write_bytes(text.encode("utf-8"))

    def docx(self, body, additional=None):
        with zipfile.ZipFile(self.source / "book.docx", "w") as archive:
            archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
            archive.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
            archive.writestr("word/document.xml", f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>')
            for name, data in (additional or {}).items():
                archive.writestr(name, data)

    def heading(self, text="First"):
        return f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>{text}</w:t></w:r></w:p>'

    def paragraph(self, text):
        return f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'

    def output_bytes(self, directory):
        return {p.relative_to(directory).as_posix(): p.read_bytes() for p in directory.rglob("*") if p.is_file()}

    def test_markdown_preservation_order_hash_and_determinism(self):
        self.md()
        before = self.output_bytes(self.source)
        self.cli()
        self.cli(output="again")
        result = self.output / "imported"
        self.assertEqual(self.output_bytes(result), self.output_bytes(self.output / "again"))
        self.assertEqual(before, self.output_bytes(self.source))
        config = json.loads((result / "edition.json").read_text(encoding="utf-8"))
        self.assertEqual(config["metadata"], META)
        self.assertEqual([s["title"] for s in config["sections"]], ["First", "Second"])
        section = json.loads((result / "sections/section-0001.json").read_text(encoding="utf-8"))
        self.assertEqual(section["blocks"], [{"type": "paragraph", "text": "“Café”—Ω…\nA second line."}])
        manifest = json.loads((result / "import-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["inputs"][0]["sha256"], hashlib.sha256(before["book.md"]).hexdigest())
        self.assertEqual(len(manifest["coverage"]), 4)
        self.assertEqual(manifest["coverage"][1]["location"], "lines:3-4")
        for output in manifest["outputs"]:
            self.assertEqual(hashlib.sha256((result / output["path"]).read_bytes()).hexdigest(), output["sha256"])

    def test_docx_plain_runs_preserved(self):
        self.docx(self.heading("章 一") + '<w:p><w:r><w:t xml:space="preserve"> Café—</w:t></w:r><w:r><w:t>Ω… </w:t></w:r></w:p>' + self.heading("Second") + self.paragraph("Last."))
        self.cli("book.docx")
        section = json.loads((self.output / "imported/sections/section-0001.json").read_text(encoding="utf-8"))
        self.assertEqual(section["blocks"][0]["text"], " Café—Ω… ")

    def test_preflight_has_no_writes(self):
        self.md()
        before = self.output_bytes(self.source)
        report = self.cli(extra=["--preflight"])
        self.assertEqual(report["status"], "preflight_passed_no_outputs_written")
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertEqual(before, self.output_bytes(self.source))

    def test_unicode_separators_are_text_and_crlf_normalizes(self):
        self.md("# One\r\n\r\nA\u2028B\u0085C\u2029D\r\nnext\r\n")
        self.cli()
        section = json.loads((self.output / "imported/sections/section-0001.json").read_text(encoding="utf-8"))
        self.assertEqual(section["blocks"][0]["text"], "A\u2028B\u0085C\u2029D\nnext")

    def test_docx_inherited_emphasis_and_unknown_parts_refused(self):
        styles = f'<w:styles xmlns:w="{W}"><w:style w:type="paragraph" w:styleId="Normal"><w:rPr><w:i/></w:rPr></w:style></w:styles>'
        for additional in ({"word/styles.xml": styles}, {"word/glossary/document.xml": "<glossary/>"}):
            self.docx(self.heading() + self.paragraph("Text"), additional)
            report = self.cli("book.docx", success=False)
            self.assertTrue(report["unsupported_features"])

    def test_markdown_features_refused_with_locations(self):
        for text in ("*emphasis*", "[link](https://example.invalid)", "![image](x.png)", "| table |", "[^note]", "<b>HTML</b>", "```code", "- list", "    code", "raw\\escape", "&amp;"):
            with self.subTest(text=text):
                self.md("# One\n\n" + text + "\n")
                report = self.cli(success=False)
                self.assertEqual(report["unsupported_features"][0]["location"], "line:3")
                self.assertEqual(list(self.output.iterdir()), [])

    def test_docx_features_refused_with_locations(self):
        cases = [('<w:tbl/>', None), ('<w:p><w:hyperlink><w:r><w:t>link</w:t></w:r></w:hyperlink></w:p>', None), ('<w:p><w:r><w:rPr><w:i/></w:rPr><w:t>Italic</w:t></w:r></w:p>', None), ('<w:p><w:ins><w:r><w:t>change</w:t></w:r></w:ins></w:p>', None), ('<w:p><w:r><w:drawing/></w:r></w:p>', None), (self.paragraph("Plain"), {"word/footnotes.xml": "<notes/>"}), (self.paragraph("Plain"), {"word/media/image.png": b"image"})]
        for body, additional in cases:
            with self.subTest(body=body, additional=additional):
                self.docx(self.heading() + body, additional)
                report = self.cli("book.docx", success=False)
                self.assertTrue(report["unsupported_features"])
                self.assertTrue(report["unsupported_features"][0]["location"].startswith("word/"))
                self.assertEqual(list(self.output.iterdir()), [])

    def test_requires_heading_and_nonempty_sections(self):
        for text in ("A paragraph.", "# One\n", "Before.\n\n# One\n\nBody.", "# One\n\n# Two\n\nBody."):
            with self.subTest(text=text):
                self.md(text)
                self.cli(success=False)
                self.assertEqual(list(self.output.iterdir()), [])

    def test_path_traversal_and_absolute_refused(self):
        self.md()
        for path in ("../input/book.md", str(self.source / "book.md"), "sub/../book.md", "sub\\book.md"):
            with self.subTest(path=path):
                self.cli(path, success=False)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_no_overwrite_and_preserve_unrelated(self):
        self.md()
        self.cli()
        (self.output / "unrelated.txt").write_bytes(b"preserve")
        before = self.output_bytes(self.output)
        self.cli(success=False)
        self.assertEqual(before, self.output_bytes(self.output))

    def test_output_inside_input_and_bad_output_name_refused(self):
        self.md()
        old = self.output
        self.output = self.source
        self.cli(success=False)
        self.output = old
        for name in ("../escape", "NUL", "nested/name"):
            self.cli(output=name, success=False)

    def test_zip_traversal_dtd_and_expansion_bound(self):
        self.docx(self.heading() + self.paragraph("Text"), {"../escape": b"bad"})
        self.cli("book.docx", success=False)
        self.docx(self.heading() + self.paragraph("Text"), {"word/_rels/document.xml.rels": '<!DOCTYPE x [<!ENTITY y "bad">]><x/>'})
        self.cli("book.docx", success=False)
        with zipfile.ZipFile(self.source / "book.docx", "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("large.bin", b"0" * (32 * 1024 * 1024 + 1))
        self.cli("book.docx", success=False)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_invalid_metadata_and_xml_characters(self):
        self.md()
        for value in ({**META, "extra": "unsupported"}, {**META, "modified": "today"}, {**META, "title": "\u0000"}):
            (self.source / "metadata.json").write_text(json.dumps(value), encoding="utf-8")
            self.cli(success=False)
        (self.source / "metadata.json").write_text(json.dumps(META), encoding="utf-8")
        self.md("# One\n\nBad\x00character")
        self.cli(success=False)

    def test_symlink_escape_when_supported(self):
        outside = self.base / "outside.md"
        outside.write_text("# One\n\nText", encoding="utf-8")
        link = self.source / "link.md"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("OS/user does not permit symlink creation")
        self.cli("link.md", success=False)


if __name__ == "__main__":
    unittest.main()
