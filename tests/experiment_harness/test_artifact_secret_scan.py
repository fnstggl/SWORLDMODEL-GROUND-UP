"""No committed artifact may carry a credential.

Scans every file under ``artifacts/full_trace_validation_*`` and the
experiment package itself for key-shaped strings, ``Authorization``
headers, bearer tokens, and cookies -- and, when a live credential is
present in this environment, for that exact value.

Runs on either interpreter (pure stdlib) so it also guards the system
Python product suite.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.full_trace_validation import recorder as rec  # noqa: E402

SCAN_ROOTS = (REPO_ROOT / "experiments", )
ARTIFACT_GLOB = "artifacts/full_trace_validation_*"

#: this test file itself names the shapes it hunts for
SELF = Path(__file__).resolve()
RECORDER_SOURCE = (REPO_ROOT / "experiments" / "full_trace_validation"
                   / "recorder.py").resolve()
HARNESS_TESTS = (REPO_ROOT / "tests" / "experiment_harness").resolve()

_PATTERNS = (
    ("api key", re.compile(r"sk-[A-Za-z0-9_\-]{12,}")),
    ("authorization header",
     re.compile(r"(?i)authorization\s*[\"']?\s*[:=]\s*[\"']?bearer\s+\S")),
    ("bearer token", re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]{16,}")),
    ("cookie", re.compile(r"(?i)\bset-cookie\s*:")),
)

_TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".txt", ".py", ".yaml", ".yml",
                  ".csv", ".html", ".js"}


def _scan_targets():
    targets = []
    for root in SCAN_ROOTS:
        if root.is_dir():
            targets.extend(path for path in root.rglob("*")
                           if path.is_file())
    for artifact_dir in REPO_ROOT.glob(ARTIFACT_GLOB):
        targets.extend(path for path in artifact_dir.rglob("*")
                       if path.is_file())
    return [path for path in targets
            if path.suffix.lower() in _TEXT_SUFFIXES
            and path.resolve() != SELF
            and path.resolve() != RECORDER_SOURCE
            and HARNESS_TESTS not in path.resolve().parents]


def test_no_committed_artifact_contains_credential_shaped_material():
    offences = []
    for path in _scan_targets():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in _PATTERNS:
            for match in pattern.finditer(text):
                if rec._REDACTED in match.group(0):
                    continue
                offences.append(
                    f"{path.relative_to(REPO_ROOT)}: {label}: "
                    f"{match.group(0)[:32]!r}")
    assert not offences, "credential-shaped material in tracked files:\n" \
        + "\n".join(offences[:20])


def test_no_committed_artifact_contains_a_live_environment_credential():
    secrets = rec.secret_values()
    if not secrets:
        # nothing to leak in this environment; the shape scan above still
        # runs, and the recorder's own writer refuses secrets at source
        return
    offences = []
    for path in _scan_targets():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for secret in secrets:
            if secret in text:
                offences.append(str(path.relative_to(REPO_ROOT)))
    assert not offences, ("a live credential value appears in: "
                          + ", ".join(sorted(set(offences))))


def test_the_scanner_actually_finds_a_planted_key(tmp_path, monkeypatch):
    """The scan has teeth."""
    planted = tmp_path / "artifacts" / "full_trace_validation_planted"
    planted.mkdir(parents=True)
    (planted / "leak.json").write_text(
        '{"authorization": "Bearer sk-planted-key-abcdefghijkl"}',
        encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sys.modules[__name__], "SCAN_ROOTS", ())
    found = _scan_targets()
    assert found, "the planted artifact was not even scanned"
    text = found[0].read_text(encoding="utf-8")
    assert any(pattern.search(text) for _label, pattern in _PATTERNS)


def test_environment_credentials_are_never_echoed_by_the_scrubber():
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return
    assert key not in rec.scrub(f"Authorization: Bearer {key}")
    assert key not in rec.scrub({"h": {"Authorization": f"Bearer {key}"}})
