import io
import json
import os
import re
import shutil
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, NamedTuple, Optional, Set, Tuple, Union

from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTCollection, TTFont
from lxml import etree

from .constants import NS_OPF, NS_XHTML
from .epub_io import find_opf, opf_dir
from .opf_metadata import get_effective_book_language
from .text_io import read_text_file, write_text_file
from .utils import LogCallback, _default_log, write_xhtml_doc


def _run_fonttools_quietly(fn, *args, **kwargs):
    sink = io.StringIO()
    with redirect_stdout(sink), redirect_stderr(sink):
        return fn(*args, **kwargs)


class FontScanResult(NamedTuple):
    embedded: Dict[str, Dict]
    missing: Set[str]
    css_files: List[Path]
    used_families: Set[str]


class ResolvedFontPlan(NamedTuple):
    imported: Dict[str, "ImportedFontSpec"]
    builtin_fallbacks: Dict[str, Tuple[str, ...]]
    unresolved: Set[str]


@dataclass(frozen=True)
class ImportedFontSpec:
    path: str
    font_number: Optional[int] = None
    source: str = "manual"


@dataclass(frozen=True)
class SystemFontEntry:
    path: str
    family_name: str
    full_name: str
    postscript_name: str
    font_number: Optional[int] = None


KINDLE_BUILTIN_FONTS = {
    "bookerly",
    "amazon ember",
    "ember",
    "baskerville",
    "caecilia",
    "caecilia condensed",
    "futura",
    "georgia",
    "helvetica",
    "palatino",
    "times new roman",
    "times",
    "arial",
    "courier",
    "courier new",
    "comic sans",
    "comic sans ms",
    "trebuchet ms",
    "verdana",
    "garamond",
    "lucida",
    "optima",
    "athelas",
    "iowan old style",
    "serif",
    "sans-serif",
    "sans serif",
    "monospace",
    "cursive",
    "fantasy",
    "default",
    "initial",
    "inherit",
    "none",
    "stsong",
    "stkai",
    "styuan",
    "stsongtc",
    "stkaititc",
    "styuantc",
    "tbmincho",
    "tbgothic",
    "amztsukumincho",
}


_GENERIC_FONT_KEYWORDS = {
    "serif",
    "sans-serif",
    "sans serif",
    "monospace",
    "cursive",
    "fantasy",
    "default",
    "initial",
    "inherit",
    "none",
    "unset",
    "revert",
    "revert-layer",
    "-webkit-standard",
}


_STYLE_SUFFIX_PATTERN = re.compile(
    r"(?i)[\s_-]+(regular|book|roman|normal|medium|semibold|demibold|bold|heavy|black|light|italic|oblique)$"
)

_FONT_SIZE_PATTERN = re.compile(
    r"(?ix)"
    r"(?:^|[\s(])"
    r"(?:xx-small|x-small|small|medium|large|x-large|xx-large|smaller|larger|"
    r"\d*\.?\d+(?:px|pt|pc|in|cm|mm|q|em|rem|ex|ch|vh|vw|vmin|vmax|%))"
    r"(?:\s*/\s*[^ ,;]+)?"
)

