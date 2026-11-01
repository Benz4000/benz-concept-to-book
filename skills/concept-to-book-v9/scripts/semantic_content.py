"""Bounded inline semantic model. No source HTML is accepted."""
import html
import re


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
        keys(run, ("text", "emphasis", "strong"))
        need(isinstance(run["text"], str) and bool(run["text"]), "run.text must be nonempty")
        string(run["text"] if run["text"].strip() else "x" + run["text"], "run.text")
        need(type(run["emphasis"]) is bool and type(run["strong"]) is bool, "run semantics must be booleans")
    need("".join(r["text"] for r in value) == block["text"], "runs concatenation differs from text")


def markup(block):
    result = []
    for run in runs(block):
        value = html.escape(run["text"], quote=True)
        if run.get("emphasis"):
            value = "<em>" + value + "</em>"
        if run.get("strong"):
            value = "<strong>" + value + "</strong>"
        result.append(value)
    return "".join(result)


def inline(text):
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
