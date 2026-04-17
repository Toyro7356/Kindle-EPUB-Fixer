import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from .constants import NS_OPF, NS_SVG, NS_XHTML
from .epub_io import opf_dir
from .text_io import read_text_file


@dataclass
class BookProfile:
    layout_mode: str = "reflowable"
    page_count: int = 0
    has_fixed_layout_metadata: bool = False
    has_viewport_pages: bool = False
    has_svg_pages: bool = False
    has_javascript: bool = False
    has_vertical_writing: bool = False
    has_rtl_progression: bool = False
    has_kobo_adobe_markers: bool = False
    is_probably_illustrated_layout: bool = False
    svg_page_ratio: float = 0.0
    viewport_page_ratio: float = 0.0
    image_like_page_ratio: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def preserve_layout(self) -> bool:
        return (
            self.layout_mode == "pre-paginated"
            or self.has_fixed_layout_metadata
            or self.viewport_page_ratio >= 0.15
            or self.svg_page_ratio >= 0.35
            or self.image_like_page_ratio >= 0.75
            or self.has_vertical_writing
            or self.is_probably_illustrated_layout
        )


def detect_book_profile(opf_path: str) -> BookProfile:
    tree = etree.parse(opf_path)
    root = tree.getroot()
    profile = BookProfile()
    metadata = root.find(f"{{{NS_OPF}}}metadata")
    manifest = root.find(f"{{{NS_OPF}}}manifest")
    spine = root.find(f"{{{NS_OPF}}}spine")
    ns = {"opf": NS_OPF}

    if metadata is not None:
        for meta in metadata.findall(f"{{{NS_OPF}}}meta"):
            prop = (meta.get("property") or "").strip().lower()
            name = (meta.get("name") or "").strip().lower()
            text = (meta.text or "").strip().lower()
            content = (meta.get("content") or "").strip().lower()

            if prop == "rendition:layout" and text == "pre-paginated":
                profile.layout_mode = "pre-paginated"
                profile.has_fixed_layout_metadata = True
            if prop.startswith("rendition:"):
                profile.has_fixed_layout_metadata = True
            if name == "fixed-layout" and content == "true":
                profile.layout_mode = "pre-paginated"
                profile.has_fixed_layout_metadata = True
            if name == "adept.expected.resource":
                profile.has_kobo_adobe_markers = True
            if "writing-mode" in prop or "writing-mode" in name:
                if "vertical" in text or "vertical" in content:
                    profile.has_vertical_writing = True

    if spine is not None:
        if (spine.get("page-progression-direction") or "").lower() == "rtl":
            profile.has_rtl_progression = True

    if manifest is None:
        return profile

    items = manifest.xpath(
        "//opf:manifest/opf:item[@media-type='application/xhtml+xml']",
        namespaces=ns,
    )
    base_dir = Path(opf_dir(opf_path))
    viewport_pages = 0
    svg_pages = 0
    image_like_pages = 0
    js_refs = 0

    for item in items:
        href = item.get("href")
        if not href:
            continue
        file_path = base_dir / href.replace("/", os.sep)
        if not file_path.exists():
            continue
        profile.page_count += 1

        try:
            raw = read_text_file(file_path)
        except OSError:
            continue

        lowered = raw.lower()
        if "adept.expected.resource" in lowered:
            profile.has_kobo_adobe_markers = True
        if "<script" in lowered or re.search(r"\son[a-z]+\s*=", lowered):
            profile.has_javascript = True
        if "name=\"viewport\"" in lowered or "name='viewport'" in lowered:
            viewport_pages += 1
        if "writing-mode" in lowered and "vertical" in lowered:
            profile.has_vertical_writing = True

        try:
            doc = etree.parse(str(file_path))
        except etree.XMLSyntaxError:
            continue

        root_elem = doc.getroot()
        body = root_elem.find(f".//{{{NS_XHTML}}}body")
        text_len = len("".join(body.itertext()).strip()) if body is not None else 0
        img_count = len(root_elem.findall(f".//{{{NS_XHTML}}}img"))
        object_count = len(root_elem.findall(f".//{{{NS_XHTML}}}object"))
        svg_image_count = 0
        for svg in root_elem.iter(f"{{{NS_SVG}}}svg"):
            if list(svg.iter(f"{{{NS_SVG}}}image")):
                svg_image_count += 1

        if svg_image_count:
            svg_pages += 1
        if text_len < 80 and (img_count or object_count or svg_image_count):
            image_like_pages += 1

    for item in manifest.findall(f"{{{NS_OPF}}}item"):
        href = (item.get("href") or "").lower()
        media_type = (item.get("media-type") or "").lower()
        if "javascript" in media_type or href.endswith(".js"):
            js_refs += 1

    if profile.page_count:
        profile.viewport_page_ratio = viewport_pages / profile.page_count
        profile.svg_page_ratio = svg_pages / profile.page_count
        profile.image_like_page_ratio = image_like_pages / profile.page_count

    profile.has_viewport_pages = viewport_pages > 0
    profile.has_svg_pages = svg_pages > 0
    profile.has_javascript = profile.has_javascript or js_refs > 0

    if profile.layout_mode != "pre-paginated":
        if profile.viewport_page_ratio >= 0.8:
            profile.layout_mode = "pre-paginated"
            profile.notes.append("Most content pages define viewport metadata.")
        elif profile.image_like_page_ratio >= 0.8:
            profile.layout_mode = "pre-paginated"
            profile.notes.append("Most content pages are image-dominant.")

    profile.is_probably_illustrated_layout = (
        profile.page_count > 0
        and (profile.svg_page_ratio >= 0.5 or profile.image_like_page_ratio >= 0.8)
    )

    if profile.layout_mode == "pre-paginated":
        profile.notes.append("Layout should be preserved.")
    elif profile.preserve_layout:
        profile.notes.append("Layout-sensitive structure detected.")
    elif profile.has_javascript:
        profile.notes.append("Scripts detected but layout does not look fixed-layout.")

    return profile
