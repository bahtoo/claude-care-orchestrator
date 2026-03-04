---
description: How to close a completed sprint — commit, changelog, tag, and prepare for next phase
---

# Sprint Close Workflow

Run this workflow after completing a sprint/phase. It handles git hygiene, changelog updates, roadmap tracking, and sets up the next sprint.

## Prerequisites

- All tests pass (`python -m pytest tests/ -v`)
- All planned items in the sprint are completed or explicitly deferred

## Steps

### 1. Verify all tests pass

// turbo

```bash
python -m pytest tests/ -v --tb=short
```

Ensure **0 failures**. Do not proceed if tests fail.

---

### 2. Run linter

// turbo

```bash
python -m ruff check src/ tests/
```

Fix any issues before proceeding.

---

### 3. Update CHANGELOG.md

Add a new entry at the top of `CHANGELOG.md` following this format:

```markdown
## [version] - YYYY-MM-DD

### Added

- List of new features/modules

### Changed

- List of modifications to existing features

### Fixed

- List of bug fixes

### Removed

- List of removed features (if any)
```

---

### 4. Update ROADMAP.md

- Mark the completed phase with ✅
- Add implementation notes under the completed phase
- Ensure the next phase objectives are clearly defined

---

### 5. Stage and commit all changes

```bash
git add -A
git status
```

Review the staged files, then commit:

```bash
git commit -m "sprint: Complete [Phase/Sprint Name] - [brief summary]"
```

---

### 6. Create a git tag for the release

```bash
git tag -a v[version] -m "[Phase/Sprint Name] complete"
```

---

### 7. Push to remote

```bash
git push origin main
git push origin --tags
```

---

### 8. Prepare next sprint

- Create or update the sprint backlog in `task.md` or project board
- Identify the top 3-5 items for the next sprint
- Update any relevant documentation

---

## Notes

- Version format: `0.x.0` for phases (0.1.0 = Phase 1, 0.2.0 = Phase 2, etc.)
- Hotfixes within a phase: `0.x.y` (e.g., 0.1.1, 0.1.2)
- Always run tests before pushing — CI will catch failures, but local verification is faster
