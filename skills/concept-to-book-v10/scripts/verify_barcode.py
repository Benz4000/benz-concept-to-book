#!/usr/bin/env python3
"""Bounded digital ISBN/EAN-13 decode of supplied and actual cover-rendered bars."""
from __future__ import annotations
import argparse
import io
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
import build_reading_edition as reading
from aggregate_reviews import digest
from render_review import pdf_identity, output_target, render_pdf_files

BuildError, need = reading.BuildError, reading.need
VERSION = "1.0.0"
L = ("0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011")
G = ("0100111", "0110011", "0011011", "0100001", "0011101", "0111001", "0000101", "0010001", "0001001", "0010111")
R = tuple("".join("1" if bit == "0" else "0" for bit in value) for value in L)
PARITY = ("LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL")
LIMITATION = "Digital decode only. No ISO/IEC print-quality grade, physical scanner acceptance, printer acceptance, ISBN assignment/ownership or supplement validation. Supports one upright axis-aligned dark-on-light EAN-13 symbol, intact quiet zones, at least 2 pixels/module; no add-ons, rotation, skew, reverse, search, error correction or arbitrary barcode formats. Unsupported or unreadable input fails closed."


def valid_identifier(value):
    return isinstance(value, str) and len(value) == 13 and value.isascii() and value.isdigit() and value.startswith(("978", "979")) and sum(int(n) * (1 if i % 2 == 0 else 3) for i, n in enumerate(value)) % 10 == 0


def _row_decode(values):
    low, high = min(values), max(values)
    need(high - low >= 128, "Insufficient contrast")
    bits = [int(v < (low + high) / 2) for v in values]
    dark = [i for i, bit in enumerate(bits) if bit]
    need(dark, "No dark bars")
    start, stop = dark[0], dark[-1] + 1
    module = (stop - start) / 95
    need(module >= 2, "Less than 2 pixels/module")
    need(start >= 11 * module - 1 and len(bits) - stop >= 7 * module - 1, "Quiet zone clipped or insufficient")
    # Every observed transition must fit an integral 1..4-module run. Sampling
    # centers alone could conceal damage; run validation checks all row pixels.
    runs, prior, length = [], bits[start], 0
    for bit in bits[start:stop]:
        if bit != prior:
            runs.append(length)
            length, prior = 0, bit
        length += 1
    runs.append(length)
    need(len(runs) == 59, "Unexpected bar/space transitions")
    widths = [round(run / module) for run in runs]
    need(all(1 <= width <= 4 and abs(run / module - width) <= .42 for run, width in zip(runs, widths)) and sum(widths) == 95, "Damaged or unsupported bar widths")
    modules = "".join(str(1 - i % 2) * width for i, width in enumerate(widths))
    need(modules[:3] == "101" and modules[45:50] == "01010" and modules[-3:] == "101", "Invalid guard pattern")
    digits, parity = "", ""
    for offset in range(3, 45, 7):
        value = modules[offset:offset + 7]
        need(value in L or value in G, "Invalid left digit")
        table = L if value in L else G
        digits += str(table.index(value))
        parity += "L" if table is L else "G"
    need(parity in PARITY, "Invalid leading digit parity")
    for offset in range(50, 92, 7):
        value = modules[offset:offset + 7]
        need(value in R, "Invalid right digit")
        digits += str(R.index(value))
    value = str(PARITY.index(parity)) + digits
    need(valid_identifier(value), "Invalid ISBN-compatible prefix or EAN checksum")
    return value, module


def decode_ean13(data):
    """Return evidence; no guessed value is returned for unsupported images."""
    try:
        from PIL import Image
    except ImportError:
        return {"status": "capability-missing", "reason": "Pillow unavailable"}
    try:
        with Image.open(io.BytesIO(data)) as source:
            need(source.format in ("PNG", "JPEG") and getattr(source, "n_frames", 1) == 1, "Only static PNG/JPEG supported")
            need(0 < source.width * source.height <= 40_000_000 and source.height >= 12, "Unsupported image dimensions")
            # Transparent pixels are composited on white, matching the proof's paper.
            rgba = source.convert("RGBA")
            paper = Image.new("RGBA", source.size, "white")
            paper.alpha_composite(rgba)
            image = paper.convert("L")
            width, height = image.size
            rows = sorted({round(height * (.15 + i * .7 / 20)) for i in range(21)})
            successes, failures = [], []
            for row in rows:
                try:
                    value, module = _row_decode(list(image.crop((0, row, width, row + 1)).tobytes()))
                    successes.append({"row": row, "value": value, "module_width_px": module})
                except BuildError as exc:
                    failures.append({"row": row, "reason": str(exc)})
            need(len(successes) >= 3 and len({item["value"] for item in successes}) == 1, "No consistent ISBN EAN-13 across at least three scan rows")
            return {"status": "decoded", "symbology": "EAN-13", "value": successes[0]["value"], "pixels": [width, height], "scan_rows": successes, "unsupported_rows": failures}
    except (BuildError, OSError, ValueError) as exc:
        return {"status": "unreadable", "reason": str(exc)}


