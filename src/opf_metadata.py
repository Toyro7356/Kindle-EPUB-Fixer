from lxml import etree

from .constants import NS_OPF


def get_declared_languages_from_root(root: etree._Element) -> list[str]:
    metadata = root.find(f"{{{NS_OPF}}}metadata")
    if metadata is None:
        return []

    languages: list[str] = []
    for child in metadata:
        if not isinstance(child.tag, str):
            continue
        if child.tag == "language" or child.tag.endswith("}language"):
            text = (child.text or "").strip().lower()
            if text:
                languages.append(text)
    return languages


def get_book_language_from_root(root: etree._Element) -> str:
    languages = get_declared_languages_from_root(root)
    return languages[0] if languages else ""


def get_book_language(opf_path: str) -> str:
    tree = etree.parse(opf_path)
    return get_book_language_from_root(tree.getroot())


def get_effective_book_language(opf_path: str, root: etree._Element | None = None) -> str:
    from .language_fix import detect_language_from_book

    root = root if root is not None else etree.parse(opf_path).getroot()
    languages = get_declared_languages_from_root(root)
    if len(languages) <= 1:
        return languages[0] if languages else (detect_language_from_book(opf_path) or "")

    detected = detect_language_from_book(opf_path)
    if detected:
        return detected.lower()
    return languages[0]
