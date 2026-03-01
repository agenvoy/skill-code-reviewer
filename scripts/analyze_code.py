#!/usr/bin/env python3
"""
Analyze project source code for optimization opportunities.
Detects: code quality issues, performance problems, security risks, architecture concerns.
Supports: Go, Python, JavaScript/TypeScript, PHP
"""

import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Issue:
    severity: str  # critical, high, medium, low
    category: str  # quality, performance, security, architecture
    title: str
    description: str
    file: str
    line: int = 0
    code_snippet: str = ""
    suggestion: str = ""


@dataclass
class FunctionInfo:
    name: str
    signature: str
    file: str
    line: int = 0
    line_count: int = 0
    complexity: int = 0  # cyclomatic complexity estimate
    has_doc: bool = False


@dataclass
class TypeInfo:
    name: str
    kind: str
    field_count: int = 0
    method_count: int = 0
    file: str = ""


@dataclass
class CodeMetrics:
    total_lines: int = 0
    code_lines: int = 0
    comment_lines: int = 0
    blank_lines: int = 0
    avg_function_length: float = 0.0
    max_function_length: int = 0
    max_nesting_depth: int = 0


@dataclass
class ProjectAnalysis:
    language: str
    name: str
    files: list[str] = field(default_factory=list)
    types: list[TypeInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    metrics: CodeMetrics = field(default_factory=CodeMetrics)
    dependencies: list[str] = field(default_factory=list)


IGNORE_DIRS = {
    ".git", "node_modules", "vendor", ".idea", ".vscode",
    "__pycache__", ".pytest_cache", "dist", "build", "target",
    ".next", ".nuxt", "coverage", ".nyc_output", "venv", ".venv",
}

IGNORE_FILES = {
    ".DS_Store", "Thumbs.db", ".gitignore", ".gitattributes",
    "package-lock.json", "yarn.lock", "go.sum", "Pipfile.lock",
    "poetry.lock", "composer.lock",
}

# Patterns for detecting issues
HARDCODED_PATTERNS = {
    "path": [
        r'["\']\/(?:home|Users|var|etc|tmp)\/[^"\']+["\']',
        r'["\'][A-Z]:\\[^"\']+["\']',  # Windows paths
    ],
    "url": [
        r'["\']https?:\/\/(?:localhost|127\.0\.0\.1|0\.0\.0\.0)[:\d]*[^"\']*["\']',
        r'["\']https?:\/\/\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}[:\d]*[^"\']*["\']',
    ],
    "credentials": [
        r'(?:password|passwd|pwd|secret|api_?key|token)\s*[=:]\s*["\'][^"\']{4,}["\']',
        r'["\'][a-zA-Z0-9]{32,}["\']',  # Long strings that might be keys
    ],
    "port": [
        r':\d{4,5}(?:["\']|$)',
    ],
}

SQL_INJECTION_PATTERNS = [
    r'(?:execute|query|raw)\s*\([^)]*\+[^)]*\)',
    r'(?:execute|query|raw)\s*\([^)]*%[^)]*\)',
    r'f["\'].*(?:SELECT|INSERT|UPDATE|DELETE|DROP).*\{',
]

COMMAND_INJECTION_PATTERNS = [
    r'(?:exec|system|popen|subprocess\.call|os\.system)\s*\([^)]*\+',
    r'(?:exec|system|popen)\s*\([^)]*\$',
    r'exec\.Command\s*\([^)]*\+',
]


def run_gofmt(file_path: Path) -> bool:
    """Run gofmt -s -w on a Go file. Returns True if successful."""
    try:
        result = subprocess.run(
            ["gofmt", "-s", "-w", str(file_path)],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def detect_language(root: Path) -> str:
    """Detect primary project language."""
    indicators = {
        "go": ["go.mod", "go.sum"],
        "python": ["pyproject.toml", "setup.py", "requirements.txt", "Pipfile"],
        "javascript": ["package.json"],
        "typescript": ["tsconfig.json"],
        "php": ["composer.json"],
    }

    for lang, files in indicators.items():
        for pattern in files:
            if (root / pattern).exists():
                if lang == "javascript" and (root / "tsconfig.json").exists():
                    return "typescript"
                return lang

    ext_count = {}
    ext_map = {".go": "go", ".py": "python", ".js": "javascript", ".ts": "typescript", ".php": "php"}

    for f in root.rglob("*"):
        if f.is_file() and f.suffix in ext_map:
            lang = ext_map[f.suffix]
            ext_count[lang] = ext_count.get(lang, 0) + 1

    return max(ext_count, key=ext_count.get) if ext_count else "unknown"


def count_nesting_depth(content: str, lang: str) -> int:
    """Estimate maximum nesting depth."""
    max_depth = 0
    current_depth = 0

    open_chars = {'{': '}', '(': ')'}
    if lang == "python":
        # For Python, count indentation
        for line in content.split('\n'):
            stripped = line.lstrip()
            if stripped and not stripped.startswith('#'):
                indent = len(line) - len(stripped)
                depth = indent // 4  # Assuming 4-space indent
                max_depth = max(max_depth, depth)
    else:
        for char in content:
            if char == '{':
                current_depth += 1
                max_depth = max(max_depth, current_depth)
            elif char == '}':
                current_depth = max(0, current_depth - 1)

    return max_depth


def detect_hardcoded_values(content: str, file_path: str, issues: list[Issue]):
    """Detect hardcoded paths, URLs, credentials."""
    lines = content.split('\n')

    for category, patterns in HARDCODED_PATTERNS.items():
        for pattern in patterns:
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line, re.IGNORECASE):
                    # Skip if it's a comment or test file
                    if 'test' in file_path.lower() or line.strip().startswith(('#', '//', '/*', '*')):
                        continue

                    severity = "critical" if category == "credentials" else "high"
                    issues.append(Issue(
                        severity=severity,
                        category="security" if category == "credentials" else "quality",
                        title=f"硬編碼的{category}",
                        description=f"偵測到硬編碼的 {category}，應改用環境變數或設定檔",
                        file=file_path,
                        line=i,
                        code_snippet=line.strip()[:100],
                        suggestion=f"使用環境變數 os.Getenv() 或設定檔取代硬編碼值"
                    ))


def detect_sql_injection(content: str, file_path: str, issues: list[Issue]):
    """Detect potential SQL injection vulnerabilities."""
    lines = content.split('\n')

    for pattern in SQL_INJECTION_PATTERNS:
        for i, line in enumerate(lines, 1):
            if re.search(pattern, line, re.IGNORECASE):
                issues.append(Issue(
                    severity="critical",
                    category="security",
                    title="潛在的 SQL Injection",
                    description="使用字串拼接或格式化建構 SQL 查詢，可能導致 SQL Injection",
                    file=file_path,
                    line=i,
                    code_snippet=line.strip()[:100],
                    suggestion="使用參數化查詢（Prepared Statement）取代字串拼接"
                ))


def detect_command_injection(content: str, file_path: str, issues: list[Issue]):
    """Detect potential command injection vulnerabilities."""
    lines = content.split('\n')

    for pattern in COMMAND_INJECTION_PATTERNS:
        for i, line in enumerate(lines, 1):
            if re.search(pattern, line, re.IGNORECASE):
                issues.append(Issue(
                    severity="critical",
                    category="security",
                    title="潛在的 Command Injection",
                    description="使用字串拼接建構系統指令，可能導致 Command Injection",
                    file=file_path,
                    line=i,
                    code_snippet=line.strip()[:100],
                    suggestion="使用安全的 API 並驗證所有外部輸入"
                ))


def detect_commented_code(content: str, file_path: str, lang: str, issues: list[Issue]):
    """Detect large blocks of commented code."""
    lines = content.split('\n')
    comment_block_start = None
    comment_count = 0

    comment_patterns = {
        "go": r'^\s*\/\/',
        "python": r'^\s*#',
        "javascript": r'^\s*\/\/',
        "typescript": r'^\s*\/\/',
        "php": r'^\s*(?:\/\/|#)',
    }

    pattern = comment_patterns.get(lang, r'^\s*(?:\/\/|#)')

    for i, line in enumerate(lines, 1):
        if re.match(pattern, line):
            if comment_block_start is None:
                comment_block_start = i
            comment_count += 1
        else:
            if comment_count >= 10:  # 10+ consecutive comment lines
                issues.append(Issue(
                    severity="low",
                    category="quality",
                    title="大量註解程式碼",
                    description=f"偵測到 {comment_count} 行連續註解，可能是被註解掉的程式碼",
                    file=file_path,
                    line=comment_block_start,
                    suggestion="若為廢棄程式碼，建議移除；若為文件，考慮移至獨立文件"
                ))
            comment_block_start = None
            comment_count = 0


def detect_unused_imports_go(content: str, file_path: str, issues: list[Issue]):
    """Detect unused imports in Go files."""
    import_pattern = r'import\s+(?:\(\s*([^)]+)\s*\)|"([^"]+)")'
    imports = []

    for m in re.finditer(import_pattern, content):
        if m.group(1):  # Multi-line import
            for line in m.group(1).split('\n'):
                line = line.strip()
                if line and not line.startswith('//'):
                    # Extract package name
                    parts = line.strip('"').split('/')
                    pkg_name = parts[-1].strip('"')
                    if ' ' in line:  # Aliased import
                        pkg_name = line.split()[0]
                    imports.append(pkg_name)
        elif m.group(2):  # Single import
            parts = m.group(2).split('/')
            imports.append(parts[-1])

    # Check if imports are used (simple check)
    code_without_imports = re.sub(r'import\s+(?:\([^)]+\)|"[^"]+")', '', content)

    for imp in imports:
        if imp.startswith('_'):  # Blank import
            continue
        # Simple usage check
        if not re.search(rf'\b{re.escape(imp)}\.', code_without_imports):
            issues.append(Issue(
                severity="low",
                category="quality",
                title="可能未使用的 Import",
                description=f"套件 '{imp}' 可能未被使用",
                file=file_path,
                line=0,
                suggestion="移除未使用的 import 或確認是否為 side-effect import"
            ))


def detect_missing_error_handling_go(content: str, file_path: str, issues: list[Issue]):
    """Detect ignored errors in Go code."""
    lines = content.split('\n')

    # Pattern: function call that returns error but error is ignored
    patterns = [
        r'^\s*[^,]+,\s*_\s*:?=\s*\w+\([^)]*\)',  # x, _ := func()
        r'^\s*_\s*=\s*\w+\([^)]*\)',  # _ = func()
    ]

    for i, line in enumerate(lines, 1):
        for pattern in patterns:
            if re.match(pattern, line):
                # Check if it's likely an error being ignored
                if 'err' in line.lower() or 'error' in line.lower():
                    continue  # Probably not ignoring error
                issues.append(Issue(
                    severity="medium",
                    category="quality",
                    title="忽略的回傳值",
                    description="函式回傳值被忽略，可能遺漏錯誤處理",
                    file=file_path,
                    line=i,
                    code_snippet=line.strip()[:100],
                    suggestion="檢查是否應該處理回傳的 error"
                ))


def detect_long_functions(functions: list[FunctionInfo], issues: list[Issue], threshold: int = 50):
    """Detect functions that are too long."""
    for func in functions:
        if func.line_count > threshold:
            issues.append(Issue(
                severity="medium",
                category="quality",
                title="過長的函式",
                description=f"函式 '{func.name}' 有 {func.line_count} 行，建議拆分",
                file=func.file,
                line=func.line,
                suggestion=f"考慮將函式拆分為多個小函式，每個函式專注於單一職責"
            ))


def analyze_go(root: Path) -> ProjectAnalysis:
    """Analyze Go project."""
    analysis = ProjectAnalysis(language="go", name=root.name)

    # Parse go.mod
    go_mod = root / "go.mod"
    if go_mod.exists():
        content = go_mod.read_text()
        if m := re.search(r"^module\s+(.+)$", content, re.MULTILINE):
            analysis.name = m.group(1).split("/")[-1]
        for m in re.finditer(r"^\t([^\s]+)\s+v[\d.]+", content, re.MULTILINE):
            analysis.dependencies.append(m.group(1))

    total_lines = 0
    code_lines = 0
    function_lengths = []

    for go_file in root.rglob("*.go"):
        if any(p in go_file.parts for p in IGNORE_DIRS):
            continue
        if "_test.go" in go_file.name:
            continue

        rel_path = str(go_file.relative_to(root))
        analysis.files.append(rel_path)

        run_gofmt(go_file)

        try:
            content = go_file.read_text()
        except:
            continue

        lines = content.split('\n')
        total_lines += len(lines)
        code_lines += sum(1 for l in lines if l.strip() and not l.strip().startswith('//'))

        # Detect issues
        detect_hardcoded_values(content, rel_path, analysis.issues)
        detect_sql_injection(content, rel_path, analysis.issues)
        detect_command_injection(content, rel_path, analysis.issues)
        detect_commented_code(content, rel_path, "go", analysis.issues)
        detect_unused_imports_go(content, rel_path, analysis.issues)
        detect_missing_error_handling_go(content, rel_path, analysis.issues)

        # Extract functions
        func_pattern = r"func\s+(?:\((\w+)\s+\*?(\w+)\)\s+)?(\w+)\s*\(([^)]*)\)[^{]*\{"
        for m in re.finditer(func_pattern, content):
            recv_name, recv_type, func_name, params = m.groups()

            # Find function end to count lines
            start_pos = m.end()
            brace_count = 1
            end_pos = start_pos
            for i, char in enumerate(content[start_pos:], start_pos):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_pos = i
                        break

            func_content = content[m.start():end_pos]
            line_count = func_content.count('\n') + 1
            start_line = content[:m.start()].count('\n') + 1

            function_lengths.append(line_count)

            sig = f"func {func_name}({params})"
            if recv_type:
                sig = f"func ({recv_name} *{recv_type}) {func_name}({params})"

            analysis.functions.append(FunctionInfo(
                name=func_name,
                signature=sig,
                file=rel_path,
                line=start_line,
                line_count=line_count,
                has_doc=bool(re.search(rf'//\s*{func_name}', content[:m.start()][-200:]))
            ))

        # Update max nesting
        depth = count_nesting_depth(content, "go")
        analysis.metrics.max_nesting_depth = max(analysis.metrics.max_nesting_depth, depth)

    # Detect long functions
    detect_long_functions(analysis.functions, analysis.issues)

    # Calculate metrics
    analysis.metrics.total_lines = total_lines
    analysis.metrics.code_lines = code_lines
    if function_lengths:
        analysis.metrics.avg_function_length = sum(function_lengths) / len(function_lengths)
        analysis.metrics.max_function_length = max(function_lengths)

    return analysis


def analyze_python(root: Path) -> ProjectAnalysis:
    """Analyze Python project."""
    analysis = ProjectAnalysis(language="python", name=root.name)

    total_lines = 0
    function_lengths = []

    for py_file in root.rglob("*.py"):
        if any(p in py_file.parts for p in IGNORE_DIRS):
            continue

        rel_path = str(py_file.relative_to(root))
        analysis.files.append(rel_path)

        try:
            content = py_file.read_text()
        except:
            continue

        lines = content.split('\n')
        total_lines += len(lines)

        # Detect issues
        detect_hardcoded_values(content, rel_path, analysis.issues)
        detect_sql_injection(content, rel_path, analysis.issues)
        detect_command_injection(content, rel_path, analysis.issues)
        detect_commented_code(content, rel_path, "python", analysis.issues)

        # Extract functions
        func_pattern = r"def\s+(\w+)\s*\(([^)]*)\)(?:\s*->\s*(\S+))?:"
        for m in re.finditer(func_pattern, content):
            name, params, ret = m.groups()
            start_line = content[:m.start()].count('\n') + 1

            # Estimate function length by indentation
            remaining = content[m.end():]
            line_count = 1
            for line in remaining.split('\n')[1:]:
                if line.strip() and not line.startswith(' ') and not line.startswith('\t'):
                    break
                line_count += 1

            function_lengths.append(line_count)

            analysis.functions.append(FunctionInfo(
                name=name,
                signature=f"def {name}({params})" + (f" -> {ret}" if ret else ""),
                file=rel_path,
                line=start_line,
                line_count=line_count,
            ))

        depth = count_nesting_depth(content, "python")
        analysis.metrics.max_nesting_depth = max(analysis.metrics.max_nesting_depth, depth)

    detect_long_functions(analysis.functions, analysis.issues)

    analysis.metrics.total_lines = total_lines
    if function_lengths:
        analysis.metrics.avg_function_length = sum(function_lengths) / len(function_lengths)
        analysis.metrics.max_function_length = max(function_lengths)

    return analysis


def analyze_js_ts(root: Path, lang: str) -> ProjectAnalysis:
    """Analyze JavaScript/TypeScript project."""
    analysis = ProjectAnalysis(language=lang, name=root.name)

    # Parse package.json
    pkg_json = root / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            analysis.name = pkg.get("name", root.name)
            analysis.dependencies = list(pkg.get("dependencies", {}).keys())
        except:
            pass

    total_lines = 0
    function_lengths = []
    ext = "*.ts" if lang == "typescript" else "*.js"

    for src_file in root.rglob(ext):
        if any(p in src_file.parts for p in IGNORE_DIRS):
            continue
        if ".d.ts" in src_file.name or ".spec." in src_file.name or ".test." in src_file.name:
            continue

        rel_path = str(src_file.relative_to(root))
        analysis.files.append(rel_path)

        try:
            content = src_file.read_text()
        except:
            continue

        lines = content.split('\n')
        total_lines += len(lines)

        # Detect issues
        detect_hardcoded_values(content, rel_path, analysis.issues)
        detect_sql_injection(content, rel_path, analysis.issues)
        detect_command_injection(content, rel_path, analysis.issues)
        detect_commented_code(content, rel_path, lang, analysis.issues)

        # Extract functions
        func_patterns = [
            r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*(?:<[^>]+>)?\s*\(([^)]*)\)",
            r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>",
        ]

        for pattern in func_patterns:
            for m in re.finditer(pattern, content):
                name = m.group(1)
                start_line = content[:m.start()].count('\n') + 1

                analysis.functions.append(FunctionInfo(
                    name=name,
                    signature=m.group(0)[:80],
                    file=rel_path,
                    line=start_line,
                ))

        depth = count_nesting_depth(content, lang)
        analysis.metrics.max_nesting_depth = max(analysis.metrics.max_nesting_depth, depth)

    analysis.metrics.total_lines = total_lines

    return analysis


