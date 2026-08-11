"""SSC-styled Markdown to DOCX/PDF conversion engine.

The engine bundles the pandoc filters, the SSC reference template, and the
DOCX post-processing steps (header injection, table fixes, code styling) so a
single import can turn Markdown into a formatted Word document or PDF.

Typical usage::

    import md2office

    docx = md2office.to_docx("report.md", "report.docx",
                             title="My Report", classification="Protected A")
    pdf  = md2office.to_pdf("report.md", "report.pdf")
"""

from ._version import __version__
from .engine import DEFAULT_CLASSIFICATION, VERSION, to_docx, to_pdf

__all__ = [
    "VERSION",
    "__version__",
    "DEFAULT_CLASSIFICATION",
    "to_docx",
    "to_pdf",
]