def _state(source, rendered, expected):
    if source["status"] == "capability-missing" or rendered["status"] == "capability-missing":
        return "capability-missing"
    if all(item["status"] == "decoded" and item["value"] == expected for item in (source, rendered)):
        return "verified"
    return "failed"


def verify_barcode(config_path, output_dir):
    config_path = Path(config_path).resolve(strict=True)
    inputs = reading.Inputs(config_path.parent)
    cfg = inputs.json(config_path.name)
    reading.keys(cfg, ("schema_version", "edition_identifier", "source_barcode", "source_barcode_sha256", "cover_pdf", "cover_pdf_sha256", "barcode_region_pt"), ("renderer", "dpi"))
    need(type(cfg["schema_version"]) is int and cfg["schema_version"] == 1, "Unsupported barcode schema")
    need(valid_identifier(cfg["edition_identifier"]), "Supply explicit checksum-valid 978/979 ISBN-13 edition identifier")
    source_bytes, pdf_bytes = inputs.read(cfg["source_barcode"]), inputs.read(cfg["cover_pdf"])
    need(reading.sha(source_bytes) == digest(cfg["source_barcode_sha256"]), "Supplied barcode SHA-256 mismatch")
    need(reading.sha(pdf_bytes) == digest(cfg["cover_pdf_sha256"]), "Cover PDF SHA-256 mismatch")
    identity = pdf_identity(pdf_bytes)
    need(identity["page_count"] == 1 and identity["pages"][0]["rotation"] == 0, "Cover needs one upright PDF page")
    media = identity["pages"][0]["media_box_pt"]
    need(media[:2] == [0, 0], "Cover MediaBox must begin at zero")
    region = cfg["barcode_region_pt"]
    need(isinstance(region, list) and len(region) == 4 and all(type(v) in (int, float) and math.isfinite(v) for v in region), "Region requires finite [x,y,width,height] points")
    x, y, w, h = region
    need(x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= media[2] and y + h <= media[3], "Barcode region exceeds actual cover page")
    dpi = cfg.get("dpi", 300)
    need(type(dpi) is int and 200 <= dpi <= 600, "Barcode dpi must be integer 200..600")
    need(w * h * (dpi / 72) ** 2 <= 40_000_000, "Rendered barcode crop exceeds 40 million pixels")
    target = output_target(output_dir, config_path.parent)
    target.mkdir(parents=True)
    source = decode_ean13(source_bytes)
    renderer = shutil.which(cfg.get("renderer", "pdftoppm"))
    renderer_record = None
    rendered = {"status": "capability-missing", "reason": "Existing pdftoppm unavailable; no installation attempted"}
    crop_record = None
    pdf = (config_path.parent / cfg["cover_pdf"]).resolve(strict=True)
    if renderer and Path(renderer).is_file():
        version = subprocess.run([renderer, "-v"], capture_output=True, timeout=15, check=False)
        need(version.returncode == 0, "Renderer version probe failed")
        factor = dpi / 72
        left, top = math.floor(x * factor), math.floor((media[3] - y - h) * factor)
        right, bottom = math.ceil((x + w) * factor), math.ceil((media[3] - y) * factor)
        crop_px = [left, top, right - left, bottom - top]
        renderer_record = {"path": str(Path(renderer).resolve()), "sha256": reading.sha(Path(renderer).read_bytes()), "version": (version.stderr + version.stdout).decode(errors="replace").strip(), "dpi": dpi, "crop_px": crop_px}
        native = render_pdf_files(renderer, pdf, target, [{"prefix": "rendered-barcode", "arguments": ["-f", "1", "-l", "1", "-r", str(dpi), "-x", str(left), "-y", str(top), "-W", str(right-left), "-H", str(bottom-top), "-singlefile", "-png"]}], cfg["cover_pdf_sha256"])[0]
        renderer_record["invocations"] = [native]
        renderer_record["workspace_policy"] = "Hash-verified PDF and native outputs use an isolated short temporary cwd and relative arguments; temporary paths are execution provenance, not persistent handoff dependencies."
        crop = target / "rendered-barcode.png"
        if native["returncode"] == 0 and crop.is_file() and crop.stat().st_size <= 32 * 1024 * 1024:
            crop_record = {"path": crop.name, "sha256": reading.sha(crop.read_bytes())}
            rendered = decode_ean13(crop.read_bytes())
        else:
            rendered = {"status": "unreadable", "reason": "Actual PDF region rendering failed", "renderer_stderr": native["stderr"]}
    manifest = {"schema_version": 1, "adapter": "verify-barcode", "version": VERSION, "edition_identifier": cfg["edition_identifier"], "source_barcode": {"path": str((config_path.parent / cfg["source_barcode"]).resolve()), "sha256": cfg["source_barcode_sha256"]}, "cover_pdf": {"path": str(pdf), "sha256": cfg["cover_pdf_sha256"]}, "barcode_region_pt": region, "renderer": renderer_record, "rendered_region": crop_record, "source_decode": source, "rendered_decode": rendered, "status": _state(source, rendered, cfg["edition_identifier"]), "physical_print_scanner_acceptance": "not-assessed", "limitations": LIMITATION, "inputs": inputs.manifest()}
    for item in inputs.manifest():
        need(reading.sha((config_path.parent / item["path"]).read_bytes()) == item["sha256"], "Source changed during barcode verification")
    (target / "manifest.json").write_bytes(reading.encoded(manifest))
    validate_barcode(target / "manifest.json")
    return manifest


