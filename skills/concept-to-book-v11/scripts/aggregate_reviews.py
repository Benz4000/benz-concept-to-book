#!/usr/bin/env python3
"""Aggregate explicit dispositions across hash-pinned actual render packets."""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path
import build_reading_edition as reading
from render_review import pdf_identity, output_target, validate_review

BuildError, need = reading.BuildError, reading.need
VERSION = "1.0.0"


def digest(value):
    need(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value), "Expected exact lowercase SHA-256")
    return value


def _collect(pdf, packets, explicit, packet_paths=None):
    identity = pdf_identity(pdf.read_bytes())
    need(isinstance(packets, list) and 1 <= len(packets) <= 2000, "Supply 1..2000 actual render packets")
    need(isinstance(explicit, list) and len(explicit) <= 10000, "Invalid explicit review dispositions")
    by_hash, rendered, decisions, sources = {}, set(), {}, []
    for spec in packets:
        reading.keys(spec, ("path", "sha256"))
        packet_hash = digest(spec["sha256"])
        need(packet_hash not in by_hash, "Duplicate packet identity")
        path = Path((packet_paths or {}).get(packet_hash, spec["path"])).resolve(strict=True)
        need(path.stat().st_size <= 8 * 1024 * 1024, "Packet exceeds 8 MiB")
        need(reading.sha(path.read_bytes()) == packet_hash, "Packet changed: manifest SHA-256 mismatch")
        packet = validate_review(path, pdf)
        need(reading.sha(path.read_bytes()) == packet_hash, "Packet changed during validation")
        need(packet["pdf"] == identity, "Packet belongs to a different exact PDF")
        previews = {item["page"]: item["sha256"] for item in packet["previews"]}
        by_hash[packet_hash] = previews
        rendered.update(previews)
        sources.append({"path": str(path), "sha256": packet_hash})
        for item in packet.get("dispositions", []):
            decisions.setdefault(item["page"], []).append(dict(item, packet_sha256=packet_hash, preview_sha256=previews[item["page"]], origin="packet"))
    seen_explicit = set()
    for item in explicit:
        reading.keys(item, ("packet_sha256", "page", "preview_sha256", "status", "note", "reviewer"))
        packet_hash = digest(item["packet_sha256"])
        need(packet_hash in by_hash, "Disposition references an unknown packet")
        need(type(item["page"]) is int and item["page"] in by_hash[packet_hash], "Disposition page was not rendered in its packet")
        need(digest(item["preview_sha256"]) == by_hash[packet_hash][item["page"]], "Disposition preview identity mismatch")
        need(item["status"] in ("accepted", "changes-required"), "Unsupported disposition")
        reading.string(item["note"], "review note")
        reading.string(item["reviewer"], "reviewer")
        key = (packet_hash, item["page"])
        need(key not in seen_explicit, "Duplicate explicit disposition for packet/page")
        seen_explicit.add(key)
        decisions.setdefault(item["page"], []).append(dict(item, origin="explicit"))
    for page, items in decisions.items():
        need(len({item["status"] for item in items}) == 1, f"Conflicting review dispositions for page {page}")
    need(reading.sha(pdf.read_bytes()) == identity["sha256"], "PDF changed during aggregation")
    pending = sorted(set(range(1, identity["page_count"] + 1)) - decisions.keys())
    state = "pending" if pending else ("changes-required" if any(items[0]["status"] == "changes-required" for items in decisions.values()) else "accepted")
    return {"pdf": identity, "packets": sources, "rendered_pages": sorted(rendered), "reviewed_pages": sorted(decisions), "pending_pages": pending, "changes_required_pages": sorted(page for page, items in decisions.items() if items[0]["status"] == "changes-required"), "page_dispositions": [{"page": page, "status": items[0]["status"], "evidence": items} for page, items in sorted(decisions.items())], "review_state": state}


def aggregate_reviews(config_path, output_dir):
    config_path = Path(config_path).resolve(strict=True)
    inputs = reading.Inputs(config_path.parent)
    cfg = inputs.json(config_path.name)
    reading.keys(cfg, ("schema_version", "pdf", "packets"), ("dispositions",))
    need(type(cfg["schema_version"]) is int and cfg["schema_version"] == 1, "Unsupported aggregate schema")
    inputs.read(cfg["pdf"])
    pdf = (config_path.parent / cfg["pdf"]).resolve(strict=True)
    need(isinstance(cfg["packets"], list), "packets must be a list")
    packets = []
    for spec in cfg["packets"]:
        reading.keys(spec, ("path", "sha256"))
        path = Path(reading.string(spec["path"], "packet path"))
        packets.append({"path": str((config_path.parent / path).resolve(strict=True)), "sha256": spec["sha256"]})
    result = _collect(pdf, packets, cfg.get("dispositions", []))
    target = output_target(output_dir, config_path.parent)
    target.mkdir(parents=True)
    manifest = dict(result, schema_version=1, adapter="aggregate-reviews", version=VERSION, pdf_path=str(pdf), explicit_dispositions=cfg.get("dispositions", []), inputs=inputs.manifest(), limitations="Integrity evidence, not reviewer authentication or signatures. Rendered previews alone never imply human review. Every page requires an explicit disposition for this exact PDF.")
    for item in inputs.manifest():
        need(reading.sha((config_path.parent / item["path"]).read_bytes()) == item["sha256"], "Input changed during aggregation")
    (target / "manifest.json").write_bytes(reading.encoded(manifest))
    validate_aggregate(target / "manifest.json")
    return manifest


def validate_aggregate(manifest_path, pdf_path=None, packet_paths=None):
    """Reopen PDF, packet manifests and previews; optional hash->path relocation map."""
    path = Path(manifest_path).resolve(strict=True)
    manifest = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reading.unique_object)
    need(manifest.get("schema_version") == 1 and manifest.get("adapter") == "aggregate-reviews", "Unsupported aggregate manifest")
    result = _collect(Path(pdf_path or manifest["pdf_path"]).resolve(strict=True), manifest["packets"], manifest["explicit_dispositions"], packet_paths)
    for key, value in result.items():
        if key != "packets":
            need(manifest.get(key) == value, f"Aggregate evidence changed or inconsistent: {key}")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    try:
        result = aggregate_reviews(args.config, args.output_dir)
        print(json.dumps({"status": "created", "review_state": result["review_state"], "pending_pages": result["pending_pages"]}))
        return 0
    except (BuildError, OSError, ValueError, KeyError) as exc:
        print(f"Review aggregation rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
