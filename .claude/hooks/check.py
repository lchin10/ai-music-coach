"""Stop hook: run the tests and doc checks for whatever is uncommitted.

Exit 2 hands stderr back to Claude, which then has to fix the failure or
report it before it can finish. Failures are kept in test-logs/<timestamp>/.

Skips cheaply when nothing changed since the last passing run, so a chat-only
turn on a dirty tree doesn't rerun the browser suite.
"""

import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "test-logs"
STAMP = LOGS / ".last-pass"


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout


def changes():
    """{path: status} for every uncommitted file, untracked ones included."""
    out = {}
    for line in git("status", "--porcelain", "--untracked-files=all").splitlines():
        status, path = line[:2], line[3:].split(" -> ")[-1].strip('"')
        out[path] = status
    return out


def fingerprint(paths):
    h = hashlib.sha256()
    for path in sorted(paths):
        h.update(path.encode())
        file = ROOT / path
        if file.is_file():
            h.update(file.read_bytes())
    return h.hexdigest()


def doc_drift(changed):
    """Docs that must move with the code, per the Docs rules in CLAUDE.md."""
    problems = []
    new = {p for p, s in changed.items() if "?" in s or "A" in s}

    if any(p.startswith("backend/migrations/") for p in new):
        for doc in ("backend/schema.sql", "backend/app/schema.py"):
            if doc not in changed:
                problems.append(f"New migration, but {doc} was not updated.")

    added = git("diff", "HEAD", "--", "backend/app/routers")
    for p in new:
        if p.startswith("backend/app/routers/") and p.endswith(".py"):
            added += (ROOT / p).read_text(encoding="utf-8", errors="ignore")
    if re.search(r"^\+?\s*@router\.(get|post|put|patch|delete)", added, re.M) \
            and "backend/README.md" not in changed:
        problems.append("Routes changed, but the endpoint table in backend/README.md was not updated.")

    pages = [p for p in new if re.match(r"frontend/src/app/.*page\.tsx$", p)]
    if pages:
        if "frontend/e2e/pages.spec.ts" not in changed:
            problems.append(f"New page(s) {pages}, but frontend/e2e/pages.spec.ts has no screenshot for them.")
        if (ROOT / ".claude/skills/verify/features").is_dir() and \
                not any(p.startswith(".claude/skills/verify/features/") for p in changed):
            problems.append(f"New page(s) {pages}, but the verify skill's feature map was not updated.")
    return problems


def run(cmd, cwd):
    exe = shutil.which(cmd[0]) or cmd[0]
    result = subprocess.run([exe, *cmd[1:]], cwd=ROOT / cwd, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    return result.returncode == 0, result.stdout + result.stderr


def main():
    if json.loads(sys.stdin.read() or "{}").get("stop_hook_active"):
        return 0

    changed = changes()
    code = {p: s for p, s in changed.items() if p.startswith(("backend/", "frontend/"))
            and not p.endswith(".md")}
    if not code:
        return 0
    fp = fingerprint(code)
    if STAMP.is_file() and STAMP.read_text() == fp:
        return 0

    failures, logs = [], {}
    failures += doc_drift(changed)

    if any(p.startswith("backend/") for p in code):
        ok, logs["pytest.txt"] = run(["python", "-m", "pytest", "-q"], "backend")
        if not ok:
            failures.append("Backend tests failed (pytest.txt).")

    if any(p.startswith(("frontend/src/", "frontend/e2e/", "frontend/playwright.config"))
           for p in code):
        ok, logs["e2e.txt"] = run(["npx", "playwright", "test", "--reporter=line"], "frontend")
        if not ok:
            failures.append("Screenshot/e2e suite failed (e2e.txt, e2e/ has diffs and traces).")

    LOGS.mkdir(exist_ok=True)
    if not failures:
        STAMP.write_text(fp)
        return 0

    folder = LOGS / datetime.now().strftime("%Y-%m-%d_%H%M%S")
    folder.mkdir()
    for name, text in logs.items():
        (folder / name).write_text(text, encoding="utf-8")
    if "e2e.txt" in logs and (LOGS / "e2e-latest").is_dir():
        shutil.copytree(LOGS / "e2e-latest", folder / "e2e")
    (folder / "SUMMARY.txt").write_text("\n".join(failures) + "\n", encoding="utf-8")

    rel = folder.relative_to(ROOT).as_posix()
    print(f"Checks failed. Log: {rel}/", *[f"- {f}" for f in failures],
          "Fix these, or tell the user what failed and where the log is.",
          sep="\n", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
