from lxml import etree

from .constants import NS_OPF
from .content_analysis import ContentAnalysis, analyze_content


def detect_book_type(opf_path: str, content_analysis: ContentAnalysis | None = None) -> str:
    tree = etree.parse(opf_path)
    root = tree.getroot()

    metadata = root.find(f"{{{NS_OPF}}}metadata")
    if metadata is not None:
        for meta in metadata.findall(f"{{{NS_OPF}}}meta"):
            if meta.get("property") == "rendition:layout":
                if (meta.text or "").strip().lower() == "pre-paginated":
                    return "comic"

    content = content_analysis or analyze_content(opf_path)

    # When the whole book clearly contains a lot of flowing text, prefer novel
    # so illustrated novels do not get misclassified as comics.
    if content.page_count > 0 and (content.total_p_count >= 50 or content.total_text_len >= 15000):
        return "novel"

    # Only count low-text SVG pages as comic-like pages.
    if content.page_count > 0 and content.comic_like_svg_page_ratio >= 0.85:
        return "comic"
    return "novel"