_COMMON_FONT_ALIAS_TARGETS = {
    "zhuque fangsong (technical preview)": ("Zhuque Fangsong (technical preview)", "朱雀仿宋（预览测试版）"),
    "朱雀仿宋（预览测试版）": ("Zhuque Fangsong (technical preview)", "朱雀仿宋（预览测试版）"),
    "booksming": ("宋体", "SimSun", "MingLiU", "PMingLiU"),
    "bookskai": ("STKai", "楷体", "KaiTi", "DFKai-SB"),
    "dfkai-sb": ("STKai", "DFKai-SB", "KaiTi", "楷体"),
    "booksheiti": ("黑体", "SimHei", "Microsoft YaHei"),
    "stsong": ("serif", "宋体", "Songti SC"),
    "stsongtc": ("serif", "Songti TC", "MingLiU"),
    "stkai": ("STKai", "楷体", "KaiTi", "DFKai-SB"),
    "stkaiti": ("STKai", "楷体", "KaiTi", "DFKai-SB"),
    "stkaititc": ("STKai", "DFKai-SB", "標楷體"),
    "styuan": ("STYuan", "sans-serif"),
    "styuantc": ("STYuanTC", "sans-serif"),
    "stheiti": ("sans-serif", "黑体", "Heiti SC", "Microsoft YaHei"),
    "stheititc": ("sans-serif", "微軟正黑體", "Microsoft JhengHei", "Heiti TC"),
    "heiti sc": ("sans-serif", "黑体", "Microsoft YaHei"),
    "songti sc": ("serif", "宋体", "SimSun"),
    "songti tc": ("serif", "STSongTC", "MingLiU", "PMingLiU"),
    "kai": ("STKai", "serif", "KaiTi", "楷体"),
    "kaiti sc": ("STKai", "楷体", "KaiTi"),
    "kaiti tc": ("STKaitiTC", "STKai", "DFKai-SB", "標楷體"),
    "fangsong": ("Zhuque Fangsong (technical preview)", "朱雀仿宋（预览测试版）", "仿宋", "FangSong", "仿宋_GB2312"),
    "fangsong sc": ("Zhuque Fangsong (technical preview)", "朱雀仿宋（预览测试版）", "仿宋", "FangSong"),
    "biaukai": ("標楷體", "DFKai-SB", "KaiTi"),
    "標楷體": ("DFKai-SB", "KaiTi", "PMingLiU"),
    "yahei": ("sans-serif", "微软雅黑", "Microsoft YaHei", "黑体", "SimHei"),
    "fang-song": ("Zhuque Fangsong (technical preview)", "朱雀仿宋（预览测试版）", "仿宋", "FangSong", "仿宋_GB2312"),
    "ssa": ("Tempus Sans ITC", "TempusSansITC"),
    "emoji": ("Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji", "Segoe UI Symbol"),
    "sym": ("Segoe UI Symbol", "Symbol", "Arial Unicode MS"),
    "zifu": ("Segoe UI Symbol", "Symbol", "Arial Unicode MS"),
    "lucida grande": ("Segoe UI", "Arial", "Helvetica"),
    "serif-ja": ("Yu Mincho", "游明朝", "MS Mincho", "MingLiU", "PMingLiU", "SimSun"),
    "serif-jp": ("Yu Mincho", "游明朝", "MS Mincho", "MingLiU", "PMingLiU", "SimSun"),
    "serif-ja-v": ("Yu Mincho", "游明朝", "MS Mincho", "MingLiU", "PMingLiU", "SimSun"),
    "serif-tw": ("serif", "STSongTC", "MingLiU", "PMingLiU", "Songti TC", "SimSun"),
    "sans-serif-ja": ("Yu Gothic", "游ゴシック", "Meiryo", "MS Gothic", "Microsoft YaHei", "SimHei"),
    "sans-serif-jp": ("Yu Gothic", "游ゴシック", "Meiryo", "MS Gothic", "Microsoft YaHei", "SimHei"),
    "sans-serif-ja-v": ("Yu Gothic", "游ゴシック", "Meiryo", "MS Gothic", "Microsoft YaHei", "SimHei"),
    "sans-serif-tw": ("sans-serif", "Microsoft JhengHei", "JhengHei", "Microsoft YaHei", "SimHei"),
    "dk-songti": ("宋体", "SimSun", "Songti SC"),
    "dk-heiti": ("黑体", "SimHei", "微软雅黑", "Microsoft YaHei"),
    "dk-kaiti": ("楷体", "KaiTi", "楷体_GB2312"),
    "dk-fangsong": ("Zhuque Fangsong (technical preview)", "朱雀仿宋（预览测试版）", "仿宋", "FangSong", "仿宋_GB2312"),
    "dk-xiaobiaosong": ("serif", "STSong", "宋体", "Songti SC"),
    "dk-symbol": ("Segoe UI Symbol", "Symbol", "Arial Unicode MS"),
    "sthupo": ("STHupo", "华文琥珀"),
    "方正兰亭黑": ("微软雅黑", "Microsoft YaHei", "黑体", "SimHei"),
    "方正兰亭宋": ("宋体", "SimSun", "仿宋", "FangSong"),
    "方正书宋": ("宋体", "SimSun", "仿宋", "FangSong"),
    "方正黑体": ("黑体", "SimHei", "微软雅黑", "Microsoft YaHei"),
    "方正楷体": ("楷体", "KaiTi", "楷体_GB2312"),
    "方正仿宋": ("Zhuque Fangsong (technical preview)", "朱雀仿宋（预览测试版）", "仿宋", "FangSong", "仿宋_GB2312"),
    "华文黑体": ("黑体", "SimHei", "微软雅黑", "Microsoft YaHei"),
    "华文宋体": ("宋体", "SimSun", "Songti SC"),
    "华文楷体": ("楷体", "KaiTi", "楷体_GB2312"),
    "华文仿宋": ("Zhuque Fangsong (technical preview)", "朱雀仿宋（预览测试版）", "仿宋", "FangSong", "仿宋_GB2312"),
    "微软雅黑": ("sans-serif", "微软雅黑", "Microsoft YaHei", "黑体", "SimHei"),
    "宋体": ("serif", "宋体", "SimSun", "Songti SC"),
    "黑体": ("sans-serif", "黑体", "SimHei", "微软雅黑", "Microsoft YaHei"),
    "simsun": ("serif", "宋体", "SimSun", "Songti SC"),
    "simhei": ("sans-serif", "黑体", "SimHei", "Microsoft YaHei"),
    "楷体": ("STKai", "楷体", "KaiTi", "楷体_GB2312"),
    "仿宋": ("Zhuque Fangsong (technical preview)", "朱雀仿宋（预览测试版）", "仿宋", "FangSong", "仿宋_GB2312"),
    "幼圆": ("STYuan", "YouYuan", "sans-serif"),
    "youyuan": ("STYuan", "YouYuan", "sans-serif"),
    "細明體": ("serif", "MingLiU", "PMingLiU", "Songti TC"),
    "新細明體": ("serif", "PMingLiU", "MingLiU"),
    "微軟正黑體": ("sans-serif", "Microsoft JhengHei", "JhengHei", "PingFang TC"),
    "游明朝": ("TBMincho", "AMZTsukuMincho", "serif", "Yu Mincho", "游明朝", "MS Mincho"),
    "游ゴシック": ("TBGothic", "sans-serif", "Yu Gothic", "游ゴシック", "MS Gothic", "Meiryo"),
    "明朝": ("TBMincho", "AMZTsukuMincho", "serif", "Yu Mincho", "游明朝", "MS Mincho"),
    "ゴシック": ("TBGothic", "sans-serif", "Yu Gothic", "游ゴシック", "MS Gothic", "Meiryo"),
    "맑은 고딕": ("Malgun Gothic", "Dotum", "Gulim"),
}


_ROLE_PROFILE = {
    "body-serif": ("serif", "STSong", "Bookerly", "Palatino"),
    "body-sans": ("sans-serif", "Helvetica", "Amazon Ember", "Arial"),
    "body-kai": ("STKai", "serif"),
    "toc-title": ("sans-serif", "Helvetica", "Amazon Ember", "Futura"),
    "toc-item-bold": ("sans-serif", "Helvetica", "Amazon Ember", "Arial"),
    "toc-item-light": ("serif", "STSong", "Bookerly", "Palatino"),
    "heading-bold": ("sans-serif", "Helvetica", "Amazon Ember", "Futura"),
    "heading-medium": ("serif", "STSong", "Bookerly", "Palatino"),
    "heading-light": ("STKai", "serif"),
    "emphasis": ("STKai", "serif"),
    "note": ("serif", "STSong", "Bookerly", "Caecilia"),
    "symbol": ("Arial", "Helvetica", "sans-serif"),
    "emoji": ("sans-serif",),
    "illustration": ("sans-serif", "Helvetica", "Amazon Ember", "Arial"),
    "number-serif": ("serif", "Bookerly", "Baskerville", "Georgia"),
    "number-sans": ("sans-serif", "Helvetica", "Amazon Ember", "Arial"),
    "japanese-serif": ("TBMincho", "AMZTsukuMincho", "serif"),
    "japanese-sans": ("TBGothic", "sans-serif"),
}


