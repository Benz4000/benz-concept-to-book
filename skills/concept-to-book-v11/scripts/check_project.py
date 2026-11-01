#!/usr/bin/env python3
"""Read-only, explicitly scoped mechanical checks. Python 3.9+, standard library."""

import argparse
import hashlib
import json
import math
import re
import stat
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath


MAX_TEXT_BYTES = 32 * 1024 * 1024
SECTION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
SECTION_LINE = re.compile(r"^[ \t]*<!--[ \t]*section:[ \t]*([A-Za-z0-9][A-Za-z0-9._-]*)[ \t]*-->[ \t]*$")
LIMITS = [
    "Hashes identify the bytes read; a baseline must come from a trusted, approved source.",
    "Section markers and literal matches do not establish semantic or editorial identity.",
    "Local destination existence does not establish link wiring, fragment validity, or destination content.",
    "Recorded pixel/placement arithmetic does not verify actual dimensions or embedded-image PPI.",
    "PDF font embedding, actual embedded-image PPI, live sites, prose, visual quality, accessibility, and platform acceptance are not checked.",
]


class ManifestError(ValueError):
    pass


class Unavailable(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ManifestError(message)


def fields(value, required, optional, label):
    require(isinstance(value, dict), f"{label}: expected an object")
    require(set(required) <= set(value), f"{label}: missing fields {sorted(set(required) - set(value))}")
    require(set(value) <= set(required) | set(optional), f"{label}: unknown fields {sorted(set(value) - set(required) - set(optional))}")


def nonempty(value, label):
    require(isinstance(value, str) and bool(value.strip()), f"{label}: expected a nonempty string")


def bounded(root, relative):
    """Reject absolute paths, parents, ADS, and symlink/reparse traversal below root."""
    nonempty(relative, "path")
    win = PureWindowsPath(relative)
    require(not win.drive and not win.root and not Path(relative).is_absolute(), f"path must be relative: {relative}")
    require(":" not in relative and "\x00" not in relative, f"invalid path: {relative}")
    parts = relative.replace("\\", "/").split("/")
    require(".." not in parts, f"parent traversal is forbidden: {relative}")
    candidate = root.joinpath(*parts)
    cursor = root
    for part in parts:
        if part in ("", "."):
            continue
        cursor = cursor / part
        try:
            info = cursor.lstat()
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode) and not (getattr(info, "st_file_attributes", 0) & 0x400),
                f"symlink/reparse traversal is forbidden: {relative}")
    resolved = candidate.resolve()
    require(resolved == root or root in resolved.parents, f"path escapes project root: {relative}")
    return resolved


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise ManifestError(f"non-finite JSON number: {value}")


def finite_float(value):
    parsed = float(value)
    require(math.isfinite(parsed), "non-finite JSON number")
    return parsed


def parse_json(text):
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant, parse_float=finite_float)


