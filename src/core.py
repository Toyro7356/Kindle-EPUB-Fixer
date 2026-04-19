"""
Kindle EPUB Fixer - Core Engine

Conservative EPUB repair focused on preserving the author's intended layout.
"""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Union

from .book_profile import BookProfile, detect_book_profile
from .book_type import detect_book_type
from .comic_fix import sanitize_comic_for_kindle
from .content_analysis import ContentAnalysis, analyze_content
from .css_sanitize import downgrade_risky_css_for_kindle
from .epub_io import find_opf, repack_epub, unpack_epub
from .epub_validator import validate_epub
from .font_handler import FontScanResult, ImportedFontSpec, handle_fonts
from .footnote_fix import fix_footnotes_for_kindle
from .html_fix import clean_html_meta, fix_cover_image_references, fix_html_structure, fix_self_closing_tags
from .image_fix import convert_webp_images, update_html_css_webp_refs, update_opf_webp_refs
from .language_fix import fix_language_tags
from .ncx_fix import fix_ncx_parent_navpoints
from .opf_sanitize import fix_spine_direction_for_novel, sanitize_opf_for_kindle
from .script_remove import remove_known_helper_scripts, remove_scripts_from_book
from .svg_fix import convert_svg_pages_to_img, remove_stale_svg_properties
from .utils import LogCallback, _default_log
from .vertical_fix import fix_vertical_writing_mode


@dataclass(frozen=True)
class ProcessingPlan:
    book_type: str
    preserve_layout: bool
    has_kobo_markers: bool
    run_novel_compat_repairs: bool
    run_reflow_repairs: bool
    run_source_specific_cleanup: bool


def resolve_output_path(epub_path: str, output_path: Optional[str] = None) -> str:
    if output_path:
        candidate = Path(output_path)
        if candidate.exists() and candidate.is_dir():
            return str((candidate / Path(epub_path).name).resolve())
        return str(candidate.resolve())

    input_path = Path(epub_path).resolve()
    output_dir = input_path.parent / "转换后"
    output_dir.mkdir(exist_ok=True)
    return str((output_dir / input_path.name).resolve())


def _apply_safe_repairs(
    opf_path: str,
    book_type: str,
    preserve_layout: bool,
    log: LogCallback,
) -> None:
    mapping = convert_webp_images(opf_path)
    if mapping:
        log(f"Converted {len(mapping)} WebP images")
        update_opf_webp_refs(opf_path, mapping)
        update_html_css_webp_refs(opf_path, mapping)

    helper_cleanup = remove_known_helper_scripts(opf_path)
    if helper_cleanup:
        log(f"Removed {helper_cleanup} known helper script artifacts")

    fixed_count = fix_html_structure(opf_path)
    if fixed_count:
        log(f"Fixed HTML structure in {fixed_count} documents")

    sc_fixed = fix_self_closing_tags(opf_path)
    if sc_fixed:
        log(f"Fixed self-closing tags in {sc_fixed} documents")

    clean_html_meta(opf_path)

    # Kindle chooses its CJK/Latin font set from language metadata.
    # Keep this repair in the always-safe stage so preserve-layout books
    # do not accidentally stay on the wrong font family bucket.
    if fix_language_tags(opf_path):
        log("Updated language metadata from book content")

    cover_fixed = fix_cover_image_references(opf_path)
    if cover_fixed:
        log(f"Fixed broken cover image references in {cover_fixed} documents")

    ncx_fixed = fix_ncx_parent_navpoints(opf_path)
    if ncx_fixed:
        log(f"Fixed {ncx_fixed} NCX parent navPoints for Kindle navigation")

    if book_type == "comic":
        if preserve_layout:
            log("Detected comic-like layout; applying conservative Kindle comic enrichment")
        comic_fixed = sanitize_comic_for_kindle(opf_path, preserve_layout=preserve_layout)
        if comic_fixed:
            log(f"Applied {comic_fixed} comic compatibility adjustments")

    sanitize_opf_for_kindle(opf_path, book_type, preserve_layout=preserve_layout)
    log("Sanitized OPF metadata conservatively")


def _apply_reflow_repairs(
    temp_dir: str,
    opf_path: str,
    profile_preserve_layout: bool,
    log: LogCallback,
) -> None:
    if profile_preserve_layout:
        return

    css_sanitized = downgrade_risky_css_for_kindle(opf_path)
    if css_sanitized:
        log(f"Downgraded risky CSS transforms in {css_sanitized} documents")

    svg_converted = convert_svg_pages_to_img(opf_path)
    if svg_converted:
        log(f"Converted {svg_converted} simple SVG wrapper pages to img")

    ff_fixed = fix_footnotes_for_kindle(opf_path)
    if ff_fixed:
        log(f"Normalized footnotes in {ff_fixed} documents")

    stale_removed = remove_stale_svg_properties(opf_path)
    if stale_removed:
        log(f"Removed {stale_removed} stale svg manifest properties")


