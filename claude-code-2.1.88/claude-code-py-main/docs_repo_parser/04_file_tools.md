# 文件工具详解

## 概述

项目提供三个核心文件工具：**Read**、**Edit** 和 **Write**，每个工具都有严格的安全检查和错误处理机制。

| 工具 | 文件 | 功能 | 只读 |
|------|------|------|------|
| Read | `file_read.py` | 读取文件内容（支持图片、PDF、Notebook） | ✅ |
| Edit | `file_edit.py` | 精确字符串替换编辑 | ❌ |
| Write | `file_write.py` | 写入文件（覆盖或创建） | ❌ |

## Read 工具

### 功能特性

```python
class FileReadTool(BaseTool):
    """读取文件工具。"""
    
    def is_read_only(self, args: dict) -> bool:
        return True  # 只读工具，可并行执行
    
    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        # 支持：
        # - 文本文件（最多 2000 行，可分页）
        # - 图片文件（PNG, JPG, GIF 等，返回 Base64）
        # - PDF 文件（支持指定页码范围）
        # - Jupyter Notebook（.ipynb）
```

### 输入 Schema

```json
{
  "type": "object",
  "properties": {
    "file_path": {
      "type": "string",
      "description": "The absolute path to the file to read"
    },
    "offset": {
      "type": "number",
      "description": "The line number to start reading from (1-based)"
    },
    "limit": {
      "type": "number",
      "description": "The number of lines to read"
    },
    "pages": {
      "type": "string",
      "description": "Page range for PDF files (e.g., '1-5')"
    }
  },
  "required": ["file_path"]
}
```

### 支持的文件类型

| 类型 | 扩展名 | 处理方式 |
|------|--------|----------|
| 文本文件 | .py, .js, .md, .txt 等 | 按行读取，带行号显示 |
| 图片 | .png, .jpg, .jpeg, .gif, .bmp, .webp, .svg | Base64 编码 |
| PDF | .pdf | 使用 pypdf 提取文本 |
| Notebook | .ipynb | 解析 JSON 提取单元格 |

### 二进制文件拒绝

```python
BINARY_EXTS = {
    ".exe", ".dll", ".so", ".dylib", ".o", ".a", ".lib",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".class", ".pyc", ".pyo", ".wasm",
    ".mp3", ".mp4", ".avi", ".mov", ".mkv", ".flac", ".wav",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
}

# 内容检测
if b"\x00" in sample:
    return ToolResult(error=f"Cannot read binary file: {file_path}", is_error=True)
```

### 行号格式

```
   1\tdef hello():
   2\t    print("Hello, World!")
   3\t
   4\tif __name__ == "__main__":
   5\t    hello()
```

### 已读文件追踪

```python
# 读取文件时记录 mtime
def mark_file_read(self, file_path: str, mtime: float):
    self._read_files[file_path] = mtime

# 编辑前检查是否已读取
def was_file_read(self, file_path: str) -> bool:
    return file_path in self._read_files
```

**设计目的**：确保 Edit/Write 工具在修改文件前先读取文件，避免误操作。

## Edit 工具

### 核心逻辑

```python
class FileEditTool(BaseTool):
    """文件编辑工具 - 精确字符串替换。"""
    
    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        file_path = args.get("file_path", "")
        old_string = args.get("old_string", "")
        new_string = args.get("new_string", "")
        replace_all = args.get("replace_all", False)
        
        # 1. 验证
        if not old_string or old_string == new_string:
            return ToolResult(error="Invalid arguments", is_error=True)
        
        # 2. 检查是否已读取
        if not _app_state.was_file_read(file_path):
            return ToolResult(
                error=f"File has not been read yet: {file_path}. "
                      "You must use the Read tool before editing.",
                is_error=True,
            )
        
        # 3. 查找匹配
        count = content.count(old_string)
        
        if count == 0:
            # 尝试智能引号标准化
            normalized = _normalize_quotes(old_string)
            count = content.count(normalized)
            # ...
        
        if count > 1 and not replace_all:
            return ToolResult(
                error=f"old_string found {count} times. "
                      "Provide more context or use replace_all=true",
                is_error=True,
            )
        
        # 4. 应用替换
        if replace_all:
            new_content = content.replace(old_string, new_string)
        else:
            new_content = content.replace(old_string, new_string, 1)
        
        # 5. 写回文件
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        # 6. 返回结果（包含上下文片段）
        return ToolResult(output=f"Replaced {replaced} occurrence(s)...\n\nContext:\n{snippet}")
```

### 智能引号标准化

```python
def _normalize_quotes(text: str) -> str:
    """Normalize smart quotes to straight quotes."""
    replacements = {
        "\u2018": "'", "\u2019": "'",  # 单引号
        "\u201c": '"', "\u201d": '"',  # 双引号
        "\u2013": "-", "\u2014": "--", # 破折号
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text
```

