#!/usr/bin/env python3
"""Create hash-bound, actual Poppler previews. Human review remains explicit."""
from __future__ import annotations
import argparse
import html
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote
import build_reading_edition as reading

BuildError, need = reading.BuildError, reading.need
VERSION = "1.0.0"


def pdf_identity(data):
    from pypdf import PdfReader
    need(data.startswith(b"%PDF-"), "Expected actual PDF")
    reader = PdfReader(io.BytesIO(data), strict=True)
    need(not reader.is_encrypted, "Encrypted PDF unsupported")
    need(0 < len(reader.pages) <= 2000, "PDF must have 1..2000 pages")
    pages = []
    for index, page in enumerate(reader.pages, 1):
        box = [float(v) for v in page.mediabox]
        need(0 < box[2] - box[0] <= 3600 and 0 < box[3] - box[1] <= 3600, "Unsupported PDF page geometry")
        pages.append({"page": index, "media_box_pt": box, "trim_box_pt": [float(v) for v in page.trimbox], "rotation": page.rotation, "text_sha256": reading.sha((page.extract_text() or "").encode("utf-8"))})
    return {"sha256": reading.sha(data), "page_count": len(pages), "pages": pages}


def output_target(output_dir, input_root):
    target = Path(output_dir).resolve()
    need(not target.exists(), "Output directory must be new; no overwrite")
    need(not target.is_relative_to(input_root) and not input_root.is_relative_to(target), "Output must be outside and not contain input directory")
    return target


def validate_review(manifest_path, pdf_path=None):
    """Recheck artifact identity; never infer human acceptance from images."""
    path = Path(manifest_path).resolve(strict=True)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    need(manifest.get("schema_version") == 1 and manifest.get("adapter") == "render-review", "Unsupported review manifest")
    pdf = Path(pdf_path or manifest["pdf_path"]).resolve(strict=True)
    identity = pdf_identity(pdf.read_bytes())
    need(identity == manifest["pdf"], "Review invalidated: PDF hash/page identity changed")
    need(isinstance(manifest.get("previews"), list) and manifest["previews"], "Review has no actual rendered coverage")
    rendered = set()
    for item in manifest["previews"]:
        reading.keys(item, ("page", "path", "sha256"))
        need(type(item["page"]) is int and 1 <= item["page"] <= identity["page_count"] and item["page"] not in rendered, "Invalid or duplicate rendered page")
        rendered.add(item["page"])
        local = path.parent / item["path"]
        need(local.resolve().parent == path.parent, "Unsafe preview path")
        need(local.is_file() and reading.sha(local.read_bytes()) == item["sha256"], "Review preview missing or changed")
    for item in manifest.get("comparisons", []):
        for label in ("previous", "diff"):
            if label + "_path" in item:
                local = (path.parent / item[label + "_path"]).resolve()
                need(local.parent == path.parent and local.is_file() and reading.sha(local.read_bytes()) == item[label + "_sha256"], "Comparison preview missing or changed")
    dispositions = manifest.get("dispositions", [])
    need(isinstance(dispositions, list), "Invalid dispositions")
    for item in dispositions:
        reading.keys(item, ("page", "status", "note"))
        need(type(item["page"]) is int and item["page"] in rendered and item["status"] in ("accepted", "changes-required"), "Invalid or unrendered disposition")
        reading.string(item["note"], "review note")
    need(not dispositions or manifest.get("disposition_pdf_sha256") == identity["sha256"], "Disposition PDF hash mismatch")
    reviewed = {d["page"] for d in dispositions}
    need(len(reviewed) == len(dispositions), "Duplicate disposition page")
    expected_state = "pending"
    if reviewed == set(range(1, identity["page_count"] + 1)):
        expected_state = "changes-required" if any(d["status"] == "changes-required" for d in dispositions) else "accepted"
    need(manifest["review_state"] == expected_state, "Review state inconsistent with exact coverage")
    return manifest