def validate_barcode(manifest_path, source_barcode=None, cover_pdf=None):
    path = Path(manifest_path).resolve(strict=True)
    manifest = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reading.unique_object)
    need(manifest.get("schema_version") == 1 and manifest.get("adapter") == "verify-barcode", "Unsupported barcode manifest")
    need(valid_identifier(manifest["edition_identifier"]), "Invalid explicit edition identifier")
    source_data = None
    for key, override in (("source_barcode", source_barcode), ("cover_pdf", cover_pdf)):
        data = Path(override or manifest[key]["path"]).resolve(strict=True).read_bytes()
        need(reading.sha(data) == manifest[key]["sha256"], f"Barcode evidence invalidated: {key} changed")
        if key == "source_barcode":
            source_data = data
    source = decode_ean13(source_data)
    need(source == manifest["source_decode"], "Supplied barcode decode evidence inconsistent")
    rendered = manifest["rendered_decode"]
    if manifest["renderer"] is not None:
        renderer = manifest["renderer"]
        need(reading.sha(Path(renderer["path"]).resolve(strict=True).read_bytes()) == renderer["sha256"], "Barcode renderer binary changed")
    if manifest["rendered_region"] is not None:
        record = manifest["rendered_region"]
        crop = (path.parent / record["path"]).resolve(strict=True)
        need(crop.parent == path.parent and reading.sha(crop.read_bytes()) == record["sha256"], "Rendered barcode crop changed")
        rendered = decode_ean13(crop.read_bytes())
        need(rendered == manifest["rendered_decode"], "Rendered barcode decode evidence inconsistent")
    else:
        need(rendered["status"] in ("capability-missing", "unreadable"), "Missing rendered barcode evidence")
    need(manifest["status"] == _state(source, rendered, manifest["edition_identifier"]), "Barcode verification status inconsistent")
    need(manifest["physical_print_scanner_acceptance"] == "not-assessed", "Digital decode cannot establish physical scanner acceptance")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    try:
        result = verify_barcode(args.config, args.output_dir)
        print(json.dumps({"status": result["status"], "source_decode": result["source_decode"].get("value"), "rendered_decode": result["rendered_decode"].get("value")}))
        return 0 if result["status"] == "verified" else 2
    except (BuildError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f"Barcode verification rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
