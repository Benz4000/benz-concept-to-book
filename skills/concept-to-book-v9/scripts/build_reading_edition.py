#!/usr/bin/env python3
"""Build bounded HTML reading proofs and EPUB containers from explicit local inputs.

Python 3.10+, standard library only. No network, original edits, PDF, or publishing.
See references/production-adapters.md for the deliberately limited input contract.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import io
import json
import platform
import re
import shutil
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path, PurePosixPath

import semantic_content as semantic

VERSION = "2.0.0"
MAX_FILE = 32 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024
ID = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
RESERVED = {"book-id", "cover", "nav", "package", "style"}
DEVICE_NAMES = {"con", "prn", "aux", "nul"} | {f"{prefix}{n}" for prefix in ("com", "lpt") for n in range(1, 10)}
XHTML = "http://www.w3.org/1999/xhtml"
EPUB = "http://www.idpf.org/2007/ops"
OPF = "http://www.idpf.org/2007/opf"


class BuildError(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise BuildError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def keys(value, required, optional=()):
    need(isinstance(value, dict), "Expected a JSON object")
    need(set(required) <= value.keys(), f"Missing keys: {sorted(set(required) - value.keys())}")
    need(value.keys() <= set(required) | set(optional), f"Unsupported keys: {sorted(value.keys() - set(required) - set(optional))}")


def string(value, label):
    need(isinstance(value, str) and bool(value.strip()), f"{label} must be a nonempty string")
    need(all(c in "\t\n\r" or 0x20 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF for c in value), f"{label} contains invalid XML characters")
    return value


def identifier(value):
    need(isinstance(value, str) and ID.fullmatch(value) and value not in RESERVED | DEVICE_NAMES, f"Unsafe or reserved ID: {value!r}")
    return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


class Inputs:
    def __init__(self, root):
        self.root = root
        self.files = {}
        self.total = 0

    def read(self, name):
        need(isinstance(name, str) and bool(name), "Input paths must be nonempty strings")
        path = PurePosixPath(name)
        need(not path.is_absolute() and "\\" not in name and ":" not in name and all(p not in (".", "..", "") for p in name.split("/")), f"Unsafe input path: {name}")
        resolved = (self.root / Path(*path.parts)).resolve(strict=True)
        need(resolved.is_relative_to(self.root) and resolved.is_file(), f"Input escapes root or is not a file: {name}")
        if name not in self.files:
            need(resolved.stat().st_size <= MAX_FILE, f"Input exceeds 32 MiB: {name}")
            with resolved.open("rb") as stream:
                data = stream.read(MAX_FILE + 1)
            need(len(data) <= MAX_FILE, f"Input exceeds 32 MiB: {name}")
            self.total += len(data)
            need(self.total <= MAX_TOTAL, "Inputs exceed 128 MiB")
            self.files[name] = data
        return self.files[name]

    def json(self, name):
        return json.loads(self.read(name).decode("utf-8-sig"), object_pairs_hook=unique_object)

    def manifest(self):
        return [{"path": name, "bytes": len(data), "sha256": sha(data)} for name, data in sorted(self.files.items())]


def image_info(data, suffix):
    if suffix == ".png":
        need(data[:8] == b"\x89PNG\r\n\x1a\n", "PNG signature missing")
        pos, dimensions, ended, has_data = 8, None, False, False
        while pos + 12 <= len(data):
            size = struct.unpack_from(">I", data, pos)[0]
            kind = data[pos + 4:pos + 8]
            end = pos + 12 + size
            need(end <= len(data), "Truncated PNG chunk")
            payload = data[pos + 8:pos + 8 + size]
            need(zlib.crc32(kind + payload) & 0xFFFFFFFF == struct.unpack_from(">I", data, end - 4)[0], "PNG chunk CRC mismatch")
            if pos == 8:
                need(kind == b"IHDR" and size == 13, "PNG must start with IHDR")
                dimensions = struct.unpack_from(">II", payload)
            elif kind == b"IHDR":
                raise BuildError("Duplicate PNG IHDR")
            has_data |= kind == b"IDAT"
            pos = end
            if kind == b"IEND":
                need(size == 0 and pos == len(data), "Invalid PNG end")
                ended = True
                break
        need(ended and has_data and dimensions, "Incomplete PNG structure")
        media = "image/png"
    else:
        need(suffix in (".jpg", ".jpeg") and data[:2] == b"\xff\xd8" and data[-2:] == b"\xff\xd9", "Expected JPEG start/end markers")
        pos, dimensions = 2, None
        while pos < len(data) - 2:
            need(data[pos] == 0xFF, "Invalid JPEG marker")
            while pos < len(data) and data[pos] == 0xFF:
                pos += 1
            need(pos < len(data), "Truncated JPEG marker")
            marker = data[pos]
            pos += 1
            if marker == 0xDA:
                break
            if marker == 0x01 or 0xD0 <= marker <= 0xD9:
                continue
            need(pos + 2 <= len(data), "Truncated JPEG segment")
            size = struct.unpack_from(">H", data, pos)[0]
            need(size >= 2 and pos + size <= len(data), "Invalid JPEG segment size")
            if marker in (0xC0, 0xC1, 0xC2):
                need(size >= 8, "Truncated JPEG frame")
                height, width = struct.unpack_from(">HH", data, pos + 3)
                dimensions = (width, height)
            pos += size
        need(dimensions is not None, "Only baseline/extended/progressive JPEG frames are supported")
        media = "image/jpeg"
    width, height = dimensions
    need(0 < width <= 100000 and 0 < height <= 100000, "Invalid or unsupported image dimensions")
    return {"width_px": width, "height_px": height, "media_type": media, "inspection": "file structure and stored dimensions; pixels not decoded"}


def font_info(data, suffix):
    need(suffix in (".ttf", ".otf") and len(data) >= 12 and data[:4] in (b"\x00\x01\x00\x00", b"OTTO"), "Only standalone TrueType/OpenType fonts are supported")
    count = struct.unpack_from(">H", data, 4)[0]
    need(0 < count <= 256 and 12 + count * 16 <= len(data), "Invalid font table directory")
    tables = {}
    for n in range(count):
        tag, _, offset, size = struct.unpack_from(">4sIII", data, 12 + n * 16)
        need(tag not in tables and offset + size <= len(data), "Duplicate or truncated font table")
        tables[tag] = (offset, size)
    need(all(tag in tables for tag in (b"head", b"cmap", b"name", b"OS/2")), "Required font tables missing")
    offset, size = tables[b"OS/2"]
    need(size >= 10, "OS/2 embedding flags unavailable")
    flags = struct.unpack_from(">H", data, offset + 8)[0]
    need(not flags & (0x0002 | 0x0200), "Font flags prohibit this outline embedding")
    return {"media_type": "font/otf" if data[:4] == b"OTTO" else "font/ttf", "fs_type": flags, "inspection": "table bounds and embedding flags; glyph coverage/rendering not checked", "subset": False}


def prepare(inputs, config_name):
    config = inputs.json(config_name)
    keys(config, ("schema_version", "edition_id", "metadata", "formats", "assets", "sections"), ("cover_image", "font"))
    need(type(config["schema_version"]) is int and config["schema_version"] == 1, "Unsupported schema_version")
    identifier(config["edition_id"])
    metadata = config["metadata"]
    keys(metadata, ("title", "author", "identifier", "language", "modified"))
    for key, value in metadata.items():
        string(value, f"metadata.{key}")
    need(re.fullmatch(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", metadata["language"]), "Language must use a simple BCP 47 tag")
    need(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", metadata["modified"]), "modified must be an explicit UTC timestamp, YYYY-MM-DDTHH:MM:SSZ")
    dt.datetime.strptime(metadata["modified"], "%Y-%m-%dT%H:%M:%SZ")
    formats = config["formats"]
    need(isinstance(formats, list) and 0 < len(formats) <= 2 and all(f in ("html", "epub") for f in formats) and len(set(formats)) == len(formats), "formats must contain html and/or epub, without duplicates")
    need(isinstance(config["assets"], list) and len(config["assets"]) <= 100, "assets must be a list of at most 100 images")
    assets, used_ids = {}, set(RESERVED)
    for asset in config["assets"]:
        keys(asset, ("id", "path", "role", "alt"))
        asset_id = identifier(asset["id"])
        need(asset_id not in used_ids, f"Duplicate ID: {asset_id}")
        used_ids.add(asset_id)
        need(asset["role"] in ("front-cover", "illustration", "map", "portrait"), "Unsupported image role")
        string(asset["alt"], f"asset {asset_id} alt")
        data = inputs.read(asset["path"])
        suffix = PurePosixPath(asset["path"]).suffix.lower()
        info = image_info(data, suffix)
        assets[asset_id] = dict(asset, **info, output_name=asset_id + suffix, data=data)
    cover = config.get("cover_image")
    need(cover is None or isinstance(cover, str), "cover_image must be an asset ID or null")
    need(cover is None or cover in assets and assets[cover]["role"] == "front-cover", "cover_image must refer to a front-cover asset")
    need([a["id"] for a in assets.values() if a["role"] == "front-cover"] == ([] if cover is None else [cover]), "Declare exactly the selected front cover, or no front-cover asset")
    font = config.get("font")
    if font is not None:
        keys(font, ("id", "path", "embedding_authorized"))
        font_id = identifier(font["id"])
        need(font_id not in used_ids, f"Duplicate ID: {font_id}")
        used_ids.add(font_id)
        need(font["embedding_authorized"] is True, "A supplied font requires embedding_authorized: true")
        data = inputs.read(font["path"])
        suffix = PurePosixPath(font["path"]).suffix.lower()
        font = dict(font, **font_info(data, suffix), output_name=font_id + suffix, data=data)
    sections = config["sections"]
    need(isinstance(sections, list) and 0 < len(sections) <= 500, "sections must contain 1 to 500 entries")
    prepared, last_part, used_assets = [], -1, set([cover] if cover else [])
    for section in sections:
        keys(section, ("id", "part", "kind", "title", "source"), ("heading_level", "title_runs"))
        need(type(section.get("heading_level", 1)) is int and 1 <= section.get("heading_level", 1) <= 6, "section.heading_level must be 1..6")
        semantic.validate({"text": section["title"], **({"runs": section["title_runs"]} if "title_runs" in section else {})}, need, keys, string)
        section_id = identifier(section["id"])
        need(section_id not in used_ids, f"Duplicate ID: {section_id}")
        used_ids.add(section_id)
        need(section["part"] in ("front", "body", "back"), "section.part must be front/body/back")
        part = ("front", "body", "back").index(section["part"])
        need(part >= last_part, "Section sequence must keep front, body and back matter in that order")
        last_part = part
        for field in ("kind", "title"):
            string(section[field], f"section {section_id} {field}")
        source = inputs.json(section["source"])
        keys(source, ("blocks",))
        need(isinstance(source["blocks"], list) and 0 < len(source["blocks"]) <= 10000, "Each section needs 1 to 10000 explicit blocks")
        for block in source["blocks"]:
            need(isinstance(block, dict), "Block must be an object")
            if block.get("type") in ("paragraph", "heading"):
                keys(block, ("type", "text") + (("level",) if block["type"] == "heading" else ()), ("runs",))
                string(block["text"], "block.text")
                semantic.validate(block, need, keys, string)
                if block["type"] == "heading":
                    need(type(block["level"]) is int and 1 <= block["level"] <= 6, "heading.level must be 1..6")
            elif block.get("type") == "scene_break":
                keys(block, ("type",))
            elif block.get("type") == "image":
                keys(block, ("type", "asset_id"), ("caption",))
                need(isinstance(block["asset_id"], str) and block["asset_id"] in assets, "Image block refers to a missing asset")
                need(assets[block["asset_id"]]["role"] != "front-cover", "Front cover belongs in cover_image, not body blocks")
                used_assets.add(block["asset_id"])
                if "caption" in block:
                    string(block["caption"], "image.caption")
            else:
                raise BuildError("Only paragraph, heading, scene_break and image blocks are supported")
        prepared.append(dict(section, blocks=source["blocks"]))
    need(any(s["part"] == "body" for s in prepared), "At least one body section is required")
    need(used_assets == assets.keys(), f"Unused assets: {sorted(assets.keys() - used_assets)}")
    return config, assets, font, prepared


def esc(text):
    return html.escape(text, quote=True)


def picture(asset, prefix):
    return f'<img src="{prefix}assets/{asset["output_name"]}" alt="{esc(asset["alt"])}" width="{asset["width_px"]}" height="{asset["height_px"]}" />'


def section_body(section, assets, prefix):
    lines = [f'<section id="{section["id"]}" data-part="{section["part"]}" data-kind="{esc(section["kind"])}">', f'<h{section.get("heading_level", 1)}>{semantic.markup({"text": section["title"], **({"runs": section["title_runs"]} if "title_runs" in section else {})})}</h{section.get("heading_level", 1)}>']
    for block in section["blocks"]:
        if block["type"] == "paragraph":
            lines.append(f'<p>{semantic.markup(block)}</p>')
        elif block["type"] == "heading":
            lines.append(f'<h{block["level"]}>{semantic.markup(block)}</h{block["level"]}>')
        elif block["type"] == "scene_break":
            lines.append('<hr class="scene-break" />')
        else:
            lines.append("<figure>" + picture(assets[block["asset_id"]], prefix))
            if "caption" in block:
                lines.append(f'<figcaption>{esc(block["caption"])}</figcaption>')
            lines.append("</figure>")
    return "\n".join(lines + ["</section>"])


def page(title, language, body, css):
    return (f'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n<html xmlns="{XHTML}" xmlns:epub="{EPUB}" lang="{esc(language)}" xml:lang="{esc(language)}"><head><meta charset="utf-8" /><title>{esc(title)}</title><link rel="stylesheet" href="{css}" /></head><body>\n{body}\n</body></html>\n').encode("utf-8")


def make_outputs(config, assets, font, sections):
    meta, outputs = config["metadata"], {}
    css = "body { margin: 2em auto; padding: 0 1em; max-width: 42em; font-family: serif; line-height: 1.55; }\nsection { margin: 3em 0; }\nh1 { line-height: 1.2; }\nimg { display: block; max-width: 100%; height: auto; margin: 0 auto; }\nfigure { margin: 1.5em 0; }\nfigcaption { font-size: .9em; }\n.cover img { max-height: 90vh; width: auto; }\na { text-decoration: underline; }\n"
    if font:
        css += f'@font-face {{ font-family: "EditionText"; src: url("assets/{font["output_name"]}"); }}\nbody {{ font-family: "EditionText", serif; }}\n'
    files = {"style.css": css.encode("utf-8")}
    for asset in assets.values():
        files["assets/" + asset["output_name"]] = asset["data"]
    if font:
        files["assets/" + font["output_name"]] = font["data"]
    cover = config.get("cover_image")
    order = (["cover"] if cover else []) + [s["id"] for s in sections]
    titles = {s["id"]: s["title"] for s in sections}
    titles["cover"] = "Cover"
    if "html" in config["formats"]:
        nav = '<nav aria-label="Contents"><h1>Contents</h1><ol>' + "".join(f'<li><a href="#{sid}">{esc(titles[sid])}</a></li>' for sid in order) + "</ol></nav>"
        body = [f'<header><h1>{esc(meta["title"])}</h1><p>{esc(meta["author"])}</p></header>', nav, '<main>']
        if cover:
            body.append('<section id="cover" class="cover"><h1>Cover</h1>' + picture(assets[cover], "") + "</section>")
        body.extend(section_body(s, assets, "") for s in sections)
        body.append("</main>")
        outputs["html/index.html"] = page(meta["title"], meta["language"], "\n".join(body), "style.css")
        outputs.update({"html/" + name: data for name, data in files.items()})
    if "epub" in config["formats"]:
        package = {"mimetype": b"application/epub+zip", "META-INF/container.xml": b'<?xml version="1.0" encoding="utf-8"?>\n<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml" /></rootfiles></container>\n'}
        package.update({"EPUB/" + name: data for name, data in files.items()})
        if cover:
            package["EPUB/content/cover.xhtml"] = page("Cover", meta["language"], '<section id="cover" class="cover" epub:type="cover"><h1>Cover</h1>' + picture(assets[cover], "../") + "</section>", "../style.css")
        for section in sections:
            package[f'EPUB/content/{section["id"]}.xhtml'] = page(section["title"], meta["language"], section_body(section, assets, "../"), "../style.css")
        toc = '<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>' + "".join(f'<li><a href="content/{sid}.xhtml">{esc(titles[sid])}</a></li>' for sid in order) + "</ol></nav>"
        package["EPUB/nav.xhtml"] = page("Contents", meta["language"], toc, "style.css")
        manifest = ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav" />', '<item id="style" href="style.css" media-type="text/css" />']
        manifest.extend(f'<item id="{sid}" href="content/{sid}.xhtml" media-type="application/xhtml+xml" />' for sid in order)
        for asset in assets.values():
            prop = ' properties="cover-image"' if asset["id"] == cover else ""
            manifest.append(f'<item id="{asset["id"]}" href="assets/{asset["output_name"]}" media-type="{asset["media_type"]}"{prop} />')
        if font:
            manifest.append(f'<item id="{font["id"]}" href="assets/{font["output_name"]}" media-type="{font["media_type"]}" />')
        spine = "".join(f'<itemref idref="{sid}" />' for sid in order)
        package["EPUB/package.opf"] = (f'<?xml version="1.0" encoding="utf-8"?>\n<package xmlns="{OPF}" version="3.0" unique-identifier="book-id" xml:lang="{esc(meta["language"])}"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="book-id">{esc(meta["identifier"])}</dc:identifier><dc:title>{esc(meta["title"])}</dc:title><dc:creator>{esc(meta["author"])}</dc:creator><dc:language>{esc(meta["language"])}</dc:language><meta property="dcterms:modified">{meta["modified"]}</meta></metadata><manifest>{"".join(manifest)}</manifest><spine>{spine}</spine></package>\n').encode("utf-8")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
            for name in ["mimetype"] + sorted(set(package) - {"mimetype"}):
                entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_STORED
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                archive.writestr(entry, package[name])
        outputs[config["edition_id"] + ".epub"] = buffer.getvalue()
    return outputs, order


def verify_outputs(outputs, order, config):
    """Narrow byte/ZIP/XML checks, deliberately not a reading-system validator."""
    if "html" in config["formats"]:
        root = ET.fromstring(outputs["html/index.html"])
        actual = [s.get("id") for s in root.findall(f".//{{{XHTML}}}main/{{{XHTML}}}section")]
        need(actual == order, "HTML section order differs from source contract")
    if "epub" in config["formats"]:
        with zipfile.ZipFile(io.BytesIO(outputs[config["edition_id"] + ".epub"])) as archive:
            need(archive.testzip() is None, "ZIP CRC check failed")
            first = archive.infolist()[0]
            need(first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED and not first.extra and archive.read("mimetype") == b"application/epub+zip", "EPUB mimetype check failed")
            opf = ET.fromstring(archive.read("EPUB/package.opf"))
            package_ids = [node.get("id") for node in opf.iter() if node.get("id") is not None]
            need(len(package_ids) == len(set(package_ids)), "Duplicate XML ID in EPUB package")
            need([e.get("idref") for e in opf.findall(f"{{{OPF}}}spine/{{{OPF}}}itemref")] == order, "EPUB spine order mismatch")
            for item in opf.findall(f"{{{OPF}}}manifest/{{{OPF}}}item"):
                need("EPUB/" + item.attrib["href"] in archive.namelist(), "Missing manifested resource")
            nav = ET.fromstring(archive.read("EPUB/nav.xhtml"))
            need([e.get("href") for e in nav.findall(f".//{{{XHTML}}}a")] == [f"content/{sid}.xhtml" for sid in order], "EPUB navigation order mismatch")
            for name in archive.namelist():
                if name.endswith((".xml", ".opf", ".xhtml")):
                    ET.fromstring(archive.read(name))


def capabilities(font):
    return {"builder_version": VERSION, "python": platform.python_version(), "python_implementation": platform.python_implementation(), "dependencies": "Python standard library only", "html": "available: single-document reflowable reading proof", "epub": "available: EPUB 3 package with structural checks only", "pdf": "not implemented", "fonts": "supplied whole font embedded; rendering/glyph coverage unverified" if font else "generic serif fallback; installed font and appearance not pinned", "epubcheck": "available but not run" if shutil.which("epubcheck") else "not found on PATH; not run", "real_reader": "not run", "visual_review": "not run", "physical_cover_template": "not supplied or implemented", "manufacturing": "not available"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--config", required=True, help="Relative POSIX path beneath input-root")
    parser.add_argument("--output-root", required=True, type=Path, help="Existing explicitly designated output parent")
    parser.add_argument("--output-dir", required=True, help="New single directory name beneath output-root")
    parser.add_argument("--preflight", action="store_true", help="Validate/snapshot inputs and report capabilities without writing")
    args = parser.parse_args(argv)
    destination = None
    try:
        input_root = args.input_root.resolve(strict=True)
        output_root = args.output_root.resolve(strict=True)
        need(input_root.is_dir() and output_root.is_dir(), "Both roots must be existing directories")
        need(not output_root.is_relative_to(input_root), "output-root must be outside input-root")
        need(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.output_dir), "output-dir must be a simple new directory name")
        need(args.output_dir.lower() not in DEVICE_NAMES, "output-dir must not be a reserved device name")
        candidate = output_root / args.output_dir
        need(not candidate.exists() and not candidate.is_symlink(), "Output directory already exists; overwriting is forbidden")
        inputs = Inputs(input_root)
        config, assets, font, sections = prepare(inputs, args.config)
        report = {"schema_version": 1, "edition_id": config["edition_id"], "metadata": config["metadata"], "capabilities": capabilities(font), "builder_sha256": sha(Path(__file__).read_bytes()), "inputs": inputs.manifest(), "assets": [{k: v for k, v in asset.items() if k != "data"} for asset in assets.values()], "font": {k: v for k, v in font.items() if k != "data"} if font else None, "section_sources": [{k: v for k, v in s.items() if k != "blocks"} for s in sections], "formats": config["formats"]}
        if args.preflight:
            print(encoded(dict(report, status="preflight_passed_no_outputs_written")).decode("utf-8"), end="")
            return 0
        outputs, order = make_outputs(config, assets, font, sections)
        verify_outputs(outputs, order, config)
        report.update(status="local_build_complete_structural_checks_passed", reading_order=order, checks={"input_validation": "passed", "generated_zip_xml_order_resources": "passed", "output_hash_readback": "passed", "visual_and_real_reader_acceptance": "unrun", "epubcheck": "unrun", "print_readiness": "unsupported"}, outputs=[{"path": name, "bytes": len(data), "sha256": sha(data)} for name, data in sorted(outputs.items())], manifest_hash_policy="build-manifest.json excludes itself; hash it separately at handoff")
        candidate.mkdir(exist_ok=False)
        destination = candidate
        for name, data in sorted(outputs.items()):
            target = destination / Path(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(data)
            need(sha(target.read_bytes()) == sha(data), f"Written output hash mismatch: {name}")
        with (destination / "build-manifest.json").open("xb") as stream:
            stream.write(encoded(report))
        print(encoded({"status": report["status"], "output_directory": str(destination), "manifest_sha256": sha((destination / "build-manifest.json").read_bytes()), "reading_order": order, "output_files": len(outputs)}).decode("utf-8"), end="")
        return 0
    except (BuildError, OSError, ValueError, TypeError, KeyError, struct.error, ET.ParseError, zipfile.BadZipFile) as error:
        print(f"Build refused: {error}", file=sys.stderr)
        if destination:
            print(f"Incomplete new output directory retained for inspection: {destination}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
