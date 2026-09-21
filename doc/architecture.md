# code-reviewer - Architecture

> Back to [README](../README.md)

## Overview

```mermaid
graph TB
    User[User runs /code-reviewer] --> Skill[SKILL.md<br/>Orchestration]
    Skill --> Entry[analyze_code.py<br/>Detect and Dispatch]
    Entry --> Go[analyze_go.py<br/>+ go_ast.go]
    Entry --> Py[analyze_python.py]
    Entry --> JS[analyze_js_ts.py]
    Go --> Common[common.py<br/>Data Classes and Security Checks]
    Py --> Common
    JS --> Common
    Entry --> JSON[Analysis JSON]
    JSON --> Eval[Evaluate<br/>analysis_categories.md]
    Rules[CLAUDE.md / AGENTS.md] --> Eval
    Eval --> Validate[Validation Pass]
    Validate --> Gate{No-Op?}
    Gate -->|Yes| Msg[One-line no-op message]
    Gate -->|No| Gen[Generate<br/>recommendation_principles.md]
    Gen --> Save[Save<br/>output_format.md]
    Save --> Report[.doc/code-reviewer/ report]
```

## Module: SKILL.md (Orchestration)

Defines arguments, the seven-step workflow, the Validation Pass, convention scope, no-op conditions, and the checklist; the analyzer path uses `{skill_dir}`, resolved from the actual load location.

```mermaid
graph LR
    subgraph Workflow[SKILL.md]
        W1[1 Detect] --> W2[2 Analyze]
        W2 --> W3[3 Evaluate]
        W3 --> W4[4 Validate]
        W4 --> W5[5 Gate]
        W5 --> W6[6 Generate]
        W6 --> W7[7 Save]
    end
```

## Module: analyze_code.py (Entry)

```mermaid
graph TB
    subgraph Entry[analyze_code.py]
        M[main] --> P{Path exists?}
        P -->|No| Err[Print error JSON]
        P -->|Yes| D[detect_language<br/>indicator files → extension count]
        D --> X[_dispatch]
        X -->|go| G[analyze_go.analyze]
        X -->|python| Y[analyze_python.analyze]
        X -->|javascript / typescript| J[analyze_js_ts.analyze]
        X -->|other| U[Unsupported-language Low issue]
        G --> B[_build_output<br/>sort by severity + counts]
        Y --> B
        J --> B
        U --> B
    end
    B --> Out[stdout JSON]
```

## Module: Language Analyzers

```mermaid
graph TB
    subgraph GoA[analyze_go.py]
        G1[gofmt -s -w per file] --> G2[String scan]
        G3[go run go_ast.go] --> G4{Succeeded?}
        G4 -->|Yes| G5[Merge functions and AST issues<br/>with source snippets]
        G4 -->|No| G6[Mark as string scan only]
        G7[Parse go.mod dependencies]
    end
    subgraph PyA[analyze_python.py]
        P1[ast.parse] --> P2[Length / nesting / unused imports]
        P1 --> P3[Bare except]
        P4[String scan]
    end
    subgraph JSA[analyze_js_ts.py]
        J1[Strip strings and comments] --> J2[Brace structural scan<br/>function bounds / nesting]
        J3{Project eslint?} -->|Yes| J4[eslint --format json<br/>map severities]
        J5[String scan]
    end
```

## Module: common.py (Shared Data and Security Checks)

```mermaid
graph TB
    subgraph Common[common.py]
        C1[detect_hardcoded_credentials] --> C2{Keyword hit?}
        C2 -->|Yes| C3[Critical]
        C1 --> C4[High-entropy candidates]
        C4 --> C5{Entropy ≥ 4.0<br/>and not UUID / hash / MIME?}
        C5 -->|Yes| C6[High]
        C7[detect_sql_injection] --> C8[High]
        C9[detect_command_injection] --> C10[High]
        C11[detect_commented_code<br/>≥ 10 lines] --> C12[Low]
    end
```

```mermaid
classDiagram
    class ProjectAnalysis {
        +str language
        +str name
        +list~str~ files
        +list~FunctionInfo~ functions
        +list~Issue~ issues
        +CodeMetrics metrics
        +list~str~ dependencies
    }
    class Issue {
        +str severity
        +str category
        +str title
        +str description
        +str file
        +int line
        +str code_snippet
        +str suggestion
    }
    class FunctionInfo {
        +str name
        +str signature
        +str file
        +int line
        +int line_count
        +bool has_doc
    }
    class CodeMetrics {
        +int total_lines
        +int code_lines
        +float avg_function_length
        +int max_function_length
        +int max_nesting_depth
    }
    ProjectAnalysis --> Issue
    ProjectAnalysis --> FunctionInfo
    ProjectAnalysis --> CodeMetrics
```

## Module: Suggestion Filtering (Evaluate → Generate)

```mermaid
graph TB
    subgraph Filter[Suggestion Filtering]
        F1[issues + metrics] --> F2[Convention check<br/>rule files in own and parent directories]
        F2 --> F3[Validation Pass<br/>re-anchor in source]
        F3 -->|Unconfirmed| Drop[Remove]
        F3 -->|Confirmed| F4[Recommendation Principles]
        F4 -->|Wrapping / speculative / decorative<br/>linter-covered / silenced| Drop
        F4 -->|Passes| F5[Write to its section]
    end
```

## Data Flow

```mermaid
sequenceDiagram
    participant User
    participant Agent as Agent Harness
    participant Skill as SKILL.md
    participant Py as analyze_code.py
    participant Src as Target Project
    participant FS as .doc/code-reviewer/

    User->>Agent: /code-reviewer [PROJECT_PATH] [OUTPUT_FILE]
    Agent->>Skill: Load skill definition
    Skill->>Py: python3 analyze_code.py <path>
    Py->>Src: Scan sources (gofmt first for Go)
    Py-->>Skill: issues / metrics JSON
    Skill->>Src: Read rule files, re-verify each finding
    alt No-op and no OUTPUT_FILE
        Skill-->>User: One-line no-op message
    else Findings or OUTPUT_FILE given
        Skill->>FS: Create directory and write report
        Skill-->>User: Report path
    end
```

## No-Op State Machine

```mermaid
stateDiagram-v2
    [*] --> Evaluated
    Evaluated --> CheckIssues
    CheckIssues --> Write: issue_counts non-zero
    CheckIssues --> CheckSuggestions: All zero
    CheckSuggestions --> Write: Any section has a suggestion
    CheckSuggestions --> CheckMetrics: All four empty
    CheckMetrics --> Write: A metric exceeds its threshold
    CheckMetrics --> NoOp: None exceed
    NoOp --> Write: User set OUTPUT_FILE
    NoOp --> [*]: One-line message, no directory, no file
    Write --> [*]: Write report
```
