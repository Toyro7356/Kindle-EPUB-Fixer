"""
更精确的 EPUB 批量分析器
"""
import json
import os
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote, urlparse

from lxml import etree

NS_OPF = "http://www.idpf.org/2007/opf"
NS_DC = "http://purl.org/dc/elements/1.1/"
NS_XHTML = "http://www.w3.org/1999/xhtml"


def normalize_path(base_dir: str, href: str) -> str:
    href = unquote(href)
    href = href.split("?")[0].split("#")[0]
    if href.startswith("/"):
        href = href[1:]
    else:
        href = os.path.normpath(os.path.join(base_dir, href)).replace("\\", "/")
    return href


def analyze_epub(epub_path: str) -> dict:
    issues = defaultdict(list)
    stats = {}

    try:
        zf = zipfile.ZipFile(epub_path, 'r')
    except Exception as e:
        issues["zip_error"].append(str(e))
        return {"issues": dict(issues), "stats": {}}

    namelist = set(zf.namelist())
    stats["file_count"] = len(namelist)

    # container -> OPF
    try:
        container = zf.read("META-INF/container.xml").decode("utf-8")
        m = re.search(r'full-path=["\']([^"\']+)["\']', container)
        if not m:
            issues["container_no_rootfile"].append(True)
            return dict(issues)
        opf_path = m.group(1)
    except Exception as e:
        issues["container_error"].append(str(e))
        return dict(issues)

    try:
        opf = etree.fromstring(zf.read(opf_path))
    except Exception as e:
        issues["opf_parse_error"].append(str(e))
        return dict(issues)

    opf_dir = os.path.dirname(opf_path).replace("\\", "/")

    langs = opf.xpath("//dc:language/text()", namespaces={"dc": NS_DC})
    stats["opf_language"] = langs[0] if langs else None
    if not langs:
        issues["missing_dc_language"].append(True)

    titles = opf.xpath("//dc:title/text()", namespaces={"dc": NS_DC})
    stats["title"] = titles[0] if titles else "Unknown"

    modifieds = opf.xpath("//opf:meta[@property='dcterms:modified']/text()", namespaces={"opf": NS_OPF})
    if not modifieds:
        issues["missing_dcterms_modified"].append(True)

    ppd = opf.xpath("//opf:spine/@page-progression-direction", namespaces={"opf": NS_OPF})
    stats["ppd"] = ppd[0] if ppd else "ltr"
    if ppd and ppd[0] == "rtl":
        issues["spine_rtl"].append(True)

    manifest_items = opf.xpath("//opf:manifest/opf:item", namespaces={"opf": NS_OPF})
    itemrefs = opf.xpath("//opf:spine/opf:itemref", namespaces={"opf": NS_OPF})
    stats["manifest_count"] = len(manifest_items)
    stats["spine_count"] = len(itemrefs)

    id_map = {}
    href_map = {}
    manifest_hrefs = set()
    manifest_types = {}
    for item in manifest_items:
        iid = item.get("id")
        href = item.get("href", "").replace("\\", "/")
        mtype = item.get("media-type", "")
        props = item.get("properties", "")
        if iid:
            id_map[iid] = href
        href_map[href] = mtype
        manifest_hrefs.add(href)
        manifest_types[href] = mtype
        if mtype == "application/x-javascript" or href.endswith(".js"):
            issues["manifest_js"].append(href)
        if href.endswith(".webp"):
            issues["manifest_webp"].append(href)
        if "svg" in props and mtype != "image/svg+xml":
            issues["stale_svg_property"].append(href)

    for ir in itemrefs:
        idref = ir.get("idref")
        if idref and idref not in id_map:
            issues["spine_idref_missing"].append(idref)

    ncx_items = opf.xpath("//opf:item[@media-type='application/x-dtbncx+xml']", namespaces={"opf": NS_OPF})
    stats["has_ncx"] = len(ncx_items) > 0

    # Collect files by type
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

    # 检查超大图片
    large_images = []
    for img_path in image_files:
        info = zf.getinfo(img_path)
        if info.file_size > 4 * 1024 * 1024:
            large_images.append(f"{img_path} ({info.file_size // 1024 // 1024}MB)")
    if large_images:
        issues["large_images"].extend(large_images[:5])

    # HTML 分析
    html_ids_counter = defaultdict(int)
    bad_namespaces = []
    missing_doctype = []
    illegal_self_closing = []
    inline_scripts = []
    missing_lang = []
    bad_viewports = []

    all_missing_imgs = set()
    all_img_srcs = []

    for hpath in html_files:
        try:
            raw = zf.read(hpath)
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            continue

        hdir = os.path.dirname(hpath).replace("\\", "/")

        if "<!DOCTYPE" not in text.upper():
            missing_doctype.append(hpath)

        if re.search(r"<(p|div|span|h[1-6]|li|td|th|tr|tbody|thead|tfoot|section|article|aside|header|footer|main|nav|figure|figcaption|em|strong|b|i|u|s|small|sub|sup|mark|ruby|rt|rp|wbr)(\s+[^>]*)?/>", text, re.I):
            illegal_self_closing.append(hpath)

        if re.search(r'<script\b', text, re.I):
            inline_scripts.append(hpath)

        # viewport
        if '<meta' in text and 'viewport' in text:
            if not re.search(r'<meta[^>]*name=["\']viewport["\']', text, re.I):
                bad_viewports.append(hpath)

        # img src 精确检查
        for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', text, re.I):
            src = m.group(1)
            all_img_srcs.append(src)
            if src.startswith("http"):
                continue
            norm = normalize_path(hdir, src)
            if norm not in namelist:
                all_missing_imgs.add(f"{hpath} -> {src} (resolved: {norm})")

        try:
            tree = etree.fromstring(raw, etree.HTMLParser())
            root = tree
            if root.tag and root.tag.startswith("{") and root.tag != "{http://www.w3.org/1999/xhtml}html":
                bad_namespaces.append(f"{hpath}: {root.tag}")
            ids = tree.xpath("//*[@id]/@id")
            for i in ids:
                html_ids_counter[i] += 1
            lang = tree.get("lang") or tree.get("{%s}lang" % "http://www.w3.org/XML/1998/namespace")
            if not lang:
                missing_lang.append(hpath)
        except Exception:
            pass

    if missing_doctype:
        issues["missing_doctype"].extend(missing_doctype[:10])
    if illegal_self_closing:
        issues["illegal_self_closing"].extend(illegal_self_closing[:10])
    if inline_scripts:
        issues["html_inline_script"].extend(inline_scripts[:10])
    if bad_viewports:
        issues["bad_viewport"].extend(bad_viewports[:10])
    if missing_lang:
        issues["missing_html_lang"].extend(missing_lang[:10])
    if bad_namespaces:
        issues["bad_namespace"].extend(bad_namespaces[:5])

    dup_ids = [i for i, c in html_ids_counter.items() if c > 1]
    if dup_ids:
        issues["duplicate_ids"].extend(dup_ids[:10])

    if all_missing_imgs:
        issues["missing_image_refs"].extend(sorted(all_missing_imgs)[:10])

    # CSS 分析
    css_font_face_files = []
    css_vertical_files = []
    css_missing_fonts = []
    css_kindle_unsafe = []
    for cpath in css_files:
        try:
            ctext = zf.read(cpath).decode("utf-8", errors="replace")
        except Exception:
            continue
        cdir = os.path.dirname(cpath).replace("\\", "/")

        if re.search(r'@font-face\s*\{', ctext):
            css_font_face_files.append(cpath)
        if re.search(r'writing-mode\s*:\s*vertical-rl', ctext):
            css_vertical_files.append(cpath)

        for m in re.finditer(r'url\s*\(\s*["\']?([^"\')\s]+)\s*["\']?\s*\)', ctext):
            font_url = m.group(1)
            if font_url.startswith("http"):
                continue
            norm = normalize_path(cdir, font_url)
            if norm not in namelist and not norm.endswith((".ttf", ".otf", ".woff", ".woff2")):
                # 只关心字体文件
                continue
            if norm not in namelist:
                css_missing_fonts.append(f"{cpath} -> {font_url}")

        # Kindle 不友好的 CSS 属性
        unsafe_props = [
            (r'position\s*:\s*fixed', 'position:fixed'),
            (r'position\s*:\s*sticky', 'position:sticky'),
            (r'float\s*:', 'float'),
            (r'z-index\s*:', 'z-index'),
            (r'overflow\s*:\s*(?!visible|auto)\w+', 'overflow-non-default'),
            (r'-webkit-', 'webkit-prefix'),
            (r'-moz-', 'moz-prefix'),
            (r'box-shadow\s*:', 'box-shadow'),
            (r'text-shadow\s*:', 'text-shadow'),
            (r'animation\s*:', 'animation'),
            (r'transform\s*:', 'transform'),
            (r'transition\s*:', 'transition'),
            (r'cursor\s*:', 'cursor'),
        ]
        found_unsafe = []
        for pattern, name in unsafe_props:
            if re.search(pattern, ctext, re.I):
                found_unsafe.append(name)
        if found_unsafe:
            css_kindle_unsafe.append(f"{cpath}: {', '.join(found_unsafe[:5])}")

    if css_font_face_files:
        issues["css_font_face"] = css_font_face_files
    if css_vertical_files:
        issues["css_vertical_rl"] = css_vertical_files
    if css_missing_fonts:
        issues["css_missing_font_file"].extend(css_missing_fonts[:10])
    if css_kindle_unsafe:
        issues["css_kindle_unsafe"].extend(css_kindle_unsafe[:10])

    # webp
    webp_files = [p for p in image_files if p.lower().endswith(".webp")]
    if webp_files:
        issues["webp_images"].extend(webp_files[:10])

    # js
    if js_files:
        issues["js_files"].extend(js_files[:10])

    zf.close()
    return {"issues": dict(issues), "stats": stats}


def main():
    base = None
    for p in Path(".").rglob("*epub"):
        if p.is_dir() and any(f.suffix == ".epub" for f in p.iterdir()):
            base = p
            break

    if base is None:
        print("No epub directory found")
        return

    epubs = sorted(base.glob("*.epub"))
    print(f"Found {len(epubs)} EPUBs in {base}")

    results = []
    for epub in epubs:
        print(f"Analyzing: {epub.name} ...")
        res = analyze_epub(str(epub))
        results.append({"file": epub.name, **res})

    summary = defaultdict(int)
    for r in results:
        for k in r["issues"]:
            summary[k] += 1

    print("\n========== SUMMARY ==========")
    for k, v in sorted(summary.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}/{len(epubs)}")

    out_path = "tools/epub_analysis_report_v2.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"summary": dict(summary), "details": results}, f, ensure_ascii=False, indent=2)
    print(f"\nDetailed report saved to: {out_path}")


if __name__ == "__main__":
    main()
