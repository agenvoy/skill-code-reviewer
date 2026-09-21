# code-reviewer - Documentation

> Back to [README](../README.md)

## Prerequisites

- An agent harness that loads `SKILL.md` skills and can run shell commands
- Python 3.10 or higher (the analyzers, plus `ast` analysis of Python projects)
- Go 1.21 or higher (optional; runs the `go/ast` helper and `gofmt` for Go projects)
- `node_modules/.bin/eslint` in the target project (optional; used for JS/TS projects)

When a toolchain is missing, that language falls back to string scanning and the report says so.

## Installation

`<skills-dir>` is the skill directory your harness scans.

### Clone from GitHub

```bash
git clone https://github.com/agenvoy/skill-code-reviewer.git \
    <skills-dir>/code-reviewer
```

### Verify Installation

```bash
ls <skills-dir>/code-reviewer/SKILL.md
ls <skills-dir>/code-reviewer/scripts/analyze_code.py
```

Invoke it from your harness with `/code-reviewer`.

## Usage

### Basic

```bash
/code-reviewer
```

Analyzes the current directory and writes `.doc/code-reviewer/{yyyy-MM-dd_HH-mm}.md` (24-hour local time), creating the directory if needed.

### Target a Project

```bash
/code-reviewer ./my-project
```

Writes `my-project/.doc/code-reviewer/{yyyy-MM-dd_HH-mm}.md`.

### Set the Output File

```bash
/code-reviewer . custom.md
```

Writes straight to `./custom.md`; create any directory in the path first. An explicit output file forces a report, so a minimal one is written even when the no-op conditions hold.

### Nothing to Do

```
無需處理：python 專案 my-project（12 檔 / 48 函式）未觀察到可執行建議
```

No `.doc/code-reviewer/` directory is created and no file is written.

### Run the Analyzer Manually

```bash
python3 <skills-dir>/code-reviewer/scripts/analyze_code.py /path/to/project
```

Exits 1 when the argument is missing; prints `{"error": "Path does not exist: ..."}` when the path does not exist.

## CLI Reference

### Slash Command Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `PROJECT_PATH` | Current directory | Project root |
| `OUTPUT_FILE` | `.doc/code-reviewer/{yyyy-MM-dd_HH-mm}.md` | Output path relative to `PROJECT_PATH`; reports never land in the project root unless named explicitly |

### Language Detection

Indicator files (`go.mod`, `tsconfig.json`, `package.json`, `pyproject.toml`) are checked first, then the most frequent source extension.

| Language | Analysis | Dependency |
|----------|----------|------------|
| Go | `go run go_ast.go` + string scan; `gofmt -s -w` on non-test files first (failures silently skipped) | `go` ≥ 1.21 |
| Python | Built-in `ast` | Python ≥ 3.10 |
| JavaScript / TypeScript | Brace-based structural scan (function bounds, nesting depth) + project eslint (optional) + string scan | `node_modules/.bin/eslint` (optional) |

Other languages return a single Low issue, "unsupported language".

### Analyzer Output JSON

| Field | Description |
|-------|-------------|
| `language` / `name` | Primary language and project name |
| `file_count` / `function_count` | File and function counts |
| `files` | Sorted file list |
| `functions` | `name`, `signature`, `file`, `line`, `line_count`, `has_doc` |
| `issues` | `severity`, `category`, `title`, `description`, `file`, `line`, `code_snippet`, `suggestion`; sorted by severity |
| `issue_counts` | `critical` / `high` / `medium` / `low` counts |
| `metrics` | `total_lines`, `code_lines`, `avg_function_length`, `max_function_length`, `max_nesting_depth` |
| `dependencies` | Dependencies |

### Detection Categories

| Category | Issue | Criterion | Severity |
|----------|-------|-----------|----------|
| Quality | Long function | > 50 lines | Medium |
| Quality | Deep nesting | > 3 levels | Medium |
| Quality | Unused import | AST name references | Low |
| Quality | Large comment block | ≥ 10 consecutive lines | Low |
| Quality | Go `interface{}` | AST empty interface | Low |
| Quality | Go discarded return | `_ = f()` | Medium |
| Quality | Python bare except | `except:` | Medium |
| Quality | JS/TS eslint rule | Project eslint | High / Medium |
| Security | Hardcoded secret | `password=`, `secret=`, `api_key=`, etc. | Critical |
| Security | Suspicious high-entropy string | Entropy ≥ 4.0, length ≥ 32, excluding UUID / MD5 / SHA1 / SHA256 / MIME type | High |
| Security | SQL injection | Concatenated / f-string / `%`-formatted SQL | High |
| Security | Command injection | Concatenated system commands | High |

Security checks are pattern-based, so high-severity hits are always marked for manual confirmation.

### Report Structure

Summary, then Critical / High / Medium / Low issues, architecture, performance, security, convention adherence, and a to-do list. Each issue carries its file location, current state, current code, suggested change, and reason; convention findings add the rule file path and the verbatim rule. The convention section is omitted when the project has no `CLAUDE.md` / `AGENTS.md`.

### Convention Scope

A file answers only to the rule files in its own directory and its parents:

| File | Rule Files Checked |
|------|--------------------|
| `internal/note/new.go` | `internal/note/CLAUDE.md`, `internal/CLAUDE.md`, root `CLAUDE.md` (same for `AGENTS.md`) |
| `page/view.ts` | Rule files in `page/` and the root; nothing under `internal/` applies |

### Suggestion Rules

| Rule | Content |
|------|---------|
| Anchor | Every suggestion maps to an `issues` entry or a concrete file and line |
| Validation | Re-checked against the source before writing; unconfirmed items are removed, not downgraded |
| Forbidden | Wrapping existing abstractions, documentation for its own sake, speculative optimization, decorative refactors without a metric |
| Skipped | Findings a linter already covers, trade-offs marked with `nolint` / `noqa` / a comment, issues that only hold for specific inputs |
| Zero suggestions | A valid output; each section says nothing needs attention |

### No-Op Conditions (All Must Hold)

1. Every `issue_counts` value is 0
2. The architecture, performance, security, and convention sections have no actionable suggestion
3. No metric exceeds its threshold