def validate(manifest, root):
    fields(manifest, ["schema_version", "files"],
           ["sections", "placeholder_scans", "local_links", "metadata_pairs", "assets", "external_checks"], "manifest")
    require(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1, "schema_version must be 1")
    for name in ("files", "sections", "placeholder_scans", "local_links", "metadata_pairs", "assets", "external_checks"):
        require(isinstance(manifest.get(name, []), list), f"{name} must be an array")
    require(bool(manifest["files"]), "files must contain at least one explicit file")
    files, paths = {}, set()
    for entry in manifest["files"]:
        fields(entry, ["id", "path"], ["sha256"], "file")
        nonempty(entry["id"], "file id")
        require(entry["id"] not in files, f"duplicate file id: {entry['id']}")
        path = bounded(root, entry["path"])
        require(path not in paths, f"duplicate file path: {entry['path']}")
        if "sha256" in entry:
            require(isinstance(entry["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is not None,
                    "sha256 must be 64 lowercase hexadecimal characters")
        files[entry["id"]] = entry
        paths.add(path)

    def file_ref(file_id):
        require(isinstance(file_id, str) and file_id in files, f"unknown file id: {file_id}")

    for entry in manifest.get("sections", []):
        fields(entry, ["file", "expected"], [], "sections")
        file_ref(entry["file"])
        expected = entry["expected"]
        require(isinstance(expected, list) and bool(expected), "expected sections must be a nonempty array")
        require(all(isinstance(x, str) and SECTION_ID.fullmatch(x) for x in expected), "invalid section id")
        require(len(set(expected)) == len(expected), "duplicate expected section id")
    for entry in manifest.get("placeholder_scans", []):
        fields(entry, ["file", "markers"], [], "placeholder scan")
        file_ref(entry["file"])
        require(isinstance(entry["markers"], list) and bool(entry["markers"]), "markers must be a nonempty array")
        for marker in entry["markers"]:
            nonempty(marker, "placeholder marker")
        require(len(set(entry["markers"])) == len(entry["markers"]), "duplicate placeholder marker")
    for entry in manifest.get("local_links", []):
        fields(entry, ["source", "target"], ["fragment"], "local link")
        file_ref(entry["source"])
        bounded(root, entry["target"])
        if "fragment" in entry:
            nonempty(entry["fragment"], "fragment")
    for entry in manifest.get("metadata_pairs", []):
        fields(entry, ["name", "left", "right"], [], "metadata pair")
        nonempty(entry["name"], "metadata pair name")
        for side in ("left", "right"):
            ref = entry[side]
            fields(ref, ["file", "pointer"], [], "metadata reference")
            file_ref(ref["file"])
            require(isinstance(ref["pointer"], str) and ref["pointer"].startswith("/"), "JSON pointer must begin with /")
            require(re.search(r"~(?![01])", ref["pointer"]) is None, "invalid JSON pointer escape")
    for entry in manifest.get("assets", []):
        fields(entry, ["file", "pixels", "placement_inches", "minimum_ppi"], [], "asset")
        file_ref(entry["file"])
        require(isinstance(entry["pixels"], list) and len(entry["pixels"]) == 2 and
                all(type(n) is int and n > 0 for n in entry["pixels"]), "pixels must be two positive integers")
        sizes = entry["placement_inches"]
        require(isinstance(sizes, list) and len(sizes) == 2, "placement_inches must contain width and height")
        require(all(type(n) in (int, float) and math.isfinite(n) and n > 0 for n in sizes + [entry["minimum_ppi"]]),
                "placement dimensions and minimum_ppi must be positive finite numbers")
    for name in manifest.get("external_checks", []):
        nonempty(name, "external check")
    for key, identity in (
        ("sections", lambda e: e["file"]),
        ("placeholder_scans", lambda e: e["file"]),
        ("local_links", lambda e: (e["source"], e["target"], e.get("fragment"))),
        ("metadata_pairs", lambda e: e["name"]),
        ("assets", lambda e: e["file"]),
        ("external_checks", lambda e: e),
    ):
        identities = [identity(e) for e in manifest.get(key, [])]
        require(len(set(identities)) == len(identities), f"duplicate declaration in {key}")
    return files, paths


class Checker:
    def __init__(self, root, files):
        self.root, self.files = root, files
        self.checks, self.text_cache, self.json_cache, self.available = [], {}, {}, set()
        self.fingerprints = {}

    def add(self, kind, subject, status, detail, **evidence):
        self.checks.append(dict(kind=kind, subject=subject, status=status, detail=detail, **evidence))

    def path(self, file_id):
        return bounded(self.root, self.files[file_id]["path"])

    def text(self, file_id):
        if file_id not in self.available:
            raise Unavailable("Declared file is unavailable; dependent check was not run.")
        if file_id not in self.text_cache:
            path = self.path(file_id)
            with path.open("rb") as stream:
                data = stream.read(MAX_TEXT_BYTES + 1)
            if len(data) > MAX_TEXT_BYTES:
                raise Unavailable("Text exceeds the 32 MiB read limit; dependent check was not run.")
            if hashlib.sha256(data).hexdigest() != self.fingerprints[file_id]:
                raise Unavailable("File bytes changed after hashing; dependent check was not run. Rerun on a stable copy.")
            self.text_cache[file_id] = data.decode("utf-8-sig")
        return self.text_cache[file_id]

    def scalar(self, ref):
        file_id = ref["file"]
        if file_id not in self.json_cache:
            self.json_cache[file_id] = parse_json(self.text(file_id))
        value = self.json_cache[file_id]
        for part in ref["pointer"].split("/")[1:]:
            key = part.replace("~1", "/").replace("~0", "~")
            if isinstance(value, dict) and key in value:
                value = value[key]
            elif isinstance(value, list) and re.fullmatch(r"0|[1-9][0-9]*", key) and int(key) < len(value):
                value = value[int(key)]
            else:
                raise ValueError(f"JSON pointer does not resolve: {file_id} {ref['pointer']}")
        if isinstance(value, (dict, list)):
            raise ValueError("Metadata comparisons require scalar JSON values.")
        return value

    def run_one(self, kind, subject, action):
        try:
            action()
        except Unavailable as error:
            self.add(kind, subject, "UNVERIFIED", str(error))
        except (OSError, ValueError, OverflowError) as error:
            self.add(kind, subject, "FAIL", str(error))

    def file(self, file_id, entry):
        path = self.path(file_id)
        if not path.is_file():
            raise ValueError(f"Missing file or not a regular file: {entry['path']}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            before = path.stat()
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
            after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise Unavailable("File changed while hashing; no stable fingerprint recorded. Rerun on a stable copy.")
        self.available.add(file_id)
        observed = digest.hexdigest()
        self.fingerprints[file_id] = observed
        expected = entry.get("sha256")
        status = "OBSERVED" if expected is None else "PASS" if expected == observed else "FAIL"
        self.add("file_sha256", file_id, status,
                 "SHA-256 computed; no expected baseline supplied." if expected is None else "Compared exact bytes with supplied SHA-256.",
                 path=entry["path"], sha256=observed, expected_sha256=expected, bytes=after.st_size)

    def sections(self, entry):
        actual = [match.group(1) for line in self.text(entry["file"]).splitlines()
                  for match in [SECTION_LINE.fullmatch(line)] if match]
        duplicates = sorted(key for key, count in Counter(actual).items() if count > 1)
        self.add("sections", entry["file"], "PASS" if actual == entry["expected"] and not duplicates else "FAIL",
                 "Compared declared section marker IDs, order, and duplicates; body content was not compared.",
                 expected=entry["expected"], actual=actual, duplicates=duplicates)

    def placeholders(self, entry):
        text = self.text(entry["file"])
        counts = {marker: text.count(marker) for marker in entry["markers"]}
        self.add("placeholder_markers", entry["file"], "FAIL" if any(counts.values()) else "PASS",
                 "Case-sensitive literal marker counts only; other placeholders may remain.", counts=counts)

    def link(self, entry):
        exists = bounded(self.root, entry["target"]).is_file()
        self.add("local_destination", entry["source"], "PASS" if exists else "FAIL",
                 "Checked declared local target file existence only.", target=entry["target"])
        self.add("link_behavior", entry["source"], "UNVERIFIED",
                 "Source link wiring, navigation, fragment resolution, and destination content were not tested.",
                 target=entry["target"], fragment=entry.get("fragment"))

    def metadata(self, entry):
        left, right = self.scalar(entry["left"]), self.scalar(entry["right"])
        if any(value is None or (isinstance(value, str) and not value.strip()) for value in (left, right)):
            self.add("metadata_pair", entry["name"], "UNVERIFIED",
                     "At least one field is null or blank; no substantive value comparison is possible.",
                     left=entry["left"], right=entry["right"])
            return
        equal = type(left) is type(right) and left == right
        self.add("metadata_pair", entry["name"], "PASS" if equal else "FAIL",
                 "Compared explicitly declared same-field JSON scalar values with exact type and value equality; no normalization.",
                 left=entry["left"], right=entry["right"])

    def asset(self, entry):
        ppi = [pixels / inches for pixels, inches in zip(entry["pixels"], entry["placement_inches"])]
        require(all(math.isfinite(value) for value in ppi), "PPI arithmetic is not finite")
        self.add("declared_asset_arithmetic", entry["file"], "PASS" if min(ppi) >= entry["minimum_ppi"] else "FAIL",
                 "Computed width/height PPI from recorded dimensions and placement only.",
                 ppi=ppi, minimum_ppi=entry["minimum_ppi"], pixels=entry["pixels"], placement_inches=entry["placement_inches"])
        self.add("actual_asset_quality", entry["file"], "UNVERIFIED",
                 "Actual pixel dimensions, crop/scale, embedding, effective PPI in the exported file, and visual quality were not inspected.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Explicit project directory (resolved before establishing the boundary)")
    parser.add_argument("--manifest", required=True, help="JSON manifest path relative to --root")
    parser.add_argument("--report", help="Optional NEW JSON report path relative to --root; parent must exist")
    args = parser.parse_args()
    try:
        root = Path(args.root).resolve(strict=True)
        require(root.is_dir(), "root must be a directory")
        manifest_path = bounded(root, args.manifest)
        require(manifest_path.stat().st_size <= MAX_TEXT_BYTES, "manifest exceeds 32 MiB")
        manifest = parse_json(manifest_path.read_text(encoding="utf-8-sig"))
        files, input_paths = validate(manifest, root)
        report_path = None
        if args.report:
            report_path = bounded(root, args.report)
            input_paths.add(manifest_path)
            input_paths.update(bounded(root, link["target"]) for link in manifest.get("local_links", []))
            require(report_path not in input_paths, "report path collides with a declared input")
            require(not report_path.exists(), "report already exists; choose a new report path")
            require(report_path.parent.is_dir(), "report parent directory must already exist")
        checker = Checker(root, files)
        for file_id, entry in files.items():
            checker.run_one("file_sha256", file_id, lambda i=file_id, e=entry: checker.file(i, e))
        for key, kind, label, method in (
            ("sections", "sections", "file", checker.sections),
            ("placeholder_scans", "placeholder_markers", "file", checker.placeholders),
            ("local_links", "local_destination", "source", checker.link),
            ("metadata_pairs", "metadata_pair", "name", checker.metadata),
            ("assets", "declared_asset_arithmetic", "file", checker.asset),
        ):
            for entry in manifest.get(key, []):
                checker.run_one(kind, entry[label], lambda e=entry, m=method: m(e))
        for name in manifest.get("external_checks", []):
            checker.add("external_check", name, "UNVERIFIED", "Not run by this helper; no external tools or network access are used.")
        counts = {status: sum(c["status"] == status for c in checker.checks) for status in ("PASS", "FAIL", "OBSERVED", "UNVERIFIED")}
        report = dict(schema_version=1, generated_at=datetime.now(timezone.utc).isoformat(),
                      scope="Declared mechanical checks only; this report is not release or platform approval.",
                      outcome="failures_found" if counts["FAIL"] else "no_failures_found", counts=counts,
                      checks=checker.checks, limits=LIMITS)
        serialized = json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + "\n"
        if report_path is not None:
            report_path = bounded(root, args.report)
            with report_path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(serialized)
        sys.stdout.write(serialized)
        return 1 if counts["FAIL"] else 0
    except (OSError, ValueError, OverflowError) as error:
        print(f"Manifest or invocation error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
