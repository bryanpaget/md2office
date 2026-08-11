---
title: md2office Sample Document
classification: Unclassified | Non classifié
author: CI
version: 0.1.0
---

# Overview

This document is built automatically by the sample-release CI workflow. It
exercises the pieces md2office formats: headings, a table, and a fenced code
block.

## A table

| Tool        | Purpose                          | Status     |
| ----------- | -------------------------------- | ---------- |
| pandoc      | Markdown to DOCX                 | Required   |
| LibreOffice | DOCX to PDF                      | Required   |
| python-docx | Post-process table cell styling  | Bundled    |

## Some code

```python
import md2office

md2office.to_pdf(
    "report.md",
    "report.pdf",
    template="template.dotx",
)
```

Inline `code` stays readable inside a sentence.

# Conclusion

One pipeline, two polished artifacts, one release asset.
