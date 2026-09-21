# code-reviewer - 技術文件

> 返回 [README](./README.zh.md)

## 前置需求

- 可載入 `SKILL.md` skill 並執行 shell 指令的 agent harness
- Python 3.10 或更高版本（分析器與 Python 專案的 `ast` 分析）
- Go 1.21 或更高版本（選用；分析 Go 專案時執行 `go/ast` 輔助程式與 `gofmt`）
- 目標專案的 `node_modules/.bin/eslint`（選用；分析 JS/TS 專案時串接）

工具鏈缺失時對應語言降級為字串掃描，並在報告中標示。

## 安裝

`<skills-dir>` 為所用 harness 掃描的 skill 目錄。

### 從 GitHub 複製

```bash
git clone https://github.com/agenvoy/skill-code-reviewer.git \
    <skills-dir>/code-reviewer
```

### 確認安裝

```bash
ls <skills-dir>/code-reviewer/SKILL.md
ls <skills-dir>/code-reviewer/scripts/analyze_code.py
```

安裝完成後，於 harness 中以 `/code-reviewer` 呼叫即可。

## 使用方式

### 基本用法

```bash
/code-reviewer
```

分析當前目錄，報告寫入 `.doc/code-reviewer/{yyyy-MM-dd_HH-mm}.md`（24 小時制本地時間，目錄不存在時自動建立）。

### 指定專案

```bash
/code-reviewer ./my-project
```

報告寫入 `my-project/.doc/code-reviewer/{yyyy-MM-dd_HH-mm}.md`。

### 指定輸出檔

```bash
/code-reviewer . custom.md
```

直接寫入 `./custom.md`；路徑含目錄時需先自行建立。指定輸出檔視為強制產檔，即使命中 No-Op 條件也會寫入最小報告。

### 無需處理時

```
無需處理：python 專案 my-project（12 檔 / 48 函式）未觀察到可執行建議
```

不建立 `.doc/code-reviewer/`，不寫入任何檔案。

### 手動執行分析器

```bash
python3 <skills-dir>/code-reviewer/scripts/analyze_code.py /path/to/project
```

缺少參數時 exit 1；路徑不存在時輸出 `{"error": "Path does not exist: ..."}`。

## 命令列參考

### Slash Command 參數

| 參數 | 預設 | 說明 |
|------|------|------|
| `PROJECT_PATH` | 當前目錄 | 專案根目錄 |
| `OUTPUT_FILE` | `.doc/code-reviewer/{yyyy-MM-dd_HH-mm}.md` | 輸出路徑（相對於 `PROJECT_PATH`）；報告永不寫在專案根目錄，除非明確指定 |

### 語言偵測

先比對指標檔（`go.mod`、`tsconfig.json`、`package.json`、`pyproject.toml`），無命中再依副檔名數量決定。

| 語言 | 分析方式 | 相依 |
|------|----------|------|
| Go | `go run go_ast.go` + 字串掃描；分析前對非測試檔執行 `gofmt -s -w`（失敗靜默略過） | `go` ≥ 1.21 |
| Python | 內建 `ast` | Python ≥ 3.10 |
| JavaScript / TypeScript | 大括號結構掃描（函式邊界、巢狀深度）+ 專案 eslint（選用）+ 字串掃描 | `node_modules/.bin/eslint`（選用） |

其他語言回傳單一 Low 問題「不支援的語言」。

### 分析器輸出 JSON

| 欄位 | 說明 |
|------|------|
| `language` / `name` | 主要語言與專案名稱 |
| `file_count` / `function_count` | 檔案數與函式數 |
| `files` | 檔案清單（排序） |
| `functions` | `name`、`signature`、`file`、`line`、`line_count`、`has_doc` |
| `issues` | `severity`、`category`、`title`、`description`、`file`、`line`、`code_snippet`、`suggestion`；依嚴重度排序 |
| `issue_counts` | `critical` / `high` / `medium` / `low` 計數 |
| `metrics` | `total_lines`、`code_lines`、`avg_function_length`、`max_function_length`、`max_nesting_depth` |
| `dependencies` | 相依套件 |

### 偵測類別

| 類別 | 問題 | 判準 | 嚴重度 |
|------|------|------|--------|
| Quality | 過長函式 | > 50 行 | Medium |
| Quality | 過深巢狀 | > 3 層 | Medium |
| Quality | 未使用 import | AST 名稱引用 | Low |
| Quality | 大量連續註解 | ≥ 10 行 | Low |
| Quality | Go `interface{}` | AST 空介面 | Low |
| Quality | Go 丟棄回傳值 | `_ = f()` | Medium |
| Quality | Python bare except | `except:` | Medium |
| Quality | JS/TS eslint 規則 | 專案 eslint | High／Medium |
| Security | 硬編碼密鑰 | `password=`、`secret=`、`api_key=` 等 | Critical |
| Security | 可疑高熵字串 | entropy ≥ 4.0、長度 ≥ 32，排除 UUID／MD5／SHA1／SHA256／MIME type | High |
| Security | SQL Injection | 字串拼接／f-string／`%` 格式化 SQL | High |
| Security | Command Injection | 拼接系統指令 | High |

Security 屬樣式比對，高嚴重度一律標註「需人工確認」。

### 報告結構

依序為摘要、Critical／High／Medium／Low 問題、架構建議、效能優化建議、安全性強化建議、規範遵循、待處理項目清單。每條問題含檔案位置、現況、目前程式碼、建議修改與原因；規範遵循另附規範檔路徑與逐字引用的原文。專案沒有 `CLAUDE.md`／`AGENTS.md` 時省略規範遵循段。

### 規範遵循範圍

一個檔案只受所在目錄與各層父目錄的規範檔約束：

| 檔案 | 比對的規範檔 |
|------|--------------|
| `internal/note/new.go` | `internal/note/CLAUDE.md`、`internal/CLAUDE.md`、根目錄 `CLAUDE.md`（`AGENTS.md` 同理） |
| `page/view.ts` | `page/` 與根目錄的規範檔；不受 `internal/` 下規範影響 |

### 建議產出規則

| 規則 | 內容 |
|------|------|
| 錨點 | 每條建議對應 `issues` 條目或明確的檔案與行號 |
| 驗證 | 寫入前回原始碼確認；確認不了的移除，不降級 |
| 禁止 | 包裝既有抽象、為補文件而補文件、預測性優化、無指標佐證的裝飾性重構 |
| 不列 | linter 已涵蓋、已用 `nolint`／`noqa`／註解說明的取捨、只依賴特定輸入才成立的問題 |
| 零建議 | 合法輸出；各段寫「目前未觀察到需處理事項」 |

### No-Op 條件（同時滿足時不產檔）

1. `issue_counts` 全為 0
2. 架構／效能／安全／規範遵循四段皆無有效建議
3. 沒有超標 metric
