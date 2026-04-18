from dataclasses import dataclass, field

from lxml import etree

from .constants import NS_OPF
from .content_analysis import ContentAnalysis, analyze_content


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


def detect_book_profile(opf_path: str, content_analysis: ContentAnalysis | None = None) -> BookProfile:
    tree = etree.parse(opf_path)
    root = tree.getroot()
    profile = BookProfile()
    metadata = root.find(f"{{{NS_OPF}}}metadata")
    manifest = root.find(f"{{{NS_OPF}}}manifest")
    spine = root.find(f"{{{NS_OPF}}}spine")
    analysis = content_analysis or analyze_content(opf_path)

    if metadata is not None:
        for meta in metadata.findall(f"{{{NS_OPF}}}meta"):
            prop = (meta.get("property") or "").strip().lower()
            name = (meta.get("name") or "").strip().lower()
            text = (meta.text or "").strip().lower()
            meta_content = (meta.get("content") or "").strip().lower()

            if prop == "rendition:layout" and text == "pre-paginated":
                profile.layout_mode = "pre-paginated"
                profile.has_fixed_layout_metadata = True
            if name == "fixed-layout" and meta_content == "true":
                profile.layout_mode = "pre-paginated"
                profile.has_fixed_layout_metadata = True
            if name == "adept.expected.resource":
                profile.has_kobo_adobe_markers = True
            if "writing-mode" in prop or "writing-mode" in name:
                if "vertical" in text or "vertical" in meta_content:
                    profile.has_vertical_writing = True

    if spine is not None:
        if (spine.get("page-progression-direction") or "").lower() == "rtl":
            profile.has_rtl_progression = True

    if manifest is None:
        return profile

    profile.page_count = analysis.page_count
    profile.viewport_page_ratio = analysis.viewport_page_ratio
    profile.svg_page_ratio = analysis.svg_page_ratio
    profile.image_like_page_ratio = analysis.image_like_page_ratio
    profile.has_viewport_pages = analysis.viewport_pages > 0
    profile.has_svg_pages = analysis.svg_pages > 0
    profile.has_javascript = profile.has_javascript or analysis.has_javascript_markup or analysis.js_manifest_refs > 0
    profile.has_vertical_writing = profile.has_vertical_writing or analysis.has_vertical_writing
    profile.has_kobo_adobe_markers = profile.has_kobo_adobe_markers or analysis.has_kobo_marker_text

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
