"""
批量分析 EPUB 的常见问题，用于改进通用修复引擎。
分析维度：
- 基础结构 (mimetype, META-INF/container.xml, OPF)
- HTML 结构 (DOCTYPE, 自闭合标签, lang, viewport, 非法字符)
- CSS (font-face, vertical-rl, 非法属性/值)
- 图片 (webp, svg, 超大图片, 缺失引用)
- 脚本 (JS, inline script)
- 字体 (缺失, WOFF/WOFF2)
- Kindle 规范 (page-progression-direction, fixed-layout, manifest 一致性)
- 其他 (重复 id, 非法路径, NCX 存在性)
"""

import json
import os
import re
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from lxml import etree

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
NS_OPF = "http://www.idpf.org/2007/opf"
NS_DC = "http://purl.org/dc/elements/1.1/"
NS_XHTML = "http://www.w3.org/1999/xhtml"

SELF_CLOSING_BAD_RE = re.compile(r"<(p|div|span|h[1-6]|li|td|th|tr|tbody|thead|tfoot|section|article|aside|header|footer|main|nav|figure|figcaption|em|strong|b|i|u|s|small|sub|sup|mark|ruby|rt|rp|wbr)(\s+[^>]*)?/>", re.I)
IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)
SCRIPT_TAG_RE = re.compile(r'<script\b', re.I)
FONT_FACE_RE = re.compile(r'@font-face\s*\{', re.I)
VERTICAL_RL_RE = re.compile(r'writing-mode\s*:\s*vertical-rl', re.I)
WEBP_RE = re.compile(r'\.webp\b', re.I)

def shortname(path: str) -> str:
    return Path(path).name

