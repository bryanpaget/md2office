"""Command-line interface for md2office."""

from __future__ import annotations

import argparse
import sys

from ._version import __version__
from .engine import DEFAULT_CLASSIFICATION, ConvertOptions, doctor, to_docx, to_pdf


def _add_shared_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--title", help="Document title (defaults to YAML frontmatter)")
    parser.add_argument("--classification", default=DEFAULT_CLASSIFICATION,
                        help=f"Sensitivity label in the header "
                             f"(default: {DEFAULT_CLASSIFICATION})")
    parser.add_argument("--author", default="",
                        help="Author, used for page-break sections")
    parser.add_argument("--version", default="",
                        help="Document version, used for page-break sections")
    parser.add_argument("--effective-date", default="",
                        help="Effective date, used for page-break sections")
    parser.add_argument("--number-sections", action="store_true",
                        help="Pass --number-sections to pandoc")
    parser.add_argument("--no-code-style", action="store_true",
                        help="Skip monospace/shading on code blocks")
    parser.add_argument("--page-breaks", choices=["none", "sections"],
                        default="none",
                        help="Insert page breaks (default: none)")
    parser.add_argument("--font", choices=["default", "arial"],
                        default="default",
                        help="Document font (default: template fonts)")
    parser.add_argument("--mermaid", choices=["auto", "true", "false"],
                        default="auto",
                        help="Render mermaid fenced blocks (default: auto)")
    parser.add_argument("-r", "--resource-path", action="append", default=[],
                        help="Extra pandoc resource path (repeatable)")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="Suppress the result message")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="md2office",
        description="Convert Markdown to a polished DOCX/PDF via pandoc + LibreOffice.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_conv = sub.add_parser("convert", help="Convert Markdown to DOCX or PDF")
    p_conv.add_argument("markdown", help="Input Markdown file")
    p_conv.add_argument("output", help="Output file (.docx or .pdf)")
    p_conv.add_argument("--keep-docx", action="store_true",
                        help="Keep the intermediate DOCX when producing PDF")
    _add_shared_options(p_conv)

    p_conv = sub.add_parser("docx", help="Convert Markdown to DOCX")
    p_conv.add_argument("markdown", help="Input Markdown file")
    p_conv.add_argument("output", help="Output .docx file")
    _add_shared_options(p_conv)

    p_conv = sub.add_parser("pdf", help="Convert Markdown to PDF")
    p_conv.add_argument("markdown", help="Input Markdown file")
    p_conv.add_argument("output", help="Output .pdf file")
    p_conv.add_argument("--keep-docx", action="store_true",
                        help="Keep the intermediate DOCX")
    _add_shared_options(p_conv)

    sub.add_parser("doctor", help="Check prerequisites (pandoc, soffice, fonts)")
    return parser


def _opts_from_args(args) -> ConvertOptions:
    return ConvertOptions(
        title=args.title or "",
        classification=args.classification,
        author=args.author or "",
        version=args.version or "",
        effective_date=args.effective_date or "",
        number_sections=args.number_sections,
        code_style=not args.no_code_style,
        page_breaks=args.page_breaks,
        font=args.font,
        mermaid=args.mermaid,
        resource_path=args.resource_path or [],
        keep_docx=getattr(args, "keep_docx", False),
    )


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return doctor()

    opts = _opts_from_args(args)
    try:
        if args.command == "pdf" or (
            args.command == "convert" and args.output.lower().endswith(".pdf")
        ):
            out = to_pdf(args.markdown, args.output, options=opts)
        else:
            out = to_docx(args.markdown, args.output, options=opts)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
