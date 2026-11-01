#!/usr/bin/env python3
"""Produce a bounded, deterministic interior proof PDF, never printer acceptance."""
from __future__ import annotations
import argparse
import io
import json
import re
import struct
import sys
import unicodedata
from pathlib import Path
import build_reading_edition as reading

BuildError = reading.BuildError
need = reading.need
import semantic_content as semantic
import rich_content as rich

VERSION = "3.0.0"
DEFAULTS = {
    "schema_version": 1, "trim_inches": [6, 9],
    "margins_inches": {"top": .65, "bottom": .65, "inner": .7, "outer": .6},
    "font_size_pt": 11, "leading_pt": 15, "heading_size_pt": 16,
    "paragraph_gap_pt": 6, "section_start": "new_page",
    "widow_lines": 1, "orphan_lines": 1, "keep_image_caption": False,
    "footer": {"page_numbers": True, "font_size_pt": 9, "offset_pt": 20},
}


def dependencies():
    try:
        import reportlab
        import pypdf
        from PIL import Image
    except ImportError as exc:
        raise BuildError("Print requires ReportLab, pypdf and Pillow; see requirements-print.txt") from exc
    return {"reportlab": reportlab.Version, "pypdf": pypdf.__version__, "Pillow": Image.__version__}


def number(value, label, low, high):
    need(type(value) in (int, float) and low <= value <= high, f"{label} must be {low}..{high}")
    return float(value)


def normalize(text):
    """Comparison policy: NFC Unicode, whitespace runs collapsed; no case/punctuation folding."""
    return " ".join(unicodedata.normalize("NFC", text).split())


