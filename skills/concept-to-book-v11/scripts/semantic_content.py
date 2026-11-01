"""Bounded inline semantic model. No source HTML is accepted."""
import html
import re
import rich_content as rich
from urllib.parse import urlsplit

NOTE_ID = re.compile(r"[a-z][a-z0-9_-]{0,47}\Z")


def safe_href(value):
    """Bounded external URI; never fetched. No relative/file/script/data links."""
    if not isinstance(value, str) or len(value) > 2048 or re.search(r'[\s<>"\\\x00-\x1f\x7f]', value):
        return False
    try:
        uri = urlsplit(value)
        return uri.scheme in ("http", "https") and bool(uri.hostname) and not uri.username and not uri.password or uri.scheme == "mailto" and bool(uri.path) and "@" in uri.path and not uri.netloc
    except ValueError:
        return False


def note_map(sections, need):
    """One reference and one definition per stable ID, globally, without nesting."""
    notes, refs = {}, {}
    for section in sections:
        blocks = [{"text": section["title"], "runs": section.get("title_runs", [{"text": section["title"]}])}] + section["blocks"]
        for outer in blocks:
          for block in rich.leaves(outer):
            if outer.get("type") == "endnote":
                nid = outer["id"]
                if block is rich.leaves(outer)[0]:
                    need(nid not in notes, f"Duplicate endnote definition: {nid}")
                    notes[nid] = section["id"]
            if "text" not in block:
                continue
            for run in runs(block):
                if "note_id" in run:
                    nid = run["note_id"]
                    need(outer.get("type") != "endnote", "Nested note references unsupported")
                    need(nid not in refs, f"Duplicate endnote reference: {nid}")
                    refs[nid] = section["id"]
    need(notes.keys() == refs.keys(), f"Missing endnote definitions/references: definitions={sorted(notes.keys() - refs.keys())}, references={sorted(refs.keys() - notes.keys())}")
    return {nid: {"note_section": notes[nid], "ref_section": refs[nid]} for nid in notes}


def runs(block):
    return block.get("runs", [{"text": block["text"], "emphasis": False, "strong": False}])


def style(run):
    return "bold_italic" if run.get("strong") and run.get("emphasis") else "bold" if run.get("strong") else "italic" if run.get("emphasis") else "regular"


def validate(block, need, keys, string):
    if "runs" not in block:
        return
    value = block["runs"]
    need(isinstance(value, list) and 0 < len(value) <= 10000, "runs must contain 1..10000 entries")
    for run in value:
        keys(run, ("text", "emphasis", "strong"), ("href", "note_id", "target_id"))
        need(isinstance(run["text"], str) and bool(run["text"]), "run.text must be nonempty")
        string(run["text"] if run["text"].strip() else "x" + run["text"], "run.text")
        need(type(run["emphasis"]) is bool and type(run["strong"]) is bool, "run semantics must be booleans")
        need(sum(k in run for k in ("href", "note_id", "target_id")) <= 1, "A run has conflicting link destinations")
        if "href" in run:
            need(safe_href(run["href"]), "Unsupported or unsafe hyperlink URI")
        if "target_id" in run:
            need(isinstance(run["target_id"],str) and re.fullmatch(r"bm-[a-z0-9-]{1,48}", run["target_id"]), "Unsafe cross-reference target")
        if "note_id" in run:
            need(isinstance(run["note_id"], str) and NOTE_ID.fullmatch(run["note_id"]), "Unsafe note ID")
    need("".join(r["text"] for r in value) == block["text"], "runs concatenation differs from text")


def markup(block, links=None, epub=False):
    result = []
    for run in runs(block):
        value = html.escape(run["text"], quote=True)
        if run.get("emphasis"):
            value = "<em>" + value + "</em>"
        if run.get("strong"):
            value = "<strong>" + value + "</strong>"
        if "href" in run:
            value = '<a href="' + html.escape(run["href"], quote=True) + '">' + value + '</a>'
        elif "target_id" in run:
            target=(links or {}).get("__anchors__", {}).get(run["target_id"], "")
            href=(target+".xhtml" if epub else "")+"#"+run["target_id"]
            value='<a href="'+href+'">'+value+'</a>'
        elif "note_id" in run:
            nid = run["note_id"]
            target = (links or {}).get(nid, {}).get("note_section", "")
            href = (target + ".xhtml" if epub else "") + "#note-" + nid
            value = f'<a id="ref-{nid}" href="{href}" role="doc-noteref"' + (' epub:type="noteref"' if epub else '') + '>' + value + '</a>'
        result.append(value)
    return "".join(result)


def emphasis_inline(text):
    """Asterisks only; balanced *em*, **strong**, ***both***; no nesting.

    Deliberately refuse ambiguous nested delimiters and intraword markers.
    """
    output, pos = [], 0
    while pos < len(text):
        if text[pos] != "*":
            end = text.find("*", pos)
            if end < 0:
                end = len(text)
            output.append({"text": text[pos:end], "emphasis": False, "strong": False})
            pos = end
            continue
        match = re.match(r"\*{1,3}", text[pos:])
        token = match[0]
        if pos and text[pos-1].isalnum():
            raise ValueError("Intraword emphasis unsupported")
        end = text.find(token, pos + len(token))
        if end < 0:
            raise ValueError("Unbalanced emphasis")
        value = text[pos+len(token):end]
        after = end + len(token)
        if not value or value != value.strip() or "*" in value or (after < len(text) and (text[after] == "*" or text[after].isalnum())):
            raise ValueError("Nested or ambiguous emphasis unsupported")
        output.append({"text": value, "emphasis": len(token) in (1, 3), "strong": len(token) in (2, 3)})
        pos = after
    plain = "".join(r["text"] for r in output)
    return {"text": plain, **({"runs": output} if any(r["emphasis"] or r["strong"] for r in output) else {})}


def inline(text):
    """Links contain plain labels; emphasis outside links retains the V9 grammar."""
    output, pos = [], 0
    token = re.compile(r"\[\^([a-z][a-z0-9_-]{0,47})\]|\[([^\[\]\n*]+)\]\(([^()\s]+)\)")
    for match in token.finditer(text):
        if match.start() and text[match.start() - 1] == "!":
            raise ValueError("Inline Markdown images unsupported")
        before = text[pos:match.start()]
        if "[" in before or "]" in before:
            raise ValueError("Unsupported link/note syntax")
        if before:
            output.extend(runs(emphasis_inline(before)))
        if match[1]:
            output.append({"text": "[" + match[1] + "]", "emphasis": False, "strong": False, "note_id": match[1]})
        else:
            if not safe_href(match[3]):
                raise ValueError("Unsupported or unsafe hyperlink URI")
            output.append({"text": match[2], "emphasis": False, "strong": False, "href": match[3]})
        pos = match.end()
    after = text[pos:]
    if "[" in after or "]" in after:
        raise ValueError("Unsupported link/note syntax")
    if after:
        output.extend(runs(emphasis_inline(after)))
    plain = "".join(r["text"] for r in output)
    return {"text": plain, **({"runs": output} if any(r.get("emphasis") or r.get("strong") or "href" in r or "note_id" in r for r in output) else {})}
