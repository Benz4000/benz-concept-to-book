#!/usr/bin/env python3
"""Assemble one bounded flat paperback wrap from explicit geometry and assets."""
from __future__ import annotations
import argparse
import io
import json
import math
import sys
import unicodedata
from pathlib import Path
import build_reading_edition as reading
from render_review import pdf_identity, output_target

BuildError, need = reading.BuildError, reading.need
VERSION = "1.0.0"


def number(value, label, low=0, high=3600):
    need(type(value) in (int, float) and math.isfinite(value) and low <= value <= high, f"Invalid {label}")
    return float(value)


def rect(value, scale, label):
    need(isinstance(value, list) and len(value) == 4, f"{label} must be [x,y,width,height]")
    result = [number(v, label) * scale for v in value]
    need(result[2] > 0 and result[3] > 0, f"{label} needs positive width and height")
    return result


def inside(a, b):
    return a[0] >= b[0] - .001 and a[1] >= b[1] - .001 and a[0]+a[2] <= b[0]+b[2]+.001 and a[1]+a[3] <= b[1]+b[3]+.001


def normalized(value):
    return " ".join(unicodedata.normalize("NFC", value).split())


def audit_cover(path, expected_size, expected_text, expected_runs=None, expected_images=None):
    from pypdf import PdfReader
    reader = PdfReader(str(path), strict=True)
    need(len(reader.pages) == 1 and not reader.is_encrypted, "Cover must be one unencrypted PDF page")
    page = reader.pages[0]
    need(all(abs(float(x)-v) < .001 for x,v in zip(page.mediabox, [0, 0, *expected_size])), "Cover media box mismatch")
    need(all(abs(float(x)-v) < .001 for x,v in zip(page.trimbox, [0, 0, *expected_size])), "Flat-wrap trim box mismatch")
    actual_runs, actual_images = [], []
    def operand(operator, operands, cm, tm):
        if operator == b"Do":
            resource = page["/Resources"]["/XObject"][operands[0]].get_object()
            need(resource.get("/Subtype") == "/Image", "Unsupported nonimage cover XObject")
            need(abs(cm[1]) < .001 and abs(cm[2]) < .001 and cm[0] > 0 and cm[3] > 0, "Unsupported image rotation/skew")
            raw = resource.get_data()
            if "/DCTDecode" in str(resource.get("/Filter", "")):
                from PIL import Image
                with Image.open(io.BytesIO(raw)) as image:
                    raw = image.tobytes()
            alpha = resource.get("/SMask")
            actual_images.append({"box_pt": [cm[4], cm[5], cm[0], cm[3]], "pixels": [int(resource["/Width"]), int(resource["/Height"])], "pixel_sha256": reading.sha(raw), "alpha_sha256": reading.sha(alpha.get_object().get_data()) if alpha else None})
    def visitor(text, cm, tm, font, size):
        if text.strip():
            actual_runs.append({"text": text.rstrip("\n"), "baseline_pt": [tm[4]*cm[0]+tm[5]*cm[2]+cm[4], tm[4]*cm[1]+tm[5]*cm[3]+cm[5]], "rotation_matrix": cm[:4], "font_size_pt": float(size), "font": str(font.get("/BaseFont")) if font else None})
    text = page.extract_text(visitor_text=visitor, visitor_operand_before=operand) or ""
    need(normalized(text) == normalized("\n".join(expected_text)), "Actual cover text extraction differs from supplied copy")
    fonts = []
    for name, reference in page["/Resources"].get("/Font", {}).items():
        font = reference.get_object()
        descriptor = font.get("/FontDescriptor")
        need(descriptor is not None, f"Unembedded or unsupported cover font {name}")
        descriptor = descriptor.get_object()
        need(any(key in descriptor for key in ("/FontFile", "/FontFile2", "/FontFile3")), f"Cover font is not embedded: {name}")
        fonts.append({"resource": str(name), "base_font": str(font.get("/BaseFont")), "embedded": True})
    need(fonts, "No actual cover fonts")
    if expected_runs is not None:
        need(len(actual_runs) == len(expected_runs), "Actual PDF text run count differs from planned layout")
        for actual, expected in zip(actual_runs, expected_runs):
            need(actual["text"] == expected["text"] and abs(actual["font_size_pt"]-expected["font_size_pt"]) < .001 and all(abs(a-b) < .01 for a,b in zip(actual["baseline_pt"], expected["baseline_pt"])) and all(abs(a-b) < .001 for a,b in zip(actual["rotation_matrix"], expected["rotation_matrix"])), "Actual PDF text position/font size/rotation differs from layout")
    if expected_images is not None:
        need(len(actual_images) == len(expected_images), "Actual PDF image count differs from placement plan")
        for actual, expected in zip(actual_images, expected_images):
            need(actual["pixels"] == expected["pixels"] and actual["pixel_sha256"] == expected["pixel_sha256"] and actual["alpha_sha256"] == expected["alpha_sha256"] and all(abs(a-b) < .01 for a,b in zip(actual["box_pt"], expected["box_pt"])), "Actual PDF image pixels/placement/dimensions differ from layout")
    return {"page_count": 1, "media_box_pt": [0, 0, *expected_size], "trim_box_pt": [0, 0, *expected_size], "fonts": fonts, "actual_text_runs": actual_runs, "actual_images": actual_images, "extracted_text": text, "extracted_text_sha256": reading.sha(text.encode("utf-8")), "status": "passed"}


