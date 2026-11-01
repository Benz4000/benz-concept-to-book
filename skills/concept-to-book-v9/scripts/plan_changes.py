#!/usr/bin/env python3
"""Create a read-only, hash-based advisory change impact report."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
HASH = re.compile(r"^[0-9a-f]{64}$")
MAX_JSON = 8 * 1024 * 1024
MAX_ARTIFACTS = 10000
MAX_CHECKS = 10000
MAX_INPUT = 256 * 1024 * 1024
MAX_TOTAL = 1024 * 1024 * 1024


class InputError(ValueError):
    pass


class MissingInput(InputError):
    pass


def _unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out: raise InputError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def valid_id(value):
    return isinstance(value,str) and bool(ID.fullmatch(value)) and value.upper() not in {"CON","PRN","AUX","NUL",*(f"COM{i}" for i in range(1,10)),*(f"LPT{i}" for i in range(1,10))}


def safe_component(part):
    return part not in ("", ".", "..") and not any(ord(c)<32 for c in part) and ":" not in part and not part.endswith((" ", ".")) and part.split(".")[0].rstrip(" .").upper() not in {"CON","PRN","AUX","NUL",*(f"COM{i}" for i in range(1,10)),*(f"LPT{i}" for i in range(1,10))}


def read_json(path: Path):
    try:
        with path.open("rb") as f: raw=f.read(MAX_JSON+1)
        if len(raw)>MAX_JSON: raise InputError(f"JSON exceeds {MAX_JSON} byte limit: {path}")
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as e:
        raise InputError(f"cannot read JSON {path}: {e}") from e


def safe_file(root: Path, rel: str) -> Path:
    if not isinstance(rel, str) or not rel or Path(rel).is_absolute() or "\\" in rel:
        raise InputError(f"expected safe relative POSIX path, got {rel!r}")
    p = Path(rel)
    if any(not safe_component(part) for part in rel.split("/")):
        raise InputError(f"unsafe relative path: {rel!r}")
    candidate = root.joinpath(*p.parts)
    # Resolve every existing component and reject symlinks/reparse-like indirections.
    cur = root
    for part in p.parts:
        cur = cur / part
        if cur.is_symlink() or (hasattr(cur, "is_junction") and cur.is_junction()):
            raise InputError(f"symlink input rejected: {rel}")
    try:
        candidate.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as e:
        if not candidate.exists(): raise MissingInput(f"input missing: {rel}") from e
        raise InputError(f"input outside root: {rel}") from e
    if not candidate.is_file():
        raise InputError(f"not a file: {rel}")
    return candidate


def sha(path: Path) -> str:
    if path.stat().st_size > MAX_INPUT: raise InputError(f"artifact exceeds {MAX_INPUT} byte limit: {path}")
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_graph(graph):
    if not isinstance(graph, dict) or set(graph) - {"schema_version", "artifacts", "checks"} or graph.get("schema_version") != 1:
        raise InputError("graph must be an object with schema_version: 1")
    arts, checks = graph.get("artifacts"), graph.get("checks", [])
    if not isinstance(arts, list) or not isinstance(checks, list) or len(arts)>MAX_ARTIFACTS or len(checks)>MAX_CHECKS:
        raise InputError("artifacts and checks must be arrays")
    ids, paths, amap, cmap = set(), set(), {}, {}
    for a in arts:
        if not isinstance(a, dict): raise InputError("each artifact must be an object")
        if set(a) - {"id", "path", "depends_on"}: raise InputError("unknown artifact field")
        if not valid_id(a.get("id")):
            raise InputError("each artifact needs a unique safe id")
        if a["id"] in ids: raise InputError(f"duplicate id: {a['id']}")
        ids.add(a["id"]); amap[a["id"]] = a
        if not isinstance(a.get("path"), str) or len(a["path"])>1024: raise InputError(f"artifact {a['id']} needs a path of at most 1024 characters")
        if a["path"] in paths: raise InputError(f"duplicate artifact path: {a['path']}")
        paths.add(a["path"])
        deps = a.get("depends_on", [])
        if not isinstance(deps, list) or len(deps)>MAX_ARTIFACTS or any(not valid_id(x) for x in deps) or len(set(deps))!=len(deps): raise InputError(f"bad depends_on for {a['id']}")
    for a in arts:
        for dep in a.get("depends_on", []):
            if dep not in ids: raise InputError(f"unknown dependency {dep!r} in {a['id']}")
    visiting, done = set(), set()
    def visit(node):
        if node in visiting: raise InputError(f"dependency cycle involving {node}")
        if node in done: return
        visiting.add(node)
        for d in amap[node].get("depends_on", []): visit(d)
        visiting.remove(node); done.add(node)
    for node in ids: visit(node)
    for c in checks:
        if not isinstance(c, dict): raise InputError("each check must be an object")
        if set(c) - {"id", "inputs", "status", "reviewed_sha256", "reviewed_state_sha256"}: raise InputError("unknown check field")
        if not valid_id(c.get("id")): raise InputError("each check needs a safe id")
        if c["id"] in cmap: raise InputError(f"duplicate check id: {c['id']}")
        cmap[c["id"]] = c
        if not isinstance(c.get("inputs", []), list) or len(c.get("inputs", []))>MAX_ARTIFACTS: raise InputError(f"inputs must be a bounded array for {c['id']}")
        if any(not valid_id(i) for i in c.get("inputs", [])): raise InputError(f"unsafe check input id for {c['id']}")
        if "status" in c and not isinstance(c["status"], str): raise InputError(f"status must be text for {c['id']}")
        # Unknown check inputs are retained in the report as mapping gaps.
        if "reviewed_sha256" in c:
            if not isinstance(c["reviewed_sha256"], dict): raise InputError(f"reviewed_sha256 must be object for {c['id']}")
            if any(not valid_id(aid) or not isinstance(h,str) or not HASH.fullmatch(h) for aid,h in c["reviewed_sha256"].items()): raise InputError(f"invalid reviewed hash for {c['id']}")
        if c.get("reviewed_state_sha256") is not None and (not isinstance(c["reviewed_state_sha256"],str) or not HASH.fullmatch(c["reviewed_state_sha256"])): raise InputError(f"invalid reviewed_state_sha256 for {c['id']}")
    return amap, cmap


def build_report(root: Path, graph, baseline=None):
    amap, cmap = validate_graph(graph)
    hashes = {}; missing_files=[]; total=0
    for i,a in amap.items():
        try:
            path=safe_file(root,a["path"]); total += path.stat().st_size
            if total > MAX_TOTAL: raise InputError(f"total artifact bytes exceed {MAX_TOTAL}")
            hashes[i]=sha(path)
        except MissingInput:
            hashes[i]=None; missing_files.append(i)
    curr_deps = {i: sorted(a.get("depends_on", [])) for i, a in amap.items()}
    prev_art = baseline.get("artifacts", {}) if isinstance(baseline, dict) else {}
    prev_deps = baseline.get("dependencies", {}) if isinstance(baseline, dict) else {}
    if baseline is not None:
        if not isinstance(baseline,dict) or set(baseline)!={"schema_version","kind","artifacts","dependencies","changes","checks","missing_artifacts","notes"} or baseline.get("schema_version")!=1 or baseline.get("kind")!="change-impact-report": raise InputError("baseline must be a previous schema_version 1 change-impact report")
    if not isinstance(prev_art, dict) or not isinstance(prev_deps, dict): raise InputError("baseline must contain artifacts and dependencies objects")
    if baseline is not None and not isinstance(baseline.get("missing_artifacts",[]),list): raise InputError("invalid missing_artifacts in baseline")
    for aid,row in prev_art.items():
        if not valid_id(aid) or not isinstance(row,dict) or set(row)!={"path","sha256"} or not isinstance(row["path"],str) or (row["sha256"] is not None and (not isinstance(row["sha256"],str) or not HASH.fullmatch(row["sha256"]))): raise InputError("invalid artifact record in baseline")
    for aid,deps in prev_deps.items():
        if not valid_id(aid) or not isinstance(deps,list) or any(not valid_id(d) for d in deps): raise InputError("invalid dependencies in baseline")
    prior_state_required=set()
    old_checks=baseline.get("checks",[]) if baseline is not None else []
    if not isinstance(old_checks,list) or len(old_checks)>MAX_CHECKS: raise InputError("invalid checks in baseline")
    seen_old_checks=set()
    for row in old_checks:
        if not isinstance(row,dict): raise InputError("invalid check row in baseline")
        required={"check_id","authored_status","affected_inputs","reconsider","stale_or_unreviewed","missing_inputs","state_required","current_state_sha256","reviewed_state_sha256","advice"}
        if set(row)!=required or not valid_id(row["check_id"]) or row["check_id"] in seen_old_checks: raise InputError("invalid or duplicate check row in baseline")
        seen_old_checks.add(row["check_id"])
        if not isinstance(row["authored_status"],str) or not isinstance(row["advice"],str) or not isinstance(row["reconsider"],bool) or not isinstance(row["state_required"],bool): raise InputError("invalid check row fields in baseline")
        for key in ("affected_inputs","stale_or_unreviewed","missing_inputs"):
            if not isinstance(row[key],list) or any(not valid_id(x) for x in row[key]): raise InputError("invalid check row artifact IDs in baseline")
        if not isinstance(row["current_state_sha256"],str) or not HASH.fullmatch(row["current_state_sha256"]): raise InputError("invalid current_state_sha256 in baseline")
        if row["reviewed_state_sha256"] is not None and (not isinstance(row["reviewed_state_sha256"],str) or not HASH.fullmatch(row["reviewed_state_sha256"])): raise InputError("invalid reviewed_state_sha256 in baseline")
        if row["state_required"]: prior_state_required.add(row["check_id"])
    direct = {}
    all_ids = set(hashes) | set(prev_art) | set(prev_deps)
    for i in sorted(all_ids):
        reasons=[]
        if i not in hashes: reasons.append("removed")
        elif hashes[i] is None: reasons.append("missing")
        elif i not in prev_art: reasons.append("new")
        elif hashes[i] != prev_art[i].get("sha256"): reasons.append("content_changed")
        old, new = set(prev_deps.get(i, [])), set(curr_deps.get(i, []))
        if old != new: reasons.append("dependencies_changed")
        row={"artifact_id":i,"direct_reasons":reasons,"transitive":False}
        if reasons: direct[i]=row
    impacted=set(direct)
    # Propagate through the union of prior and current edges until stable.
    edges={i:set(curr_deps.get(i,[])) | set(prev_deps.get(i,[])) for i in set(curr_deps)|set(prev_deps)}
    changed=True
    while changed:
        changed=False
        for aid, deps in edges.items():
            if aid not in impacted and set(deps) & impacted:
                causes=sorted(set(deps)&impacted)
                impacted.add(aid); changed=True
                direct[aid]={"artifact_id":aid,"direct_reasons":[],"transitive":True,"because_of":causes}
    check_rows=[]
    for cid,c in cmap.items():
        affected=sorted(set(c.get("inputs",[])) & impacted)
        stale=[]; missing=[]
        for aid in c.get("inputs",[]):
            if aid not in hashes or hashes[aid] is None: missing.append(aid); continue
            expected=c.get("reviewed_sha256",{}).get(aid)
            if expected != hashes[aid]: stale.append(aid)
        # Build a stable review identity over this check's declared inputs,
        # their complete current upstream closure, bytes, and dependency edges.
        closure=set(c.get("inputs",[])); todo=list(closure)
        while todo:
            aid=todo.pop()
            for dep in curr_deps.get(aid,[]):
                if dep not in closure: closure.add(dep); todo.append(dep)
        closure_artifacts=[{"id":aid,"sha256":hashes.get(aid)} for aid in sorted(closure)]
        closure_edges=sorted([[aid,dep] for aid in closure for dep in curr_deps.get(aid,[])])
        state_doc={"check_id":cid,"inputs":sorted(c.get("inputs",[])),"artifacts":closure_artifacts,"dependencies":closure_edges}
        current_state=hashlib.sha256(json.dumps(state_doc,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("utf-8")).hexdigest()
        reviewed_state=c.get("reviewed_state_sha256")
        state_required=bool(closure_edges) or reviewed_state is not None or cid in prior_state_required
        state_stale=state_required and reviewed_state!=current_state
        needs=bool(affected or missing or stale or state_stale)
        if state_stale: advice="reconsider because the upstream dependency closure or topology has not been reviewed at its current digest"
        elif affected or missing: advice="reconsider evidence because an input or upstream dependency changed or is missing"
        elif stale: advice="reconsider because a declared input hash is stale or absent"
        else: advice="declared evidence matches the current scoped inputs and dependency closure"
        check_rows.append({"check_id":cid,"authored_status":c.get("status","unspecified"),"affected_inputs":affected,"reconsider":needs,"stale_or_unreviewed":sorted(stale),"missing_inputs":sorted(missing),"state_required":state_required,"current_state_sha256":current_state,"reviewed_state_sha256":reviewed_state,"advice":advice})
    return {"schema_version":1,"kind":"change-impact-report","artifacts":{i:{"path":a["path"],"sha256":hashes[i]} for i,a in sorted(amap.items())},"dependencies":curr_deps,"changes":[direct[i] for i in sorted(direct)],"checks":check_rows,"missing_artifacts":sorted(missing_files),"notes":["Advisory hash and dependency comparison only; hashes do not establish semantic correctness.","Check statuses and reviewed_sha256 declarations were read as authored and were not changed."]}


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root",required=True,type=Path); ap.add_argument("--graph",required=True); ap.add_argument("--baseline"); ap.add_argument("--report")
    ns=ap.parse_args(argv)
    try:
        root=ns.root.resolve(strict=True)
        if not root.is_dir(): raise InputError("--root must be an existing directory")
        graph=read_json(safe_file(root,ns.graph))
        base=read_json(safe_file(root,ns.baseline)) if ns.baseline else None
        result=build_report(root,graph,base)
        output=json.dumps(result,indent=2,ensure_ascii=False)+"\n"
        if ns.report:
            target=Path(ns.report)
            if target.is_absolute() or "\\" in ns.report or ":" in ns.report or any(not safe_component(x) for x in ns.report.split("/")): raise InputError("--report must be a safe relative path")
            dest=root.joinpath(*Path(ns.report).parts)
            cur=root
            for part in Path(ns.report).parts[:-1]:
                cur=cur/part
                if cur.is_symlink() or (hasattr(cur,"is_junction") and cur.is_junction()): raise InputError("report parent symlink or junction rejected")
            dest.parent.mkdir(parents=True,exist_ok=True)
            try: dest.parent.resolve(strict=True).relative_to(root)
            except (OSError,ValueError) as e: raise InputError("report path escapes --root") from e
            with dest.open("x",encoding="utf-8",newline="\n") as f: f.write(output)
        else: sys.stdout.write(output)
    except (InputError,OSError) as e:
        print(f"plan_changes: {e}",file=sys.stderr); return 2
    return 0

if __name__ == "__main__": raise SystemExit(main())
