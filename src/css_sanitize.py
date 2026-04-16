"""
清理 Kindle 不支持的 CSS 属性与规则。
依据: Amazon Kindle Publishing Guidelines (KDP) 对 CSS 支持的限制说明。
Kindle Enhanced Typesetting 对以下属性支持极差或完全不支持，
保留它们可能导致渲染异常、白屏或性能下降。
"""

import os
import re
from pathlib import Path
from typing import Set

from lxml import etree

from .constants import NS_OPF, NS_XHTML
from .epub_io import opf_dir
from .utils import write_xhtml_doc

# ---------------------------------------------------------------------------
# Kindle 不支持/不建议的 CSS 属性列表
# ---------------------------------------------------------------------------
# 这些属性会被直接移除（整条声明 property: value;）
REMOVE_PROPERTIES: Set[str] = {
    "z-index",
    "box-shadow",
    "text-shadow",
    "animation",
    "-webkit-animation",
    "-moz-animation",
    "transition",
    "-webkit-transition",
    "-moz-transition",
    "transform",
    "-webkit-transform",
    "-moz-transform",
    "transform-origin",
    "-webkit-transform-origin",
    "cursor",
    "pointer-events",
    "user-select",
    "-webkit-user-select",
    "-moz-user-select",
}

# position 只有 fixed / sticky 会被移除；relative / absolute / static 保留
POSITION_REMOVE_VALUES = {"fixed", "sticky"}

# 大部分 -webkit- / -moz- 前缀属性都不被 Kindle 支持，但以下白名单保留
VENDOR_PREFIX_KEEP = {
    "-webkit-text-size-adjust",
    "-webkit-tap-highlight-color",
    "-moz-osx-font-smoothing",
}


def _is_vendor_prefix(prop: str) -> bool:
    return prop.startswith("-webkit-") or prop.startswith("-moz-") or prop.startswith("-ms-")


def _should_remove_declaration(prop: str, value: str) -> bool:
    prop_lower = prop.strip().lower()
    value_lower = value.strip().lower()

    if prop_lower in REMOVE_PROPERTIES:
        return True

    if prop_lower == "position" and value_lower in POSITION_REMOVE_VALUES:
        return True

    if _is_vendor_prefix(prop_lower) and prop_lower not in VENDOR_PREFIX_KEEP:
        return True

    return False


def _remove_css_declarations(css_text: str) -> str:
    """
    从 CSS 文本中移除不支持的声明。
    策略：使用正则逐条匹配 `property: value;` 并判断是否移除。
    需要正确处理嵌套的大括号（@media, @supports）。
    """
    result = []
    i = 0
    n = len(css_text)

    while i < n:
        # 查找下一个 `{` 或 `@`
        next_at = css_text.find("@", i)
        next_brace_open = css_text.find("{", i)
        next_decl = -1

        # 尝试找下一条声明 `prop: val;`
        # 用正则向前搜索
        m = re.search(r'([A-Za-z0-9_\-\*]+)\s*:\s*([^;{}]+);', css_text[i:])
        if m:
            next_decl = i + m.start()
            decl_end = i + m.end()
        else:
            next_decl = -1

        candidates = [(next_at, "at"), (next_brace_open, "brace"), (next_decl, "decl")]
        candidates = [(pos, kind) for pos, kind in candidates if pos != -1]

        if not candidates:
            result.append(css_text[i:])
            break

        pos, kind = min(candidates, key=lambda x: x[0])

        if kind == "at":
            # 保留 @ 规则的开头部分
            # 检查是否是 @keyframes / @media / @supports / @font-face
            result.append(css_text[i:pos])
            i = pos
            # 读取 @ 规则名
            at_m = re.match(r'@([a-zA-Z0-9_\-]+)', css_text[i:])
            if at_m:
                at_name = at_m.group(1).lower()
                at_start = i
                i += at_m.end()
                # 跳过空白和直到 { 之前的内容
                prebrace = css_text[i:]
                brace_pos = prebrace.find("{")
                if brace_pos != -1:
                    i += brace_pos
                    # 如果是不支持的动画规则，跳过整个块
                    if at_name in ("keyframes", "-webkit-keyframes", "-moz-keyframes"):
                        # 找到匹配的 }
                        block_end = _find_matching_brace(css_text, i)
                        if block_end != -1:
                            i = block_end + 1
                        else:
                            i = len(css_text)
                        continue
                    # 其他 @ 规则（media / supports / font-face）保留块内容但内部继续清理
                    result.append(css_text[at_start:i + 1])
                    i += 1
                    continue
            # 无法识别的 @，直接追加
            result.append(css_text[i:pos + 1])
            i = pos + 1
            continue

        if kind == "brace":
            # 遇到 `{` 之前的内容原样保留（选择器部分）
            result.append(css_text[i:pos + 1])
            i = pos + 1
            continue

        if kind == "decl":
            # pos 到 decl_end 之间是一条声明
            prop = m.group(1)
            value = m.group(2)
            result.append(css_text[i:pos])
            if not _should_remove_declaration(prop, value):
                result.append(css_text[pos:decl_end])
            i = decl_end
            continue

    return "".join(result)