def analyze_epub(epub_path: str) -> dict:
    issues = defaultdict(list)
    stats = {}

    try:
        zf = zipfile.ZipFile(epub_path, 'r')
    except Exception as e:
        issues["zip_error"].append(str(e))
        return dict(issues)

    namelist = zf.namelist()
    stats["file_count"] = len(namelist)

    # 1. mimetype 检查
    try:
        mtype = zf.read("mimetype").decode("utf-8").strip()
        if mtype != "application/epub+zip":
            issues["mimetype_bad"].append(mtype)
    except Exception:
        issues["missing_mimetype"].append(True)

    # 2. META-INF/container.xml
    try:
        container = zf.read("META-INF/container.xml").decode("utf-8")
        rootfile_match = re.search(r'full-path=["\']([^"\']+)["\']', container)
        if not rootfile_match:
            issues["container_no_rootfile"].append(True)
            return dict(issues)
        opf_path = rootfile_match.group(1)
    except Exception as e:
        issues["container_error"].append(str(e))
        return dict(issues)

    # 3. OPF 分析
    try:
        opf_bytes = zf.read(opf_path)
        opf = etree.fromstring(opf_bytes)
    except Exception as e:
        issues["opf_parse_error"].append(str(e))
        return dict(issues)

    opf_dir = os.path.dirname(opf_path) or ""

    # 语言
    langs = opf.xpath("//dc:language/text()", namespaces={"dc": NS_DC})
    stats["opf_language"] = langs[0] if langs else None
    if not langs:
        issues["missing_dc_language"].append(True)

    # 书名
    titles = opf.xpath("//dc:title/text()", namespaces={"dc": NS_DC})
    stats["title"] = titles[0] if titles else "Unknown"

    # modified
    modifieds = opf.xpath(
        "//opf:meta[@property='dcterms:modified']/text()",
        namespaces={"opf": NS_OPF},
    )
    if not modifieds:
        issues["missing_dcterms_modified"].append(True)

    # page-progression-direction
    ppd = opf.xpath("//opf:spine/@page-progression-direction", namespaces={"opf": NS_OPF})
    if ppd:
        stats["ppd"] = ppd[0]
        if ppd[0] == "rtl":
            issues["spine_rtl"].append(True)
    else:
        stats["ppd"] = "default(ltr)"

    # fixed-layout
    rendition_layout = opf.xpath(
        "//opf:meta[@property='rendition:layout']/@content",
        namespaces={"opf": NS_OPF},
    )
    stats["rendition_layout"] = rendition_layout[0] if rendition_layout else None

    # manifest / spine
    manifest_items = opf.xpath("//opf:manifest/opf:item", namespaces={"opf": NS_OPF})
    itemrefs = opf.xpath("//opf:spine/opf:itemref", namespaces={"opf": NS_OPF})
    stats["manifest_count"] = len(manifest_items)
    stats["spine_count"] = len(itemrefs)

    id_map = {}
    href_map = {}
    manifest_hrefs = set()
    for item in manifest_items:
        iid = item.get("id")
        href = item.get("href")
        mtype = item.get("media-type")
        props = item.get("properties", "")
        if iid:
            id_map[iid] = href
        if href:
            href_map[href] = mtype
            manifest_hrefs.add(href)
            if mtype == "application/x-javascript" or href.endswith(".js"):
                issues["manifest_js"].append(href)
            if href.endswith(".webp"):
                issues["manifest_webp"].append(href)
            if "svg" in props and mtype != "image/svg+xml":
                issues["stale_svg_property"].append(href)

    # spine idref 有效性
    for ir in itemrefs:
        idref = ir.get("idref")
        if idref and idref not in id_map:
            issues["spine_idref_missing"].append(idref)

    # NCX 存在性（可选但常见）
    ncx_items = opf.xpath("//opf:item[@media-type='application/x-dtbncx+xml']", namespaces={"opf": NS_OPF})
    stats["has_ncx"] = len(ncx_items) > 0

    # 4. 遍历所有文件
    html_files = []
    css_files = []
    image_files = []
    font_files = []
    js_files = []

    for name in namelist:
        if name.endswith("/"):
            continue
        lower = name.lower()
        if lower.endswith((".html", ".xhtml", ".htm")):
            html_files.append(name)
        elif lower.endswith(".css"):
            css_files.append(name)
        elif lower.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp")):
            image_files.append(name)
        elif lower.endswith((".ttf", ".otf", ".woff", ".woff2")):
            font_files.append(name)
        elif lower.endswith(".js"):
            js_files.append(name)

    stats["html_count"] = len(html_files)
    stats["css_count"] = len(css_files)
    stats["image_count"] = len(image_files)
    stats["font_count"] = len(font_files)
    stats["js_count"] = len(js_files)

    # 5. HTML 分析
    all_img_srcs = []
    html_ids = Counter()
    for hpath in html_files:
        try:
            raw = zf.read(hpath)
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            continue

        # DOCTYPE
        if "<!DOCTYPE" not in text.upper():
            issues["missing_doctype"].append(hpath)

        # 非法自闭合标签
        if SELF_CLOSING_BAD_RE.search(text):
            issues["illegal_self_closing"].append(hpath)

        # script 标签
        if SCRIPT_TAG_RE.search(text):
            issues["html_inline_script"].append(hpath)

        # viewport (仅对漫画/插图页重要，但也常见缺失)
        if '<meta' in text and 'viewport' not in text:
            # 可能是小说，不强制报错，但记录
            pass
        elif '<meta' in text and 'viewport' in text:
            if not re.search(r'<meta[^>]*name=["\']viewport["\']', text, re.I):
                # 有 viewport 字样但格式不对
                issues["bad_viewport"].append(hpath)

        # img src 收集
        all_img_srcs.extend(IMG_SRC_RE.findall(text))

        # 解析 HTML 检查 id 重复和 lang
        try:
            tree = etree.fromstring(raw, etree.HTMLParser())
            ids = tree.xpath("//*[@id]/@id")
            for i in ids:
                html_ids[i] += 1
            lang = tree.get("lang") or tree.get("{%s}lang" % "http://www.w3.org/XML/1998/namespace")
            if not lang:
                issues["missing_html_lang"].append(hpath)
        except Exception:
            pass

    dup_ids = [i for i, c in html_ids.items() if c > 1]
    if dup_ids:
        issues["duplicate_ids"].extend(dup_ids[:5])  # 只报前5个

    # 6. 图片引用有效性
    missing_imgs = []
    for src in set(all_img_srcs):
        # 解析相对路径
        src = src.split("?")[0].split("#")[0]
        if src.startswith("http"):
            continue
        # 需要知道是在哪个 html 文件里引用的，这里简化：只检查是否在 zip 中存在
        # 实际路径需要相对于 html 文件，但我们不知道 html 路径。
        # 这里做一个近似检查：如果不在 namelist 中且不在 manifest_hrefs 中
        found = False
        for n in namelist:
            if n.endswith("/" + src) or n == src or n.replace("\\", "/").endswith("/" + src):
                found = True
                break
        if not found:
            missing_imgs.append(src)
    if missing_imgs:
        issues["missing_image_refs"].extend(missing_imgs[:10])

    # 7. CSS 分析
    for cpath in css_files:
        try:
            ctext = zf.read(cpath).decode("utf-8", errors="replace")
        except Exception:
            continue
        if FONT_FACE_RE.search(ctext):
            issues["css_font_face"].append(cpath)
        if VERTICAL_RL_RE.search(ctext):
            issues["css_vertical_rl"].append(cpath)
        # 检查 @font-face 中引用的字体文件是否存在
        for m in re.finditer(r'url\s*\(\s*["\']?([^"\')\s]+)\s*["\']?\s*\)', ctext):
            font_url = m.group(1)
            if font_url.startswith("http"):
                continue
            font_url_clean = font_url.split("?")[0]
            found = False
            for n in namelist:
                if n.endswith("/" + font_url_clean) or n == font_url_clean:
                    found = True
                    break
            if not found:
                issues["css_missing_font_file"].append(f"{cpath} -> {font_url}")

    # 8. 字体文件分析
    embedded_font_types = set()
    for fpath in font_files:
        lower = fpath.lower()
        if lower.endswith(".woff") or lower.endswith(".woff2"):
            embedded_font_types.add("woff/woff2")
        else:
            embedded_font_types.add(Path(fpath).suffix)
    stats["embedded_font_types"] = list(embedded_font_types)

    # 9. webp 图片
    webp_files = [p for p in image_files if p.lower().endswith(".webp")]
    if webp_files:
        issues["webp_images"].extend(webp_files[:10])

    # 10. JS 文件
    if js_files:
        issues["js_files"].extend(js_files[:10])

    zf.close()
    return {"issues": dict(issues), "stats": stats}


def main():
    base = Path("测试文件/自制epub")
    if not base.exists():
        # fallback 搜索
        for p in Path(".").rglob("*epub"):
            if p.is_dir() and any(f.suffix == ".epub" for f in p.iterdir()):
                base = p
                break

    epubs = sorted(base.glob("*.epub"))
    print(f"Found {len(epubs)} EPUBs in {base}")

    results = []
    for epub in epubs:
        print(f"Analyzing: {epub.name} ...")
        res = analyze_epub(str(epub))
        results.append({"file": epub.name, **res})

    # 汇总
    summary = defaultdict(int)
    for r in results:
        for k in r["issues"]:
            summary[k] += 1

    print("\n========== SUMMARY ==========")
    for k, v in sorted(summary.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}/{len(epubs)}")

    out_path = "tools/epub_analysis_report.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"summary": dict(summary), "details": results}, f, ensure_ascii=False, indent=2)
    print(f"\nDetailed report saved to: {out_path}")


if __name__ == "__main__":
    main()
