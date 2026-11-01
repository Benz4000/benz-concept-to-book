#!/usr/bin/env python3
"""Build a self-contained, explicitly scoped HTML review packet."""
from __future__ import annotations
import argparse, difflib, hashlib, html, json, re, shutil, sys
from pathlib import Path
from urllib.parse import quote

ID=re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
MAX_JSON=8*1024*1024
MAX_FILE=20*1024*1024
MAX_TEXT=2*1024*1024
MAX_ITEMS=100
MAX_LIST=100
MAX_TOTAL=200*1024*1024
class InputError(ValueError): pass

def unique_pairs(pairs):
    out={}
    for k,v in pairs:
        if k in out: raise InputError(f"duplicate JSON key: {k}")
        out[k]=v
    return out

def safe_component(part):
    return part not in ("", ".", "..") and not any(ord(c)<32 for c in part) and ":" not in part and not part.endswith((" ", ".")) and part.split(".")[0].rstrip(" .").upper() not in {"CON","PRN","AUX","NUL",*(f"COM{i}" for i in range(1,10)),*(f"LPT{i}" for i in range(1,10))}

def safe_id(value):
    return isinstance(value,str) and bool(ID.fullmatch(value)) and safe_component(value)

def safe_file(root, rel):
    if not isinstance(rel,str) or not rel or len(rel)>1024 or Path(rel).is_absolute() or "\\" in rel or ":" in rel or any(not safe_component(x) for x in rel.split("/")): raise InputError(f"unsafe relative path: {rel!r}")
    p=root.joinpath(*Path(rel).parts); cur=root
    for part in Path(rel).parts:
        cur=cur/part
        if cur.is_symlink() or (hasattr(cur,"is_junction") and cur.is_junction()): raise InputError(f"symlink or junction input rejected: {rel}")
    try: p.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError,ValueError) as e: raise InputError(f"missing input or path outside root: {rel}") from e
    if not p.is_file(): raise InputError(f"not a file: {rel}")
    if p.stat().st_size>MAX_FILE: raise InputError(f"input exceeds {MAX_FILE} byte limit: {rel}")
    return p
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read_json(p):
    try:
        with p.open("rb") as f: raw=f.read(MAX_JSON+1)
        if len(raw)>MAX_JSON: raise InputError(f"manifest exceeds {MAX_JSON} byte limit")
        return json.loads(raw.decode("utf-8"),object_pairs_hook=unique_pairs)
    except (OSError,UnicodeError,json.JSONDecodeError) as e:raise InputError(f"cannot read manifest: {e}") from e
def esc(x): return html.escape(str(x),quote=True)
def href(x): return esc(quote(str(x).replace("\\","/"),safe="/"))
def utf8_text(path):
    try:return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:return None

