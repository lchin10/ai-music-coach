---
extends: feature, bug-fix
when: Any feature, change or bug fix in this repo's Next.js frontend or FastAPI backend.
---

# Full-stack changes in ai-music-coach

This repo has standing rules for tests, security and docs (see the global and
project `CLAUDE.md`). These changes put them into the Feature and Bug fix
playbooks at the steps where they belong.

- **After** "Verify on the matching surface." Run `python -m pytest` in `backend/` and `npm run test:e2e` in `frontend/`. Open the screenshot of every page the change touched (`test-logs/e2e-latest/`) and look at it. A UI change re-baselines only the pages it meant to change, with `npm run test:e2e:update`, and says which ones.
- **After** "Verify on the same surface." Run `python -m pytest` in `backend/` and `npm run test:e2e` in `frontend/`. The regression test for the bug must fail before the fix and pass after it.
- **Before** "Run **Opening a PR**." Run the `security-review` skill on the diff and fix what it finds. Then work through the Docs checklist in the global `CLAUDE.md`: migration plus `backend/schema.sql` plus `backend/app/schema.py`, the endpoint table in `backend/README.md`, the README feature list, the project `CLAUDE.md`, and the verify skill's feature map.
- **Replace** "Run **Opening a PR**." Commit on the current branch with a one-line message. This repo is developed on `main` without pull requests. Never push without being asked.
