#!/usr/bin/env python3
"""Import explicitly selected, bounded plain Markdown or DOCX into edition JSON.

Python 3.12+, standard library only. Refuses unsupported manuscript features.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

import semantic_content as semantic

VERSION = "2.0.0"
MAX_FILE = 32 * 1024 * 1024
MAX_ZIP_TOTAL = 64 * 1024 * 1024
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DEVICE = {"con", "prn", "aux", "nul"} | {f"{p}{i}" for p in ("com", "lpt") for i in range(1, 10)}
LIMITS = [
    "Only selected manuscript and metadata files are read; DOCX members are inspected in memory, never extracted.",
    "First explicit heading establishes a section; subsequent headings at its level or above begin sections. Deeper headings retain their 1..6 levels as blocks. No content is invented.",
    "Paragraph text and heading text are preserved; source encoding, line endings, blank paragraph separators and document layout are not reproduced.",
    "DOCX direct bold/italic runs concatenate in order; inherited semantic styles are refused. Page geometry, document properties and font/typographic defaults are not reading-edition content.",
    "No visual, narrative, accessibility, EPUB or publishing acceptance is established by import.",
]


class Refusal(ValueError):
    pass


def need(ok, message):
    if not ok:
        raise Refusal(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def unique(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, f"Duplicate metadata key: {key}")
        result[key] = value
    return result


def read(root, name):
    need(isinstance(name, str) and name and "\\" not in name and ":" not in name and
         not PurePosixPath(name).is_absolute() and all(p not in ("", ".", "..") for p in name.split("/")),
         f"Unsafe relative input path: {name}")
    path = (root / Path(*PurePosixPath(name).parts)).resolve(strict=True)
    need(path.is_relative_to(root) and path.is_file(), f"Input escapes root or is not a file: {name}")
    need(path.stat().st_size <= MAX_FILE, f"Input exceeds 32 MiB: {name}")
    with path.open("rb") as stream:
        data = stream.read(MAX_FILE + 1)
    need(len(data) <= MAX_FILE, f"Input exceeds 32 MiB: {name}")
    return data


def xml_text(text):
    return all(c in "\t\n\r" or 0x20 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF for c in text)


def metadata(data):
    obj = json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique)
    need(isinstance(obj, dict) and set(obj) == {"title", "author", "identifier", "language", "modified"},
         "Metadata must contain exactly title, author, identifier, language, modified")
    for key, value in obj.items():
        need(isinstance(value, str) and value.strip() and xml_text(value), f"Invalid metadata.{key}")
    need(re.fullmatch(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", obj["language"]), "Invalid metadata.language")
    need(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", obj["modified"]), "Invalid metadata.modified UTC timestamp")
    dt.datetime.strptime(obj["modified"], "%Y-%m-%dT%H:%M:%SZ")
    return obj


def markdown(data):
    text = data.decode("utf-8-sig")
    units, issues, pending, starts = [], [], [], []

    def flush():
        if pending:
            value = "\n".join(pending)
            try:
                parsed = semantic.inline(value)
            except ValueError:
                parsed = {"text": value}
                issues.append({"feature": "unsupported_or_ambiguous_emphasis", "location": f"line:{starts[0]}"})
            units.append({"type": "paragraph", **parsed, "locator": f"lines:{starts[0]}-{starts[-1]}"})
            pending.clear()
            starts.clear()

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for line_no, line in enumerate(lines, 1):
        loc = f"line:{line_no}"
        heading = re.fullmatch(r"(#{1,6}) (\S(?:.*\S)?)", line)
        if heading:
            flush()
            title = heading[2]
            try:
                parsed = semantic.inline(title)
            except ValueError:
                parsed = {"text": title}
                issues.append({"feature": "unsupported_or_ambiguous_emphasis", "location": loc})
            units.append({"type": "heading", **parsed, "level": len(heading[1]), "locator": loc})
        elif line in ("***", "---"):
            flush()
            units.append({"type": "scene_break", "text": "", "locator": loc})
        elif not line.strip():
            flush()
        else:
            pending.append(line)
            starts.append(line_no)
        # Deliberately conservative: ambiguous markup is refused for explicit cleanup.
        check = heading[2] if heading else line
        if line not in ("***", "---") and (re.search(r"[_`\[\]<>\\|~]", check) or re.search(r"!?\[[^]]*\]", check) or
                re.match(r"\s*(?:#{1,6}(?:\s|$)|>|[-+]\s|\d+[.)]\s|[-=]{3,}\s*$|:{3,}| {4}|\t)", check) or
                line.endswith("  ") or (heading and re.search(r"\s#+$", check)) or
                re.search(r"&(?:#\w+|[A-Za-z]+);", check)):
            issues.append({"feature": "unsupported_or_ambiguous_markdown", "location": loc})
    flush()
    return units, issues, {"source_lines": len(lines), "blank_lines": sum(not x.strip() for x in lines)}


def docx(data):
    units, issues = [], []

    def issue(feature, loc):
        issues.append({"feature": feature, "location": loc})

    def parse_xml(blob, name):
        need(b"<!DOCTYPE" not in blob.upper() and b"<!ENTITY" not in blob.upper(), f"DTD/entities forbidden: {name}")
        return ET.fromstring(blob)

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = archive.infolist()
        need(len(members) <= 1000, "DOCX exceeds 1000 ZIP members")
        names = [m.filename for m in members]
        need(len(set(names)) == len(names), "DOCX contains duplicate ZIP member names")
        total = 0
        blobs = {}
        for member in members:
            name = member.filename
            need("\\" not in name and ":" not in name and not name.startswith("/") and all(p not in ("", ".", "..") for p in name.rstrip("/").split("/")), f"Unsafe ZIP member: {name}")
            need(not member.flag_bits & 1, f"Encrypted ZIP member: {name}")
            total += member.file_size
            need(member.file_size <= MAX_FILE and total <= MAX_ZIP_TOTAL, f"DOCX expanded-size limit exceeded: {name}")
            if member.is_dir():
                continue
            with archive.open(member) as stream:
                blob = stream.read(MAX_FILE + 1)
            need(len(blob) == member.file_size and len(blob) <= MAX_FILE, f"ZIP size mismatch: {name}")
            blobs[name] = blob
            if name.startswith(("word/media/", "word/embeddings/")):
                issue("embedded_media_or_object", name)
            allowed_word = {"word/document.xml", "word/styles.xml", "word/settings.xml", "word/fontTable.xml", "word/webSettings.xml", "word/theme/theme1.xml", "word/_rels/document.xml.rels", "word/_rels/fontTable.xml.rels"}
            if name.startswith("word/") and name not in allowed_word:
                issue("unsupported_docx_part", name)
            if re.match(r"word/(?:footnotes|endnotes|comments|header\d*|footer\d*)\.xml$", name):
                issue("notes_comments_header_or_footer", name)
            if name.endswith(".rels"):
                rels = parse_xml(blob, name)
                for index, rel in enumerate(rels, 1):
                    if rel.get("TargetMode") == "External" or rel.get("Type", "").endswith("/hyperlink"):
                        issue("external_relationship_or_hyperlink", f"{name}:relationship:{index}")
        need("word/document.xml" in blobs and "[Content_Types].xml" in blobs and "_rels/.rels" in blobs, "DOCX missing required package parts")
        root = parse_xml(blobs["word/document.xml"], "word/document.xml")
        need(root.tag == f"{{{W}}}document", "DOCX is not a WordprocessingML document")
        body = root.find(f"{{{W}}}body")
        need(body is not None and len(root) == 1, "DOCX must have exactly one document body")
        for node in root.iter():
            if node.tag != f"{{{W}}}t" and node.text and node.text.strip():
                issue("unexpected_mixed_XML_text", "word/document.xml:" + node.tag)
            if node.tail and node.tail.strip():
                issue("unexpected_XML_tail_text", "word/document.xml:" + node.tag)
        paragraph_count = 0
        for child_index, child in enumerate(body, 1):
            loc = f"word/document.xml:body-child:{child_index}"
            if child.tag == f"{{{W}}}sectPr":
                for node in child:
                    if node.tag not in {f"{{{W}}}{n}" for n in ("pgSz", "pgMar", "cols", "docGrid", "type")}:
                        issue("unsupported_section_property:" + node.tag, loc)
                    if len(node):
                        issue("nested_section_property", loc)
                continue
            if child.tag != f"{{{W}}}p":
                issue("unsupported_body_element:" + child.tag, loc)
                continue
            paragraph_count += 1
            loc = f"word/document.xml:paragraph:{paragraph_count}"
            texts, style, semantic_runs = [], "Normal", []
            for node in child:
                if node.tag == f"{{{W}}}pPr":
                    for prop in node:
                        if prop.tag == f"{{{W}}}pStyle":
                            style = prop.get(f"{{{W}}}val", "")
                        else:
                            issue("unsupported_paragraph_property:" + prop.tag, loc)
                elif node.tag == f"{{{W}}}r":
                    if len(node.findall(f"{{{W}}}rPr")) > 1:
                        issue("duplicate_run_properties", loc)
                    props = node.find(f"{{{W}}}rPr")
                    flags = {"emphasis": False, "strong": False}
                    if props is not None:
                        seen = set()
                        for prop in props:
                            local = prop.tag.removeprefix(f"{{{W}}}")
                            if local not in ("b", "i") or local in seen or len(prop) or set(prop.attrib) - {f"{{{W}}}val"}:
                                issue("unsupported_run_property:" + local, loc)
                            else:
                                value = prop.get(f"{{{W}}}val", "true")
                                if value not in ("true", "1", "on", "false", "0", "off"):
                                    issue("unsupported_run_property_value", loc)
                                flags["strong" if local == "b" else "emphasis"] = value in ("true", "1", "on")
                            seen.add(local)
                    for run_node in node:
                        if run_node.tag == f"{{{W}}}t":
                            texts.append(run_node.text or "")
                            if run_node.text:
                                semantic_runs.append({"text": run_node.text, **flags})
                            if len(run_node):
                                issue("nested_text_content", loc)
                        elif run_node.tag == f"{{{W}}}rPr":
                            pass
                        else:
                            issue("unsupported_run_element:" + run_node.tag, loc)
                else:
                    issue("unsupported_paragraph_element:" + node.tag, loc)
            heading = re.fullmatch(r"Heading([1-6])", style)
            if style not in ("Normal", "") and not heading:
                issue("unsupported_paragraph_style:" + style, loc)
            text = "".join(texts)
            if text in ("***", "---") and any(r["emphasis"] or r["strong"] for r in semantic_runs):
                issue("formatted_scene_break_unsupported", loc)
            if text.strip():
                units.append({"type": "heading" if heading else "scene_break" if text in ("***", "---") else "paragraph", "text": "" if not heading and text in ("***", "---") else text, "locator": loc, **({"level": int(heading[1])} if heading else {}), **({"runs": semantic_runs} if any(r["emphasis"] or r["strong"] for r in semantic_runs) and text not in ("***", "---") else {})})
            elif heading:
                issue("empty_heading", loc)
        # Inherited character formatting is also content: never silently flatten it.
        if "word/styles.xml" in blobs:
            styles = parse_xml(blobs["word/styles.xml"], "word/styles.xml")
            semantic = {f"{{{W}}}{name}" for name in ("b", "bCs", "i", "iCs", "u", "strike", "dstrike", "vertAlign", "vanish", "webHidden", "rStyle")}
            for defaults in styles.findall(f"{{{W}}}docDefaults"):
                if any(node.tag in semantic for node in defaults.iter()):
                    issue("unsupported_default_semantic_formatting", "word/styles.xml:docDefaults")
            for style in styles.findall(f"{{{W}}}style"):
                sid = style.get(f"{{{W}}}styleId", "")
                if style.get(f"{{{W}}}type") == "character" and sid != "DefaultParagraphFont":
                    issue("character_style_definition", f"word/styles.xml:style:{sid}")
                # Named heading appearance and normal typography are not inline semantics.
                if sid not in ("Normal", "DefaultParagraphFont") and not re.fullmatch(r"Heading[1-6]", sid):
                    issue("unsupported_style_definition", f"word/styles.xml:style:{sid}")
                if sid in ("Normal", "DefaultParagraphFont") and any(node.tag in semantic for node in style.iter()):
                    issue("unsupported_inherited_semantic_formatting", f"word/styles.xml:style:{sid}")
        return units, issues, {"docx_paragraphs": paragraph_count, "zip_members": len(members), "expanded_bytes": total}


def convert(units):
    sections, coverage = [], []
    section_level = next((u["level"] for u in units if u["type"] == "heading"), 1)
    for unit in units:
        need(xml_text(unit["text"]), f"Invalid XML text at {unit['locator']}")
        if unit["type"] == "heading" and unit["level"] <= section_level:
            need(len(sections) < 500, "More than 500 sections")
            sid = f"section-{len(sections) + 1:04d}"
            sections.append({"id": sid, "part": "body", "kind": "chapter", "title": unit["text"], "source": f"sections/{sid}.json", "blocks": [], "heading_level": unit["level"], **({"title_runs": unit["runs"]} if "runs" in unit else {})})
            coverage.append({"location": unit["locator"], "destination": sid + ":title", "characters": len(unit["text"]), "heading_level": unit["level"]})
        else:
            need(sections, f"Text precedes first explicit section heading: {unit['locator']}")
            section = sections[-1]
            need(len(section["blocks"]) < 10000, f"More than 10000 blocks in {section['id']}")
            block = {k: v for k, v in unit.items() if k != "locator"}
            if block["type"] == "scene_break":
                block.pop("text")
            section["blocks"].append(block)
            coverage.append({"location": unit["locator"], "destination": f"{section['id']}:block:{len(section['blocks'])}", "characters": len(unit["text"]), "type": unit["type"]})
    need(sections, "No explicit section headings found")
    for section in sections:
        need(any(b["type"] == "paragraph" for b in section["blocks"]), f"Section has no nonempty paragraphs: {section['id']} ({section['title']})")
    return sections, coverage


def main(argv=None):
    # Keep JSON diagnostics portable when stdout is redirected on Windows.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--input", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args(argv)
    report = {"schema_version": 1, "importer_version": VERSION, "unsupported_features": [], "limits": LIMITS}
    destination = None
    try:
        need(sys.version_info >= (3, 12), "Python 3.12+ is required")
        root, out = args.input_root.resolve(strict=True), args.output_root.resolve(strict=True)
        need(root.is_dir() and out.is_dir(), "Both roots must be existing directories")
        need(not out.is_relative_to(root), "output-root must be outside input-root")
        need(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.output_dir) and args.output_dir.lower() not in DEVICE, "output-dir must be a safe single new directory name")
        target = out / args.output_dir
        need(not target.exists() and not target.is_symlink(), "Output directory exists; overwriting is forbidden")
        suffix = PurePosixPath(args.input).suffix.lower()
        need(suffix in (".md", ".docx"), "Only .md and .docx input is supported")
        source, meta_bytes = read(root, args.input), read(root, args.metadata)
        meta = metadata(meta_bytes)
        report["inputs"] = [{"path": name, "bytes": len(blob), "sha256": digest(blob)} for name, blob in ((args.input, source), (args.metadata, meta_bytes))]
        units, issues, counts = markdown(source) if suffix == ".md" else docx(source)
        report.update(unsupported_features=issues, source_counts=counts)
        if issues:
            raise Refusal(f"Unsupported manuscript features at {issues[0]['location']}; see unsupported_features")
        sections, coverage = convert(units)
        config = {"schema_version": 1, "edition_id": "imported-edition", "metadata": meta, "formats": ["html", "epub"], "assets": [], "sections": [{k: v for k, v in s.items() if k != "blocks"} for s in sections]}
        outputs = {"edition.json": encoded(config)}
        for section in sections:
            outputs[section["source"]] = encoded({"blocks": section["blocks"]})
        report.update(section_order=[s["id"] for s in sections], sections=[{"id": s["id"], "title": s["title"], "paragraphs": len(s["blocks"]), "characters": sum(len(b.get("text", "")) for b in s["blocks"])} for s in sections], coverage=coverage, coverage_policy="Every nonempty source text unit maps exactly once; blank units and allowed layout/package metadata are excluded, as disclosed in limits.", outputs=[{"path": name, "bytes": len(blob), "sha256": digest(blob)} for name, blob in sorted(outputs.items())], manifest_hash_policy="Manifest excludes itself; stdout reports its SHA-256.")
        if args.preflight:
            report["status"] = "preflight_passed_no_outputs_written"
            print(encoded(report).decode(), end="")
            return 0
        report["status"] = "import_complete_review_required"
        outputs["import-manifest.json"] = encoded(report)
        target.mkdir(exist_ok=False)
        destination = target
        for name, blob in sorted(outputs.items()):
            path = target / name
            path.parent.mkdir(exist_ok=True, parents=True)
            with path.open("xb") as stream:
                stream.write(blob)
            need(digest(path.read_bytes()) == digest(blob), f"Output readback mismatch: {name}")
        print(encoded({"status": report["status"], "output_directory": str(target), "manifest_sha256": digest(outputs["import-manifest.json"]), "section_order": report["section_order"]}).decode(), end="")
        return 0
    except (Refusal, OSError, ValueError, TypeError, KeyError, ET.ParseError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as error:
        report.update(status="import_refused", error=str(error))
        if destination:
            report["incomplete_output_directory"] = str(destination)
        print(encoded(report).decode(), end="")
        print(f"Import refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