def prepare(inputs, config_name, settings_name):
    config, assets, _, sections = reading.prepare(inputs, config_name)
    raw = inputs.json(settings_name)
    reading.keys(raw, ("schema_version", "font"), set(DEFAULTS) - {"schema_version"})
    need(raw["schema_version"] == 1 and type(raw["schema_version"]) is int, "Unsupported print settings schema")
    settings = dict(DEFAULTS, **raw)
    for field in ("widow_lines", "orphan_lines"):
        need(type(settings[field]) is int and 1 <= settings[field] <= 10, field + " must be integer 1..10")
    need(type(settings["keep_image_caption"]) is bool, "keep_image_caption must be boolean")
    reading.keys(settings["font"], ("path", "embedding_authorized"), ("variants",))
    need(settings["font"]["embedding_authorized"] is True, "Print font needs embedding_authorized:true")
    data = inputs.read(settings["font"]["path"])
    need(Path(settings["font"]["path"]).suffix.lower() == ".ttf", "Print supports standalone TrueType .ttf only")
    info = reading.font_info(data, ".ttf")
    need(data[:4] == b"\x00\x01\x00\x00", "CFF/OpenType outlines unsupported in print")
    need(not info["fs_type"] & 0x0100, "No-subsetting font embedding flag unsupported")
    need(config["metadata"]["language"].split("-")[0].lower() in ("en", "fr", "de", "es", "it", "pt", "nl"), "Print supports explicitly listed Latin-script languages only")
    need(isinstance(settings["trim_inches"], list) and len(settings["trim_inches"]) == 2, "trim_inches needs width,height")
    width, height = [number(v, "trim_inches", 3, 14) * 72 for v in settings["trim_inches"]]
    margins = settings["margins_inches"]
    reading.keys(margins, ("top", "bottom", "inner", "outer"))
    margins = {k: number(v, f"margin.{k}", .1, 5) * 72 for k, v in margins.items()}
    for name, low, high in (("font_size_pt", 6, 30), ("leading_pt", 7, 60), ("heading_size_pt", 8, 48), ("paragraph_gap_pt", 0, 60)):
        number(settings[name], name, low, high)
    need(settings["leading_pt"] >= settings["font_size_pt"] * 1.1, "leading_pt must be at least 1.1 times font_size_pt")
    need(settings["section_start"] in ("new_page", "recto", "continuous"), "Unsupported section_start")
    footer = settings["footer"]
    reading.keys(footer, ("page_numbers", "font_size_pt", "offset_pt"))
    need(type(footer["page_numbers"]) is bool, "footer.page_numbers must be boolean")
    number(footer["font_size_pt"], "footer.font_size_pt", 6, 18)
    number(footer["offset_pt"], "footer.offset_pt", 10, 100)
    need(not footer["page_numbers"] or footer["offset_pt"] + footer["font_size_pt"] < margins["bottom"], "Footer must fit below text frame")
    need(width - margins["inner"] - margins["outer"] >= 72 and height - margins["top"] - margins["bottom"] >= max(72, settings["heading_size_pt"] * 2 + settings["leading_pt"]), "Negative or insufficient available frame")
    dependencies()
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    name = "Proof" + reading.sha(data)[:16]
    try:
        font = TTFont(name, io.BytesIO(data), validate=1)
        pdfmetrics.registerFont(font)
    except Exception as exc:
        raise BuildError(f"Unsupported or malformed TrueType font: {exc}") from exc
    variants = settings["font"].get("variants", {})
    reading.keys(variants, (), ("italic", "bold", "bold_italic"))
    fonts = {"regular": {"name": name, "data": data, "sha256": reading.sha(data), **info}}
    parsed = {"regular": font}
    for variant, path in variants.items():
        blob = inputs.read(path)
        need(Path(path).suffix.lower() == ".ttf" and blob[:4] == b"\x00\x01\x00\x00", "Print variants require standalone TrueType")
        variant_info = reading.font_info(blob, ".ttf")
        need(not variant_info["fs_type"] & 0x0100, "No-subsetting font embedding flag unsupported")
        variant_name = "Proof" + reading.sha(blob)[:16]
        try:
            parsed[variant] = TTFont(variant_name, io.BytesIO(blob), validate=1)
            pdfmetrics.registerFont(parsed[variant])
        except Exception as exc:
            raise BuildError(f"Malformed variant {variant}: {exc}") from exc
        flags = parsed[variant].face.flags
        # Validate actual face metadata so assigning regular.ttf to bold cannot flatten semantics.
        need(bool(flags & 64) == (variant in ("italic", "bold_italic")), f"Variant {variant} italic face flag disagrees")
        need(bool(flags & 262144) == (variant in ("bold", "bold_italic")), f"Variant {variant} weight class disagrees")
        fonts[variant] = {"name": variant_name, "data": blob, "sha256": reading.sha(blob), **variant_info}
    texts = [(value, "regular") for value in list(config["metadata"].values()) + ["0123456789", "* * *"]]
    for section in sections:
        title = {"text": section["title"], **({"runs": section["title_runs"]} if "title_runs" in section else {})}
        texts.extend((r["text"], semantic.style(r)) for r in semantic.runs(title))
        for block in section["blocks"]:
            if block["type"] in ("paragraph", "heading", "endnote", "table"):
                texts.extend((r["text"], semantic.style(r)) for p in rich.leaves(block) for r in semantic.runs(p))
            elif block.get("caption"):
                texts.append((block["caption"], "regular"))
    for text, variant in texts:
        need(variant in parsed, f"Semantic content requires supplied font variant: {variant}")
        face = parsed[variant].face
        for ch in text:
            if ch.isspace():
                need(ch in " \t\r\n", "Unsupported whitespace/control glyph")
                continue
            glyph = face.charToGlyph.get(ord(ch), 0)
            need(type(glyph) is int and 0 < glyph < face.numGlyphs, f"Font {variant} missing glyph U+{ord(ch):04X}: absent, .notdef or out-of-range glyph index")
            category = unicodedata.category(ch)
            need(category[0] in "LNPS" and (category[0] != "L" or "LATIN" in unicodedata.name(ch, "")), f"Unsupported print character U+{ord(ch):04X}: Latin, numbers and punctuation only")
            need(not 0xFB00 <= ord(ch) <= 0xFB06, "Precomposed ligatures unsupported")
    from PIL import Image
    for asset in assets.values():
        try:
            with Image.open(io.BytesIO(asset["data"])) as im:
                need(im.format in ("PNG", "JPEG") and im.mode in ("1", "L", "LA", "P", "RGB", "RGBA"), "Unsupported image colorspace")
                need(im.width * im.height <= 40_000_000, "Print image exceeds 40 million pixels")
                im.load()
        except BuildError:
            raise
        except Exception as exc:
            raise BuildError(f"Image pixel decoding failed: {asset['id']}: {exc}") from exc
    return config, assets, sections, settings, {"name": name, "data": data, "sha256": reading.sha(data), **info, "variants": {k: {field: value for field, value in v.items() if field != "data"} for k, v in fonts.items()}, "subset": True, "inspection": "TrueType table bounds/embedding flags, printable glyph coverage, Latin-script limits and ReportLab parse checked"}, (width, height), margins


