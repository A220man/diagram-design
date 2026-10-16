#!/usr/bin/env python3
"""Adversarial and regression tests for verify-rtl.py."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts/verify-rtl.py"
TEMPLATE_RTL = ROOT / "skills/diagram-design/assets/template-rtl.html"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_rtl", VERIFIER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALID_RTL_SVG = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<body>
<svg viewBox="0 0 960 600" direction="rtl" role="img" aria-labelledby="t-title t-desc">
  <title id="t-title">عنوان المخطط</title>
  <desc id="t-desc">وصف المخطط باللغة العربية.</desc>
  <rect width="100%" height="100%" fill="#f5f5f5"/>
  <rect x="597" y="252" width="56" height="16" fill="#f5f5f5"/>
  <rect x="660" y="236" width="220" height="88" fill="#ffffff" stroke="#4f5d75"/>
  <text x="864" y="270" text-anchor="start" font-family="'Cairo', 'Noto Naskh Arabic', sans-serif" font-size="14">مكتب فني</text>
  <text x="864" y="294" text-anchor="start" font-family="'Geist Mono', monospace" font-size="11">LET_CG_012</text>
</svg>
</body>
</html>
"""


LATIN_LTR_OVERRIDE_SVG = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<body>
<svg viewBox="0 0 960 600" direction="rtl" role="img" aria-labelledby="t-title t-desc">
  <title id="t-title">عنوان المخطح</title>
  <desc id="t-desc">وصف المخطح باللغة العربية.</desc>
  <rect width="100%" height="100%" fill="#f5f5f5"/>
  <rect x="597" y="252" width="56" height="16" fill="#f5f5f5"/>
  <rect x="660" y="236" width="220" height="88" fill="#ffffff" stroke="#4f5d75"/>
  <text x="864" y="270" text-anchor="start" font-family="'Cairo', 'Noto Naskh Arabic', sans-serif" font-size="14">مكتب فني</text>
  <text x="864" y="294" text-anchor="start" font-family="'Geist Mono', monospace" font-size="11">LET_CG_012</text>
  <text x="864" y="318" direction="ltr" text-anchor="end" font-family="'Geist', sans-serif" font-size="12">English label</text>
</svg>
</body>
</html>
"""


CHART_MARK_SVG = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<body>
<svg viewBox="0 0 960 600" direction="rtl" role="img" aria-labelledby="t-title t-desc">
  <title id="t-title">مخطط عمودي</title>
  <desc id="t-desc">وصف المخطط العمودي.</desc>
  <rect width="100%" height="100%" fill="#f5f5f5"/>
  <!-- Legend square (10px) — a chart data mark, NOT an Arabic label mask -->
  <rect x="50" y="50" width="10" height="10" fill="#eb6c36"/>
  <!-- Color-ramp cell (12px) — also a chart data mark -->
  <rect x="70" y="70" width="12" height="12" fill="#7c8f6f"/>
  <!-- Arabic node label at y=570 -->
  <text x="864" y="570" text-anchor="start" font-family="'Cairo', 'Noto Naskh Arabic', 'Segoe UI', 'Geeza Pro', sans-serif" font-size="14">مكتب فني</text>
</svg>
</body>
</html>
"""

INHERITED_FONTS_SVG = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<body>
<svg viewBox="0 0 960 600" direction="rtl" role="img" aria-labelledby="t-title t-desc">
  <title id="t-title">عنوان المخطح</title>
  <desc id="t-desc">وصف المخطح باللغة العربية.</desc>
  <g font-family="'Geist', sans-serif" font-size="8">
    <text x="864" y="270" text-anchor="start">مكتب فني</text>
  </g>
</svg>
</body>
</html>
"""


VAR_LATIN_ONLY_SVG = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head><style>:root { --font-sans: 'Geist', sans-serif; }</style></head>
<body>
<svg viewBox="0 0 960 600" direction="rtl" role="img" aria-labelledby="t-title t-desc">
  <title id="t-title">عنوان المخطح</title>
  <desc id="t-desc">وصف المخطح باللغة العربية.</desc>
  <text x="864" y="270" text-anchor="start" font-family="var(--font-sans)" font-size="14">مكتب فني</text>
</svg>
</body>
</html>
"""


VAR_APPROVED_SVG = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head><style>:root { --font-sans: 'Cairo', 'Noto Naskh Arabic', sans-serif; }</style></head>
<body>
<svg viewBox="0 0 960 600" direction="rtl" role="img" aria-labelledby="t-title t-desc">
  <title id="t-title">عنوان المخطح</title>
  <desc id="t-desc">وصف المخطح باللغة العربية.</desc>
  <text x="864" y="270" text-anchor="start" font-family="var(--font-sans)" font-size="14">مكتب فني</text>
</svg>
</body>
</html>
"""


VAR_UNDEFINED_SVG = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<body>
<svg viewBox="0 0 960 600" direction="rtl" role="img" aria-labelledby="t-title t-desc">
  <title id="t-title">عنوان المخطح</title>
  <desc id="t-desc">وصف المخطح باللغة العربية.</desc>
  <text x="864" y="270" text-anchor="start" font-family="var(--font-sans)" font-size="14">مكتب فني</text>
</svg>
</body>
</html>
"""