**作用**：处理从某些富文本编辑器复制时产生的智能引号。

### 上下文片段显示

```python
def _get_snippet(content: str, target: str, context_lines: int = 3) -> str:
    """Get a few lines around the replacement."""
    lines = content.split("\n")
    target_start = content.find(target)
    line_no = content[:target_start].count("\n")
    start = max(0, line_no - context_lines)
    end = min(len(lines), line_no + context_lines + 1)
    
    snippet_lines = []
    for i in range(start, end):
        snippet_lines.append(f"{i + 1:>6}\t{lines[i]}")
    return "\n".join(snippet_lines)
```

## Write 工具

### 核心逻辑

```python
class FileWriteTool(BaseTool):
    """文件写入工具。"""
    
    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        file_path = args.get("file_path", "")
        content = args.get("content", "")
        
        # 检查是否是新文件
        is_new = not os.path.exists(file_path)
        
        if not is_new:
            # 检查是否已读取
            if not _app_state.was_file_read(file_path):
                return ToolResult(
                    error=f"File exists but has not been read yet: {file_path}. "
                          "You must use the Read tool before overwriting.",
                    is_error=True,
                )
            
            # 读取旧内容用于显示 diff
            with open(file_path, "r") as f:
                old_content = f.read()
        
        # 创建父目录
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # 写入文件
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        # 显示结果
        action = "Created" if is_new else "Updated"
        result_text = f"{action}: {file_path} ({lines} lines)"
        
        # 显示 diff
        if old_content is not None and old_content != content:
            diff = _compact_diff(old_content, content, file_path)
            result_text += f"\n\n{diff}"
        
        return ToolResult(output=result_text)
```

### Diff 显示

```python
def _compact_diff(old: str, new: str, path: str, max_lines: int = 30) -> str:
    """Generate a compact unified diff."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = list(difflib.unified_diff(old_lines, new_lines, fromfile=path, tofile=path))
    
    if len(diff) > max_lines:
        return "\n".join(diff[:max_lines]) + f"\n... ({len(diff) - max_lines} more diff lines)"
    return "\n".join(diff)
```

**输出示例**：
```
Updated: app.py (12 lines)

--- app.py
+++ app.py
@@ -1,5 +1,7 @@
 from flask import Flask
+
+app = Flask(__name__)
 
 @app.route('/')
 def hello():
```

## 错误处理策略

### Read 工具的常见错误

| 错误场景 | 错误信息 |
|----------|----------|
| 文件不存在 | `File not found: /path/to/file` |
| 是目录 | `Path is a directory: /path/to/dir. Use Bash with 'ls' to list directory contents.` |
| 二进制文件 | `Cannot read binary file (.exe): /path/to/file` |
| 设备文件 | `Cannot read device path: /dev/null` |

### Edit 工具的常见错误

| 错误场景 | 错误信息 |
|----------|----------|
| 文件未读取 | `File has not been read yet: /path/to/file. You must use the Read tool before editing.` |
| 字符串未找到 | `old_string not found in /path/to/file.` |
| 多次匹配 | `old_string found 3 times. Provide more context or use replace_all=true` |
| 相同字符串 | `old_string and new_string are identical` |
| Notebook 文件 | `Use the NotebookEdit tool for Jupyter notebooks, not Edit.` |

### Write 工具的常见错误

| 错误场景 | 错误信息 |
|----------|----------|
| 文件未读取 | `File exists but has not been read yet: /path/to/file. You must use the Read tool before overwriting.` |
| Notebook 文件 | `Use the NotebookEdit tool for Jupyter notebooks.` |

## 工作流

### 推荐的文件编辑流程

```
1. Read <file_path>
   └─> 读取文件内容，标记为"已读"
   
2. Edit <file_path> with old_string/new_string
   └─> 验证已读 → 替换 → 写回
   
或

1. Read <file_path>
   └─> 读取文件内容
   
2. Write <file_path> with new_content
   └─> 验证已读 → 写回（显示 diff）
```

### 最佳实践

| 场景 | 推荐工具 |
|------|----------|
| 修改少量内容 | Edit（精确替换） |
| 完全重写文件 | Write（显示完整 diff） |
| 新建文件 | Write |
| 查看文件内容 | Read |
| 编辑 Notebook | NotebookEdit |

## 相关工具

- `NotebookEditTool` - 专门用于 Jupyter Notebook 编辑
- `TaskTools` - 任务管理（不直接操作文件）
- `BashTool` - 可执行文件操作命令（但不推荐用于常规编辑）

## 下一步

- `05_permission_system.md` - 权限系统详解
- `06_query_loop.md` - 查询循环详解