def analyze_project(root_path: str) -> dict:
    """Main entry point for project analysis."""
    root = Path(root_path).resolve()

    if not root.exists():
        return {"error": f"Path does not exist: {root_path}"}

    lang = detect_language(root)

    if lang == "go":
        analysis = analyze_go(root)
    elif lang == "python":
        analysis = analyze_python(root)
    elif lang in ("javascript", "typescript"):
        analysis = analyze_js_ts(root, lang)
    else:
        analysis = ProjectAnalysis(language=lang, name=root.name)
        for f in root.rglob("*"):
            if f.is_file() and not any(p in f.parts for p in IGNORE_DIRS):
                if f.name not in IGNORE_FILES:
                    analysis.files.append(str(f.relative_to(root)))

    # Sort issues by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    analysis.issues.sort(key=lambda x: severity_order.get(x.severity, 4))

    # Count issues by severity
    issue_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for issue in analysis.issues:
        issue_counts[issue.severity] = issue_counts.get(issue.severity, 0) + 1

    result = {
        "language": analysis.language,
        "name": analysis.name,
        "file_count": len(analysis.files),
        "function_count": len(analysis.functions),
        "files": sorted(analysis.files),
        "functions": [asdict(f) for f in analysis.functions],
        "issues": [asdict(i) for i in analysis.issues],
        "issue_counts": issue_counts,
        "metrics": asdict(analysis.metrics),
        "dependencies": analysis.dependencies,
    }

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: analyze_code.py <project_path>", file=sys.stderr)
        sys.exit(1)

    result = analyze_project(sys.argv[1])
    print(json.dumps(result, indent=2, ensure_ascii=False))
