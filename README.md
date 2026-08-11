# md2office

Convert Markdown to SSC-styled DOCX and PDF, the way the
[`security-narratives`](https://github.com/anomalyco/security-narratives) book
build does — bundled as a small reusable package.

The engine wraps **pandoc** (Markdown → DOCX with the SSC reference template
and Lua filters) and **LibreOffice** (DOCX → PDF), then post-processes the DOCX
so the output matches the assessed book: title + bilingual classification in
every page header, wide autofit tables with explicit borders, monospace shaded
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
  assets/            ssc-template-v2.7.dotx + Lua filters (pagebreak, toc, mermaid)
```

## Notes

- Pandoc must be able to find its Lua filters and the reference template; they
  are bundled inside the package so there is nothing to install.
- The template (`ssc-template-v2.7.dotx`) and the post-processing behaviour are
  vendored from the SSC `markdown-to-word` build; keep them in sync deliberately.