def main() -> int:
    if not VERIFIER.is_file():
        print(f"FAIL: verifier script missing at {VERIFIER}")
        return 1
    module = load_verifier()
    failures: list[str] = []

    def check_finding(label: str, source: str, expect_substr: str) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            candidate = Path(scratch) / "candidate.html"
            candidate.write_text(source, encoding="utf-8")
            findings = module.check(candidate)
        if not any(expect_substr in f for f in findings):
            failures.append(
                f"{label}: expected finding containing {expect_substr!r}, got {findings}"
            )
        else:
            print(f"OK: {label}")

    def check_clean(label: str, source: str) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            candidate = Path(scratch) / "candidate.html"
            candidate.write_text(source, encoding="utf-8")
            findings = module.check(candidate)
        if findings:
            failures.append(f"{label}: expected no findings, got {findings}")
        else:
            print(f"OK: {label}")

    # 1. Shipped template-rtl.html must pass cleanly
    if not TEMPLATE_RTL.is_file():
        failures.append("template-rtl.html is missing")
    else:
        template_findings = module.check(TEMPLATE_RTL)
        if template_findings:
            failures.append(f"template-rtl.html failed verify-rtl: {template_findings}")
        else:
            print("OK: shipped template-rtl.html passes verify-rtl")

    # 2. Valid RTL SVG fixture passes
    check_clean("valid-rtl-fixture", VALID_RTL_SVG)

    # 3. Missing dir="rtl" / direction="rtl" caught
    check_finding(
        "missing-rtl-direction",
        VALID_RTL_SVG.replace('dir="rtl"', "").replace('direction="rtl"', ""),
        "specifies RTL direction",
    )

    # 4. Arabic font size below 11px floor caught
    check_finding(
        "arabic-below-11px-floor",
        VALID_RTL_SVG.replace('font-size="14">مكتب فني', 'font-size="8">مكتب فني'),
        "below the 11px rendering floor",
    )

    # 5. Arabic text lacking approved font family caught
    check_finding(
        "arabic-missing-font-family",
        VALID_RTL_SVG.replace(
            "font-family=\"'Cairo', 'Noto Naskh Arabic', sans-serif\"",
            "font-family=\"'Geist', sans-serif\"",
        ),
        "lacks an approved Arabic font family",
    )

    # 6. text-anchor="end" in RTL context caught
    check_finding(
        "rtl-text-anchor-end-rejected",
        VALID_RTL_SVG.replace('text-anchor="start"', 'text-anchor="end"', 1),
        "right-edge alignment in RTL requires text-anchor='start'",
    )

    # 7. Inverted viewBox caught
    check_finding(
        "inverted-viewbox-rejected",
        VALID_RTL_SVG.replace('viewBox="0 0 960 600"', 'viewBox="0 0 -960 600"'),
        "SVG viewBox must not use negative width/height",
    )

    # 8. Undersized label mask (< 16px) for Arabic label caught
    check_finding(
        "undersized-arabic-mask-rejected",
        VALID_RTL_SVG.replace('height="16"', 'height="12"'),
        "below the 16px requirement",
    )

    # 9. Mixed Latin code identifier inline inside Arabic text caught
    check_finding(
        "mixed-inline-latin-code-rejected",
        VALID_RTL_SVG.replace("مكتب فني", "مكتب LET_CG_012 فني"),
        "mixed Latin code identifier 'LET_CG_012' inline in Arabic text",
    )

    # 11. A Latin label with an explicit direction="ltr" override must NOT be
    # flagged for text-anchor="end" even when the document root is RTL. The
    # verifier checks each element's effective direction, not a file-wide flag.
    # (Feedback PRRC_kwDOSEljpM78OM7l "Valid Latin labels fail": is_rtl
    # searched the whole file and rejected end-aligned Latin labels whose own
    # direction="ltr" made text-anchor="end" correct.)
    check_clean("latin-ltr-in-rtl-document", LATIN_LTR_OVERRIDE_SVG)

    # 12. Without the direction="ltr" override the Latin label inherits the
    # root's RTL direction and is still correctly flagged for text-anchor="end".
    check_finding(
        "latin-no-override-in-rtl-still-flagged",
        LATIN_LTR_OVERRIDE_SVG.replace('direction="ltr"', ""),
        "RTL text uses text-anchor='end'",
    )

    # 13. Chart data marks (legend squares, color-ramp cells) with heights in
    # the 6–15px range must NOT be flagged as Arabic label mask violations,
    # even though Arabic text appears elsewhere in the file at a different
    # vertical position. The height rule applies only to rects that actually
    # mask an Arabic <text> element, not to chart marks.
    # (Feedback PRRC_kwDOSEljpM78OM7x "Chart marks fail mask checks": the mask
    # check rejected every rectangle from 6px to less than 16px tall
    # whenever Arabic appeared anywhere in the file.)
    check_clean("chart-marks-not-arabic-masks", CHART_MARK_SVG)
    # Typography checks must NOT silently pass when font-size/font-family are
    # inherited from a parent <g> or a CSS custom property. (Feedback
    # PRRC_kwDOSEljpM78OM8E "Unreadable labels pass checks": checks passed when
    # font-size or font-family came from a parent or CSS rule, and accepted
    # var(--font-sans)/var(--font-serif) without reading their definitions.)
    check_finding(
        "inherited-font-size-from-parent-g-caught",
        INHERITED_FONTS_SVG,
        "below the 11px rendering floor",
    )
    check_finding(
        "inherited-font-family-from-parent-g-caught",
        INHERITED_FONTS_SVG,
        "lacks an approved Arabic font family",
    )
    check_finding(
        "var-latin-only-stack-caught",
        VAR_LATIN_ONLY_SVG,
        "lacks an approved Arabic font family",
    )
    check_clean(
        "var-resolves-to-approved-stack",
        VAR_APPROVED_SVG,
    )
    check_finding(
        "var-without-definition-caught",
        VAR_UNDEFINED_SVG,
        "no resolvable <style> definition",
    )

    # 14. An explicitly requested input file that does not exist must be
    # reported and the run must exit nonzero, not silently skipped behind a
    # green "0 files checked" summary. (Feedback PRRC_kwDOSEljpM78OM8g:
    # "Missing files report success".)
    old_argv = sys.argv
    sys.argv = [str(VERIFIER), "does-not-exist-98765.html"]
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            exit_code = module.main()
    finally:
        sys.argv = old_argv
    out = captured.getvalue()
    if exit_code == 0:
        failures.append(
            "missing-input-exit-code: verify-rtl.py exited 0 on a nonexistent "
            "input file (expected nonzero)"
        )
    elif "requested input file not found" not in out:
        failures.append(
            "missing-input-not-reported: expected a missing-file finding; "
            f"summary was: {out.strip()!r}"
        )
    else:
        print("OK: missing input file is reported and exits nonzero")

    # 10. Browser layout oracle & wide-preset export checks (requires Playwright)
    try:
        from playwright.sync_api import sync_playwright
        lint_render_path = ROOT / "scripts/lint-render.py"
        spec = importlib.util.spec_from_file_location("lint_render", lint_render_path)
        assert spec is not None and spec.loader is not None
        lint_render = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lint_render)

        with sync_playwright() as playwright:
            browser = lint_render.launch(playwright, False)
            ctx = browser.new_context()
            try:
                # 10a. Shipped template-rtl.html must pass wide-preset export without clipping
                export_errs = lint_render.template_export_failures(ctx, [TEMPLATE_RTL])
                if export_errs:
                    failures.append(f"template-rtl.html wide-preset export failed: {export_errs}")
                else:
                    print("OK: shipped template-rtl.html passes wide-preset export check")

                # 10b. Adversarial: RTL template with body { direction: rtl; } overflows leftward and clips right probe
                broken_template = TEMPLATE_RTL.read_text(encoding="utf-8").replace("direction: ltr;", "direction: rtl;")
                with tempfile.TemporaryDirectory() as scratch:
                    broken_path = Path(scratch) / "template-broken-rtl.html"
                    broken_path.write_text(broken_template, encoding="utf-8")
                    adv_errs = lint_render.template_export_failures(ctx, [broken_path])
                    if not any("missing from the PNG" in err for err in adv_errs):
                        failures.append(f"adversarial RTL clipping fixture was not caught: {adv_errs}")
                    else:
                        print("OK: adversarial leftward-overflow RTL template correctly caught by wide-preset export")

                # 10c. Physical text anchoring in browser: text-anchor="start" stays within right edge, "end" spills outside
                page = ctx.new_page()
                try:
                    page.set_content(
                        '<style>* { margin: 0; padding: 0; }</style>'
                        '<svg width="600" height="300" direction="rtl" xmlns="http://www.w3.org/2000/svg">'
                        '  <rect x="50" y="50" width="250" height="100" fill="white"/>'
                        '  <text id="t-start" x="300" y="100" text-anchor="start" font-size="14">مكتب فني</text>'
                        '  <text id="t-end" x="300" y="100" text-anchor="end" font-size="14">مكتب فني</text>'
                        '</svg>'
                    )
                    bb_start = page.locator("#t-start").bounding_box()
                    bb_end = page.locator("#t-end").bounding_box()
                    if bb_start is None or bb_end is None:
                        failures.append("failed to measure bounding box of rendered SVG text elements")
                    else:
                        right_start = bb_start["x"] + bb_start["width"]
                        right_end = bb_end["x"] + bb_end["width"]
                        if abs(right_start - 300) > 1.5:
                            failures.append(f"text-anchor='start' did not anchor at right edge (expected ~300, got {right_start})")
                        elif right_end <= 340:
                            failures.append(f"text-anchor='end' did not spill past right edge (expected >340, got {right_end})")
                        else:
                            print("OK: browser measurement confirms text-anchor='start' stays within right edge while 'end' spills outside")
                finally:
                    page.close()
            finally:
                browser.close()
    except ImportError:
        print("SKIP: playwright is not installed; browser RTL render tests skipped")

    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1

    print("All RTL verifier tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