def build(root, manifest, output_root, output_dir):
    if not isinstance(manifest,dict) or set(manifest)-{"schema_version","title","criteria","items"} or manifest.get("schema_version")!=1: raise InputError("manifest must have schema_version: 1 and no unknown fields")
    title=manifest.get("title","Review packet"); criteria=manifest.get("criteria",[]); items=manifest.get("items")
    if not isinstance(title,str) or len(title)>500 or not isinstance(criteria,list) or len(criteria)>MAX_LIST or any(not isinstance(c,str) or len(c)>1000 for c in criteria): raise InputError("title/criteria exceed limits or have wrong types")
    if not isinstance(items,list) or not items or len(items)>MAX_ITEMS: raise InputError("items must be a non-empty array of at most 100 entries")
    # Output must be a fresh sibling/location outside the manuscript root.
    root=root.resolve(strict=True); output_root=output_root.resolve(strict=True)
    try: output_root.relative_to(root)
    except ValueError: pass
    else: raise InputError("--output-root must be outside --root")
    target=output_root / output_dir
    if not isinstance(output_dir,str) or not output_dir or len(output_dir)>1024 or Path(output_dir).is_absolute() or ":" in output_dir or any(not safe_component(x) for x in output_dir.replace("\\","/").split("/")): raise InputError("--output-dir must be a safe relative path")
    cur=output_root
    for part in Path(output_dir).parts[:-1]:
        cur=cur/part
        if cur.is_symlink() or (hasattr(cur,"is_junction") and cur.is_junction()): raise InputError("output parent symlink or junction rejected")
    target.parent.mkdir(parents=True,exist_ok=True)
    try: target.parent.resolve(strict=True).relative_to(output_root)
    except (OSError,ValueError) as e: raise InputError("output directory parent escapes --output-root") from e
    if target.exists(): raise InputError(f"output directory already exists: {target}")
    target.mkdir(parents=True)
    records=[]; sections=[]; seen=set(); total=0
    try:
      for n,item in enumerate(items,1):
        if not isinstance(item,dict) or set(item)-{"id","label","current","previous","context","previews"} or not safe_id(item.get("id")): raise InputError("each item needs a safe id and no unknown fields")
        iid=item["id"]
        if iid in seen: raise InputError(f"duplicate item id: {iid}")
        seen.add(iid)
        label=item.get("label",iid); current=item.get("current"); previous=item.get("previous"); context=item.get("context",[]); previews=item.get("previews",[])
        if not isinstance(label,str) or len(label)>1000 or not isinstance(current,str) or not isinstance(context,list) or not isinstance(previews,list) or len(context)>MAX_LIST or len(previews)>MAX_LIST: raise InputError(f"bad or oversized item fields for {iid}")
        if previous is not None and not isinstance(previous,str): raise InputError(f"previous must be a path for {iid}")
        folder=target/"items"/iid; folder.mkdir(parents=True)
        cur=safe_file(root,current); total+=cur.stat().st_size
        if total>MAX_TOTAL: raise InputError(f"combined input bytes exceed {MAX_TOTAL}")
        cur_out=folder/"current"/Path(current).name; cur_out.parent.mkdir(parents=True); shutil.copyfile(cur,cur_out); records.append({"role":"current","item_id":iid,"path":current,"sha256":digest(cur),"packet_path":cur_out.relative_to(target).as_posix()})
        body=f'<h2>{esc(iid)} — {esc(label)}</h2><p><b>Current source:</b> {esc(current)} <code>sha256:{digest(cur)}</code></p><p><a href="{href(cur_out.relative_to(target).as_posix())}">Open copied current file</a></p>'
        current_text=utf8_text(cur) if cur.suffix.lower() in (".txt",".md",".markdown",".rst",".csv") and cur.stat().st_size<=MAX_TEXT else None
        body+=f'<pre class="text">{esc(current_text)}</pre>' if current_text is not None else '<p>Current file copied as supplied; no text extraction was attempted.</p>'
        if previous:
          prev=safe_file(root,previous); total+=prev.stat().st_size
          if total>MAX_TOTAL: raise InputError(f"combined input bytes exceed {MAX_TOTAL}")
          prev_out=folder/"previous"/Path(previous).name; prev_out.parent.mkdir(parents=True); shutil.copyfile(prev,prev_out); records.append({"role":"previous","item_id":iid,"path":previous,"sha256":digest(prev),"packet_path":prev_out.relative_to(target).as_posix()})
          body+=f'<p><b>Previous source:</b> {esc(previous)} <code>sha256:{digest(prev)}</code>; <a href="{href(prev_out.relative_to(target).as_posix())}">open copy</a></p>'
          previous_text=utf8_text(prev) if prev.suffix.lower() in (".txt",".md",".markdown",".rst",".csv") and prev.stat().st_size<=MAX_TEXT else None
          if current_text is not None and previous_text is not None:
            before=previous_text.splitlines(); after=current_text.splitlines(); diff="\n".join(difflib.unified_diff(before,after,fromfile=previous,tofile=current,lineterm=""))
            body+=f'<h3>Text diff (UTF-8)</h3><pre class="text">{esc(diff)}</pre>'
        for j,path in enumerate(context,1):
          if not isinstance(path,str): raise InputError(f"context paths must be text for {iid}")
          p=safe_file(root,path); total+=p.stat().st_size
          if total>MAX_TOTAL: raise InputError(f"combined input bytes exceed {MAX_TOTAL}")
          out=folder/"context"/f"{j:02d}-{Path(path).name}"; out.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(p,out); records.append({"role":"context","item_id":iid,"path":path,"sha256":digest(p),"packet_path":out.relative_to(target).as_posix()}); body+=f'<p>Context supplied: {esc(path)} <code>sha256:{digest(p)}</code> (<a href="{href(out.relative_to(target).as_posix())}">copy</a>)</p>'
        for j,path in enumerate(previews,1):
          if not isinstance(path,str): raise InputError(f"preview paths must be text for {iid}")
          p=safe_file(root,path)
          total+=p.stat().st_size
          if total>MAX_TOTAL: raise InputError(f"combined input bytes exceed {MAX_TOTAL}")
          if p.suffix.lower() not in (".png",".jpg",".jpeg"): raise InputError(f"preview must be PNG/JPEG: {path}")
          out=folder/"previews"/f"{j:02d}-{Path(path).name}"; out.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(p,out); records.append({"role":"provided_page_preview","item_id":iid,"path":path,"sha256":digest(p),"packet_path":out.relative_to(target).as_posix()}); body+=f'<figure><img src="{href(out.relative_to(target).as_posix())}" alt="User supplied preview {j}"><figcaption>Provided image: {esc(path)} (not generated or verified by this helper)</figcaption></figure>'
        body+='<h3>Review record</h3><p>Status: PENDING — reviewer completion required.</p><ul>'+''.join(f'<li><label><input type="checkbox" disabled> {esc(c)}</label></li>' for c in criteria)+'</ul><p>Coverage notes: ______________________________</p><p>Reviewer / date: ______________________________</p>'
        sections.append(body)
      provenance={"schema_version":1,"kind":"review-packet-provenance","manifest_title":title,"sources":records,"review_scope":{"criteria":criteria,"status":"pending","reviewer_completion_required":True}}
      (target/"provenance.json").write_text(json.dumps(provenance,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
      doc='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>'+esc(title)+'</title><style>body{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem;color:#222}section{border-top:2px solid #bbb;margin-top:2rem;padding-top:1rem}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f4f4;padding:1rem}figure img{max-width:100%;height:auto}code{overflow-wrap:anywhere}</style><h1>'+esc(title)+'</h1><p>Prepared from explicitly supplied files. This packet does not render PDFs, read chapters, or perform a review. Supplied preview images are identified as such. Review status is pending.</p><h2>Criteria</h2><ul>'+''.join(f'<li>{esc(c)}</li>' for c in criteria)+'</ul>'+''.join('<section>'+s+'</section>' for s in sections)+'<p><a href="provenance.json">Source provenance and hashes</a></p></html>'
      (target/"index.html").write_text(doc,encoding="utf-8")
      return target
    except Exception:
      shutil.rmtree(target,ignore_errors=True); raise

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument("--root",required=True,type=Path); ap.add_argument("--manifest",required=True); ap.add_argument("--output-root",required=True,type=Path); ap.add_argument("--output-dir",required=True); ns=ap.parse_args(argv)
    try:
      root=ns.root.resolve(strict=True); outroot=ns.output_root.resolve(strict=True)
      manifest=read_json(safe_file(root,ns.manifest)); print(build(root,manifest,outroot,ns.output_dir))
    except (InputError,OSError) as e: print(f"make_review_packet: {e}",file=sys.stderr); return 2
    return 0
if __name__=="__main__": raise SystemExit(main())