def make_pdf(prepared):
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.lib.utils import ImageReader
    config, assets, sections, settings, font, size, margins = prepared
    width, height = size
    frame_width = width - margins["inner"] - margins["outer"]
    bottom, top = margins["bottom"], height - margins["top"]
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=size, invariant=1, pageCompression=1, initialFontName=font["name"], initialFontSize=settings["font_size_pt"])
    meta = config["metadata"]
    c.setTitle(meta["title"])
    c.setAuthor(meta["author"])
    c.setSubject(meta["identifier"])
    c.setKeywords("interior proof; " + config["edition_id"])
    c.setCreator("concept-to-book-v11 build_print_edition " + VERSION)
    from reportlab.pdfbase.pdfdoc import PDFString
    c._doc.Catalog.Lang = PDFString(meta["language"])
    page, y, used = 1, top, False
    x_offset=0
    placements, image_placements, link_placements, text_placements, destinations = [], [], [], [], {}
    def left():
        return (margins["inner"] if page % 2 else margins["outer"]) + x_offset
    def finish():
        if settings["footer"]["page_numbers"]:
            c.setFont(font["name"], settings["footer"]["font_size_pt"])
            c.drawCentredString(width / 2, settings["footer"]["offset_pt"], str(page))
        c.showPage()
    def advance():
        nonlocal page, y, used
        finish()
        page += 1
        y, used = top, False
        need(page <= 5000, "Print exceeds 5000 pages")
    def wrapped(value, point_size):
        block = value if isinstance(value, dict) else {"text": value}
        # Preserve word joins across run boundaries; normalize whitespace exactly as extraction audit.
        chars = [(ch, semantic.style(run), ("uri", run["href"]) if "href" in run else ("note", run["note_id"]) if "note_id" in run else ("crossref",run["target_id"]) if "target_id" in run else None) for run in semantic.runs(block) for ch in run["text"]]
        words, word = [], []
        for ch, variant, link in chars:
            if ch.isspace():
                if word:
                    words.append(word)
                    word = []
            else:
                word.append((ch, variant, link))
        if word:
            words.append(word)
        def measure(chars):
            return sum(pdfmetrics.stringWidth(ch, font["variants"][variant]["name"], point_size) for ch, variant, _ in chars)
        lines, line = [], []
        for word in words:
            need(measure(word) <= frame_width, "Unbreakable word exceeds text frame; edit source or layout")
            candidate = line + ([(" ", line[-1][1], line[-1][2] if line[-1][2] == word[0][2] else None)] if line else []) + word
            if measure(candidate) > frame_width:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
        descent = min(pdfmetrics.getDescent(v["name"], point_size) for v in font["variants"].values())
        return lines, descent
    def text(value, point_size, leading, gap=0, paragraph=False, destination=None, backlink=None, locator=None):
        nonlocal y, used
        lines, descent = wrapped(value, point_size)
        capacity = int((top - bottom + descent + 1e-7) // leading)
        orphan, widow = settings["orphan_lines"], settings["widow_lines"]
        need(capacity >= 1, "Text line exceeds a full text frame")
        if paragraph and len(lines) > capacity:
            need(capacity >= max(orphan, widow), "Widow/orphan settings exceed full text frame capacity")
            # A feasible split must exist on some full frames, with the requested
            # minimum on both sides of every page boundary.
            minimum = max(orphan, widow)
            feasible = {0}
            for remaining in range(1, len(lines) + 1):
                if remaining <= capacity and remaining >= widow or any(remaining - n in feasible and remaining - n >= widow for n in range(minimum, min(capacity, remaining - 1) + 1)):
                    feasible.add(remaining)
            need(any(len(lines) - n in feasible for n in range(orphan, min(capacity, len(lines) - widow) + 1)), "Impossible widow/orphan combination for paragraph and frame")
        fragments, index = [], 0
        while index < len(lines):
            available = int((y - bottom + descent + 1e-7) // leading)
            remaining = len(lines) - index
            if remaining <= available:
                count = remaining
            elif not paragraph or (orphan == widow == 1):
                count = min(max(available, 0), remaining)
            elif remaining <= capacity:
                count = min(available, remaining - widow)
                if count < orphan:
                    count = 0
            else:
                minimum = max(orphan, widow) if index else orphan
                candidates = [n for n in range(minimum, min(max(available, 0), remaining - widow) + 1) if remaining - n in feasible]
                count = max(candidates, default=0)
            if count == 0:
                need(used or y < top, "Impossible widow/orphan paragraph split on an empty frame")
                advance()
                continue
            fragments.append({"page": page, "lines": count})
            for line in lines[index:index + count]:
                y -= leading
                for dest in destination if isinstance(destination,list) else [destination] if destination else []:
                    if dest not in destinations:
                        c.bookmarkHorizontalAbsolute(dest, y + point_size)
                        destinations[dest] = {"page": page, "top_pt": y + point_size}
                obj = c.beginText(left(), y)
                current, segment = None, ""
                x = left()
                link_start, active_link = x, None
                def finish_link(link, start_x, end_x):
                    if not link:
                        return
                    kind, target = link
                    rect = (start_x, y + descent, end_x, y + point_size)
                    if kind == "uri":
                        c.linkURL(target, rect, relative=0, thickness=0)
                    else:
                        c.linkAbsolute("Endnote" if kind == "note" else "Return to reference", target if kind=="crossref" else ("note-" if kind == "note" else "ref-") + target, rect, thickness=0)
                    link_placements.append({"page": page, "kind": kind, "target": target, "rect": list(rect)})
                for ch, variant, link in line + [("", None, None)]:
                    if link != active_link:
                        finish_link(active_link, link_start, x)
                        active_link, link_start = link, x
                    if link and link[0] == "note" and "ref-" + link[1] not in destinations:
                        key = "ref-" + link[1]
                        c.bookmarkHorizontalAbsolute(key, y + point_size)
                        destinations[key] = {"page": page, "top_pt": y + point_size}
                    if variant != current:
                        if segment:
                            obj.setFont(font["variants"][current]["name"], point_size)
                            obj.textOut(segment)
                        current, segment = variant, ""
                    segment += ch
                    if ch:
                        x += pdfmetrics.stringWidth(ch, font["variants"][variant]["name"], point_size)
                c.drawText(obj)
                if backlink:
                    finish_link(("return", backlink), left(), min(x, left() + pdfmetrics.stringWidth("[" + backlink + "]", font["name"], point_size)))
                    backlink = None
                used = True
            index += count
            if index < len(lines):
                advance()
        if locator:
            text_placements.append({"locator": locator, "line_count": len(lines), "fragments": fragments})
        y -= gap
    def image_size(asset_id):
        asset = assets[asset_id]
        scale = min(frame_width / asset["width_px"], (top - bottom - settings["leading_pt"]) / asset["height_px"], 1)
        return asset["width_px"] * scale, asset["height_px"] * scale
    def image(asset_id, section_id):
        nonlocal y, used
        asset = assets[asset_id]
        iw, ih = image_size(asset_id)
        if y - ih < bottom:
            advance()
        y -= ih
        x = left() + (frame_width - iw) / 2
        c.drawImage(ImageReader(io.BytesIO(asset["data"])), x, y, iw, ih, preserveAspectRatio=True, mask="auto")
        image_placements.append({"asset_id": asset_id, "section_id": section_id, "page": page, "x_pt": x, "y_pt": y, "width_pt": iw, "height_pt": ih, "source_sha256": reading.sha(asset["data"])})
        used = True
        y -= settings["paragraph_gap_pt"]
    def table_metrics(block):
        nonlocal frame_width
        original=frame_width;col=original/len(block["rows"][0]);heights=[]
        try:
            frame_width=col-8
            need(frame_width>=24,"Table columns leave insufficient text width")
            for row in block["rows"]:
                heights.append(max(sum(len(wrapped(p,settings["font_size_pt"])[0])*settings["leading_pt"]+settings["paragraph_gap_pt"] for p in cell) for cell in row)+8)
        finally:frame_width=original
        return col,heights
    def table(block,section_id,block_index):
        nonlocal frame_width,x_offset,y,used
        col,heights=table_metrics(block);total=sum(heights)
        need(total<=top-bottom,"Complete table exceeds one text frame; use another adapter or authorized layout")
        if y-total<bottom:advance()
        for aid in block.get('anchors',[]):
            c.bookmarkHorizontalAbsolute(aid,y)
            destinations[aid]={'page':page,'top_pt':y}
        original_width=frame_width;base_x=left();row_y=y
        for ri,(row,rh) in enumerate(zip(block["rows"],heights)):
            for ci,cell in enumerate(row):
                c.rect(base_x+ci*col,row_y-rh,col,rh,stroke=1,fill=0)
                frame_width=col-8;x_offset=ci*col+4;y=row_y-4
                for pi,p in enumerate(cell):
                    text(p,settings["font_size_pt"],settings["leading_pt"],settings["paragraph_gap_pt"],destination=p.get("anchors"),locator=f"{section_id}:block:{block_index+1}:row:{ri+1}:cell:{ci+1}:paragraph:{pi+1}")
            row_y-=rh
        frame_width=original_width;x_offset=0;y=row_y-settings["paragraph_gap_pt"];used=True
    def heading_size(block):
        return max(settings["font_size_pt"], settings["heading_size_pt"] - (block["level"] - 1))
    def heading_group_space(blocks, index):
        # Use the exact same wrapped lines, font widths/descent and image scale as painting.
        # Consecutive headings stay with the first line/painted block that follows them.
        occupied, required = 0, 0
        while index < len(blocks) and blocks[index]["type"] == "heading":
            block = blocks[index]
            point = heading_size(block)
            lines, descent = wrapped(block, point)
            occupied += len(lines) * point * 1.4
            required = max(required, occupied - descent)
            occupied += settings["paragraph_gap_pt"]
            index += 1
        if index < len(blocks):
            following = blocks[index]
            if following["type"] == "table":
                minimum_next=sum(table_metrics(following)[1])
            elif following["type"] == "image":
                minimum_next = image_size(following["asset_id"])[1]
                if settings["keep_image_caption"] and following.get("caption"):
                    lines, descent = wrapped(following["caption"], settings["font_size_pt"])
                    minimum_next += settings["paragraph_gap_pt"] + len(lines) * settings["leading_pt"] - descent
            else:
                value = "* * *" if following["type"] == "scene_break" else following
                lines, descent = wrapped(value, settings["font_size_pt"])
                minimum_next = settings["leading_pt"] * (min(settings["orphan_lines"], len(lines)) if following["type"] in ("paragraph", "endnote") else 1) - descent
            required = max(required, occupied + minimum_next)
        return required
    for section in sections:
        if used and settings["section_start"] != "continuous":
            advance()
        if settings["section_start"] == "recto" and page % 2 == 0:
            advance()
        if y - (settings["heading_size_pt"] * 1.4 + settings["leading_pt"] * 2) < bottom:
            advance()
        start = page
        text({"text": section["title"], **({"runs": section["title_runs"]} if "title_runs" in section else {})}, settings["heading_size_pt"], settings["heading_size_pt"] * 1.4, settings["leading_pt"], destination=section.get("anchors"))
        for block_index, block in enumerate(section["blocks"]):
            if block["type"] in ("paragraph", "endnote"):
                nid = block.get("id") if block["type"] == "endnote" else None
                paragraphs=block.get("paragraphs",[block])
                for pi,p in enumerate(paragraphs):
                    text(p, settings["font_size_pt"], settings["leading_pt"], settings["paragraph_gap_pt"], paragraph=True, destination=(["note-"+nid] if nid and pi==0 else [])+block.get("anchors",[]), backlink=nid if pi==0 else None, locator=f"{section['id']}:block:{block_index + 1}"+(f":paragraph:{pi+1}" if len(paragraphs)>1 else ""))
            elif block["type"] == "table":
                table(block,section["id"],block_index)
            elif block["type"] == "heading":
                required = heading_group_space(section["blocks"], block_index)
                need(required <= top - bottom, "Nested heading and minimum following content exceed a full text frame; edit heading or layout")
                if y - required < bottom:
                    advance()
                point = heading_size(block)
                text(block, point, point * 1.4, settings["paragraph_gap_pt"],destination=block.get("anchors"))
            elif block["type"] == "scene_break":
                text("* * *", settings["font_size_pt"], settings["leading_pt"], settings["paragraph_gap_pt"])
            else:
                if settings["keep_image_caption"] and block.get("caption"):
                    lines, descent = wrapped(block["caption"], settings["font_size_pt"])
                    required = image_size(block["asset_id"])[1] + settings["paragraph_gap_pt"] + len(lines) * settings["leading_pt"] - descent
                    need(required <= top - bottom, "Image and complete caption exceed full text frame; adjust layout/image or disable keep_image_caption")
                    if y - required < bottom:
                        advance()
                image(block["asset_id"], section["id"])
                if block.get("caption"):
                    text(block["caption"], settings["font_size_pt"], settings["leading_pt"], settings["paragraph_gap_pt"], locator=f"{section['id']}:caption:{block_index + 1}")
        placements.append({"id": section["id"], "part": section["part"], "start_page": start, "end_page": page})
    finish()
    c.save()
    return buffer.getvalue(), {"page_count": page, "section_placements": placements, "image_placements": image_placements, "link_placements": link_placements, "text_placements": text_placements, "destinations": destinations}


def build(input_root, config_name, settings_name, output_root, output_dir, preflight=False):
    input_root, output_root = Path(input_root).resolve(strict=True), Path(output_root).resolve(strict=True)
    need(input_root.is_dir() and output_root.is_dir(), "Both roots must be existing directories")
    need(not output_root.is_relative_to(input_root), "output-root must be outside input-root")
    need(isinstance(output_dir, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", output_dir) and output_dir.lower() not in reading.DEVICE_NAMES, "output-dir must be a safe new directory name")
    destination = output_root / output_dir
    need(not destination.exists() and not destination.is_symlink(), "Output directory already exists; overwriting is forbidden")
    inputs = reading.Inputs(input_root)
    prepared = prepare(inputs, config_name, settings_name)
    config, assets, sections, settings, font, size, _ = prepared
    # Preflight performs layout and actual in-memory PDF checks; writes no files.
    data, layout = make_pdf(prepared)
    from pypdf import PdfReader
    actual = PdfReader(io.BytesIO(data), strict=True)
    need(len(actual.pages) == layout["page_count"], "Generated PDF page count mismatch")
    report = {"schema_version": 1, "builder_version": VERSION, "builder_sha256": reading.sha(Path(__file__).read_bytes()), "edition_id": config["edition_id"], "metadata": config["metadata"], "formats": ["pdf"], "settings": settings, "inputs": inputs.manifest(), "dependencies": dependencies(), "font": {k: v for k, v in font.items() if k not in ("data", "name")}, "reading_order": [s["id"] for s in sections], "trim_points": list(size), **layout, "cover_policy": "front-cover asset excluded: interior proof only", "checks": {"layout": "passed_bounded_frames", "pdf_parse": "passed", "visual_review": "unrun", "printer_acceptance": "unsupported", "pdf_x": "unsupported"}, "limitations": ["Latin-script LTR paragraphs and PNG/JPEG only; no shaping, lists, tables, bleed, color profiles, PDF/X or cover wrap", "Footer numbers are physical page numbers, including blank recto pages", "Configurable minimum widow/orphan lines and whole image-caption groups only; no hyphenation, page footnotes, accessible-PDF or manufacturing guarantee"], "outputs": [{"path": config["edition_id"] + ".pdf", "bytes": len(data), "sha256": reading.sha(data)}], "manifest_hash_policy": "build-manifest.json excludes itself"}
    if preflight:
        return dict(report, status="preflight_passed_no_outputs_written")
    destination.mkdir(exist_ok=False)
    target = destination / report["outputs"][0]["path"]
    with target.open("xb") as stream:
        stream.write(data)
    need(reading.sha(target.read_bytes()) == reading.sha(data), "PDF write readback mismatch")
    report["status"] = "interior_proof_built_visual_review_required"
    with (destination / "build-manifest.json").open("xb") as stream:
        stream.write(reading.encoded(report))
    return dict(report, output_directory=str(destination))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--config", required=True)
    parser.add_argument("--settings", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = build(args.input_root, args.config, args.settings, args.output_root, args.output_dir, args.preflight)
        print(reading.encoded(report).decode("utf-8"), end="")
        return 0
    except (BuildError, OSError, ValueError, TypeError, KeyError, struct.error) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