def _apply_novel_compat_repairs(opf_path: str, book_type: str, log: LogCallback) -> None:
    if book_type != "novel":
        return

    # These two downgrades are safe compatibility fixes for non-Japanese novels
    # and should still run even when the broader preserve-layout path is chosen.
    if fix_spine_direction_for_novel(opf_path):
        log("Adjusted non-Japanese spine progression from rtl to ltr")

    wm_fixed = fix_vertical_writing_mode(opf_path)
    if wm_fixed:
        log(f"Downgraded vertical writing in {wm_fixed} locations")


def _apply_font_repairs(
    temp_dir: str,
    preserve_layout: bool,
    log: LogCallback,
    imported_fonts: Optional[Dict[str, Union[str, ImportedFontSpec]]],
    font_scan: Optional[FontScanResult],
) -> None:
    handle_fonts(
        temp_dir,
        log,
        imported_fonts,
        font_scan=font_scan,
        sanitize_missing=(not preserve_layout),
    )


def _apply_source_specific_cleanup(
    opf_path: str,
    has_kobo_markers: bool,
    preserve_layout: bool,
    log: LogCallback,
) -> None:
    if not has_kobo_markers or preserve_layout:
        return

    script_removed = remove_scripts_from_book(opf_path)
    if script_removed:
        log(f"Removed script markup from {script_removed} documents")


def _build_processing_plan(book_type: str, profile: BookProfile) -> ProcessingPlan:
    return ProcessingPlan(
        book_type=book_type,
        preserve_layout=profile.preserve_layout,
        has_kobo_markers=profile.has_kobo_adobe_markers,
        run_novel_compat_repairs=(book_type == "novel"),
        run_reflow_repairs=(not profile.preserve_layout),
        run_source_specific_cleanup=(profile.has_kobo_adobe_markers and not profile.preserve_layout),
    )


def process_files(
    temp_dir: str,
    log: LogCallback = _default_log,
    imported_fonts: Optional[Dict[str, Union[str, ImportedFontSpec]]] = None,
    profile: Optional[BookProfile] = None,
    font_scan: Optional[FontScanResult] = None,
    content_analysis: Optional[ContentAnalysis] = None,
) -> str:
    try:
        opf_path = find_opf(temp_dir)
    except FileNotFoundError as exc:
        log(f"[Warning] Unable to locate OPF: {exc}")
        return "unknown"

    content = content_analysis or analyze_content(opf_path)
    book_type = detect_book_type(opf_path, content)
    profile = profile or detect_book_profile(opf_path, content)
    plan = _build_processing_plan(book_type, profile)

    log(f"Detected book type: {plan.book_type}")
    log(f"Detected layout mode: {profile.layout_mode}")
    if plan.preserve_layout:
        log("Layout-sensitive structure detected; using preserve-layout repair mode")
    if plan.has_kobo_markers:
        log("Adobe Adept / Kobo markers detected")

    _apply_safe_repairs(opf_path, plan.book_type, plan.preserve_layout, log)
    if plan.run_novel_compat_repairs:
        _apply_novel_compat_repairs(opf_path, plan.book_type, log)
    _apply_font_repairs(
        temp_dir,
        plan.preserve_layout,
        log,
        imported_fonts,
        font_scan,
    )
    if plan.run_reflow_repairs:
        _apply_reflow_repairs(
            temp_dir,
            opf_path,
            plan.preserve_layout,
            log,
        )
    if plan.run_source_specific_cleanup:
        _apply_source_specific_cleanup(
            opf_path,
            plan.has_kobo_markers,
            plan.preserve_layout,
            log,
        )

    return plan.book_type


def process_epub(
    epub_path: str,
    output_path: Optional[str] = None,
    log: LogCallback = _default_log,
    imported_fonts: Optional[Dict[str, Union[str, ImportedFontSpec]]] = None,
) -> str:
    epub_path = os.path.abspath(epub_path)
    resolved_output_path = resolve_output_path(epub_path, output_path)

    with tempfile.TemporaryDirectory() as temp_dir:
        unpack_epub(epub_path, temp_dir)
        book_type = process_files(temp_dir, log, imported_fonts)
        repack_epub(temp_dir, resolved_output_path)

    try:
        issues = validate_epub(resolved_output_path, book_type)
        if issues:
            log("[Validation Warning] Output EPUB has issues:")
            for issue in issues:
                log(f"  - {issue}")
        else:
            log("Output EPUB validation passed")
    except Exception as exc:
        log(f"[Validation Error] Validation raised an exception: {exc}")

    return resolved_output_path
