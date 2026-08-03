"""The universality guard: scenario vocabulary must never appear in the
compiler's or kernel's executable logic -- not in identifiers, not in string
literals used by code.  Docstrings and comments may mention scenario words
only to document the boundary (they are excluded from the scan).

If this test fails, someone hardcoded a scenario."""
import ast
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: every production directory, walked RECURSIVELY.  A non-recursive listing
#: silently exempted whole packages: sworldmodel/semantic_runtime/ was
#: scanned by nothing at all, and an injected `is_email_scenario()` passed
#: this guard and the entire suite.
SCAN_ROOTS = ("compiler", "sworldmodel")

#: Per-file word allowances: path -> the exact FORBIDDEN words that file may
#: contain, each for a documented reason.  Allowlisted files are still
#: scanned for every OTHER forbidden word (the narrowest exemption the
#: mechanism allows -- never a whole-file skip), and a dedicated test below
#: rejects any allowance that is broader or staler than the file's actual
#: content.
#:
#: - compiler/scene_prompts.py: carries the UNIVERSAL prohibition doctrine,
#:   which must name the acts that may never be scheduled ("never schedule
#:   a reply, a vote, ...") and the collective decision-unit examples --
#:   the opposite of scenario routing.  Agent B audits it for routing
#:   instead of this word scan.
#: - sworldmodel/backends/concordia_local/guard.py: the minimum agency
#:   guard must name the directive's own voluntary-act categories (reply,
#:   agree, vote, ...) as plain literal word forms to DETECT event text
#:   asserting another actor's act.  "vote"/"voting" are act-category
#:   forms there, not scenario vocabulary.  This documented entry is the
#:   sanctioned remedy of review finding 7, replacing a stem+suffix table
#:   that assembled the same words at runtime to evade this scan.
ALLOWLIST = {
    "compiler/scene_prompts.py": frozenset({"vote", "meeting", "committee"}),
    "sworldmodel/backends/concordia_local/guard.py": frozenset(
        {"vote", "voting"}),
}

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


def _word_hits(text: str, allowed=frozenset()) -> list:
    hits = []
    low = text.lower()
    for word in FORBIDDEN:
        if word in allowed:
            continue
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


def scan_file(path: str, allowed=frozenset()) -> list:
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
            for word in _word_hits(text, allowed):
                problems.append(
                    f"{path}:{getattr(node, 'lineno', '?')}: {word!r} in "
                    f"{text[:70]!r}")
    return problems


def production_files() -> list:
    out = []
    for root in SCAN_ROOTS:
        for dirpath, _dirs, files in os.walk(os.path.join(HERE, root)):
            if "__pycache__" in dirpath:
                continue
            for fname in sorted(files):
                if not fname.endswith(".py"):
                    continue
                full = os.path.join(dirpath, fname)
                rel = os.path.relpath(full, HERE)
                out.append((rel, full))
    return sorted(out)


def test_every_production_file_is_actually_scanned():
    """The guard is only worth what it covers -- and word allowances must
    never remove a file from the scan."""
    scanned = {rel for rel, _ in production_files()}
    assert any(r.startswith("sworldmodel/semantic_runtime/") for r in scanned)
    assert any(r.startswith("compiler/legacy/") for r in scanned)
    assert len(scanned) > 25
    for rel in ALLOWLIST:
        assert rel in scanned, f"allowlisted file {rel} is not scanned"


def test_allowlist_entries_are_exact():
    """Every allowance names a real file and matches that file's actual
    forbidden-word content EXACTLY: a broader allowance (words the file
    does not contain) is dead weight that would silently license future
    vocabulary, and a narrower one cannot pass the scan.  This keeps
    each entry provably as narrow as the mechanism allows."""
    by_rel = dict(production_files())
    for rel, allowed in ALLOWLIST.items():
        assert rel in by_rel, f"allowlisted file {rel} does not exist"
        assert allowed, f"empty allowance for {rel}: delete the entry"
        actually_present = {
            word for word in allowed
            if scan_file(by_rel[rel], allowed - {word})}
        assert actually_present == set(allowed), (
            f"{rel}: allowance {sorted(allowed)} is broader than the "
            f"file's content {sorted(actually_present)} -- shrink it")


def test_no_scenario_vocabulary_in_core_logic():
    problems = []
    for rel, full in production_files():
        problems.extend(scan_file(full, ALLOWLIST.get(rel, frozenset())))
    assert problems == [], (
        "scenario vocabulary found in core logic -- the compiler/runtime "
        "must stay universal:\n" + "\n".join(problems))