def render_review(config_path, output_dir):
    config_path = Path(config_path).resolve(strict=True)
    inputs = reading.Inputs(config_path.parent)
    cfg = inputs.json(config_path.name)
    reading.keys(cfg, ("schema_version", "pdf"), ("renderer", "pages", "dpi", "previous_manifest", "dispositions", "disposition_pdf_sha256"))
    need(type(cfg["schema_version"]) is int and cfg["schema_version"] == 1, "Unsupported render review schema")
    identity = pdf_identity(inputs.read(cfg["pdf"]))
    count = identity["page_count"]
    pages = cfg.get("pages", list(range(1, count + 1)))
    need(isinstance(pages, list) and pages and len(pages) <= 200 and all(type(p) is int and 1 <= p <= count for p in pages) and len(set(pages)) == len(pages), "Select 1..200 distinct existing pages")
    pages = sorted(pages)
    dpi = cfg.get("dpi", 72)
    need(type(dpi) is int and 36 <= dpi <= 150, "dpi must be integer 36..150")
    pixels = sum((identity["pages"][p-1]["media_box_pt"][2] - identity["pages"][p-1]["media_box_pt"][0]) * (identity["pages"][p-1]["media_box_pt"][3] - identity["pages"][p-1]["media_box_pt"][1]) * (dpi / 72) ** 2 for p in pages)
    need(pixels <= 120_000_000, "Render selection exceeds 120 million pixels")
    renderer = shutil.which(cfg.get("renderer", "pdftoppm"))
    need(renderer and Path(renderer).is_file(), "pdftoppm unavailable; supply explicit executable or PATH (no installation attempted)")
    version = subprocess.run([renderer, "-v"], capture_output=True, timeout=15, check=False)
    need(version.returncode == 0, "Renderer version probe failed")
    prior = None
    prior_path = None
    if cfg.get("previous_manifest"):
        prior_path = Path(cfg["previous_manifest"])
        if not prior_path.is_absolute():
            prior_path = config_path.parent / prior_path
        prior_path = prior_path.resolve(strict=True)
        need(prior_path.stat().st_size <= 8 * 1024 * 1024, "Prior review manifest exceeds bound")
        prior = json.loads(prior_path.read_text(encoding="utf-8"))
        need(prior.get("schema_version") == 1 and isinstance(prior.get("previews"), list), "Unsupported prior review")
    dispositions = cfg.get("dispositions", [])
    need(isinstance(dispositions, list), "dispositions must be a list")
    need(not dispositions or cfg.get("disposition_pdf_sha256") == identity["sha256"], "Explicit dispositions must bind the exact PDF SHA-256")
    seen = set()
    for item in dispositions:
        reading.keys(item, ("page", "status", "note"))
        need(type(item["page"]) is int and item["page"] in pages and item["page"] not in seen, "Disposition page must be unique and rendered")
        seen.add(item["page"])
        need(item["status"] in ("accepted", "changes-required"), "Unsupported review disposition")
        reading.string(item["note"], "review note")
    target = output_target(output_dir, config_path.parent)
    target.mkdir(parents=True)
    pdf = (config_path.parent / cfg["pdf"]).resolve(strict=True)
    previews, comparisons = [], []
    changed = set()
    possibly_affected = set()
    if prior:
        oldpages = prior.get("pdf", {}).get("pages", [])
        changed = {p for p in range(1, count + 1) if p > len(oldpages) or oldpages[p-1] != identity["pages"][p-1]}
        if prior.get("pdf", {}).get("sha256") != identity["sha256"]:
            # Text/boxes cannot localize graphic changes on unrendered pages.
            possibly_affected = set(range(1, count + 1))
    affected = {p + delta for p in changed for delta in (-1, 0, 1) if 1 <= p + delta <= count}
    from PIL import Image, ImageChops
    for p in pages:
        prefix = target / f"page-{p:04d}"
        result = subprocess.run([renderer, "-f", str(p), "-l", str(p), "-r", str(dpi), "-singlefile", "-png", str(pdf), str(prefix)], capture_output=True, timeout=90, check=False)
        png = prefix.with_suffix(".png")
        need(result.returncode == 0 and png.is_file(), f"Renderer failed for page {p}: {result.stderr.decode(errors='replace')[:400]}")
        need(png.stat().st_size <= 32 * 1024 * 1024, "Preview too large")
        with Image.open(png) as im:
            im.verify()
        previews.append({"page": p, "path": png.name, "sha256": reading.sha(png.read_bytes())})
        if prior:
            previous = next((v for v in prior["previews"] if v.get("page") == p), None)
            record = {"page": p, "state": "affected-neighbor" if p in affected else "unverified", "previous_preview_verified": False}
            if previous and isinstance(previous.get("path"), str):
                old = (prior_path.parent / previous["path"]).resolve()
                if old.parent == prior_path.parent and old.is_file() and old.stat().st_size <= 32 * 1024 * 1024 and reading.sha(old.read_bytes()) == previous.get("sha256"):
                    oldcopy = target / f"previous-{p:04d}.png"
                    shutil.copyfile(old, oldcopy)
                    record.update(previous_preview_verified=True, previous_path=oldcopy.name, previous_sha256=previous["sha256"])
                    with Image.open(oldcopy) as a, Image.open(png) as b:
                        need(a.width * a.height <= 120_000_000, "Previous preview exceeds pixel bound")
                        if a.size == b.size:
                            diff = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
                            same = diff.getbbox() is None
                            diffpath = target / f"diff-{p:04d}.png"
                            diff.save(diffpath)
                            record.update(pixel_equal=same, diff_path=diffpath.name, diff_sha256=reading.sha(diffpath.read_bytes()))
                            if not same:
                                changed.add(p)
                            elif prior.get("pdf") == identity and prior.get("renderer", {}).get("version") == (version.stderr + version.stdout).decode(errors="replace").strip() and prior.get("dpi") == dpi:
                                record["state"] = "retained-evidence"
            comparisons.append(record)
    affected = {p + delta for p in changed for delta in (-1, 0, 1) if 1 <= p + delta <= count}
    for item in comparisons:
        if item["page"] in affected:
            item["state"] = "affected-page" if item["page"] in changed else "affected-neighbor"
    state = "pending"
    if seen == set(range(1, count + 1)):
        state = "changes-required" if any(d["status"] == "changes-required" for d in dispositions) else "accepted"
    manifest = {"schema_version": 1, "adapter": "render-review", "version": VERSION, "pdf_path": str(pdf), "pdf": identity, "renderer": {"path": str(Path(renderer).resolve()), "version": (version.stderr + version.stdout).decode(errors="replace").strip()}, "dpi": dpi, "previews": previews, "comparisons": comparisons, "previous_manifest_sha256": reading.sha(prior_path.read_bytes()) if prior_path else None, "changed_pages": sorted(changed), "possibly_affected_pages": sorted(possibly_affected), "unverified_pages": sorted(set(range(1, count + 1)) - {c["page"] for c in comparisons if c.get("state") == "retained-evidence"}), "change_detection": "Changed pages have observed text/box/pixel differences. A changed document hash leaves every current page possibly affected; equal pixels do not establish semantic equivalence.", "affected_pages_and_neighbors": sorted(affected), "dispositions": dispositions, "disposition_pdf_sha256": cfg.get("disposition_pdf_sha256"), "review_state": state, "inputs": inputs.manifest(), "limitations": "Pixel comparisons do not prove semantic equivalence; explicit human dispositions are required."}
    for item in inputs.manifest():
        need(reading.sha((config_path.parent / item["path"]).read_bytes()) == item["sha256"], "Source changed during rendering; discard output")
    (target / "manifest.json").write_bytes(reading.encoded(manifest))
    rows = []
    for v in previews:
        comparison = next((c for c in comparisons if c["page"] == v["page"]), {})
        imgs = ''.join(f'<figure><figcaption>{html.escape(label)}</figcaption><img src="{quote(name, safe="")}" alt="{html.escape(label, quote=True)}"></figure>' for label, name in [("Current page " + str(v["page"]), v["path"])] + ([("Previous", comparison["previous_path"])] if "previous_path" in comparison else []) + ([("Pixel difference", comparison["diff_path"])] if "diff_path" in comparison else []))
        rows.append(f'<section><h2>Page {v["page"]}</h2><p>{html.escape(comparison.get("state", "unverified"))}</p><div>{imgs}</div></section>')
    coverage = '<p>Rendered pages: ' + html.escape(', '.join(map(str, pages))) + ' of ' + str(count) + '.</p><p>Possibly affected pages requiring recheck: ' + html.escape(', '.join(map(str, manifest['possibly_affected_pages'])) or 'none detected') + '.</p><p>Pages without retained exact prior comparative evidence: ' + html.escape(', '.join(map(str, manifest['unverified_pages'])) or 'none') + '.</p>'
    (target / "review.html").write_text('<!doctype html><meta charset="utf-8"><title>Rendered PDF review</title><style>body{font-family:sans-serif}section div{display:flex;gap:1rem}figure{margin:0;max-width:48%}img{max-width:100%;border:1px solid #777}</style><h1>Rendered PDF review</h1><p>Review state: ' + html.escape(state) + '</p><p>PDF SHA-256: ' + identity["sha256"] + '</p><p>Pixel differences are visual evidence, not semantic review.</p>' + coverage + ''.join(rows), encoding="utf-8")
    need(reading.sha(pdf.read_bytes()) == identity["sha256"], "PDF changed during rendering; discard this packet")
    validate_review(target / "manifest.json")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    try:
        result = render_review(args.config, args.output_dir)
        print(json.dumps({"status": "created", "review_state": result["review_state"], "output": str(Path(args.output_dir).resolve())}))
        return 0
    except (BuildError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Render review rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
