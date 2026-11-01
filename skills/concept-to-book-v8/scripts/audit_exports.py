#!/usr/bin/env python3
"""Read-only audit of actual local exports against current explicit source inputs.

Exact regeneration is an additional bounded-adapter check, not a replacement for
actual PDF extraction, page/font/image inspection and HTML/EPUB parsing.
"""
from __future__ import annotations
import argparse
import io
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath
import build_reading_edition as reading


def safe_release(root, name):
    path = PurePosixPath(name)
    reading.need(isinstance(name, str) and name and not path.is_absolute() and "\\" not in name and ":" not in name and all(p not in ("", ".", "..") for p in name.split("/")), "Unsafe release path")
    target = (root / Path(*path.parts)).resolve(strict=True)
    reading.need(target.is_relative_to(root) and target.is_file(), "Release resource escapes release root")
    reading.need(target.stat().st_size <= reading.MAX_TOTAL, "Release resource exceeds 128 MiB")
    return target


def audit(input_root, config, release_root, settings=None):
    result = {"ok": False, "errors": [], "checks": [], "coverage": [], "actual_outputs": []}
    def check(condition, label):
        result["checks"].append({"check": label, "passed": bool(condition)})
        if not condition:
            result["errors"].append(label)
    try:
        root, release = Path(input_root).resolve(strict=True), Path(release_root).resolve(strict=True)
        reading.need(root.is_dir() and release.is_dir(), "Input and release roots must be existing directories")
        inputs = reading.Inputs(root)
        cfg, assets, font, sections = reading.prepare(inputs, config)
        manifest = json.loads(safe_release(release, "build-manifest.json").read_bytes(), object_pairs_hook=reading.unique_object)
        check(manifest.get("edition_id") == cfg["edition_id"], "manifest edition identity agrees with current config")
        check(manifest.get("metadata") == cfg["metadata"], "manifest metadata agrees with current config")
        actual_data = {}
        def read(name):
            if name not in actual_data:
                value = safe_release(release, name).read_bytes()
                actual_data[name] = value
                result["actual_outputs"].append({"path": name, "bytes": len(value), "sha256": reading.sha(value)})
            return actual_data[name]
        if manifest.get("formats") == ["pdf"]:
            reading.need(settings is not None, "PDF audit requires --settings relative to input-root")
            import build_print_edition as printing
            prepared = printing.prepare(inputs, config, settings)
            expected_pdf, expected_layout = printing.make_pdf(prepared)
            check(manifest.get("reading_order") == [s["id"] for s in sections], "manifest PDF reading order matches current config")
            filename = cfg["edition_id"] + ".pdf"
            data = read(filename)
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data), strict=True)
            check(not reader.is_encrypted, "actual PDF unencrypted")
            metadata = reader.metadata or {}
            for key, expected in (("/Title", cfg["metadata"]["title"]), ("/Author", cfg["metadata"]["author"]), ("/Subject", cfg["metadata"]["identifier"])):
                check(metadata.get(key) == expected, "actual PDF metadata " + key)
            check(reader.trailer["/Root"].get("/Lang") == cfg["metadata"]["language"], "actual PDF language")
            width, height = prepared[5]
            check(len(reader.pages) == expected_layout["page_count"], "actual PDF page count matches current layout")
            texts, image_fingerprints = [], []
            from PIL import Image
            def pixels(image):
                rgb = image.convert("RGB")
                return (rgb.width, rgb.height, reading.sha(rgb.tobytes()))
            required_images = []
            for section in sections:
                for block in section["blocks"]:
                    if block["type"] == "image":
                        with Image.open(io.BytesIO(assets[block["asset_id"]]["data"])) as image:
                            required_images.append(pixels(image))
            for n, page in enumerate(reader.pages, 1):
                check(abs(float(page.mediabox.width) - width) < .01 and abs(float(page.mediabox.height) - height) < .01 and list(page.mediabox.lower_left) == [0, 0], f"actual PDF page {n} MediaBox")
                check(list(page.cropbox) == list(page.mediabox) and page.get("/Rotate", 0) == 0, f"actual PDF page {n} CropBox and rotation")
                lines = (page.extract_text() or "").splitlines()
                if prepared[3]["footer"]["page_numbers"]:
                    check(bool(lines) and lines[-1].strip() == str(n), f"actual PDF page {n} footer")
                    if lines and lines[-1].strip() == str(n):
                        lines.pop()
                texts.extend(lines)
                fonts = page.get("/Resources", {}).get("/Font", {})
                for key, ref in fonts.items():
                    resource = ref.get_object()
                    descriptor = resource.get("/FontDescriptor")
                    if descriptor:
                        descriptor = descriptor.get_object()
                    check(bool(descriptor and descriptor.get("/FontFile2") and resource.get("/ToUnicode")), f"actual PDF page {n} font {key} embedded TTF with Unicode mapping")
                # Count actual paint operations, including reuse of one XObject.
                for operands, operator in page.get_contents().operations:
                    if operator == b"Do":
                        ref = page["/Resources"]["/XObject"][operands[0]].get_object()
                        reading.need(ref.get("/Subtype") == "/Image", "Nested PDF form XObjects unsupported by this adapter audit")
                        image_fingerprints.append(pixels(page.images[str(operands[0])].image))
            expected_text = []
            for section in sections:
                expected_text.append(section["title"])
                expected_text.extend(b.get("text", b.get("caption", "")) for b in section["blocks"])
            check(printing.normalize(" ".join(texts)) == printing.normalize(" ".join(expected_text)), "actual PDF extracted text and section order match current sources")
            check(sorted(image_fingerprints) == sorted(required_images), "actual PDF decoded image pixels and occurrence counts match current sources")
            check(data == expected_pdf, "actual PDF bytes match deterministic regeneration from current sources/settings/font")
            check(manifest.get("settings") == prepared[3], "manifest print settings match current settings")
            for field in ("page_count", "section_placements", "image_placements"):
                check(manifest.get(field) == expected_layout[field], "manifest " + field + " agrees with current layout")
            result["coverage"] += ["Actual PDF title, author, identifier in Subject, catalog language, extracted text/order, physical page numbers, MediaBox/CropBox, embedded TTF/ToUnicode, decoded image pixels, exact current-source regeneration", "Text normalization: NFC and whitespace collapse only; case/punctuation preserved. Latin LTR adapter only. JPEG pixel comparison uses Pillow decoded RGB; original JPEG/PNG container bytes cannot be recovered from PDF", "PDF byte regeneration requires compatible recorded ReportLab/Pillow versions; a mismatch is a failed reproducibility check, not automatically proof of content damage", "Visual appearance, glyph positioning, accessibility, physical manufacture, PDF/X, color/bleed and printer acceptance remain unverified"]
        else:
            check(manifest.get("formats") == cfg["formats"], "release formats match current config")
            expected, order = reading.make_outputs(cfg, assets, font, sections)
            check(manifest.get("reading_order") == order, "manifest reading order matches current config")
            actual = {name: read(name) for name in expected}
            if "epub" in cfg["formats"]:
                with zipfile.ZipFile(io.BytesIO(actual[cfg["edition_id"] + ".epub"])) as archive:
                    members = archive.infolist()
                    reading.need(sum(m.file_size for m in members) <= reading.MAX_TOTAL and len(members) <= 2000, "EPUB expanded resource limits exceeded")
                    reading.need(len({m.filename for m in members}) == len(members), "Duplicate EPUB ZIP resource names")
            # Parse actual document resources before comparing with freshly rendered source.
            reading.verify_outputs(actual, order, cfg)
            result["checks"].append({"check": "actual HTML section order / EPUB ZIP XML spine nav resources", "passed": True})
            for name, value in expected.items():
                check(actual[name] == value, "actual source-derived content/resource bytes: " + name)
            if "html" in cfg["formats"]:
                node = ET.fromstring(actual["html/index.html"])
                check(node.find(f"{{{reading.XHTML}}}head/{{{reading.XHTML}}}title").text == cfg["metadata"]["title"], "actual HTML title")
                header = node.find(f"{{{reading.XHTML}}}body/{{{reading.XHTML}}}header")
                check(header is not None and header.find(f"{{{reading.XHTML}}}h1").text == cfg["metadata"]["title"] and header.find(f"{{{reading.XHTML}}}p").text == cfg["metadata"]["author"], "actual HTML visible title and author")
                for section in sections:
                    exported = node.find(f".//{{{reading.XHTML}}}main/{{{reading.XHTML}}}section[@id='{section['id']}']")
                    wanted = ET.fromstring(reading.section_body(section, assets, ""))
                    # section_body is unnamespaced; compare text stream and paragraph/image sequence.
                    check(exported is not None and list(exported.itertext()) == list(wanted.itertext()), "actual HTML section text: " + section["id"])
                    if exported is not None:
                        check([n.get("src") for n in exported.findall(f".//{{{reading.XHTML}}}img")] == ["assets/" + assets[b["asset_id"]]["output_name"] for b in section["blocks"] if b["type"] == "image"], "actual HTML image placement: " + section["id"])
            if "epub" in cfg["formats"]:
                with zipfile.ZipFile(io.BytesIO(actual[cfg["edition_id"] + ".epub"])) as archive:
                    opf = ET.fromstring(archive.read("EPUB/package.opf"))
                    for tag, source in (("title", "title"), ("creator", "author"), ("identifier", "identifier"), ("language", "language")):
                        node = opf.find(f"{{{reading.OPF}}}metadata/{{http://purl.org/dc/elements/1.1/}}{tag}")
                        check(node is not None and node.text == cfg["metadata"][source], "actual EPUB metadata " + tag)
                    for section in sections:
                        page = ET.fromstring(archive.read(f"EPUB/content/{section['id']}.xhtml"))
                        exported = page.find(f".//{{{reading.XHTML}}}section")
                        wanted = ET.fromstring(reading.section_body(section, assets, "../"))
                        check(exported is not None and list(exported.itertext()) == list(wanted.itertext()), "actual EPUB section text: " + section["id"])
                    for asset in assets.values():
                        check(archive.read("EPUB/assets/" + asset["output_name"]) == asset["data"], "actual EPUB asset bytes: " + asset["id"])
            result["coverage"] += ["Actual HTML title/author/section text/image order and EPUB ZIP, XML, reading order, navigation and metadata inspected; all current-source-generated text, markup and asset bytes compared exactly", "HTML identifier audit unsupported: inherited HTML adapter does not serialize identifier. EPUB identifier checked explicitly", "No browser/reader appearance, EPUBCheck, accessibility or platform acceptance claim"]
        check(manifest.get("inputs") == inputs.manifest(), "manifest source hashes match current inputs")
        entries = manifest.get("outputs", [])
        check(isinstance(entries, list) and {e.get("path") for e in entries} == set(actual_data), "manifest output inventory matches actual expected outputs")
        for entry in entries:
            value = read(entry["path"])
            check(len(value) == entry.get("bytes") and reading.sha(value) == entry.get("sha256"), "actual output hash/size: " + entry["path"])
        result["manifest_sha256"] = reading.sha((release / "build-manifest.json").read_bytes())
        result["source_inputs"] = inputs.manifest()
    except Exception as exc:
        # Audit is a JSON-only command even for corrupt files or missing optional dependencies.
        result["errors"].append(f"{type(exc).__name__}: {exc}")
    result["ok"] = not result["errors"]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--config", required=True)
    parser.add_argument("--release-root", required=True, type=Path)
    parser.add_argument("--settings")
    args = parser.parse_args(argv)
    report = audit(args.input_root, args.config, args.release_root, args.settings)
    print(reading.encoded(report).decode("utf-8"), end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
