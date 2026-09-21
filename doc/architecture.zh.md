# code-reviewer - 架構

> 返回 [README](./README.zh.md)

## 概覽

```mermaid
graph TB
    User[使用者呼叫 /code-reviewer] --> Skill[SKILL.md<br/>流程協調]
    Skill --> Entry[analyze_code.py<br/>語言偵測與派送]
    Entry --> Go[analyze_go.py<br/>+ go_ast.go]
    Entry --> Py[analyze_python.py]
    Entry --> JS[analyze_js_ts.py]
    Go --> Common[common.py<br/>資料類別與安全偵測]
    Py --> Common
    JS --> Common
    Entry --> JSON[分析結果 JSON]
    JSON --> Eval[Evaluate<br/>analysis_categories.md]
    Rules[CLAUDE.md / AGENTS.md] --> Eval
    Eval --> Validate[Validation Pass]
    Validate --> Gate{No-Op?}
    Gate -->|是| Msg[一行無需處理訊息]
    Gate -->|否| Gen[Generate<br/>recommendation_principles.md]
    Gen --> Save[Save<br/>output_format.md]
    Save --> Report[.doc/code-reviewer/報告]
```

## Module: SKILL.md（流程協調）

定義參數、七步工作流程、Validation Pass、規範遵循範圍、No-Op 條件與驗證清單；分析器路徑以 `{skill_dir}` 表示，依實際載入位置代入。

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

## Module: analyze_code.py（入口）

```mermaid
graph TB
    subgraph Entry[analyze_code.py]
        M[main] --> P{路徑存在?}
        P -->|否| Err[輸出 error JSON]
        P -->|是| D[detect_language<br/>指標檔 → 副檔名計數]
        D --> X[_dispatch]
        X -->|go| G[analyze_go.analyze]
        X -->|python| Y[analyze_python.analyze]
        X -->|javascript / typescript| J[analyze_js_ts.analyze]
        X -->|其他| U[不支援的語言 Low 問題]
        G --> B[_build_output<br/>依嚴重度排序 + 計數]
        Y --> B
        J --> B
        U --> B
    end
    B --> Out[stdout JSON]
```

## Module: 語言分析器

```mermaid
graph TB
    subgraph GoA[analyze_go.py]
        G1[逐檔 gofmt -s -w] --> G2[字串掃描]
        G3[go run go_ast.go] --> G4{成功?}
        G4 -->|是| G5[合併函式與 AST 問題<br/>附原始碼片段]
        G4 -->|否| G6[標註僅字串掃描]
        G7[解析 go.mod 相依]
    end
    subgraph PyA[analyze_python.py]
        P1[ast.parse] --> P2[函式長度 / 巢狀 / 未使用 import]
        P1 --> P3[bare except]
        P4[字串掃描]
    end
    subgraph JSA[analyze_js_ts.py]
        J1[去除字串與註解] --> J2[大括號結構掃描<br/>函式邊界 / 巢狀]
        J3{有專案 eslint?} -->|是| J4[eslint --format json<br/>映射嚴重度]
        J5[字串掃描]
    end
```

## Module: common.py（共用資料與安全偵測）

```mermaid
graph TB
    subgraph Common[common.py]
        C1[detect_hardcoded_credentials] --> C2{關鍵字命中?}
        C2 -->|是| C3[Critical]
        C1 --> C4[高熵候選字串]
        C4 --> C5{entropy ≥ 4.0<br/>且非 UUID / 雜湊 / MIME?}
        C5 -->|是| C6[High]
        C7[detect_sql_injection] --> C8[High]
        C9[detect_command_injection] --> C10[High]
        C11[detect_commented_code<br/>≥ 10 行] --> C12[Low]
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

## Module: 建議篩選（Evaluate → Generate）

```mermaid
graph TB
    subgraph Filter[建議篩選]
        F1[issues + metrics] --> F2[規範比對<br/>所在目錄與父目錄的規範檔]
        F2 --> F3[Validation Pass<br/>回原始碼確認錨點]
        F3 -->|確認不了| Drop[移除]
        F3 -->|確認| F4[Recommendation Principles]
        F4 -->|包裝抽象 / 預測性 / 裝飾性<br/>linter 已涵蓋 / 已消音| Drop
        F4 -->|通過| F5[寫入對應段落]
    end
```

## 資料流

```mermaid
sequenceDiagram
    participant User as 使用者
    participant Agent as Agent Harness
    participant Skill as SKILL.md
    participant Py as analyze_code.py
    participant Src as 目標專案
    participant FS as .doc/code-reviewer/

    User->>Agent: /code-reviewer [PROJECT_PATH] [OUTPUT_FILE]
    Agent->>Skill: 載入 skill 定義
    Skill->>Py: python3 analyze_code.py <path>
    Py->>Src: 掃描原始碼（Go 先 gofmt）
    Py-->>Skill: issues / metrics JSON
    Skill->>Src: 讀取規範檔、回原始碼驗證每條發現
    alt 命中 No-Op 且未指定 OUTPUT_FILE
        Skill-->>User: 一行無需處理訊息
    else 有發現或指定 OUTPUT_FILE
        Skill->>FS: 建立目錄並寫入報告
        Skill-->>User: 報告路徑
    end
```

## No-Op 狀態機

```mermaid
stateDiagram-v2
    [*] --> Evaluated
    Evaluated --> CheckIssues
    CheckIssues --> Write: issue_counts 非 0
    CheckIssues --> CheckSuggestions: 全為 0
    CheckSuggestions --> Write: 任一段有有效建議
    CheckSuggestions --> CheckMetrics: 四段皆無
    CheckMetrics --> Write: 有超標 metric
    CheckMetrics --> NoOp: 無超標
    NoOp --> Write: 使用者指定 OUTPUT_FILE
    NoOp --> [*]: 輸出一行訊息，不建目錄不寫檔
    Write --> [*]: 寫入報告
```
