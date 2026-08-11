"""High-level Markdown -> DOCX -> PDF conversion engine.

Wraps pandoc (Markdown -> DOCX with a user-supplied reference template and the
bundled Lua filters) and LibreOffice (DOCX -> PDF), then post-processes the
DOCX so the output is publication-ready: title + classification in the
headers, wide autofit tables, monospace shaded code blocks, and a static
table of contents.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from . import postprocess
from ._version import __version__

VERSION = __version__
DEFAULT_CLASSIFICATION = "Unclassified | Non classifié"

ASSETS = Path(__file__).parent / "assets"
FILTER_PAGEBREAK = ASSETS / "pagebreak.lua"
FILTER_TOC = ASSETS / "toc.lua"
FILTER_MERMAID = ASSETS / "mermaid.lua"

_MERMAID_RE = re.compile(r"^```\s*mermaid", re.MULTILINE)


@dataclass
class ConvertOptions:
    """Options shared by the DOCX and PDF conversions."""

    title: str = ""
    classification: str = DEFAULT_CLASSIFICATION
    template: Optional[str] = None
    author: str = ""
    version: str = ""
    effective_date: str = ""
    number_sections: bool = False
    code_style: bool = True
    page_breaks: str = "none"  # "none" | "sections"
    font: str = "default"  # "default" | "arial"
    mermaid: str = "auto"  # "auto" | "true" | "false"
    resource_path: List[str] = field(default_factory=list)
    keep_docx: bool = False


def _check_binary(name: str) -> Optional[str]:
    return shutil.which(name)


def _bin(name: str) -> str:
    path = _check_binary(name)
    if not path:
        raise RuntimeError(
            f"Required executable '{name}' not found on PATH. "
            "Install pandoc (for Markdown->DOCX) or LibreOffice (for DOCX->PDF)."
        )
    return path


def _mermaid_needed(markdown: Path, mode: str) -> bool:
    if mode == "true":
        return True
    if mode == "false":
        return False
    try:
        return bool(_MERMAID_RE.search(markdown.read_text(encoding="utf-8")))
    except OSError:
        return False


def _frontmatter_title(markdown: Path) -> str:
    """Return the YAML frontmatter title, or '' when absent."""
    try:
        text = markdown.read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return ""
    tm = re.search(r"^title:\s*(.+?)\s*$", m.group(1), re.M)
    if not tm:
        return ""
    return tm.group(1).strip().strip("\"'")


def _resolve_title(markdown: Path, options: ConvertOptions) -> str:
    if options.title:
        return options.title
    title = _frontmatter_title(markdown)
    if title:
        return title
    return markdown.stem.replace("_", " ").replace("-", " ").title()


def _resolve_template(options: ConvertOptions) -> Optional[Path]:
    """Return the user-supplied reference template path, or None to use
    pandoc's built-in default reference document."""
    if not options.template:
        return None
    path = Path(options.template)
    if not path.exists():
        raise FileNotFoundError(f"Reference template not found: {path}")
    return path


def _pandoc_command(
    markdown: Path,
    docx: Path,
    options: ConvertOptions,
) -> List[str]:
    cmd = [_bin("pandoc"), str(markdown)]

    for path in (FILTER_PAGEBREAK, FILTER_TOC):
        cmd.extend(["--lua-filter", str(path)])
    if _mermaid_needed(markdown, options.mermaid):
        cmd.extend(["--lua-filter", str(FILTER_MERMAID)])

    if options.number_sections:
        cmd.append("--number-sections")

    resource = [str(markdown.parent)]
    resource.extend(str(p) for p in options.resource_path)
    cmd.extend(["--resource-path=" + os.pathsep.join(resource)])

    cmd.extend(
        [
            "--metadata=title=" + _resolve_title(markdown, options),
            "-o",
            str(docx),
        ]
    )
    template = _resolve_template(options)
    if template is not None:
        cmd.extend(["--reference-doc", str(template)])
    return cmd


def to_docx(
    markdown: str | os.PathLike,
    output: str | os.PathLike,
    *,
    options: Optional[ConvertOptions] = None,
) -> str:
    """Convert a Markdown file to a formatted DOCX.

    Pass a reference Word template via ``options.template`` for the full
    styling (cover page, header classification, heading/table styles).
    Without one, pandoc falls back to its built-in default reference
    document — still a clean, standard Word look.

    Returns the path to the generated .docx.
    """
    md = Path(markdown)
    out = Path(output)
    opts = options or ConvertOptions()

    if not md.exists():
        raise FileNotFoundError(f"Markdown file not found: {md}")

    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = _pandoc_command(md, out, opts)
    subprocess.run(cmd, check=True)

    title = _resolve_title(md, opts)
    postprocess.apply(
        out,
        title=title,
        classification=opts.classification,
        author=opts.author,
        version=opts.version,
        effective_date=opts.effective_date,
        code_style=opts.code_style,
        page_breaks=opts.page_breaks,
        font=opts.font,
    )
    return str(out)


