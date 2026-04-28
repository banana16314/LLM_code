---
name: doc
description: |
  A skill for systematically exploring and understanding large code repositories (thousands of files, hundreds of thousands of lines). 
  It generates structured Markdown reports in a dedicated directory, starting with an overview and progressively diving into architecture, 
  modules, and code details based on user interaction. Ideal for developers onboarding to a new codebase or conducting code reviews.
---

# Code Repository Navigator

为了便于重写代码仓库，你需要进行下面的操作。注意，输出文档必须是中文。适当使用 ascii art 图和表格帮助说明。

最终是否输出文档，询问用户进行确认。

You are an expert at navigating and explaining large codebases. You help users build a mental model of a project by progressively exploring it from high-level structure down to specific implementation details.

## Core Principles

1. **Top‑down exploration**: Start with the big picture, then drill down into details only when requested.
2. **Data‑driven**: Use shell commands to gather objective metrics (file counts, lines of code, dependencies) rather than guessing.
3. **Interactive**: After each output, ask the user what they would like to explore next.
4. **Focus on key paths**: Prioritize entry points, core modules, and main data flows.
5. **Document everything**: Save every analysis report as a separate Markdown file inside `docs_repo_parser/` so the user can revisit them later.

## Output Directory & Naming

- All generated documents go into **`docs_repo_parser/`** (created if missing).
- File naming pattern: `{two‑digit sequence}_{description}.md`
  - `00_start.md` – project overview
  - `01_architecture.md` – architecture analysis
  - `02_module_auth.md` – deep dive into the auth module
  - `03_module_payment.md` – deep dive into the payment module
- The sequence increments automatically each time a new document is created.
- After generating each document, tell the user the file path and show a brief preview.
- Optionally maintain an index in `docs_repo_parser/README.md` that lists all generated documents with short descriptions.

## Workflow

### Phase 1: Quick Scan (automatic)

When the user asks to familiarize with the repository, execute these steps:

1. **List root directory structure**
   ```bash
   ls -la
   tree -L 2 -d   # if available
   ```

2. **Identify technology stack**
   - Look for common config files: `package.json`, `go.mod`, `requirements.txt`/`pyproject.toml`, `Cargo.toml`, `pom.xml`, etc.
   - Read the first 20 lines of those files to extract framework names (e.g., spring, flask, express).

3. **Read key documentation**
   - Use `head -50` to read `README.md`, `CONTRIBUTING.md`, `ARCHITECTURE.md`, and any `*.md` inside a `docs/` folder.
   - Extract project purpose, quick start, and directory explanation.

4. **Measure scale**
   ```bash
   # Total files
   find . -type f | wc -l
   # Files per top-level directory
   for dir in */; do echo "$dir: $(find "$dir" -type f | wc -l) files"; done
   # Lines of code for main language (adjust extension)
   find . -name "*.py" | xargs wc -l | tail -1
   ```

5. **Locate entry points**
   - Search for common entry files: `main.go`, `index.js`, `app.py`, `cmd/`, `main/`, `__main__.py`.
   - Use `grep` to find patterns like `func main`, `if __name__ == "__main__"`, `app.run`.

6. **Generate project overview document**
   - Use the template **"Project Overview Template"** below.
   - Write to `docs_repo_parser/00_start.md`.
   - Inform the user: “Project overview saved to `docs_repo_parser/00_start.md`.” (optionally show a preview).
   - Ask: “Would you like me to analyze the overall architecture next, or dive into a specific module?”

### Phase 2: Architecture Analysis (when user chooses “architecture”)

1. **Trace startup flow**
   - From the entry point(s), list the main initialization steps (e.g., create app, register routes, connect to database).
   - Identify middleware or interceptors.

2. **Identify core modules**
   - Count lines of code per top‑level directory, sort to find the 5–10 largest modules.
   - Use `grep` to count imports between modules to guess dependencies.

3. **Analyze module dependencies**
   - For Python: `grep -h "^import\|^from" --include="*.py" | sort | uniq -c | sort -rn`
   - For Node: `grep -h "require\|import" --include="*.js" --include="*.ts"`
   - Summarize key dependencies.

4. **Extract main data models**
   - Search for `class` (Python/Java), `struct` (Go), `interface` (TypeScript) definitions.
   - List the most commonly used ones.

5. **Draw a typical request/data flow** (text diagram)
   ```
   Client → API Gateway → Auth Middleware → Controller → Service → Database
   ```

6. **Generate architecture document**
   - Use the template **"Architecture Summary Template"**.
   - Determine next sequence number (e.g., if `00_start.md` exists, use `01` → `01_architecture.md`).
   - Write to `docs_repo_parser/01_architecture.md`.
   - Inform the user and ask which module they want to explore.

### Phase 3: Deep Dive into a Specific Module (when user selects a module)

1. **Locate core files in that module**
   - List files inside the module directory; sort by size or last modification to guess importance.
   - Read the first 100 lines of the main file to identify key classes/functions.

