#!/usr/bin/env python3
"""Read-only checks of explicit continuity declarations. Python 3.9+, stdlib only."""

import argparse
import hashlib
import json
import re
import stat
import sys
from collections import defaultdict
from pathlib import Path, PureWindowsPath

MAX_MANIFEST = 2 * 1024 * 1024
MAX_FILE = 32 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024
MAX_RECORDS = 1000
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}\Z")
TABLES = ("files", "evidence", "scenes", "facts", "transitions", "assertions",
          "topics", "knowledge", "knowledge_uses", "reveals")
DECLARATIONS = TABLES[2:]
SCHEMAS = {
    "files": ("id path", "sha256"),
    "evidence": ("id file locator", ""),
    "scenes": ("id scope story_time read_order reader_ceiling evidence", ""),
    "facts": ("id scope entity key value start until evidence", ""),
    "transitions": ("id scene entity key from to evidence", ""),
    "assertions": ("id scene entity key value evidence", ""),
    "topics": ("id scope reveal_from evidence", ""),
    "knowledge": ("id scope character topic state start until evidence", ""),
    "knowledge_uses": ("id scene character topic evidence", ""),
    "reveals": ("id scene topic evidence", ""),
}
LIMITS = [
    "The original manuscript and accepted scoped decisions remain authoritative.",
    "PASS covers declared values only; prose, evidence locators, interpretation, omissions, and full canon are not verified.",
    "Story times are project-defined integer points; read order and reader ceilings are separate integer ranks.",
    "Scopes are exact, isolated IDs; there is no automatic inheritance, alternate-timeline merging, or retroactive update.",
    "Hashes identify the bytes read. An absent baseline is OBSERVED, not approval of those bytes.",
    "Source and decision IDs are trace labels; their existence, authority, and downstream completeness require human review.",
    "No network, prose extraction, inferred canon, autofix, or project-file writes are performed.",
]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def fields(obj, required, optional, label):
    require(isinstance(obj, dict), label + ": expected object")
    required, optional = set(required.split()), set(optional.split())
    require(required <= obj.keys(), label + ": missing fields " + str(sorted(required - obj.keys())))
    require(obj.keys() <= required | optional, label + ": unknown fields " + str(sorted(obj.keys() - required - optional)))


def string(value, label):
    require(isinstance(value, str) and bool(value.strip()) and len(value) <= 2000,
            label + ": expected nonempty string of at most 2000 characters")


def identifier(value, label):
    require(isinstance(value, str) and ID.fullmatch(value), label + ": invalid stable ID")


def ids(value, label):
    require(isinstance(value, list), label + ": expected ID array")
    for item in value:
        identifier(item, label)
    require(len(value) == len(set(value)), label + ": duplicate ID")


def point(value, label, rank=False):
    require(value is None or (type(value) is int and abs(value) <= 10**9 and (not rank or value >= 0)),
            label + ": expected bounded integer or null")


def bounded(root, relative):
    """Allow local relative paths only; reject aliases and links below the root."""
    string(relative, "path")
    win = PureWindowsPath(relative)
    require(not win.drive and not win.root and not Path(relative).is_absolute(), "path must be relative: " + relative)
    require(not re.search(r'[\\:\x00-\x1f*?"<>|]', relative), "unsafe path characters: " + relative)
    parts = relative.split("/")
    require(all(p not in ("", ".", "..") and not p.endswith((" ", ".")) for p in parts),
            "unsafe path component: " + relative)
    reserved = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?\Z", re.I)
    cursor = root
    for part in parts:
        require(not reserved.fullmatch(part), "reserved path component: " + relative)
        cursor = cursor / part
        try:
            info = cursor.lstat()
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode) and not (getattr(info, "st_file_attributes", 0) & 0x400),
                "symlink/reparse path forbidden: " + relative)
    resolved = cursor.resolve()
    require(root in resolved.parents, "path escapes project root: " + relative)
    return resolved