def _normalize_font_name(value: str) -> str:
    normalized = value.strip().strip("\"'").replace("\u3000", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.lower()


def _font_settings_path() -> Path:
    for fonts_root in _font_roots():
        candidate = fonts_root / "font-settings.json"
        if candidate.exists():
            return candidate
    return _font_roots()[0] / "font-settings.json"


def writable_font_settings_path() -> Path:
    return _font_roots()[0] / "font-settings.json"


def user_font_dir() -> Path:
    return _font_roots()[0] / "user"


def clear_font_caches() -> None:
    _load_font_settings.cache_clear()
    _load_system_font_index.cache_clear()


@lru_cache(maxsize=1)
def _load_font_settings() -> Dict[str, object]:
    default_settings: Dict[str, object] = {
        "family_aliases": {},
    }

    config_path = _font_settings_path()
    if not config_path.exists():
        return default_settings

    try:
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return default_settings

    if not isinstance(loaded, dict):
        return default_settings

    family_aliases = loaded.get("family_aliases")
    if isinstance(family_aliases, dict):
        normalized_aliases: Dict[str, List[str]] = {}
        for family, values in family_aliases.items():
            if not isinstance(family, str):
                continue
            if isinstance(values, str):
                normalized_aliases[_normalize_font_name(family)] = [values]
                continue
            if isinstance(values, list):
                normalized_aliases[_normalize_font_name(family)] = [value for value in values if isinstance(value, str)]
        default_settings["family_aliases"] = normalized_aliases

    return default_settings


def _active_role_profile() -> Dict[str, Tuple[str, ...]]:
    return _ROLE_PROFILE


def _configured_family_aliases(family: str) -> Tuple[str, ...]:
    settings = _load_font_settings()
    family_aliases = settings.get("family_aliases", {})
    if not isinstance(family_aliases, dict):
        return ()
    values = family_aliases.get(_normalize_font_name(family), ())
    if not isinstance(values, list):
        return ()
    return tuple(value for value in values if isinstance(value, str) and value.strip())


def _role_alias_targets(family: str) -> Tuple[str, ...]:
    normalized = _normalize_font_name(family)
    profile = _active_role_profile()

    if normalized in {"main", "cnepub", "booksming", "dk-songti"}:
        return profile["body-serif"]
    if normalized in {"mes", "sum", "cont", "title", "title1", "title2", "toc", "art", "zc", "ml", "booksheiti", "dk-heiti"}:
        return profile["toc-title"]
    if normalized in {"ctt1"}:
        return profile["toc-item-bold"]
    if normalized in {"ctt2"}:
        return profile["toc-item-light"]
    if normalized in {"ch1"}:
        return profile["heading-bold"]
    if normalized in {"ch2"}:
        return profile["heading-medium"]
    if normalized in {"ch3"}:
        return profile["heading-light"]
    if normalized in {"int", "bookskai", "dk-kaiti", "biaukai", "標楷體", "xinyalan"}:
        return profile["emphasis"]
    if normalized in {"note"}:
        return profile["note"]
    if normalized in {"emoji"}:
        return profile["emoji"]
    if normalized in {"sym", "zifu", "dk-symbol"}:
        return profile["symbol"]
    if normalized in {"num"}:
        return profile["number-serif"]
    if normalized in {"x-num"}:
        return profile["number-sans"]
    if normalized in {"serif-ja", "serif-jp", "serif-ja-v"}:
        return profile["japanese-serif"]
    if normalized in {"sans-serif-ja", "sans-serif-jp", "sans-serif-ja-v", "hiraginokaku", "jp"}:
        return profile["japanese-sans"]
    if normalized.startswith("illus"):
        return profile["illustration"]
    if re.fullmatch(r"zt\d+", normalized):
        return profile["heading-medium"]
    if normalized.startswith("message") or normalized in {"messagetff"}:
        return profile["body-sans"]

    return ()


def _safe_font_filename(value: str) -> str:
    sanitized = re.sub(r"[^\w\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af-]+", "_", value, flags=re.UNICODE)
    sanitized = sanitized.strip("._")
    return sanitized or "imported-font"


def _font_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".otf":
        return "font/otf"
    if suffix == ".woff":
        return "font/woff"
    if suffix == ".woff2":
        return "font/woff2"
    return "font/ttf"


def _is_builtin_or_generic_font(family: str) -> bool:
    normalized = _normalize_font_name(family)
    return normalized in KINDLE_BUILTIN_FONTS or normalized in _GENERIC_FONT_KEYWORDS


def _strip_css_comments(css_content: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css_content, flags=re.DOTALL)


def _split_font_family_list(value: str) -> List[str]:
    items: List[str] = []
    current: List[str] = []
    quote: Optional[str] = None
    depth = 0

    for char in value:
        if quote:
            if char == quote:
                quote = None
            else:
                current.append(char)
            continue

        if char in {"'", '"'}:
            quote = char
            continue
        if char == "(":
            depth += 1
            current.append(char)
            continue
        if char == ")":
            depth = max(depth - 1, 0)
            current.append(char)
            continue
        if char == "," and depth == 0:
            token = "".join(current).strip()
            if token:
                items.append(token)
            current = []
            continue
        current.append(char)

    token = "".join(current).strip()
    if token:
        items.append(token)

    families: List[str] = []
    for token in items:
        stripped = re.sub(r"\s*!important\s*$", "", token.strip(), flags=re.IGNORECASE).strip().strip("\"'")
        normalized = _normalize_font_name(stripped)
        if not stripped or normalized in _GENERIC_FONT_KEYWORDS:
            continue
        if normalized.startswith("var("):
            continue
        families.append(stripped)
    return families


def _extract_families_from_font_shorthand(value: str) -> Set[str]:
    shorthand = value.strip()
    shorthand = re.sub(r"\s*!important\s*$", "", shorthand, flags=re.IGNORECASE)
    match = _FONT_SIZE_PATTERN.search(shorthand)
    if not match:
        return set()
    trailing = shorthand[match.end() :].strip()
    if not trailing:
        return set()
    return {_normalize_font_name(name) for name in _split_font_family_list(trailing)}


def _extract_css_used_families(css_content: str) -> Set[str]:
    content = _strip_css_comments(css_content)
    used: Set[str] = set()

    for match in re.finditer(r"font-family\s*:\s*([^;}{]+)", content, re.IGNORECASE):
        used.update(_normalize_font_name(name) for name in _split_font_family_list(match.group(1)))

    for match in re.finditer(r"(?<!-)\bfont\s*:\s*([^;}{]+)", content, re.IGNORECASE):
        used.update(_extract_families_from_font_shorthand(match.group(1)))

    return {family for family in used if family}


def _parse_css_font_faces(css_content: str) -> List[Dict[str, Optional[str]]]:
    content = _strip_css_comments(css_content)
    faces: List[Dict[str, Optional[str]]] = []
    for match in re.finditer(r"@font-face\s*\{(.*?)\}", content, re.IGNORECASE | re.DOTALL):
        block = match.group(1)
        family_match = re.search(
            r'font-family\s*:\s*["\']?([^";\']+)["\']?\s*;',
            block,
            re.IGNORECASE,
        )
        src_match = re.search(r"src\s*:\s*([^;]+);", block, re.IGNORECASE)
        if not family_match:
            continue
        family = _normalize_font_name(family_match.group(1))
        src_url = None
        fmt = None
        if src_match:
            src_decl = src_match.group(1)
            url_match = re.search(
                r'url\s*\(\s*["\']?([^"\')]+)["\']?\s*\)',
                src_decl,
                re.IGNORECASE,
            )
            if url_match:
                src_url = url_match.group(1)
                format_match = re.search(
                    r'format\s*\(\s*["\']?([^"\')]+)["\']?\s*\)',
                    src_decl,
                    re.IGNORECASE,
                )
                fmt = format_match.group(1).lower() if format_match else None
        faces.append({"family": family, "src_url": src_url, "format": fmt})
    return faces


def _resolve_font_asset_path(
    base_dir: Path,
    owner_path: Path,
    src_url: str,
) -> Optional[Path]:
    if src_url.startswith(("http://", "https://", "data:")):
        return None
    if src_url.startswith("/"):
        resolved = (base_dir / src_url.lstrip("/")).resolve()
    else:
        resolved = (owner_path.parent / src_url).resolve()
    try:
        resolved.relative_to(base_dir.resolve())
    except ValueError:
        return None
    return resolved


def _collect_css_scan(
    css_content: str,
    owner_path: Path,
    base_dir: Path,
    embedded: Dict[str, Dict],
    broken_faces: Set[str],
    used_families: Set[str],
) -> None:
    used_families.update(_extract_css_used_families(css_content))

    for face in _parse_css_font_faces(css_content):
        family = face["family"] or ""
        if not family:
            continue

        src_url = face["src_url"]
        if not src_url:
            if not _is_builtin_or_generic_font(family):
                broken_faces.add(family)
            continue

        resolved = _resolve_font_asset_path(base_dir, owner_path, src_url)
        if resolved is None or not resolved.exists():
            if not _is_builtin_or_generic_font(family):
                broken_faces.add(family)
            continue

        fmt = face["format"]
        if not fmt:
            suffix = resolved.suffix.lower()
            if suffix == ".woff2":
                fmt = "woff2"
            elif suffix == ".woff":
                fmt = "woff"
            elif suffix in {".ttf", ".otf"}:
                fmt = suffix.lstrip(".")

        embedded[family] = {
            "path": resolved,
            "format": fmt,
            "css_path": owner_path,
            "src_url": src_url,
        }


def _collect_xhtml_paths(opf_path: str) -> List[Path]:
    tree = etree.parse(opf_path)
    base_dir = Path(opf_dir(opf_path))
    items = tree.xpath(
        "//opf:manifest/opf:item[@media-type='application/xhtml+xml' or @media-type='text/html']",
        namespaces={"opf": NS_OPF},
    )

    paths: List[Path] = []
    for item in items:
        href = item.get("href")
        if not href:
            continue
        path = (base_dir / href.replace("/", os.sep)).resolve()
        if path.exists():
            paths.append(path)
    return paths


def scan_fonts(temp_dir: str) -> FontScanResult:
    base_dir = Path(temp_dir).resolve()
    opf_path = find_opf(temp_dir)
    css_files = list(base_dir.rglob("*.css"))
    embedded: Dict[str, Dict] = {}
    broken_faces: Set[str] = set()
    used_families: Set[str] = set()

    for css_path in css_files:
        css_content = read_text_file(css_path)
        _collect_css_scan(css_content, css_path, base_dir, embedded, broken_faces, used_families)

    for xhtml_path in _collect_xhtml_paths(opf_path):
        try:
            doc = etree.parse(str(xhtml_path))
        except etree.XMLSyntaxError:
            continue

        for style_elem in doc.findall(f".//{{{NS_XHTML}}}style"):
            css_text = style_elem.text or ""
            _collect_css_scan(css_text, xhtml_path, base_dir, embedded, broken_faces, used_families)

        for elem in doc.xpath("//*[@style]"):
            style = elem.get("style") or ""
            used_families.update(_extract_css_used_families(style))

    missing = {
        family
        for family in (used_families | broken_faces)
        if family not in embedded and not _is_builtin_or_generic_font(family)
    }
    used_families = {family for family in used_families if not _is_builtin_or_generic_font(family)}

    return FontScanResult(
        embedded=embedded,
        missing=missing,
        css_files=css_files,
        used_families=used_families,
    )


def _fallback_font_family(language: str) -> str:
    if language.startswith("zh"):
        return "serif"
    if language.startswith("ja"):
        return "TBMincho, serif"
    if language.startswith("ko"):
        return "serif"
    return "serif"


def _sanitize_css_font_family(
    css_content: str,
    missing: Set[str],
    fallback: str,
    replacements: Optional[Dict[str, Tuple[str, ...]]] = None,
) -> str:
    replacements = replacements or {}

    def _replace_decl(match: re.Match[str]) -> str:
        prefix = match.group(1)
        values = match.group(2)
        kept: List[str] = []
        seen: Set[str] = set()
        for part in _split_font_family_list(values):
            normalized = _normalize_font_name(part)
            if normalized not in missing:
                if normalized not in seen:
                    kept.append(part if part.startswith(("'", '"')) else part)
                    seen.add(normalized)
                continue
            for replacement in replacements.get(normalized, ()):
                replacement_normalized = _normalize_font_name(replacement)
                if replacement_normalized in seen:
                    continue
                kept.append(replacement)
                seen.add(replacement_normalized)
        if kept:
            return prefix + ", ".join(kept)
        return prefix + fallback

    pattern = re.compile(r"(font-family\s*:\s*)([^;}\n]+?)(?=[;}\n]|$)", re.IGNORECASE)
    return pattern.sub(_replace_decl, css_content)


def _remove_font_face_blocks(css_content: str, families: Set[str]) -> Tuple[str, int]:
    content = css_content
    removed = 0
    for family in sorted(families):
        pattern = re.compile(
            rf"@font-face\s*\{{.*?font-family\s*:\s*[\"']?{re.escape(family)}[\"']?\s*;.*?\}}",
            re.IGNORECASE | re.DOTALL,
        )
        content, count = pattern.subn("", content)
        removed += count
    return content, removed


def sanitize_missing_fonts(
    temp_dir: str,
    missing: Set[str],
    log: LogCallback = _default_log,
    font_scan: Optional[FontScanResult] = None,
    replacements: Optional[Dict[str, Tuple[str, ...]]] = None,
) -> None:
    if not missing:
        return

    opf_path = find_opf(temp_dir)
    language = get_effective_book_language(opf_path)
    fallback = _fallback_font_family(language)
    css_files = list(font_scan.css_files) if font_scan is not None else list(scan_fonts(temp_dir).css_files)

    removed_faces = 0
    replaced_css = 0

    for css_path in css_files:
        content = read_text_file(css_path)
        updated, removed = _remove_font_face_blocks(content, missing)
        updated = _sanitize_css_font_family(updated, missing, fallback, replacements=replacements)
        if updated != content:
            write_text_file(css_path, updated)
            replaced_css += 1
        removed_faces += removed

    if removed_faces:
        log(f"已移除 {removed_faces} 个缺失字体的 @font-face 声明")
    if replaced_css:
        log(f"已在 {replaced_css} 个样式表中替换缺失字体为回退字体")

    replaced_html = 0
    for xhtml_path in _collect_xhtml_paths(opf_path):
        try:
            doc = etree.parse(str(xhtml_path))
        except etree.XMLSyntaxError:
            continue

        changed = False

        for style_elem in doc.findall(f".//{{{NS_XHTML}}}style"):
            original = style_elem.text or ""
            updated, _ = _remove_font_face_blocks(original, missing)
            updated = _sanitize_css_font_family(updated, missing, fallback, replacements=replacements)
            if updated != original:
                style_elem.text = updated
                changed = True

        for elem in doc.xpath("//*[@style]"):
            style = elem.get("style") or ""
            if not style or "font-family" not in style.lower():
                continue
            new_style = _sanitize_css_font_family(style, missing, fallback, replacements=replacements)
            if new_style != style:
                elem.set("style", new_style)
                changed = True

        if changed:
            write_xhtml_doc(doc, xhtml_path)
            replaced_html += 1

    if replaced_html:
        log(f"已在 {replaced_html} 个 HTML 文件中替换缺失字体为回退字体")


def _iter_system_font_paths() -> Iterable[Path]:
    seen: Set[str] = set()
    candidates = [
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts",
    ]

    for directory in candidates:
        if not directory.exists():
            continue
        for suffix in ("*.ttf", "*.otf", "*.ttc", "*.otc"):
            for path in directory.glob(suffix):
                key = str(path.resolve()).lower()
                if key in seen:
                    continue
                seen.add(key)
                yield path.resolve()


def _application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _resource_roots() -> List[Path]:
    roots: List[Path] = []
    seen: Set[str] = set()

    def _push(path: Path) -> None:
        resolved = path.resolve()
        key = str(resolved).lower()
        if key in seen:
            return
        seen.add(key)
        roots.append(resolved)

    if getattr(sys, "frozen", False):
        _push(Path(sys.executable).resolve().parent)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            _push(Path(meipass))
    else:
        _push(Path(__file__).resolve().parent.parent)

    return roots


def _font_roots() -> List[Path]:
    roots: List[Path] = []
    seen: Set[str] = set()

    def _push(path: Path) -> None:
        try:
            resolved = path.resolve()
        except OSError:
            return
        key = str(resolved).lower()
        if key in seen:
            return
        seen.add(key)
        roots.append(resolved)

    for value in os.environ.get("KINDLE_EPUB_FIXER_FONT_DIRS", "").split(os.pathsep):
        value = value.strip()
        if value:
            _push(Path(value))

    for root in _resource_roots():
        _push(root / "fonts")

    return roots


def _iter_bundled_font_paths() -> Iterable[Path]:
    seen: Set[str] = set()
    candidates: List[Path] = []
    for fonts_root in _font_roots():
        candidates.extend([fonts_root, fonts_root / "common", fonts_root / "user"])

    for directory in candidates:
        if not directory.exists():
            continue
        for suffix in ("*.ttf", "*.otf", "*.ttc", "*.otc", "*.woff", "*.woff2"):
            for path in directory.rglob(suffix):
                key = str(path.resolve()).lower()
                if key in seen:
                    continue
                seen.add(key)
                yield path.resolve()


def _detect_font_source(path: str) -> str:
    resolved = Path(path).resolve()
    for fonts_root in _font_roots():
        try:
            resolved.relative_to(fonts_root.resolve())
            return "bundled"
        except ValueError:
            continue
    return "system"


def _looks_like_font_path(value: str) -> bool:
    normalized = value.strip().replace("\\", "/")
    return normalized.lower().endswith((".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2")) or "/" in normalized


def _resolve_configured_font_path(value: str) -> Optional[Path]:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate.resolve() if candidate.exists() else None

    for fonts_root in _font_roots():
        resolved_root = fonts_root.resolve()
        relative_candidate = (resolved_root / candidate).resolve()
        try:
            relative_candidate.relative_to(resolved_root)
        except ValueError:
            continue
        if relative_candidate.exists():
            return relative_candidate
    return None


def _extract_name_values(font: TTFont, name_id: int) -> List[str]:
    try:
        name_table = font["name"]
    except Exception:
        return []

    values: List[str] = []
    seen: Set[str] = set()
    for record in name_table.names:
        if record.nameID != name_id:
            continue
        try:
            value = str(record.toUnicode()).strip()
        except Exception:
            continue
        if not value:
            continue
        normalized = _normalize_font_name(value)
        if normalized in seen:
            continue
        seen.add(normalized)
        values.append(value)
    return values


@lru_cache(maxsize=1)
def _load_system_font_index() -> Dict[str, Tuple[SystemFontEntry, ...]]:
    index: Dict[str, List[SystemFontEntry]] = {}

    def _register_name(name: str, entry: SystemFontEntry) -> None:
        normalized = _normalize_font_name(name)
        if not normalized:
            return
        bucket = index.setdefault(normalized, [])
        if entry not in bucket:
            bucket.append(entry)

    for font_path in [*_iter_bundled_font_paths(), *_iter_system_font_paths()]:
        suffix = font_path.suffix.lower()
        try:
            if suffix in {".ttc", ".otc"}:
                collection = _run_fonttools_quietly(TTCollection, str(font_path))
                for font_number, font in enumerate(collection.fonts):
                    families = _extract_name_values(font, 1)
                    full_names = _extract_name_values(font, 4)
                    postscript_names = _extract_name_values(font, 6)
                    family_name = families[0] if families else (full_names[0] if full_names else font_path.stem)
                    full_name = full_names[0] if full_names else family_name
                    postscript_name = postscript_names[0] if postscript_names else full_name
                    entry = SystemFontEntry(
                        path=str(font_path),
                        family_name=family_name,
                        full_name=full_name,
                        postscript_name=postscript_name,
                        font_number=font_number,
                    )
                    for name in [family_name, full_name, postscript_name, *families, *full_names, *postscript_names]:
                        _register_name(name, entry)
            else:
                font = _run_fonttools_quietly(TTFont, str(font_path))
                families = _extract_name_values(font, 1)
                full_names = _extract_name_values(font, 4)
                postscript_names = _extract_name_values(font, 6)
                family_name = families[0] if families else (full_names[0] if full_names else font_path.stem)
                full_name = full_names[0] if full_names else family_name
                postscript_name = postscript_names[0] if postscript_names else full_name
                entry = SystemFontEntry(
                    path=str(font_path),
                    family_name=family_name,
                    full_name=full_name,
                    postscript_name=postscript_name,
                    font_number=None,
                )
                for name in [family_name, full_name, postscript_name, *families, *full_names, *postscript_names]:
                    _register_name(name, entry)
        except Exception:
            continue

    return {key: tuple(value) for key, value in index.items()}


def _system_entry_sort_key(entry: SystemFontEntry) -> Tuple[int, int, int, str]:
    suffix = Path(entry.path).suffix.lower()
    return (
        0 if entry.font_number is None else 1,
        0 if suffix == ".ttf" else 1,
        0 if suffix == ".otf" else 1,
        entry.path.lower(),
    )


def _candidate_font_names(family: str) -> List[str]:
    raw = family.strip().strip("\"'")
    if not raw:
        return []

    candidates: List[str] = []
    seen: Set[str] = set()

    def _push(value: str) -> None:
        normalized = _normalize_font_name(value)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        candidates.append(value)

    for value in _configured_family_aliases(raw):
        if value.strip():
            _push(value.strip())

    for alias in _COMMON_FONT_ALIAS_TARGETS.get(_normalize_font_name(raw), ()):
        _push(alias)

    _push(raw)
    _push(raw.replace("_", " "))
    _push(raw.replace("-", " "))

    base_variants = list(candidates)
    for value in base_variants:
        stripped = _STYLE_SUFFIX_PATTERN.sub("", value).strip()
        if stripped:
            _push(stripped)

    for value in list(candidates):
        for alias in _COMMON_FONT_ALIAS_TARGETS.get(_normalize_font_name(value), ()):
            _push(alias)

    for alias in _role_alias_targets(raw):
        _push(alias)

    return candidates


def _resolve_system_font_entry(family: str) -> Optional[SystemFontEntry]:
    index = _load_system_font_index()

    for candidate in _candidate_font_names(family):
        if _looks_like_font_path(candidate):
            continue
        entries = index.get(_normalize_font_name(candidate))
        if entries:
            return sorted(entries, key=_system_entry_sort_key)[0]

    for candidate in _candidate_font_names(family):
        if _looks_like_font_path(candidate):
            continue
        normalized = _normalize_font_name(candidate)
        if not normalized:
            continue
        fuzzy_matches: List[SystemFontEntry] = []
        for name, entries in index.items():
            if normalized in name or name in normalized:
                fuzzy_matches.extend(entries)
        if fuzzy_matches:
            unique_matches = sorted(set(fuzzy_matches), key=_system_entry_sort_key)
            return unique_matches[0]

    return None


def resolve_missing_font_plan(
    missing_families: Set[str],
) -> ResolvedFontPlan:
    imported: Dict[str, ImportedFontSpec] = {}
    builtin_fallbacks: Dict[str, Tuple[str, ...]] = {}
    unresolved: Set[str] = set()

    for family in sorted(missing_families):
        explicit_aliases = list(_configured_family_aliases(family))
        builtin_candidates: List[str] = []
        seen_builtin: Set[str] = set()

        def _add_builtin_candidate(value: str) -> None:
            normalized = _normalize_font_name(value)
            if normalized in seen_builtin:
                return
            seen_builtin.add(normalized)
            builtin_candidates.append(value)

        if explicit_aliases:
            explicit_resolved = False
            for alias in explicit_aliases:
                if _looks_like_font_path(alias):
                    font_path = _resolve_configured_font_path(alias)
                    if font_path is None:
                        continue
                    imported[family] = ImportedFontSpec(path=str(font_path), source=_detect_font_source(str(font_path)))
                    explicit_resolved = True
                    break

                normalized = _normalize_font_name(alias)
                if normalized in KINDLE_BUILTIN_FONTS or normalized in _GENERIC_FONT_KEYWORDS:
                    _add_builtin_candidate(alias)
                    continue

                entry = _resolve_system_font_entry(alias)
                if entry is None:
                    continue
                imported[family] = ImportedFontSpec(
                    path=entry.path,
                    font_number=entry.font_number,
                    source=_detect_font_source(entry.path),
                )
                explicit_resolved = True
                break

            if explicit_resolved:
                continue
            if builtin_candidates:
                builtin_fallbacks[family] = tuple(builtin_candidates)
                continue

        for candidate in _candidate_font_names(family):
            normalized = _normalize_font_name(candidate)
            if normalized in KINDLE_BUILTIN_FONTS or normalized in _GENERIC_FONT_KEYWORDS:
                _add_builtin_candidate(candidate)
        if builtin_candidates:
            builtin_fallbacks[family] = tuple(dict.fromkeys(builtin_candidates))
            continue

        resolved = False
        for candidate in _candidate_font_names(family):
            normalized = _normalize_font_name(candidate)
            if normalized in KINDLE_BUILTIN_FONTS or normalized in _GENERIC_FONT_KEYWORDS:
                _add_builtin_candidate(candidate)
                continue

            entry = _resolve_system_font_entry(candidate)
            if entry is None:
                continue
            imported[family] = ImportedFontSpec(
                path=entry.path,
                font_number=entry.font_number,
                source=_detect_font_source(entry.path),
            )
            resolved = True
            break

        if resolved:
            continue
        if builtin_candidates:
            builtin_fallbacks[family] = tuple(dict.fromkeys(builtin_candidates))
            continue
        unresolved.add(family)

    return ResolvedFontPlan(imported=imported, builtin_fallbacks=builtin_fallbacks, unresolved=unresolved)


def resolve_missing_font_specs(
    missing_families: Set[str],
) -> Tuple[Dict[str, ImportedFontSpec], Set[str]]:
    plan = resolve_missing_font_plan(missing_families)
    return plan.imported, plan.unresolved


def _coerce_imported_font_spec(value: Union[str, ImportedFontSpec]) -> ImportedFontSpec:
    if isinstance(value, ImportedFontSpec):
        return value
    return ImportedFontSpec(path=str(value))


def _pick_collection_font(collection: TTCollection, family: str, preferred_index: Optional[int]) -> TTFont:
    if preferred_index is not None and 0 <= preferred_index < len(collection.fonts):
        return collection.fonts[preferred_index]

    candidates = {_normalize_font_name(name) for name in _candidate_font_names(family)}
    for font in collection.fonts:
        names = {
            _normalize_font_name(name)
            for name in (
                _extract_name_values(font, 1)
                + _extract_name_values(font, 4)
                + _extract_name_values(font, 6)
            )
        }
        if candidates & names:
            return font

    return collection.fonts[0]


def _materialize_imported_font(
    spec: ImportedFontSpec,
    family: str,
    fonts_dir: Path,
) -> Path:
    source_path = Path(spec.path)
    if not source_path.exists():
        raise FileNotFoundError(str(source_path))

    suffix = source_path.suffix.lower()
    target_stem = _safe_font_filename(family)
    target_path = fonts_dir / f"{target_stem}{suffix if suffix not in {'.ttc', '.otc', '.woff', '.woff2'} else '.ttf'}"

    counter = 1
    while target_path.exists():
        target_path = fonts_dir / f"{target_stem}_{counter}{target_path.suffix}"
        counter += 1

    if suffix in {".ttc", ".otc"}:
        collection = _run_fonttools_quietly(TTCollection, str(source_path))
        font = _pick_collection_font(collection, family, spec.font_number)
        _run_fonttools_quietly(font.save, str(target_path))
        return target_path

    if suffix in {".woff", ".woff2"}:
        font = _run_fonttools_quietly(TTFont, str(source_path))
        _run_fonttools_quietly(font.save, str(target_path))
        return target_path

    shutil.copy2(str(source_path), str(target_path))
    return target_path


def _ensure_manifest_item(
    manifest: etree._Element,
    href: str,
    media_type: str,
    preferred_id: str,
) -> etree._Element:
    for item in manifest.findall(f"{{{NS_OPF}}}item"):
        if item.get("href") == href:
            item.set("media-type", media_type)
            return item

    existing_ids = {item.get("id") for item in manifest.findall(f"{{{NS_OPF}}}item")}
    item_id = preferred_id
    counter = 1
    while item_id in existing_ids:
        item_id = f"{preferred_id}-{counter}"
        counter += 1

    item = etree.SubElement(manifest, f"{{{NS_OPF}}}item")
    item.set("id", item_id)
    item.set("href", href)
    item.set("media-type", media_type)
    return item


def _ensure_head_element(doc: etree._ElementTree) -> etree._Element:
    root = doc.getroot()
    head = root.find(f"{{{NS_XHTML}}}head")
    if head is not None:
        return head

    head = etree.Element(f"{{{NS_XHTML}}}head")
    root.insert(0, head)
    return head


def _ensure_font_stylesheet(
    opf_path: str,
    imported_assets: Dict[str, Path],
) -> Path:
    tree = etree.parse(opf_path)
    base_dir = Path(opf_dir(opf_path))
    styles_dir = base_dir / "Styles"
    styles_dir.mkdir(exist_ok=True)

    stylesheet_path = styles_dir / "kindle-fonts.css"
    lines = [
        "@charset \"utf-8\";",
        "/* Auto-generated by Kindle EPUB Fixer. */",
        "",
    ]

    for family in sorted(imported_assets):
        font_path = imported_assets[family]
        relative_url = os.path.relpath(font_path, stylesheet_path.parent).replace(os.sep, "/")
        lines.extend(
            [
                "@font-face {",
                f"  font-family: \"{family}\";",
                f"  src: url(\"{relative_url}\") format(\"{font_path.suffix.lower().lstrip('.')}\" );",
                "  font-style: normal;",
                "  font-weight: normal;",
                "}",
                "",
            ]
        )

    write_text_file(stylesheet_path, "\n".join(lines).replace('") format("ttf"', '") format("truetype"').replace('") format("otf"', '") format("opentype"'))

    manifest = tree.getroot().find(f"{{{NS_OPF}}}manifest")
    if manifest is not None:
        stylesheet_href = os.path.relpath(stylesheet_path, base_dir).replace(os.sep, "/")
        _ensure_manifest_item(manifest, stylesheet_href, "text/css", "kindle-fonts-css")

    for xhtml_path in _collect_xhtml_paths(opf_path):
        try:
            doc = etree.parse(str(xhtml_path))
        except etree.XMLSyntaxError:
            continue

        head = _ensure_head_element(doc)
        href = os.path.relpath(stylesheet_path, xhtml_path.parent).replace(os.sep, "/")
        already_linked = False
        for link in head.findall(f"{{{NS_XHTML}}}link"):
            if (link.get("rel") or "").lower() == "stylesheet" and link.get("href") == href:
                already_linked = True
                break

        if not already_linked:
            link = etree.Element(f"{{{NS_XHTML}}}link")
            link.set("rel", "stylesheet")
            link.set("type", "text/css")
            link.set("href", href)
            head.append(link)
            write_xhtml_doc(doc, xhtml_path)

    tree.write(opf_path, encoding="utf-8", xml_declaration=True)
    return stylesheet_path


def _rewrite_asset_names_in_xhtml(xhtml_path: Path, renamed: Dict[str, str]) -> bool:
    try:
        doc = etree.parse(str(xhtml_path))
    except etree.XMLSyntaxError:
        return False

    changed = False

    for style_elem in doc.findall(f".//{{{NS_XHTML}}}style"):
        text = style_elem.text or ""
        updated = text
        for old_name, new_name in renamed.items():
            updated = re.sub(re.escape(old_name) + r'(?=["\'\s)\]])', new_name, updated)
        if updated != text:
            style_elem.text = updated
            changed = True

    for elem in doc.xpath("//*[@style]"):
        style = elem.get("style") or ""
        updated = style
        for old_name, new_name in renamed.items():
            updated = re.sub(re.escape(old_name) + r'(?=["\'\s)\]])', new_name, updated)
        if updated != style:
            elem.set("style", updated)
            changed = True

    if changed:
        write_xhtml_doc(doc, xhtml_path)
    return changed


def _collect_text_characters(opf_path: str) -> str:
    chars: Set[str] = set()
    for xhtml_path in _collect_xhtml_paths(opf_path):
        try:
            doc = etree.parse(str(xhtml_path))
        except etree.XMLSyntaxError:
            continue
        chars.update("".join(doc.getroot().itertext()))

    chars.update(chr(i) for i in range(32, 127))
    chars.update("\n\r\t")
    return "".join(chars)


def handle_fonts(
    temp_dir: str,
    log: LogCallback = _default_log,
    imported_fonts: Optional[Dict[str, Union[str, ImportedFontSpec]]] = None,
    font_scan: Optional[FontScanResult] = None,
    sanitize_missing: bool = True,
) -> None:
    provided_fonts = {
        _normalize_font_name(family): _coerce_imported_font_spec(spec)
        for family, spec in (imported_fonts or {}).items()
    }

    opf_path = find_opf(temp_dir)
    base_dir = Path(opf_dir(opf_path))
    tree = etree.parse(opf_path)
    manifest = tree.getroot().find(f"{{{NS_OPF}}}manifest")

    scan = font_scan if font_scan is not None else scan_fonts(temp_dir)
    embedded = dict(scan.embedded)
    missing = set(scan.missing)
    css_files = list(scan.css_files)

    auto_plan = resolve_missing_font_plan(missing - set(provided_fonts))
    import_plan = dict(auto_plan.imported)
    import_plan.update(provided_fonts)
    builtin_fallbacks = dict(auto_plan.builtin_fallbacks)

    if auto_plan.imported:
        log(f"已自动匹配 {len(auto_plan.imported)} 个缺失字体到可导入字体库")
    if auto_plan.builtin_fallbacks:
        log(f"已为 {len(auto_plan.builtin_fallbacks)} 个缺失字体分配 Kindle 回落字体")
    if auto_plan.unresolved and not provided_fonts:
        log(f"[Warning] 仍有 {len(auto_plan.unresolved)} 个字体未能自动匹配")

    imported_assets: Dict[str, Path] = {}

    if import_plan and missing:
        fonts_dir = base_dir / "Fonts"
        fonts_dir.mkdir(exist_ok=True)

        for family in sorted(missing):
            spec = import_plan.get(family)
            if spec is None:
                continue
            try:
                target_path = _materialize_imported_font(spec, family, fonts_dir)
            except Exception as exc:
                log(f"[Warning] 导入字体失败 {family}: {exc}")
                continue

            if manifest is not None:
                href = os.path.relpath(target_path, base_dir).replace(os.sep, "/")
                _ensure_manifest_item(manifest, href, _font_media_type(target_path), f"font-{_safe_font_filename(family)}")

            embedded[family] = {
                "path": target_path,
                "format": target_path.suffix.lower().lstrip("."),
                "css_path": None,
                "src_url": os.path.relpath(target_path, base_dir).replace(os.sep, "/"),
            }
            imported_assets[family] = target_path
            missing.discard(family)
            if spec.source == "system":
                source_label = "系统字体"
            elif spec.source == "bundled":
                source_label = "预置字体库"
            else:
                source_label = "外部字体"
            log(f"已导入缺失字体 {family} -> {target_path.name} ({source_label})")

    if imported_assets:
        stylesheet_path = _ensure_font_stylesheet(opf_path, imported_assets)
        if stylesheet_path not in css_files:
            css_files.append(stylesheet_path)

    if missing and sanitize_missing:
        sanitize_missing_fonts(temp_dir, missing, log, font_scan=scan, replacements=builtin_fallbacks)
        missing.clear()
    elif missing:
        log(f"[Warning] 保留排版模式下保留 {len(missing)} 个未解析字体引用")

    text = _collect_text_characters(opf_path)
    renamed: Dict[str, str] = {}

    for family, info in list(embedded.items()):
        font_path = info["path"]
        if not font_path.exists():
            continue

        original_name = font_path.name
        ext = font_path.suffix.lower()
        converted = False

        if ext in {".woff", ".woff2"}:
            try:
                font = _run_fonttools_quietly(TTFont, str(font_path))
                new_path = font_path.with_suffix(".ttf")
                _run_fonttools_quietly(font.save, str(new_path))
                font_path.unlink()
                font_path = new_path
                converted = True
                log(f"字体格式转换: {original_name} -> {font_path.name}")
            except Exception as exc:
                log(f"[Warning] 字体格式转换失败 {original_name}: {exc}")
                continue

        if font_path.exists() and font_path.stat().st_size > 50 * 1024 and text:
            try:
                font = _run_fonttools_quietly(TTFont, str(font_path))
                options = Options()
                options.hinting = False
                options.desubroutinize = True
                subsetter = Subsetter(options=options)
                subsetter.populate(text=text)
                _run_fonttools_quietly(subsetter.subset, font)
                tmp_path = font_path.with_suffix(".subset" + font_path.suffix)
                _run_fonttools_quietly(font.save, str(tmp_path))
                font_path.unlink()
                tmp_path.rename(font_path)
                log(f"字体子集化: {font_path.name}")
            except Exception as exc:
                log(f"[Warning] 字体子集化失败 {font_path.name}: {exc}")

        if converted:
            renamed[original_name] = font_path.name
            embedded[family]["path"] = font_path
            embedded[family]["format"] = font_path.suffix.lower().lstrip(".")

    if renamed:
        for css_path in css_files:
            content = read_text_file(css_path)
            updated = content
            for old_name, new_name in renamed.items():
                updated = re.sub(re.escape(old_name) + r'(?=["\'\s)\]])', new_name, updated)
            if updated != content:
                write_text_file(css_path, updated)

        for xhtml_path in _collect_xhtml_paths(opf_path):
            _rewrite_asset_names_in_xhtml(xhtml_path, renamed)

        if manifest is not None:
            for item in manifest.findall(f"{{{NS_OPF}}}item"):
                href = item.get("href")
                if not href:
                    continue
                old_name = Path(href).name
                if old_name in renamed:
                    new_name = renamed[old_name]
                    new_href = str(Path(href).parent / new_name).replace("\\", "/")
                    item.set("href", new_href)
                    item.set("media-type", _font_media_type(Path(new_name)))

    tree = etree.parse(opf_path)
    tree.write(opf_path, encoding="utf-8", xml_declaration=True)
