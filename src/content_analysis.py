import os
import re
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from .constants import NS_OPF, NS_SVG, NS_XHTML
from .epub_io import opf_dir
from .text_io import read_text_file


@dataclass(frozen=True)
class PageAnalysis:
    text_len: int
    p_count: int
    img_count: int
    object_count: int
    has_svg_image: bool
    has_viewport_meta: bool
    has_javascript_markup: bool
    has_vertical_writing: bool
    has_kobo_marker_text: bool

    @property
    def is_image_like(self) -> bool:
        return self.text_len < 80 and (self.img_count or self.object_count or self.has_svg_image)


@dataclass(frozen=True)
class ContentAnalysis:
    page_count: int
    viewport_pages: int
    svg_pages: int
    comic_like_svg_pages: int
    image_like_pages: int
    total_text_len: int
    total_p_count: int
    has_javascript_markup: bool
    has_vertical_writing: bool
    has_kobo_marker_text: bool
    js_manifest_refs: int

    @property
    def viewport_page_ratio(self) -> float:
        return self.viewport_pages / self.page_count if self.page_count else 0.0

    @property
    def svg_page_ratio(self) -> float:
        return self.svg_pages / self.page_count if self.page_count else 0.0

    @property
    def comic_like_svg_page_ratio(self) -> float:
        return self.comic_like_svg_pages / self.page_count if self.page_count else 0.0

    @property
    def image_like_page_ratio(self) -> float:
        return self.image_like_pages / self.page_count if self.page_count else 0.0


def analyze_content(opf_path: str) -> ContentAnalysis:
    tree = etree.parse(opf_path)
    root = tree.getroot()
    manifest = root.find(f"{{{NS_OPF}}}manifest")
    if manifest is None:
        return ContentAnalysis(
            page_count=0,
            viewport_pages=0,
            svg_pages=0,
            comic_like_svg_pages=0,
            image_like_pages=0,
            total_text_len=0,
            total_p_count=0,
            has_javascript_markup=False,
            has_vertical_writing=False,
            has_kobo_marker_text=False,
            js_manifest_refs=0,
        )

    ns = {"opf": NS_OPF}
    items = manifest.xpath(
        "//opf:manifest/opf:item[@media-type='application/xhtml+xml']",
        namespaces=ns,
    )
    base_dir = Path(opf_dir(opf_path))

    page_count = 0
    viewport_pages = 0
    svg_pages = 0
    comic_like_svg_pages = 0
    image_like_pages = 0
    total_text_len = 0
    total_p_count = 0
    has_javascript_markup = False
    has_vertical_writing = False
    has_kobo_marker_text = False

    for item in items:
        href = item.get("href")
        if not href:
            continue
        file_path = base_dir / href.replace("/", os.sep)
        if not file_path.exists():
            continue
        page_count += 1

        try:
            raw = read_text_file(file_path)
        except OSError:
            continue

        lowered = raw.lower()
        has_viewport_meta = "name=\"viewport\"" in lowered or "name='viewport'" in lowered
        has_script = "<script" in lowered or re.search(r"\son[a-z]+\s*=", lowered) is not None
        has_vertical = "writing-mode" in lowered and "vertical" in lowered
        has_kobo_marker = "adept.expected.resource" in lowered

        has_javascript_markup = has_javascript_markup or has_script
        has_vertical_writing = has_vertical_writing or has_vertical
        has_kobo_marker_text = has_kobo_marker_text or has_kobo_marker
        if has_viewport_meta:
            viewport_pages += 1

        try:
            doc = etree.parse(str(file_path))
        except etree.XMLSyntaxError:
            continue

        root_elem = doc.getroot()
        body = root_elem.find(f".//{{{NS_XHTML}}}body")
        p_count = len(body.findall(f".//{{{NS_XHTML}}}p")) if body is not None else 0
        text_len = len("".join(body.itertext()).strip()) if body is not None else 0
        img_count = len(root_elem.findall(f".//{{{NS_XHTML}}}img"))
        object_count = len(root_elem.findall(f".//{{{NS_XHTML}}}object"))
        has_svg_image = False
        for svg in root_elem.iter(f"{{{NS_SVG}}}svg"):
            if list(svg.iter(f"{{{NS_SVG}}}image")):
                has_svg_image = True
                break

        total_p_count += p_count
        total_text_len += text_len
        if has_svg_image:
            svg_pages += 1
            if p_count <= 2 and text_len <= 300:
                comic_like_svg_pages += 1
        if text_len < 80 and (img_count or object_count or has_svg_image):
            image_like_pages += 1

    js_manifest_refs = 0
    for item in manifest.findall(f"{{{NS_OPF}}}item"):
        href = (item.get("href") or "").lower()
        media_type = (item.get("media-type") or "").lower()
        if "javascript" in media_type or href.endswith(".js"):
            js_manifest_refs += 1

    return ContentAnalysis(
        page_count=page_count,
        viewport_pages=viewport_pages,
        svg_pages=svg_pages,
        comic_like_svg_pages=comic_like_svg_pages,
        image_like_pages=image_like_pages,
        total_text_len=total_text_len,
        total_p_count=total_p_count,
        has_javascript_markup=has_javascript_markup,
        has_vertical_writing=has_vertical_writing,
        has_kobo_marker_text=has_kobo_marker_text,
        js_manifest_refs=js_manifest_refs,
    )
