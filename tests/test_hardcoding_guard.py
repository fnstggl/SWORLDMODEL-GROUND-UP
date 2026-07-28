"""The universality guard: scenario vocabulary must never appear in the
compiler's or kernel's executable logic -- not in identifiers, not in string
literals used by code.  Docstrings and comments may mention scenario words
only to document the boundary (they are excluded from the scan).

If this test fails, someone hardcoded a scenario."""
import ast
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN_DIRS = ("compiler", "compiler/legacy", "sworldmodel")

#: scene_prompts.py contains the UNIVERSAL prohibition doctrine, which must
#: name the acts that may never be scheduled ("never schedule a reply, a
#: vote, ...") -- the opposite of scenario routing.  Agent B audits it for
#: routing instead of this word scan.
ALLOWLIST = {"compiler/scene_prompts.py"}

#: words from acceptance scenarios and classic domains; matched as whole-ish
#: words, lowercase (so `default_factory` does not trip `factory`)
FORBIDDEN = (
    "email", "e-mail", "vote", "voting", "ballot", "committee", "meeting",
    "factory", "widget", "shipment", "warehouse", "invoice",
    "senate", "senator", "congress", "legislation", "bill_",
    "election", "poll", "tesla", "coca", "cola", "cuban",
    "campaign", "marketing", "advert", "tweet", "influencer",
    "negotiation", "merger", "treaty", "hiring", "protest",
)


def _word_hits(text: str) -> list:
    hits = []
    low = text.lower()
    for word in FORBIDDEN:
        i = low.find(word)
        while i != -1:
            before = low[i - 1] if i > 0 else " "
            after = low[i + len(word)] if i + len(word) < len(low) else " "
            if not (before.isalnum() or before == "_") \
                    and not (after.isalnum() or after == "_"):
                hits.append(word)
                break
            i = low.find(word, i + 1)
    return hits


def _docstring_nodes(tree) -> set:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) \
                    and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def scan_file(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
    doc_ids = _docstring_nodes(tree)
    problems = []
    for node in ast.walk(tree):
        texts = []
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in doc_ids:
            texts.append(node.value)
        for attr in ("name", "id", "attr", "arg", "module"):
            v = getattr(node, attr, None)
            if isinstance(v, str):
                texts.append(v)
        for text in texts:
            for word in _word_hits(text):
                problems.append(
                    f"{path}:{getattr(node, 'lineno', '?')}: {word!r} in "
                    f"{text[:70]!r}")
    return problems


def test_no_scenario_vocabulary_in_core_logic():
    problems = []
    for d in SCAN_DIRS:
        for fname in sorted(os.listdir(os.path.join(HERE, d))):
            rel = f"{d}/{fname}"
            if fname.endswith(".py") and rel not in ALLOWLIST:
                problems.extend(scan_file(os.path.join(HERE, d, fname)))
    assert problems == [], (
        "scenario vocabulary found in core logic -- the compiler/runtime "
        "must stay universal:\n" + "\n".join(problems))
