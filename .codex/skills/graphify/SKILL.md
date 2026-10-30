---
name: graphify
description: Consult the local knowledge graph of this Flask, Jinja, JavaScript, and SQL project for architecture, dependencies, call paths, and impact analysis. Use compact graph queries before broad codebase searches when graphify-out/graph.json exists.
---

# Graphify for Panadería Amada

Run commands from `C:\Ingenieria de software\panaderia_amada` in PowerShell. The verified Graphify Labs CLI is installed at `C:\Users\miure\.codex\tools\graphify\Scripts\graphify.exe` (package `graphifyy` with SQL and MCP extras). Do not install another similarly named package.

## Query first

If `graphify-out\graph.json` exists, use a small result budget before reading broad sets of source files:

```powershell
& 'C:\Users\miure\.codex\tools\graphify\Scripts\graphify.exe' query 'How does payroll use cash accounts?' --budget 1200
```

Use `graphify explain <symbol>` for one symbol and `graphify path <source> <target>` for a relationship. Treat graph findings as leads; confirm any consequential behavior in source code or tests. An absent graph edge does not prove that a dependency is absent, especially across templates, dynamic imports, SQL, and Flask route registration.

## Build or refresh

For the first build, use local structural extraction without a model/API key:

```powershell
& 'C:\Users\miure\.codex\tools\graphify\Scripts\graphify.exe' extract . --code-only
```

After source changes, run `graphify update .` using the same executable. The graph is a generated local artifact in `graphify-out/`; do not commit it or treat it as a source of truth. To view it, run `graphify export html` and open the generated HTML locally.

Source: Graphify Labs local CLI and Codex integration documentation, https://docs.graphify.com/integrations/codex and https://docs.graphify.com/reference/extract.