def read_bytes(root, relative, limit):
    path = bounded(root, relative)
    require(path.is_file(), "missing or non-regular input: " + relative)
    with path.open("rb") as stream:
        before = path.stat()
        require(stat.S_ISREG(before.st_mode) and before.st_size <= limit, "input exceeds size limit: " + relative)
        data = stream.read(limit + 1)
        after = path.stat()
    require(len(data) <= limit and (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns),
            "input changed during read or exceeded limit: " + relative)
    bounded(root, relative)
    return data


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj, "duplicate JSON key: " + key)
        obj[key] = value
    return obj


def reject_number(value):
    raise ValueError("only bounded integer numbers are supported: " + value)


def validate(manifest, root):
    fields(manifest, "schema_version " + " ".join(TABLES), "", "manifest")
    require(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1, "schema_version must be 1")
    require(all(isinstance(manifest[t], list) for t in TABLES), "all record tables must be arrays")
    require(sum(len(manifest[t]) for t in TABLES) <= MAX_RECORDS, "manifest exceeds 1000 total records")
    tables, seen, paths = {}, set(), set()
    for name in TABLES:
        tables[name] = {}
        for record in manifest[name]:
            required, optional = SCHEMAS[name]
            if name in DECLARATIONS:
                optional += " source_ids decision_ids"
            fields(record, required, optional, name)
            identifier(record["id"], name + " id")
            require(record["id"] not in seen, "IDs must be globally unique: " + record["id"])
            seen.add(record["id"])
            tables[name][record["id"]] = record
            for key in ("scope", "entity", "key", "character", "scene", "topic", "file"):
                if key in record:
                    identifier(record[key], name + " " + key)
            for key in ("evidence", "source_ids", "decision_ids"):
                if key in record:
                    ids(record[key], name + " " + key)
            for key in ("story_time", "start"):
                if key in record:
                    point(record[key], name + " " + key)
            for key in ("read_order", "reader_ceiling", "reveal_from"):
                if key in record:
                    point(record[key], name + " " + key, rank=True)
            if "until" in record:
                if record["until"] != "open":
                    point(record["until"], name + " until")
                if type(record["start"]) is int and type(record["until"]) is int:
                    require(record["start"] < record["until"], name + ": interval must have start < until")
            for key in ("value", "from", "to"):
                if key in record and record[key] is not None:
                    string(record[key], name + " " + key)
            if name == "files":
                path = bounded(root, record["path"])
                require(path not in paths, "duplicate input path: " + record["path"])
                paths.add(path)
                if "sha256" in record:
                    require(isinstance(record["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", record["sha256"]),
                            "sha256 must contain 64 lowercase hexadecimal characters")
            if name == "evidence":
                string(record["locator"], "evidence locator")
            if name == "knowledge":
                require(record["state"] in ("knows", "unaware", None), "knowledge state must be knows, unaware, or null")
    for name in TABLES:
        for record in manifest[name]:
            for key, target in (("file", "files"), ("scene", "scenes"), ("topic", "topics")):
                if key in record:
                    require(record[key] in tables[target], name + ": missing " + key + " ID " + record[key])
            for ref in record.get("evidence", []):
                require(ref in tables["evidence"], name + ": missing evidence ID " + ref)
    return tables


class Checker:
    def __init__(self, root, manifest, tables, manifest_hash):
        self.root, self.manifest, self.tables = root, manifest, tables
        self.checks, self.inputs, self.usable = [], [], set()
        self.manifest_hash = manifest_hash

    def add(self, code, status, detail, *records):
        linked = {r["id"]: r for r in records}
        for record in records:
            for key, table in (("scene", "scenes"), ("topic", "topics")):
                if key in record:
                    related = self.tables[table][record[key]]
                    linked[related["id"]] = related
        records = list(linked.values())
        self.checks.append({"code": code, "status": status, "detail": detail,
                            "declaration_ids": [r["id"] for r in records],
                            "evidence_ids": sorted({e for r in records for e in r.get("evidence", [])} |
                                                   {r["id"] for r in records if r["id"] in self.tables["evidence"]}),
                            "source_ids": sorted({e for r in records for e in r.get("source_ids", [])}),
                            "decision_ids": sorted({e for r in records for e in r.get("decision_ids", [])})})

    def inputs_check(self):
        total = 0
        for record in self.manifest["files"]:
            try:
                data = read_bytes(self.root, record["path"], min(MAX_FILE, MAX_TOTAL - total))
                total += len(data)
                digest = hashlib.sha256(data).hexdigest()
                expected = record.get("sha256")
                self.inputs.append({"id": record["id"], "path": record["path"], "sha256": digest,
                                    "expected_sha256": expected, "bytes": len(data)})
                status = "OBSERVED" if expected is None else "PASS" if digest == expected else "FAIL"
                self.add("input_hash", status, "Exact input bytes hashed; expected baseline compared only if supplied.", record)
                if status != "FAIL":
                    self.usable.add(record["id"])
            except (OSError, ValueError) as error:
                self.add("input_unavailable", "UNVERIFIED", str(error), record)
        for record in self.manifest["evidence"]:
            if record["file"] not in self.usable:
                self.add("evidence_unavailable", "UNVERIFIED", "Evidence input unavailable or differs from supplied baseline.", record)
        for name in DECLARATIONS:
            for record in self.manifest[name]:
                if not record["evidence"] or any(self.tables["evidence"][e]["file"] not in self.usable for e in record["evidence"]):
                    self.add("declaration_evidence", "UNVERIFIED", "Declaration lacks usable evidence; semantic comparisons below concern ledger values only.", record)

    @staticmethod
    def interval_known(record):
        return record["start"] is not None and record["until"] is not None

    @staticmethod
    def end(record):
        return float("inf") if record["until"] == "open" else record["until"]

    def groups(self, table, keys, value_key):
        grouped = defaultdict(list)
        for record in self.manifest[table]:
            grouped[tuple(record[k] for k in keys)].append(record)
            if not self.interval_known(record) or record[value_key] is None:
                self.add("incomplete_interval", "UNVERIFIED", "Unknown bound or value; do not infer a state or absence.", record)
        for group in grouped.values():
            known = sorted((r for r in group if self.interval_known(r)), key=lambda r: r["start"])
            previous = None
            for record in known:
                if previous is not None and record["start"] < self.end(previous):
                    self.add("interval_overlap", "FAIL", "Explicit intervals overlap for the same scope/entity/property; reconcile even duplicate values.", previous, record)
                if previous is None or self.end(record) > self.end(previous):
                    previous = record
        return grouped

    def state(self, grouped, key, time, expected, owner, value_key="value", before=False):
        if time is None or expected is None:
            self.add("state_comparison", "UNVERIFIED", "Time or expected state unknown.", owner)
            return
        candidates = grouped.get(key, [])
        uncertain = [r for r in candidates if not self.interval_known(r)]
        active = [r for r in candidates if self.interval_known(r) and
                  ((r["start"] < time <= self.end(r)) if before else (r["start"] <= time < self.end(r)))]
        if uncertain or len(active) != 1 or active[0][value_key] is None:
            self.add("state_comparison", "UNVERIFIED", "No unique known state at this story time; gaps and unknown bounds do not establish absence.", owner, *(active + uncertain))
            return
        status = "PASS" if active[0][value_key] == expected else "FAIL"
        self.add("state_comparison", status, "Compared explicit " + ("pre-transition" if before else "scene-time") + " state with exact declared value.", owner, active[0])

    def run(self):
        self.inputs_check()
        facts = self.groups("facts", ("scope", "entity", "key"), "value")
        knowledge = self.groups("knowledge", ("scope", "character", "topic"), "state")
        demands = {}
        for name, sides in (("assertions", (("value", "at"),)),
                            ("transitions", (("from", "before"), ("to", "at")))):
            for record in self.manifest[name]:
                for field, side in sides:
                    if record[field] is None:
                        continue
                    key = (record["scene"], record["entity"], record["key"], side)
                    previous = demands.get(key)
                    if previous is not None and previous[0] != record[field]:
                        self.add("scene_declaration_conflict", "FAIL",
                                 "Explicit scene declarations demand different values for the same property and time side.",
                                 previous[1], record)
                    else:
                        demands[key] = (record[field], record)
        for scene in self.manifest["scenes"]:
            if any(scene[k] is None for k in ("story_time", "read_order", "reader_ceiling")):
                self.add("scene_order", "UNVERIFIED", "One or more story/disclosure coordinates are unknown.", scene)
        for topic in self.manifest["topics"]:
            if topic["reveal_from"] is None:
                self.add("reveal_gate", "UNVERIFIED", "Earliest permitted reader disclosure is unknown.", topic)
        for record in self.manifest["knowledge"]:
            topic = self.tables["topics"][record["topic"]]
            if record["scope"] != topic["scope"]:
                self.add("scope_mismatch", "FAIL", "Knowledge and topic scopes differ; no inheritance is inferred.", record, topic)
        for name in ("assertions", "transitions"):
            for record in self.manifest[name]:
                scene = self.tables["scenes"][record["scene"]]
                key = (scene["scope"], record["entity"], record["key"])
                if name == "transitions":
                    self.state(facts, key, scene["story_time"], record["from"], record, before=True)
                    self.state(facts, key, scene["story_time"], record["to"], record)
                else:
                    self.state(facts, key, scene["story_time"], record["value"], record)
        for name in ("knowledge_uses", "reveals"):
            for record in self.manifest[name]:
                scene = self.tables["scenes"][record["scene"]]
                topic = self.tables["topics"][record["topic"]]
                if scene["scope"] != topic["scope"]:
                    self.add("scope_mismatch", "FAIL", "Scene and topic scopes differ; no inheritance is inferred.", record, scene, topic)
                    continue
                if name == "knowledge_uses":
                    self.state(knowledge, (scene["scope"], record["character"], record["topic"]),
                               scene["story_time"], "knows", record, value_key="state")
                else:
                    coordinates = (scene["read_order"], scene["reader_ceiling"], topic["reveal_from"])
                    if any(x is None for x in coordinates):
                        self.add("reader_reveal", "UNVERIFIED", "Reading position, reader ceiling, or reveal gate unknown.", record, scene, topic)
                    else:
                        allowed = topic["reveal_from"] <= min(scene["read_order"], scene["reader_ceiling"])
                        self.add("reader_reveal", "PASS" if allowed else "FAIL", "Disclosure compared with both reading position and the permitted reader ceiling.", record, scene, topic)
        if not self.manifest["scenes"] or not any(self.manifest[t] for t in ("assertions", "transitions", "knowledge_uses", "reveals")):
            self.add("coverage", "UNVERIFIED", "No scene or no declared scene checks; an empty ledger cannot establish continuity.")
        counts = {status: sum(c["status"] == status for c in self.checks) for status in ("PASS", "FAIL", "OBSERVED", "UNVERIFIED")}
        outcome = "failures_found" if counts["FAIL"] else "incomplete" if counts["UNVERIFIED"] else "declared_checks_passed"
        return {"schema_version": 1, "scope": "Explicit ledger declarations only; no manuscript or release approval.",
                "manifest_sha256": self.manifest_hash, "inputs": self.inputs,
                "outcome": outcome, "counts": counts, "checks": self.checks, "limits": LIMITS}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Explicit local project directory")
    parser.add_argument("--manifest", required=True, help="Local ledger path relative to --root, using forward slashes")
    args = parser.parse_args()
    try:
        require(not PureWindowsPath(args.root).drive.startswith("\\\\"), "network roots are forbidden")
        root = Path(args.root).resolve(strict=True)
        require(root.is_dir(), "root must be a directory")
        data = read_bytes(root, args.manifest, MAX_MANIFEST)
        manifest = json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique_object,
                              parse_constant=reject_number, parse_float=reject_number)
        tables = validate(manifest, root)
        report = Checker(root, manifest, tables, hashlib.sha256(data).hexdigest()).run()
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + "\n")
        return 1 if report["counts"]["FAIL"] else 3 if report["counts"]["UNVERIFIED"] else 0
    except (OSError, ValueError, OverflowError, RecursionError) as error:
        print("Manifest or invocation error: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
