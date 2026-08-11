# md2office

Convert Markdown to polished DOCX and PDF as a small reusable package.

The engine wraps **pandoc** (Markdown → DOCX with a bundled reference template
and Lua filters) and **LibreOffice** (DOCX → PDF), then post-processes the DOCX
so the output is publication-ready: title + bilingual classification in every
page header, wide autofit tables with explicit borders, monospace shaded
code blocks, and a static table of contents.

## Requirements

- Python 3.9+
- [`pandoc`](https://pandoc.org/installing.html)
- LibreOffice (`soffice`) for PDF conversion
- Carlito + Noto Color Emoji fonts (for PDF rendering)
- `python-docx` (installed automatically with the package)

Run `md2office doctor` to check everything.

## Install

```
pip install -e .
```

## Getting started

md2office converts **one Markdown file into one document**. Keep everything a
document needs in a single folder and point md2office at the master file:

```
docs/
  report.md          # master document (frontmatter + chapters/sections)
  chapter-2.md       # optional: keep long sections as separate files
  images/
    diagram.png
output/              # generated files (gitignore this)
  report.docx
  report.pdf
```

Rules of thumb:

- **One folder per document.** Images and attachments are resolved relative to
  the Markdown file's folder, which is automatically on pandoc's resource
  path. Extra folders can be added with `-r <dir>` (CLI) or
  `resource_path=[...]` (library).
- **Set the title in YAML frontmatter** at the top of the master file. It is
  written into the page headers, cover, and core metadata:

  ```
  ---
  title: Developer Guide
  author: Platform Team
  version: 1.2.0
  effective_date: 2026-01-15
  classification: Unclassified | Non classifié
  ---
  ```

- **Reference images with relative paths**, e.g. `![Architecture](images/diagram.png)`.
- **Fenced code blocks** are styled automatically (monospace, 9pt, shaded).
  Mermaid blocks (```` ```mermaid ````) are rendered when `mmdc` is installed.
- **A static table of contents** is inserted at the top of every document.
  Drop a `\newpage` to force a page break, or use `--page-breaks sections`
  to start each Heading1 on a new page.

Convert:

```
cd docs
md2office pdf report.md ../output/report.pdf
```

> **Multi-chapter books:** md2office does not assemble multiple files. Either
> keep one master file per document, or combine chapters first (a small build
> script or `cat chapters/*.md > book.md`) and convert the result once.

## Usage

### CLI

```
md2office docx report.md report.docx --title "My Report" --classification "Protected A"
md2office pdf  report.md report.pdf
md2office pdf  report.md report.pdf --keep-docx   # keep intermediate .docx
md2office doctor
```

The title defaults to the YAML frontmatter `title:`; the classification
defaults to `Unclassified | Non classifié`.

### Library

```python
import md2office

md2office.to_docx("report.md", "report.docx",
                  title="My Report", classification="Protected A")
md2office.to_pdf("report.md", "report.pdf")

# fine-grained control
from md2office import ConvertOptions, to_pdf

opts = ConvertOptions(number_sections=True, font="arial", page_breaks="sections")
to_pdf("report.md", "report.pdf", options=opts)
```

### Options (`ConvertOptions`)

| Option              | Default    | Meaning                                             |
| ------------------- | ---------- | --------------------------------------------------- |
| `title`             | `""`       | Document title; header + core metadata              |
| `classification`    | `"Unclassified \| Non classifié"` | Sensitivity label in headers |
| `author`            | `""`       | Author (used for section page breaks)               |
| `version`           | `""`       | Version (used for section page breaks)              |
| `effective_date`    | `""`       | Effective date (used for section page breaks)       |
| `number_sections`   | `False`    | Pass `--number-sections` to pandoc                  |
| `code_style`        | `True`     | Monospace + shading on `SourceCode`/`VerbatimChar`  |
| `page_breaks`       | `"none"`   | `"sections"` puts each Heading1 on a new page       |
| `font`              | `"default"`| `"arial"` switches document fonts                   |
| `mermaid`           | `"auto"`   | Render ``` ```mermaid``` blocks (needs `mmdc`)      |
| `resource_path`     | `[]`       | Extra pandoc resource directories                   |
| `keep_docx`         | `False`    | Keep the intermediate DOCX when producing PDF       |

## Layout

```
src/md2office/
  __init__.py        public API (to_docx, to_pdf, ConvertOptions)
  engine.py          pandoc/LibreOffice orchestration + doctor
  postprocess.py     DOCX post-processing (headers, tables, code style)
  cli.py / __main__.py
  assets/            reference.dotx + Lua filters (pagebreak, toc, mermaid)
```

## Notes

- Pandoc must be able to find its Lua filters and the reference template; they
  are bundled inside the package so there is nothing to install.
- The template and post-processing behaviour are tailored to the style used by
  the documentation build this was extracted from; swap in your own template
  and tune `postprocess.py` deliberately when you need a different look.