def validate_cover_pair(manifest_path, interior_pdf=None):
    path = Path(manifest_path).resolve(strict=True)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    current = Path(interior_pdf or manifest["interior"]["absolute_path"]).resolve(strict=True)
    identity = pdf_identity(current.read_bytes())
    need(identity["sha256"] == manifest["interior"]["sha256"] and identity["page_count"] == manifest["interior"]["page_count"], "Cover/interior pair invalidated: interior hash or page count changed")
    cover = path.parent / "cover.pdf"
    need(cover.is_file() and reading.sha(cover.read_bytes()) == manifest["output"]["sha256"], "Cover output changed or missing")
    audit_cover(cover, manifest["sheet_pt"], manifest["text_sequence"], manifest["expected_text_runs"], [p for p in manifest["placements"] if p["kind"] in ("art", "barcode")])
    return manifest


def build_cover(config_path, output_dir):
    config_path = Path(config_path).resolve(strict=True)
    inputs = reading.Inputs(config_path.parent)
    cfg = inputs.json(config_path.name)
    reading.keys(cfg, ("schema_version", "template", "interior", "fonts", "images", "texts"))
    need(type(cfg["schema_version"]) is int and cfg["schema_version"] == 1, "Unsupported cover config schema")
    template = inputs.json(cfg["template"])
    reading.keys(template, ("schema_version", "units", "edition", "page_count", "sheet", "panels"), ("source",))
    need(template["schema_version"] == 1 and template["units"] in ("pt", "in", "mm"), "Unsupported template schema or units")
    reading.string(template["edition"], "edition")
    need(type(template["page_count"]) is int and 1 <= template["page_count"] <= 2000, "Template page count must be explicit")
    scale = {"pt": 1, "in": 72, "mm": 72 / 25.4}[template["units"]]
    need(isinstance(template["sheet"], list) and len(template["sheet"]) == 2, "sheet must be [width,height]")
    sheet = [number(v, "sheet", .01) * scale for v in template["sheet"]]
    need(max(sheet) <= 3600, "Sheet exceeds bounded 50-inch geometry")
    sheet_rect = [0, 0, *sheet]
    reading.keys(template["panels"], ("back", "spine", "front"))
    panels = {}
    for name, spec in template["panels"].items():
        reading.keys(spec, ("trim", "bleed", "safe"))
        panels[name] = {k: rect(v, scale, f"{name}.{k}") for k, v in spec.items()}
        p = panels[name]
        need(inside(p["safe"], p["trim"]) and inside(p["trim"], p["bleed"]) and inside(p["bleed"], sheet_rect), "Template safe/trim/bleed containment failed")
    back, spine, front = [panels[k]["trim"] for k in ("back", "spine", "front")]
    need(abs(back[0]+back[2]-spine[0]) < .001 and abs(spine[0]+spine[2]-front[0]) < .001, "Only adjacent back/spine/front flat wraps supported")
    need(all(abs(p[1]-back[1]) < .001 and abs(p[3]-back[3]) < .001 for p in (spine, front)) and abs(back[2]-front[2]) < .001, "Unsupported unequal trim panel geometry")
    interior = cfg["interior"]
    reading.keys(interior, ("path", "sha256", "page_count", "edition"))
    ident = pdf_identity(inputs.read(interior["path"]))
    need(ident["sha256"] == interior["sha256"] and ident["page_count"] == interior["page_count"], "Interior exact hash/page count mismatch")
    need(interior["page_count"] == template["page_count"] and interior["edition"] == template["edition"], "Template page-count/edition mismatch")
    for page in ident["pages"]:
        trim = page["trim_box_pt"]
        need(page["rotation"] == 0 and abs(trim[2]-trim[0]-front[2]) < .01 and abs(trim[3]-trim[1]-front[3]) < .01, "Interior page trim geometry differs from supplied cover template")
    need(isinstance(cfg["fonts"], list) and 1 <= len(cfg["fonts"]) <= 8, "Supply 1..8 fonts")
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from PIL import Image
    fonts = {}
    for item in cfg["fonts"]:
        reading.keys(item, ("id", "path", "embedding_authorized"))
        reading.identifier(item["id"])
        need(item["id"] not in fonts and item["embedding_authorized"] is True, "Duplicate font or missing font embedding authorization")
        data = inputs.read(item["path"])
        need(Path(item["path"]).suffix.lower() == ".ttf" and data[:4] == b"\x00\x01\x00\x00", "Only standalone TrueType fonts supported")
        info = reading.font_info(data, ".ttf")
        need(not info["fs_type"] & 0x0100, "Font prohibits subsetting")
        font = TTFont("Cover" + reading.sha(data)[:16], io.BytesIO(data), validate=1)
        pdfmetrics.registerFont(font)
        fonts[item["id"]] = font
    need(isinstance(cfg["images"], list) and 2 <= len(cfg["images"]) <= 12, "Supply actual cover art and barcode images")
    need(all(isinstance(item, dict) for item in cfg["images"]), "Image placements must be objects")
    need(isinstance(cfg["texts"], list) and 1 <= len(cfg["texts"]) <= 30, "Supply 1..30 copy blocks")
    placements, assets, ids = [], [], set()
    barcode_count, front_art = 0, 0
    # Draw the supplied barcode after every art image so later art cannot hide it.
    for item in sorted(cfg["images"], key=lambda item: item.get("role") == "barcode"):
        reading.keys(item, ("id", "path", "role", "panel", "box", "usage_authorized"))
        reading.identifier(item["id"])
        need(item["id"] not in ids, "Duplicate placement ID")
        ids.add(item["id"])
        need(item["role"] in ("art", "barcode") and item["panel"] in panels and item["usage_authorized"] is True, "Unsupported image role/panel or missing usage authorization")
        box = rect(item["box"], scale, "image.box")
        area = "safe" if item["role"] == "barcode" else "bleed"
        need(inside(box, panels[item["panel"]][area]), "Image exceeds declared panel area")
        if item["role"] == "barcode":
            need(item["panel"] == "back", "Supplied barcode must be on back")
            barcode_count += 1
        front_art += int(item["role"] == "art" and item["panel"] == "front")
        data = inputs.read(item["path"])
        need(Path(item["path"]).suffix.lower() in (".png", ".jpg", ".jpeg"), "Only PNG/JPEG images supported")
        with Image.open(io.BytesIO(data)) as image:
            need(image.format in ("PNG", "JPEG") and image.mode in ("RGB", "RGBA", "L"), "Unsupported image encoding/color mode")
            need(image.width * image.height <= 40_000_000 and getattr(image, "n_frames", 1) == 1, "Image dimensions/animation exceeds bound")
            dimensions = list(image.size)
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            pixel_sha = reading.sha(image.convert("RGB").tobytes() if image.mode == "RGBA" else image.tobytes())
            alpha_sha = reading.sha(image.getchannel("A").tobytes()) if image.mode == "RGBA" else None
        need(abs((dimensions[0] / dimensions[1]) / (box[2] / box[3]) - 1) <= .02, "Image aspect ratio differs from explicit placement; prepare crop externally")
        assets.append((data, box))
        placements.append({"id": item["id"], "kind": item["role"], "panel": item["panel"], "box_pt": box, "source": item["path"], "source_sha256": reading.sha(data), "pixels": dimensions, "pixel_sha256": pixel_sha, "alpha_sha256": alpha_sha})
    need(barcode_count == 1 and front_art >= 1, "Need exactly one supplied barcode and at least one front art image")
    layouts, expected, expected_runs = [], [], []
    for item in cfg["texts"]:
        reading.keys(item, ("id", "text", "font", "panel", "box", "font_size_pt", "leading_pt"), ("rotation", "color_rgb"))
        reading.identifier(item["id"])
        need(item["id"] not in ids, "Duplicate placement ID")
        ids.add(item["id"])
        text = reading.string(item["text"], "cover copy")
        need(len(text) <= 10000 and item["font"] in fonts and item["panel"] in panels, "Unsupported copy/font/panel")
        font = fonts[item["font"]]
        for ch in text:
            if ch in " \n":
                continue
            cat = unicodedata.category(ch)
            need(cat[0] in "LNPS" and (cat[0] != "L" or "LATIN" in unicodedata.name(ch, "")) and not 0xFB00 <= ord(ch) <= 0xFB06, "Cover supports simple Latin copy without shaping/combining marks")
            need(0 < font.face.charToGlyph.get(ord(ch), 0) < font.face.numGlyphs, f"Cover font missing glyph U+{ord(ch):04X}")
        size = number(item["font_size_pt"], "font_size_pt", 5, 120)
        leading = number(item["leading_pt"], "leading_pt", size * 1.1, 180)
        rotation = item.get("rotation", 0)
        need(type(rotation) is int and rotation in (0, 90), "Only 0/90 degree text supported")
        box = rect(item["box"], scale, "text.box")
        need(inside(box, panels[item["panel"]]["safe"]), "Copy exceeds declared safe area")
        # Copy cannot overlap barcode or another copy box; art may sit beneath copy.
        for other in placements:
            if other["kind"] in ("barcode", "text"):
                b = other["box_pt"]
                overlap = min(box[0]+box[2], b[0]+b[2]) > max(box[0], b[0])+.001 and min(box[1]+box[3], b[1]+b[3]) > max(box[1], b[1])+.001
                need(not overlap, "Text/barcode placement boxes overlap")
        width, height = (box[3], box[2]) if rotation == 90 else (box[2], box[3])
        lines = []
        for paragraph in text.split("\n"):
            current = ""
            for word in paragraph.split():
                need(pdfmetrics.stringWidth(word, font.fontName, size) <= width, "Unbreakable cover copy overflows box")
                candidate = (current + " " + word).strip()
                if current and pdfmetrics.stringWidth(candidate, font.fontName, size) > width:
                    lines.append(current)
                    current = word
                else:
                    current = candidate
            lines.append(current)
        ascent, descent = pdfmetrics.getAscentDescent(font.fontName, size)
        need(ascent - descent + (len(lines)-1)*leading <= height, "Cover copy vertically overflows box")
        color = item.get("color_rgb", [0, 0, 0])
        need(isinstance(color, list) and len(color) == 3, "color_rgb requires three components")
        color = [number(c, "color_rgb", 0, 1) for c in color]
        layouts.append((font.fontName, size, leading, rotation, box, lines, ascent, color))
        for n, line in enumerate(lines):
            if line:
                baseline = height-ascent-n*leading
                expected_runs.append({"text": line, "baseline_pt": [box[0]+box[2]-baseline, box[1]] if rotation == 90 else [box[0], box[1]+baseline], "rotation_matrix": [0, 1, -1, 0] if rotation == 90 else [1, 0, 0, 1], "font_size_pt": size})
        expected.append("\n".join(lines))
        placements.append({"id": item["id"], "kind": "text", "panel": item["panel"], "box_pt": box, "font": item["font"], "font_size_pt": size, "rotation": rotation, "lines": lines, "line_widths_pt": [pdfmetrics.stringWidth(line, font.fontName, size) for line in lines]})
    target = output_target(output_dir, config_path.parent)
    target.mkdir(parents=True)
    path = target / "cover.pdf"
    firstfont = next(iter(fonts.values())).fontName
    pdf = canvas.Canvas(str(path), pagesize=sheet, invariant=1, pageCompression=1, initialFontName=firstfont)
    pdf.setTitle("Flat paperback wrap proof: " + template["edition"])
    for data, box in assets:
        pdf.drawImage(ImageReader(io.BytesIO(data)), *box, mask="auto")
    for font, size, leading, rotation, box, lines, ascent, color in layouts:
        pdf.saveState()
        if rotation == 90:
            pdf.translate(box[0]+box[2], box[1])
            pdf.rotate(90)
            height = box[2]
        else:
            pdf.translate(box[0], box[1])
            height = box[3]
        pdf.setFont(font, size)
        pdf.setFillColorRGB(*color)
        for n, line in enumerate(lines):
            pdf.drawString(0, height-ascent-n*leading, line)
        pdf.restoreState()
    pdf.showPage()
    pdf.save()
    audit = audit_cover(path, sheet, expected, expected_runs, [p for p in placements if p["kind"] in ("art", "barcode")])
    manifest = {"schema_version": 1, "adapter": "flat-paperback-cover", "version": VERSION, "template": {"path": cfg["template"], "sha256": reading.sha(inputs.read(cfg["template"])), "facts": template}, "interior": dict(interior, absolute_path=str((config_path.parent / interior["path"]).resolve())), "sheet_pt": sheet, "panels_pt": panels, "placements": placements, "text_sequence": expected, "inputs": inputs.manifest(), "output": {"path": "cover.pdf", "sha256": reading.sha(path.read_bytes()), "bytes": path.stat().st_size}, "audit": audit, "review_state": "pending-rendered-human-review", "limitations": ["No publisher acceptance, PDF/X, color-management, jacket or case-wrap claim.", "Supplied barcode image is placed; encoded ISBN/content is not decoded or verified.", "Template geometry is supplied, never inferred from page count; verify against current printer template."]}
    manifest["expected_text_runs"] = expected_runs
    (target / "manifest.json").write_bytes(reading.encoded(manifest))
    (target / "layout-evidence.json").write_bytes(reading.encoded({"sheet_pt": sheet, "panels_pt": panels, "placements": placements, "actual_pdf_audit": audit}))
    # Detect source races as well as future pair mismatches.
    for item in inputs.manifest():
        need(reading.sha((config_path.parent / item["path"]).read_bytes()) == item["sha256"], "Source changed during cover build; discard output")
    validate_cover_pair(target / "manifest.json")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    try:
        result = build_cover(args.config, args.output_dir)
        print(json.dumps({"status": "created", "review_state": result["review_state"], "output": str(Path(args.output_dir).resolve())}))
        return 0
    except (BuildError, OSError, ValueError) as exc:
        print(f"Cover build rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