def to_pdf(
    markdown: str | os.PathLike,
    output: str | os.PathLike,
    *,
    options: Optional[ConvertOptions] = None,
    keep_docx: bool | None = None,
) -> str:
    """Convert a Markdown file to a PDF via DOCX + LibreOffice.

    The intermediate DOCX is written to a sibling of ``output`` and removed
    unless ``keep_docx`` (or ``options.keep_docx``) is true.

    Returns the path to the generated .pdf.
    """
    md = Path(markdown)
    out = Path(output)
    opts = options or ConvertOptions()

    keep = opts.keep_docx if keep_docx is None else keep_docx

    docx = out.with_suffix(".docx")
    to_docx(md, docx, options=opts)
    try:
        docx_to_pdf(docx, out)
    finally:
        if not keep and docx.exists():
            docx.unlink()
    return str(out)


def docx_to_pdf(docx: str | os.PathLike, output: str | os.PathLike) -> str:
    """Convert an existing DOCX to PDF using headless LibreOffice.

    Uses a fresh per-run LibreOffice profile (a ``-env:UserInstallation`` temp
    dir) to avoid lock contention between concurrent conversions.
    """
    src = Path(docx)
    dest = Path(output)
    if not src.exists():
        raise FileNotFoundError(f"DOCX file not found: {src}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    soffice = _bin("soffice")

    outdir = dest.parent.resolve()
    base = dest.stem

    # LibreOffice writes "<basename>.pdf" into --outdir. If our destination
    # basename differs from the source's, copy the source so it matches.
    src_name = src.name
    src_base = src.stem
    work_dir: Optional[Path] = None
    to_convert = src
    if src_base != base:
        work_dir = Path(tempfile.mkdtemp(prefix="md2office-"))
        to_convert = work_dir / f"{base}{src.suffix}"
        shutil.copy2(src, to_convert)

    profile = Path(tempfile.mkdtemp(prefix="md2office-loffice-"))
    try:
        subprocess.run(
            [
                soffice,
                "--headless",
                "--nofirststartwizard",
                "--norestore",
                "--invisible",
                f"-env:UserInstallation=file://{profile}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(outdir),
                str(to_convert),
            ],
            check=True,
        )
    finally:
        shutil.rmtree(profile, ignore_errors=True)
        if work_dir is not None:
            shutil.rmtree(work_dir, ignore_errors=True)

    generated = outdir / f"{base}.pdf"
    if not generated.exists():
        raise RuntimeError(f"LibreOffice did not produce {generated}")
    if generated.resolve() != dest.resolve():
        shutil.move(str(generated), str(dest))
    return str(dest)


def doctor() -> int:
    """Check prerequisites and print a status report. Returns exit code."""
    problems = 0

    def check(name: str, present: bool, hint: str = "") -> None:
        nonlocal problems
        status = "OK" if present else "MISSING"
        print(f"[{status:7}] {name}")
        if not present:
            problems += 1
            if hint:
                print(f"          {hint}")

    check("python-docx", _check_binary("python3") is not None
          and _importable("docx"), "pip install python-docx")
    check("pandoc", _check_binary("pandoc") is not None,
          "sudo apt install pandoc  (or use the vendored release)")
    check("soffice (LibreOffice)", _check_binary("soffice") is not None,
          "sudo apt install libreoffice-writer")
    check("mermaid CLI (optional)", _check_binary("mmdc") is not None,
          "npm install -g @mermaid-js/mermaid-cli  (only needed for mermaid blocks)")

    fc = _font_list()
    for font, hint in (
        ("Carlito", "sudo apt install fonts-crosextra-carlito"),
        ("Noto Color Emoji", "sudo apt install fonts-noto-color-emoji"),
        ("Noto Sans Symbols2", "sudo apt install fonts-noto-core"),
    ):
        check(f"font: {font}", font in fc, hint)

    return 1 if problems else 0


def _importable(module: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(module) is not None


def _font_list() -> str:
    if not _check_binary("fc-list"):
        return ""
    try:
        return subprocess.run(
            ["fc-list"], capture_output=True, text=True, check=True
        ).stdout
    except (subprocess.CalledProcessError, OSError):
        return ""
