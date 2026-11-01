"""Portable generated fixtures; no installs, network, or fake review acceptance."""
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
import build_cover as cover
import render_review as review
import build_reading_edition as reading

DEPS = all(importlib.util.find_spec(name) is not None for name in ("pypdf", "reportlab", "PIL"))


@unittest.skipUnless(DEPS, "Cover/review tests require reportlab, pypdf, Pillow")
class CoverReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.inputs = self.root / "inputs"
        self.inputs.mkdir()
        from reportlab.pdfgen import canvas
        from PIL import Image, ImageDraw
        import reportlab
        font = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
        if not font.is_file():
            self.skipTest("ReportLab Vera.ttf fixture unavailable")
        shutil.copyfile(font, self.inputs / "font.ttf")
        self.pdf(self.inputs / "interior.pdf", ["Actual interior first page", "Actual interior second page"])
        art = Image.new("RGB", (600, 900), "#15394b")
        d = ImageDraw.Draw(art)
        d.ellipse((90, 280, 510, 700), fill="#d2b87a")
        art.save(self.inputs / "art.png")
        barcode = Image.new("RGB", (200, 100), "white")
        d = ImageDraw.Draw(barcode)
        for x in range(10, 185, 7):
            d.rectangle((x, 8, x+2, 75), fill="black")
        barcode.save(self.inputs / "barcode.png")
        self.template = {"schema_version": 1, "units": "in", "edition": "paperback-test", "page_count": 2, "source": "Explicit synthetic test geometry; not publisher specifications", "sheet": [12.75, 9.25], "panels": {"back": {"trim": [.125, .125, 6, 9], "bleed": [0, 0, 6.25, 9.25], "safe": [.375, .375, 5.5, 8.5]}, "spine": {"trim": [6.125, .125, .5, 9], "bleed": [6.125, 0, .5, 9.25], "safe": [6.225, .375, .3, 8.5]}, "front": {"trim": [6.625, .125, 6, 9], "bleed": [6.5, 0, 6.25, 9.25], "safe": [6.875, .375, 5.5, 8.5]}}}
        self.write("template.json", self.template)
        self.config = {"schema_version": 1, "template": "template.json", "interior": {"path": "interior.pdf", "sha256": reading.sha((self.inputs / "interior.pdf").read_bytes()), "page_count": 2, "edition": "paperback-test"}, "fonts": [{"id": "body", "path": "font.ttf", "embedding_authorized": True}], "images": [{"id": "front-art", "path": "art.png", "role": "art", "panel": "front", "box": [6.625, .125, 6, 9], "usage_authorized": True}, {"id": "barcode-image", "path": "barcode.png", "role": "barcode", "panel": "back", "box": [3.5, .6, 2, 1], "usage_authorized": True}], "texts": [{"id": "title", "text": "THE QUIET SEA", "font": "body", "panel": "front", "box": [7, 7.3, 5.2, 1], "font_size_pt": 24, "leading_pt": 28}, {"id": "back-copy", "text": "A patient voyage across a changing sea.\nA paperback proof for rendered review.", "font": "body", "panel": "back", "box": [.5, 5.4, 5, 2], "font_size_pt": 12, "leading_pt": 16}, {"id": "spine-copy", "text": "THE QUIET SEA", "font": "body", "panel": "spine", "box": [6.24, 3, .25, 4], "font_size_pt": 9, "leading_pt": 11, "rotation": 90}]}
        self.write("cover.json", self.config)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        (self.inputs / name).write_bytes(reading.encoded(data))
        return self.inputs / name

    def pdf(self, path, pages):
        from reportlab.pdfgen import canvas
        c = canvas.Canvas(str(path), pagesize=(432, 648), invariant=1)
        for text in pages:
            c.drawString(40, 600, text)
            c.showPage()
        c.save()

    def renderer(self):
        executable = os.environ.get("BOOK_TEST_PDFTOPPM") or shutil.which("pdftoppm")
        if not executable:
            self.skipTest("Actual pdftoppm missing: set BOOK_TEST_PDFTOPPM or PATH")
        return executable

    def test_cover_actual_pdf_and_same_count_changed_pair(self):
        before = {p.name: reading.sha(p.read_bytes()) for p in self.inputs.iterdir()}
        output = self.root / "cover"
        result = cover.build_cover(self.inputs / "cover.json", output)
        self.assertEqual(result["audit"]["status"], "passed")
        self.assertIn("THE QUIET SEA", result["audit"]["extracted_text"])
        self.assertTrue(all(f["embedded"] for f in result["audit"]["fonts"]))
        self.assertEqual(len(result["audit"]["actual_images"]), 2)
        self.assertTrue(result["audit"]["actual_text_runs"])
        self.assertEqual(before, {p.name: reading.sha(p.read_bytes()) for p in self.inputs.iterdir()})
        cover.validate_cover_pair(output / "manifest.json")
        self.pdf(self.inputs / "interior.pdf", ["Changed actual first page", "Actual interior second page"])
        with self.assertRaisesRegex(reading.BuildError, "invalidated"):
            cover.validate_cover_pair(output / "manifest.json")

    def test_actual_layout_audit_rejects_displaced_pdf_text(self):
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import DecodedStreamObject, NameObject
        output = self.root / "cover"
        result = cover.build_cover(self.inputs / "cover.json", output)
        reader = PdfReader(output / "cover.pdf")
        page = reader.pages[0]
        stream = page.get_contents().get_data()
        # Change actual painted title transform without changing supplied copy.
        self.assertIn(b'1 0 0 1 504 525.6 cm', stream)
        stream = stream.replace(b'1 0 0 1 504 525.6 cm', b'1 0 0 1 300 525.6 cm', 1)
        obj = DecodedStreamObject()
        obj.set_data(stream)
        page[NameObject('/Contents')] = obj
        writer = PdfWriter()
        writer.add_page(page)
        wrong = self.root / "displaced.pdf"
        with wrong.open('wb') as handle:
            writer.write(handle)
        with self.assertRaisesRegex(reading.BuildError, "position"):
            cover.audit_cover(wrong, result['sheet_pt'], result['text_sequence'], result['expected_text_runs'])

    def test_reject_missing_template_geometry_and_edition_hash(self):
        for field, value in [("sha256", "0"*64), ("edition", "another-edition"), ("page_count", 99)]:
            cfg = copy.deepcopy(self.config)
            cfg["interior"][field] = value
            self.write("bad.json", cfg)
            with self.assertRaises(reading.BuildError):
                cover.build_cover(self.inputs / "bad.json", self.root / ("bad-" + field))
        template = copy.deepcopy(self.template)
        del template["panels"]["front"]["safe"]
        self.write("template.json", template)
        with self.assertRaises(reading.BuildError):
            cover.build_cover(self.inputs / "cover.json", self.root / "bad-geometry")

    def test_actual_interior_trim_must_match_cover_template(self):
        from reportlab.pdfgen import canvas
        c = canvas.Canvas(str(self.inputs / 'interior.pdf'), pagesize=(360, 576), invariant=1)
        for _ in range(2):
            c.drawString(30, 500, 'Actual 5 by 8 interior')
            c.showPage()
        c.save()
        self.config['interior']['sha256'] = reading.sha((self.inputs / 'interior.pdf').read_bytes())
        self.write('cover.json', self.config)
        with self.assertRaisesRegex(reading.BuildError, 'trim geometry'):
            cover.build_cover(self.inputs / 'cover.json', self.root / 'wrong-trim')

    def test_barcode_drawn_after_art_even_if_config_reversed(self):
        from PIL import Image
        Image.new('RGB', (200, 100), 'red').save(self.inputs / 'back-art.png')
        self.config['images'].reverse()
        self.config['images'].append({'id':'back-art','path':'back-art.png','role':'art','panel':'back','box':[3.5,.6,2,1],'usage_authorized':True})
        self.write('cover.json', self.config)
        result = cover.build_cover(self.inputs / 'cover.json', self.root / 'order')
        images = [p for p in result['placements'] if p['kind'] in ('art','barcode')]
        self.assertEqual(images[-1]['kind'], 'barcode')
        self.assertEqual(result['audit']['actual_images'][-1]['pixel_sha256'],images[-1]['pixel_sha256'])

    def test_jpeg_and_rgba_actual_embedded_pixels(self):
        from PIL import Image
        for mode,suffix in [('RGB','jpg'),('RGBA','png')]:
            color = (20,80,150,120) if mode=='RGBA' else (20,80,150)
            Image.new(mode,(600,900),color).save(self.inputs / ('variant.'+suffix))
            self.config['images'][0]['path']='variant.'+suffix
            self.write('cover.json',self.config)
            result=cover.build_cover(self.inputs/'cover.json',self.root/('variant-'+mode))
            self.assertEqual(result['audit']['status'],'passed')

    def test_reject_copy_overflow_permission_barcode_and_output(self):
        mutations = [lambda c: c["texts"][0].update(text="X"*300), lambda c: c["fonts"][0].update(embedding_authorized=False), lambda c: c["images"].pop(), lambda c: c["images"][0].update(usage_authorized=False), lambda c: c["texts"][0].update(box=[0, 0, 5, 1])]
        for index, mutation in enumerate(mutations):
            cfg = copy.deepcopy(self.config)
            mutation(cfg)
            self.write("bad.json", cfg)
            with self.assertRaises(reading.BuildError):
                cover.build_cover(self.inputs / "bad.json", self.root / f"bad-{index}")
        with self.assertRaises(reading.BuildError):
            cover.build_cover(self.inputs / "cover.json", self.inputs / "nested-output")

    def test_actual_render_pending_and_explicit_exact_review(self):
        cfg = {"schema_version": 1, "pdf": "interior.pdf", "renderer": self.renderer(), "dpi": 48}
        self.write("review.json", cfg)
        out = self.root / "review"
        manifest = review.render_review(self.inputs / "review.json", out)
        self.assertEqual(manifest["review_state"], "pending")
        self.assertEqual(len(manifest["previews"]), 2)
        self.assertTrue((out / "page-0001.png").read_bytes().startswith(b"\x89PNG"))
        cfg.update(dispositions=[{"page": p, "status": "accepted", "note": "Explicit test disposition"} for p in (1, 2)], disposition_pdf_sha256=manifest["pdf"]["sha256"], previous_manifest=str(out / "manifest.json"))
        self.write("review.json", cfg)
        accepted = review.render_review(self.inputs / "review.json", self.root / "review-accepted")
        self.assertEqual(accepted["review_state"], "accepted")
        self.assertTrue(all(c["pixel_equal"] for c in accepted["comparisons"]))
        self.assertTrue(all(c["state"] == "retained-evidence" for c in accepted["comparisons"]))
        manufactured = copy.deepcopy(accepted)
        manufactured['previews'] = []
        (out / 'manufactured.json').write_bytes(reading.encoded(manufactured))
        with self.assertRaisesRegex(reading.BuildError, 'rendered coverage'):
            review.validate_review(out / 'manufactured.json')
        manufactured = copy.deepcopy(accepted)
        manufactured['dispositions'][0]['status'] = 'fabricated-acceptance'
        accepted_path = self.root / 'review-accepted' / 'manifest.json'
        accepted_path.write_bytes(reading.encoded(manufactured))
        with self.assertRaisesRegex(reading.BuildError, 'disposition'):
            review.validate_review(accepted_path)
        (out / "page-0001.png").write_bytes(b"tampered")
        with self.assertRaisesRegex(reading.BuildError, "preview"):
            review.validate_review(out / "manifest.json")

    def test_changed_pdf_review_invalidated_neighbors_and_stale_dispositions(self):
        cfg = {"schema_version": 1, "pdf": "interior.pdf", "renderer": self.renderer(), "pages": [1], "dpi": 48}
        self.write("review.json", cfg)
        out = self.root / "before"
        old = review.render_review(self.inputs / "review.json", out)
        self.pdf(self.inputs / "interior.pdf", ["Changed first page", "Actual interior second page"])
        with self.assertRaisesRegex(reading.BuildError, "invalidated"):
            review.validate_review(out / "manifest.json")
        cfg["previous_manifest"] = str(out / "manifest.json")
        self.write("review.json", cfg)
        after = review.render_review(self.inputs / "review.json", self.root / "after")
        self.assertEqual(after["review_state"], "pending")
        self.assertIn(1, after["changed_pages"])
        self.assertEqual(after["affected_pages_and_neighbors"], [1, 2])
        self.assertEqual(after['possibly_affected_pages'], [1, 2])
        self.assertEqual(after['unverified_pages'], [1, 2])
        cfg.update(dispositions=[{"page": 1, "status": "accepted", "note": "Stale human review"}], disposition_pdf_sha256=old["pdf"]["sha256"])
        self.write("review.json", cfg)
        with self.assertRaisesRegex(reading.BuildError, "exact PDF"):
            review.render_review(self.inputs / "review.json", self.root / "stale")

    def test_missing_renderer_and_bounds_rejected(self):
        cfg = {"schema_version": 1, "pdf": "interior.pdf", "renderer": str(self.root / "missing-renderer")}
        self.write("review.json", cfg)
        with self.assertRaisesRegex(reading.BuildError, "unavailable"):
            review.render_review(self.inputs / "review.json", self.root / "missing")
        cfg.update(pages=[0])
        self.write("review.json", cfg)
        with self.assertRaises(reading.BuildError):
            review.render_review(self.inputs / "review.json", self.root / "bounds")


if __name__ == "__main__":
    unittest.main()