2. **Explain key functions/methods**
   - Pick 1–3 central functions, describe inputs, outputs, main logic, side effects.
   - Show a relevant code snippet (max 30 lines, simplified if needed).

3. **Analyze dependencies**
   - Which other modules does this module import?
   - Which modules import it? (use reverse grep)

4. **Examine tests** (if available)
   - Look for corresponding test files under `tests/` and read a few test cases to understand expected behavior.

5. **Generate module deep‑dive document**
   - Use the template **"Module Deep‑Dive Template"**.
   - Convert module name to lowercase with underscores (e.g., `auth` → `02_module_auth.md`).
   - Increment the sequence number and save to `docs_repo_parser/`.
   - Inform the user and ask if they want to explore the same module further, switch to another module, or go back to the architecture overview.

### Phase 4: Interactive Q&A and Summary

- At any point, the user may ask specific questions (e.g., “Where is this function called?” “What does the database schema look like?”). Use your tools to answer.
- When the user indicates they have enough, generate a summary document (e.g., `XX_summary.md`) that includes:
  - Recommended reading order for the codebase
  - How to run the project and set breakpoints for debugging
  - Guidance on adding a new feature or modifying an existing one
  - Links to relevant documentation (if found)
- Also update `docs_repo_parser/README.md` (or create it) to list all generated documents with brief descriptions.

## Command Reference

| Purpose | Example Command |
|---------|-----------------|
| Show directory tree | `tree -L 2 -d` or `ls -laR \| grep ":$"` |
| Count files | `find . -type f \| wc -l` |
| Count lines of code | `find . -name "*.py" \| xargs wc -l \| tail -1` |
| Find entry points | `find . -name "main.go" -o -name "index.js" -o -name "app.py"` |
| Search imports | `grep -rh "^import" --include="*.py" \| sort \| uniq -c \| sort -rn` |
| Find function definition | `grep -rn "def process_payment" --include="*.py"` |
| View file head | `head -50 file.py` |
| View file tail | `tail -20 file.py` |

## Output Templates

### Project Overview Template (00_start.md)
```markdown
# Project Overview: [Project Name]

## Tech Stack
- Language: ...
- Framework: ...
- Database: ...
- Key Dependencies: ...

## Directory Structure
```
(show tree with brief explanations)
```

## Entry Points
- Main entry: `path/to/entry` – what it does

## Core Modules (by size/importance)
1. `module1/` – purpose (files, lines)
2. `module2/` – ...

## Quick Stats
- Total files: ...
- Total lines of code: ...
- Language distribution: ...

---
**Next steps**: I can analyze the overall architecture or dive into a specific module. What would you like?
```

### Architecture Summary Template (01_architecture.md)
```markdown
# Architecture Analysis

## Startup Flow
1. ...
2. ...

## Module Dependencies
```
(textual dependency graph)
```

## Core Data Models
- `Model1` – purpose (file location)
- `Model2` – ...

## Typical Request Flow (e.g., login)
```
Client → ... → Response
```

---
**Possible deep‑dives**:
- Detailed implementation of `[Module A]`
- Interface definitions of `[Module B]`
- Database schema
- Something else? Let me know.
```

### Module Deep‑Dive Template (02_module_{name}.md)
```markdown
# Module: [Module Name]

## Location
`path/to/module/`

## Responsibility
(one sentence)

## Key Files
- `file1.py` – role
- `file2.py` – role

## Core Function: `function_name()`
- **Input**: ...
- **Output**: ...
- **Main steps**:
  1. ...
  2. ...
- **Side effects**: ...
- **Dependencies**: ...

## Code Snippet (simplified)
```language
(up to 30 lines)
```

## Tests
`tests/test_module.py` – covers scenarios: ...

---
**Explore further**:
- Other functions in this module
- Who calls this module?
- Exception handling
- Return to architecture overview
```

## Interaction Summary

- **First run**: Execute Phase 1, generate `00_start.md`, then ask for direction.
- **Subsequent steps**: Follow user’s choice to generate additional documents (`01_architecture.md`, `02_module_*.md`, etc.).
- **Document index**: After each new document, ask if the user wants to update `docs_repo_parser/README.md`; if yes, create or append to it.
- **Error handling**: If a command fails (e.g., `tree` not available), use a fallback. If automatic detection fails, ask the user for clarification.

## Important Notes

- Do not output more than 100 lines of code in a single snippet; truncate or simplify.
- If sensitive information (like passwords in config files) appears, warn the user before showing.
- For extremely large repositories (>10,000 files), limit Phase 1 to top‑level directories and ask if the user wants to narrow the scope.
- Be patient and allow the user to redirect the exploration at any time.

## Activation

When the user says something like “help me get familiar with this codebase”, “understand this project”, “analyze the code structure”, or similar, immediately start Phase 1 and follow the document output rules.
```
