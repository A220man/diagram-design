#!/usr/bin/env python3
"""Verify RTL and Arabic typography, bidi rules, and layout contracts.

Ensures that diagrams containing Arabic text or RTL layout adhere to the
guidelines in style-guide.md:
1. Root direction: <html> has dir="rtl" or <svg> has direction="rtl".
2. Font stack: Arabic text uses an approved font family (Cairo, Noto Naskh Arabic).
3. Font size floor: Arabic text maintains at least 11px font size (no 7-8px mono slots).
4. Text anchor: Right-inset alignment in RTL uses text-anchor="start", not text-anchor="end".
5. Invariant viewBox: viewBox is not mirrored or inverted.
6. Mask height: Label masks for Arabic text are at least 16px tall.
7. Bidi isolation: Mixed Latin code identifiers are isolated in separate <text> elements.

Typography note: font-size and font-family on Arabic <text> elements are resolved
through the SVG inheritance chain (ancestor <g>/<svg> presentation attributes and
inline styles) and CSS custom properties (var(--font-sans)/var(--font-serif) read
against <style> definitions). A declaration that cannot be attributed to an element
is reported as unsupported rather than silently assumed clean.

Usage:
    python3 scripts/verify-rtl.py [--all] [files ...]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
APPROVED_ARABIC_FONTS = {"cairo", "noto naskh arabic", "segoe ui", "geeza pro", "amiri"}
LATIN_CODE_RE = re.compile(r"\b[A-Z][A-Z0-9_/-]{2,}\b")

VIEWBOX_RE = re.compile(r'\bviewBox="(?P<vx>[^"]+)"', re.IGNORECASE)
TEXT_TAG_RE = re.compile(
    r"<text\b(?P<attrs>[^>]*)>(?P<body>.*?)</text>",
    re.IGNORECASE | re.DOTALL,
)
RECT_RE = re.compile(
    r"<rect\b(?P<attrs>[^>]*?)\bheight=\"(?P<h>[\d.]+)\"[^>]*>",
    re.IGNORECASE,
)
SVG_ROOT_RE = re.compile(r"<svg\b[^>]*>", re.IGNORECASE)
HTML_ROOT_RE = re.compile(r"<html\b[^>]*>", re.IGNORECASE)
G_OPEN_RE = re.compile(r"<g\b[^>]*>", re.IGNORECASE)
G_CLOSE_RE = re.compile(r"</g\s*>", re.IGNORECASE)
STYLE_RE = re.compile(r"<style[^>]*>(?P<css>.*?)</style>", re.IGNORECASE | re.DOTALL)
CSS_VAR_DEF_RE = re.compile(r"--font-(sans|serif)\s*:\s*([^;]+);", re.IGNORECASE)
VAR_USE_RE = re.compile(r"var\(\s*--font-(sans|serif)\s*\)", re.IGNORECASE)


def root_direction_is_rtl(source: str) -> bool:
    """True when the document root (<html> or <svg>) declares RTL direction.

    Lets each text element derive its effective direction from the root rather
    than from a file-wide flag: a ``direction="ltr"`` override on one element
    must not inherit the root's RTL for the text-anchor check.
    """
    for regex in (HTML_ROOT_RE, SVG_ROOT_RE):
        match = regex.search(source)
        if match:
            opening = match.group(0).lower()
            if 'dir="rtl"' in opening or 'direction="rtl"' in opening:
                return True
    return False


def line_number(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def _font_size_from(attrs: str) -> float | None:
    """Pull a numeric font-size out of one element's attribute string
    (presentation attribute or inline style)."""
    match = re.search(r'\bfont-size="(?P<size>[\d.]+)"', attrs, re.IGNORECASE)
    if not match:
        match = re.search(r'font-size:\s*(?P<size>[\d.]+)(?:px)?', attrs, re.IGNORECASE)
    if match:
        try:
            return float(match.group("size"))
        except ValueError:
            return None
    return None


def _font_family_from(attrs: str) -> str | None:
    """Pull a font-family declaration out of one element's attribute string
    (presentation attribute or inline style)."""
    match = re.search(r'\bfont-family="(?P<ff>[^"]+)"', attrs, re.IGNORECASE)
    if not match:
        match = re.search(r'font-family:\s*([^;"]+)', attrs, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def _var_definitions(source: str) -> dict[str, str]:
    """Collect --font-sans/--font-serif definitions declared in <style> blocks."""
    definitions: dict[str, str] = {}
    for style in STYLE_RE.finditer(source):
        for name, value in CSS_VAR_DEF_RE.findall(style.group("css")):
            definitions[name.lower()] = value.strip().lower()
    return definitions


def _resolve_vars(value: str, var_defs: dict[str, str]) -> tuple[str, bool]:
    """Substitute var(--font-sans)/var(--font-serif) with their <style> values.

    Returns (resolved_value, unresolved) where unresolved is True when a var()
    reference has no <style> definition and could not be substituted.
    """
    unresolved = False

    def _substitute(match: re.Match) -> str:
        nonlocal unresolved
        name = match.group(1).lower()
        if name in var_defs:
            return var_defs[name]
        unresolved = True
        return match.group(0)

    return VAR_USE_RE.sub(_substitute, value), unresolved


def _text_ancestors(source: str) -> dict[int, list[str]]:
    """Map each <text> start offset to the attribute strings of its enclosing
    <svg> root and <g> ancestors, outermost first.

    Lets the typography checks inherit font-size/font-family declared on a
    parent <g>/<svg> (the SVG inheritance chain) instead of only the <text>'s
    own attributes. CSS class-rule declarations cannot be attributed to a
    specific <text> here and are reported as unsupported by the caller.
    """
    text_starts = [m.start() for m in TEXT_TAG_RE.finditer(source)]
    svg_match = SVG_ROOT_RE.search(source)
    svg_attrs = svg_match.group(0) if svg_match else ""
    events: list[tuple[int, int, str | None]] = []
    for match in G_OPEN_RE.finditer(source):
        events.append((match.start(), 0, match.group(0)))
    for match in G_CLOSE_RE.finditer(source):
        events.append((match.start(), 1, None))
    events.sort(key=lambda event: event[0])

    ancestors: dict[int, list[str]] = {}
    stack: list[str] = []
    index = 0
    for offset, kind, attrs in events:
        while index < len(text_starts) and text_starts[index] <= offset:
            ancestors[text_starts[index]] = ([svg_attrs] if svg_attrs else []) + list(stack)
            index += 1
        if kind == 0:
            stack.append(attrs)
        elif stack:
            stack.pop()
    while index < len(text_starts):
        ancestors[text_starts[index]] = ([svg_attrs] if svg_attrs else []) + list(stack)
        index += 1
    return ancestors


def check(path: Path) -> list[str]:
    """Check a single diagram file for RTL / Arabic contract compliance."""
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as err:
        return [f"{path}: read error: {err}"]

    has_arabic = bool(ARABIC_RE.search(source))
    is_rtl = 'dir="rtl"' in source or 'direction="rtl"' in source
    root_rtl = root_direction_is_rtl(source)

    if not has_arabic and not is_rtl:
        return []

    # Precompute font-style inheritance (<g>/<svg> ancestors) and CSS custom-
    # property definitions once per file so per-text typography checks can
    # resolve inherited and var() declarations instead of silently passing
    # (feedback PRRC_kwDOSEljpM78OM8E: "Unreadable labels pass checks").
    ancestors = _text_ancestors(source)
    var_defs = _var_definitions(source)

    findings: list[str] = []

    # 1. Root direction contract
    if has_arabic and not is_rtl:
        findings.append(
            f"{path}: Arabic text found but neither <html> nor <svg> specifies RTL direction "
            "(dir='rtl' or direction='rtl')"
        )

    # 2. Invariant viewBox contract
    for vb_match in VIEWBOX_RE.finditer(source):
        parts = vb_match.group("vx").strip().split()
        if len(parts) == 4:
            try:
                min_x, min_y, w, h = (float(v) for v in parts)
                if w < 0 or h < 0:
                    findings.append(
                        f"{path}: line {line_number(source, vb_match.start())}: SVG viewBox must "
                        "not use negative width/height; RTL flow is a coordinate layout decision"
                    )
            except ValueError:
                pass

    # 3. Text element checks (font-family, floor, text-anchor, bidi isolation)
    for match in TEXT_TAG_RE.finditer(source):
        attrs = match.group("attrs")
        body = match.group("body")
        offset = match.start()
        line = line_number(source, offset)

        has_arabic_text = bool(ARABIC_RE.search(body))

        # Check text-anchor="end" in RTL context.
        # Effective direction is per-element: direction="ltr" wins over the
        # file-wide flag; direction="rtl" confirms RTL; otherwise the
        # <svg>/<html> root direction is inherited. A file-level is_rtl flag
        # must not reject a Latin label whose own direction="ltr" override
        # makes text-anchor="end" correct for that element.
        attrs_lower = attrs.lower()
        if 'direction="ltr"' in attrs_lower:
            eff_rtl = False
        elif 'direction="rtl"' in attrs_lower:
            eff_rtl = True
        else:
            eff_rtl = root_rtl
        if eff_rtl and 'text-anchor="end"' in attrs_lower:
            findings.append(
                f"{path}: line {line}: RTL text uses text-anchor='end'; right-edge alignment "
                "in RTL requires text-anchor='start' (start anchors at logical right edge)"
            )

        if has_arabic_text:
            ancestor_attrs = ancestors.get(offset, [])

            # Font-size floor (11px). Resolve through the <text>'s own attribute
            # first, then inherit from the nearest ancestor <g>/<svg>. A value
            # that cannot be attributed to the element (e.g. a CSS class rule)
            # is reported as unsupported rather than silently assumed clean
            # (feedback PRRC_kwDOSEljpM78OM8E).
            size = _font_size_from(attrs)
            if size is None:
                for g_attrs in reversed(ancestor_attrs):
                    size = _font_size_from(g_attrs)
                    if size is not None:
                        break
            if size is not None:
                if size < 11.0:
                    findings.append(
                        f"{path}: line {line}: Arabic text font-size {size:g}px is below "
                        "the 11px rendering floor"
                    )
            else:
                findings.append(
                    f"{path}: line {line}: Arabic <text> font-size is not declared on the "
                    "element or an ancestor <g>/<svg>; cannot verify the 11px floor "
                    "(declare font-size explicitly)"
                )

            # Font-family stack. Resolve through the <text>'s own attribute,
            # inherit from the nearest ancestor <g>/<svg>, and resolve
            # var(--font-sans)/var(--font-serif) against <style> definitions.
            # The ordinary (non-RTL) template maps those variables to Latin-only
            # stacks, so a var() reference must be read rather than accepted on
            # sight (feedback PRRC_kwDOSEljpM78OM8E).
            declared_ff = _font_family_from(attrs)
            if declared_ff is None:
                for g_attrs in reversed(ancestor_attrs):
                    declared_ff = _font_family_from(g_attrs)
                    if declared_ff is not None:
                        break
            if declared_ff is None:
                findings.append(
                    f"{path}: line {line}: Arabic <text> lacks an explicit font-family and no "
                    "ancestor <g>/<svg> or var() provides one; cannot verify Arabic coverage "
                    "(declare an Arabic family: Cairo, Noto Naskh Arabic)"
                )
            else:
                resolved_ff, var_unresolved = _resolve_vars(declared_ff.lower(), var_defs)
                has_approved = any(approved in resolved_ff for approved in APPROVED_ARABIC_FONTS)
                if var_unresolved and not has_approved:
                    findings.append(
                        f"{path}: line {line}: Arabic <text> font-family references "
                        "var(--font-sans)/var(--font-serif) with no resolvable <style> "
                        "definition; cannot verify Arabic coverage (declare an explicit "
                        "Arabic family)"
                    )
                elif not has_approved:
                    findings.append(
                        f"{path}: line {line}: Arabic <text> lacks an approved Arabic font "
                        "family (Cairo, Noto Naskh Arabic) in its resolved font-family stack"
                    )

            # Check bidi isolation: inline Latin code token inside Arabic string
            latin_matches = LATIN_CODE_RE.findall(body)
            if latin_matches and len(body.strip()) > len(latin_matches[0]):
                # Latin code identifier embedded in an Arabic text node
                for code in latin_matches:
                    findings.append(
                        f"{path}: line {line}: mixed Latin code identifier {code!r} inline in "
                        "Arabic text; must be on its own <text> element in Geist Mono to prevent "
                        "bidi layout corruption"
                    )

    # 4. Mask height contract for Arabic label masks
    # Apply the height floor only to rects that are actual label masks for
    # Arabic text, not chart data marks (legend squares, color-ramp cells) that
    # happen to be small. A rect is a candidate label mask when it sits in the
    # vertical band of an Arabic <text> element. (Feedback
    # PRRC_kwDOSEljpM78OM7x: "Apply the height rule only to actual Arabic label
    # masks.")
    if has_arabic:
        # Collect vertical bands of Arabic text elements (baseline ± font size).
        arabic_text_bands: list[tuple[float, float]] = []
        for tmatch in TEXT_TAG_RE.finditer(source):
            tbody = tmatch.group("body")
            if not ARABIC_RE.search(tbody):
                continue
            tattrs = tmatch.group("attrs")
            ty_match = re.search(r'\by="([\d.]+)"', tattrs, re.IGNORECASE)
            tfs_match = re.search(r'\bfont-size="([\d.]+)"', tattrs, re.IGNORECASE)
            if ty_match:
                ty = float(ty_match.group(1))
                tfs = float(tfs_match.group(1)) if tfs_match else 14.0
                arabic_text_bands.append((ty - tfs, ty))

        for match in RECT_RE.finditer(source):
            height = float(match.group("h"))
            # Eyebrow / arrow label mask rects typically have height 8..15px in Latin diagrams
            if not (6.0 <= height < 16.0):
                continue
            element = match.group(0)
            ry_match = re.search(r'\by="([\d.]+)"', element, re.IGNORECASE)
            if ry_match:
                ry = float(ry_match.group(1))
                near_arabic = any(
                    ry <= band_y2 and ry + height >= band_y1
                    for band_y1, band_y2 in arabic_text_bands
                )
                if not near_arabic:
                    continue  # chart data mark, not an Arabic label mask
            line = line_number(source, match.start())
            findings.append(
                f"{path}: line {line}: label mask rect height {height:g}px is below the 16px "
                "requirement for 11px Arabic text"
            )

    return findings


def targets(args: argparse.Namespace) -> list[Path]:
    if args.all:
        return sorted(ASSET_DIR.glob("*.html"))
    return [Path(p) for p in args.files]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="HTML diagrams to check")
    parser.add_argument("--all", action="store_true", help="check all assets in assets/")
    args = parser.parse_args()

    paths = targets(args)
    if not paths:
        parser.error("pass one or more files, or --all")

    findings: list[str] = []
    checked = 0
    for path in paths:
        if not path.is_file():
            # An explicitly requested input file must exist. Silently skipping a
            # missing path hides typos behind a green check (feedback
            # PRRC_kwDOSEljpM78OM8g): report it and fail the run.
            findings.append(f"{path}: requested input file not found")
            continue
        checked += 1
        findings.extend(check(path))

    for finding in findings:
        print(finding)

    print(f"Summary: {checked} file(s) checked, {len(findings)} finding(s).")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())