def _find_matching_brace(text: str, open_idx: int) -> int:
    """从 open_idx（指向 {）开始找到匹配的 }。"""
    depth = 1
    j = open_idx + 1
    while j < len(text) and depth > 0:
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
        j += 1
    return j - 1 if depth == 0 else -1


def _clean_css_file(css_path: Path) -> bool:
    original = css_path.read_text(encoding="utf-8")
    cleaned = _remove_css_declarations(original)
    # 额外清理 animation keyframes 规则（正则兜底）
    cleaned = re.sub(
        r'@(?:-webkit-|-moz-)?keyframes\s+[A-Za-z0-9_-]+\s*\{[^}]*(?:\{[^}]*\}[^}]*)*\}\s*',
        '',
        cleaned,
        flags=re.IGNORECASE,
    )
    # 清理连续的空行
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    if cleaned != original:
        css_path.write_text(cleaned, encoding="utf-8")
        return True
    return False


def _clean_inline_style(style_text: str) -> str:
    """清理 HTML style 属性中的不支持声明。"""
    if not style_text:
        return style_text
    decls = [d.strip() for d in style_text.split(";") if d.strip()]
    kept = []
    for d in decls:
        colon_idx = d.find(":")
        if colon_idx == -1:
            kept.append(d)
            continue
        prop = d[:colon_idx].strip()
        value = d[colon_idx + 1:].strip()
        if not _should_remove_declaration(prop, value):
            kept.append(d)
    return "; ".join(kept) + ";" if kept else ""


def sanitize_css_for_kindle(opf_path: str) -> dict:
    """
    清理 EPUB 中所有 CSS 文件和 HTML inline style 的 Kindle 不兼容属性。
    返回统计字典 {"css_files": int, "html_files": int}
    """
    base_dir = Path(opf_dir(opf_path))
    tree = etree.parse(opf_path)
    ns = {"opf": NS_OPF}

    css_fixed = 0
    for css_path in base_dir.rglob("*.css"):
        if _clean_css_file(css_path):
            css_fixed += 1

    html_fixed = 0
    items = tree.xpath(
        "//opf:manifest/opf:item[@media-type='application/xhtml+xml']",
        namespaces=ns,
    )
    for item in items:
        href = item.get("href")
        if not href:
            continue
        fp = base_dir / href.replace("/", os.sep)
        if not fp.exists():
            continue
        try:
            doc = etree.parse(str(fp))
        except etree.XMLSyntaxError:
            continue
        root = doc.getroot()
        changed = False
        for elem in root.iter():
            style = elem.get("style")
            if style:
                new_style = _clean_inline_style(style)
                if new_style != style:
                    elem.set("style", new_style)
                    changed = True
        if changed:
            write_xhtml_doc(doc, fp)
            html_fixed += 1

    return {"css_files": css_fixed, "html_files": html_fixed}
