"""
Kindle EPUB Fixer — Core Engine

智能修复 EPUB 文件以提升 Amazon Kindle / Send to Kindle 兼容性。
支持漫画(comic)与小说(novel)的自动识别与差异化处理。
"""

import os
import tempfile
from typing import Dict, Optional

from .book_type import detect_book_type
from .epub_io import find_opf, repack_epub, unpack_epub
from .font_handler import handle_fonts, scan_fonts
from .footnote_fix import fix_footnotes_for_kindle
from .css_sanitize import sanitize_css_for_kindle
from .html_fix import clean_html_meta, fix_duplicate_ids, fix_html_structure, fix_self_closing_tags
from .image_fix import clean_invalid_image_refs, convert_webp_images, update_html_css_webp_refs, update_opf_webp_refs
from .language_fix import fix_language_tags
from .opf_sanitize import fix_spine_direction_for_novel, inject_dcterms_modified, sanitize_opf_for_kindle
from .comic_fix import sanitize_comic_for_kindle
from .epub_validator import validate_epub
from .script_remove import remove_scripts_from_book
from .svg_fix import convert_svg_pages_to_img, remove_stale_svg_properties
from .utils import LogCallback, _default_log
from .vertical_fix import fix_vertical_writing_mode


def process_files(
    temp_dir: str,
    log: LogCallback = _default_log,
    imported_fonts: Optional[Dict[str, str]] = None,
) -> str:
    """对解压后的 EPUB 临时目录执行全套修复，返回检测到的书籍类型。"""
    try:
        opf_path = find_opf(temp_dir)
    except FileNotFoundError as e:
        log(f"[Warning] 无法定位 OPF: {e}")
        return "unknown"

    book_type = detect_book_type(opf_path)
    log(f"检测到书籍类型: {book_type}")

    if fix_language_tags(opf_path):
        log("已根据正文内容修正语言标签")

    handle_fonts(temp_dir, log, imported_fonts)

    invalid_img_fixed = clean_invalid_image_refs(opf_path)
    if invalid_img_fixed:
        log(f"已修复 {invalid_img_fixed} 个 HTML 文件中的无效图片引用")

    mapping = convert_webp_images(opf_path)
    if mapping:
        log(f"转换了 {len(mapping)} 张 webp 图片")
        update_opf_webp_refs(opf_path, mapping)
        update_html_css_webp_refs(opf_path, mapping)

    # 对小说和漫画都执行 SVG 图片页面转换，以提升 Kindle 兼容性
    svg_converted = convert_svg_pages_to_img(opf_path)
    if svg_converted:
        log(f"转换了 {svg_converted} 个 SVG 图片页面为 <img>")

    if book_type == "comic":
        comic_fixed = sanitize_comic_for_kindle(opf_path)
        if comic_fixed:
            log(f"已应用 {comic_fixed} 项漫画 Kindle 兼容性修复")

    # 所有书籍类型都移除脚本（Kobo 脚本对 Kindle 无意义且可能触发崩溃）
    script_removed = remove_scripts_from_book(opf_path)
    if script_removed:
        log(f"已移除 {script_removed} 个页面中的脚本")

    if book_type == "novel":
        if fix_spine_direction_for_novel(opf_path):
            log("已将非日文小说的 page-progression-direction 从 rtl 修正为 ltr")

    # 修复竖排（Kindle 对非日文不支持 vertical-rl）
    wm_fixed = fix_vertical_writing_mode(opf_path)
    if wm_fixed:
        log(f"已修复 {wm_fixed} 处竖排设置为横排")

    clean_html_meta(opf_path)

    ff_fixed = fix_footnotes_for_kindle(opf_path)
    if ff_fixed:
        log(f"修复了 {ff_fixed} 个文件的脚注结构以支持 Kindle Pop-up")

    fixed_count = fix_html_structure(opf_path)
    if fixed_count:
        log(f"已修复 {fixed_count} 个 HTML 文件的 DOCTYPE/结构")

    sc_fixed = fix_self_closing_tags(opf_path)
    if sc_fixed:
        log(f"已修复 {sc_fixed} 个 HTML 文件中的自闭合标签")

    dup_fixed = fix_duplicate_ids(opf_path)
    if dup_fixed:
        log(f"已修复 {dup_fixed} 个 HTML 文件中的重复 id")

    css_stats = sanitize_css_for_kindle(opf_path)
    if css_stats.get("css_files"):
        log(f"已清理 {css_stats['css_files']} 个 CSS 文件中的 Kindle 不兼容属性")
    if css_stats.get("html_files"):
        log(f"已清理 {css_stats['html_files']} 个 HTML 文件内联样式中的 Kindle 不兼容属性")

    if inject_dcterms_modified(opf_path):
        log("已注入缺失的 dcterms:modified 元数据")

    sanitize_opf_for_kindle(opf_path, book_type)
    log(f"已根据 {book_type} 类型清理 OPF 不兼容元数据")

    # 小说 SVG 转 img 后，清理已无 svg 内容但 manifest 仍声明 svg 的条目
    stale_removed = remove_stale_svg_properties(opf_path)
    if stale_removed:
        log(f"已清理 {stale_removed} 个过时的 svg manifest 声明")

    return book_type


def process_epub(
    epub_path: str,
    output_path: Optional[str] = None,
    log: LogCallback = _default_log,
    imported_fonts: Optional[Dict[str, str]] = None,
) -> str:
    """处理单个 EPUB 文件并返回输出路径。"""
    if output_path is None:
        base, ext = os.path.splitext(epub_path)
        output_path = f"{base}.processed{ext}"

    epub_path = os.path.abspath(epub_path)
    output_path = os.path.abspath(output_path)

    with tempfile.TemporaryDirectory() as temp_dir:
        unpack_epub(epub_path, temp_dir)
        book_type = process_files(temp_dir, log, imported_fonts)
        repack_epub(temp_dir, output_path)

    # 独立校验输出文件
    try:
        issues = validate_epub(output_path, book_type)
        if issues:
            log("[Validation Warning] 输出 EPUB 存在以下问题:")
            for issue in issues:
                log(f"  - {issue}")
        else:
            log("输出 EPUB 校验通过")
    except Exception as e:
        log(f"[Validation Error] 校验过程异常: {e}")

    return output_path
