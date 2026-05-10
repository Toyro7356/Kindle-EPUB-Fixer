"""Direct Kindle-friendly EPUB conversion for normalized web novel data."""

from __future__ import annotations

import html as html_lib
import io
import os
import posixpath
import re
import shutil
import tempfile
import time
import uuid
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import lxml.etree as etree
import lxml.html as lxml_html
from PIL import Image

from .epub_validator import validate_epub
from .novel_source import NovelAsset, NovelBook, NovelChapter
from .utils import LogCallback, _default_log


@dataclass(frozen=True)
class EpubConversionOptions:
    output_path: Optional[str] = None
    output_dir: Optional[str] = None
    validate_output: bool = True


def _safe_filename(value: str, default: str = "book") -> str:
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(" .")
    return sanitized[:120] or default


def _slug(value: str, default: str = "item") -> str:
    sanitized = re.sub(r"[^0-9A-Za-z._-]+", "-", value).strip("-._")
    return sanitized[:80] or default


def _book_uuid(url: str) -> str:
    seed = url or f"urn:kindle-epub-fixer:{uuid.uuid4()}"
    return "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def _media_type_for_path(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
    }.get(suffix, "application/octet-stream")


def _asset_href(asset: NovelAsset) -> str:
    filename = _safe_filename(asset.filename, asset.id)
    return f"Images/{filename}"


def _relative_href(owner_href: str, target_href: str) -> str:
    owner_dir = posixpath.dirname(owner_href) or "."
    return posixpath.relpath(target_href, owner_dir)


def _inner_xml(element: etree._Element) -> str:
    chunks: list[str] = []
    if element.text:
        chunks.append(html_lib.escape(element.text))
    for child in element:
        chunks.append(etree.tostring(child, encoding="unicode", method="xml"))
    return "".join(chunks).strip()


def _normalise_image_asset(asset: NovelAsset) -> NovelAsset:
    suffix = Path(asset.filename).suffix.lower()
    needs_conversion = asset.media_type == "image/webp" or suffix == ".webp"
    if not needs_conversion and (asset.media_type == "image/gif" or suffix == ".gif"):
        try:
            with Image.open(io.BytesIO(asset.data)) as image:
                needs_conversion = bool(getattr(image, "is_animated", False)) or getattr(image, "n_frames", 1) > 1
        except Exception:
            needs_conversion = False
    if not needs_conversion:
        return asset

    with Image.open(io.BytesIO(asset.data)) as image:
        try:
            image.seek(0)
        except EOFError:
            pass
        frame = image.convert("RGBA")
        converted = Image.new("RGB", frame.size, "white")
        converted.paste(frame, mask=frame.getchannel("A"))
        output = io.BytesIO()
        converted.save(output, "JPEG", quality=92)

    stem = Path(asset.filename).stem or asset.id
    return NovelAsset(
        id=asset.id,
        filename=f"{stem}.jpg",
        data=output.getvalue(),
        media_type="image/jpeg",
    )


@contextmanager
def _temporary_work_dir():
    temp_root = Path(os.environ.get("KINDLE_EPUB_FIXER_TEMP_DIR") or tempfile.gettempdir())
    temp_root.mkdir(parents=True, exist_ok=True)
    temp_dir = temp_root / f"novel-epub-{uuid.uuid4().hex}"
    temp_dir.mkdir()
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


class KindleNovelEpubConverter:
    def __init__(self, log: LogCallback = _default_log) -> None:
        self.log = log

    def convert(self, book: NovelBook, options: EpubConversionOptions) -> str:
        content_chapters = [chapter for chapter in book.chapters if not chapter.is_volume]
        if not content_chapters:
            raise RuntimeError("No readable chapters were provided by the source reader")

        output_path = self._resolve_output_path(book, options)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with _temporary_work_dir() as temp_dir:
            root = temp_dir / "epub"
            self._write_epub_tree(book, root)
            self._zip_epub(root, output_path)

        if options.validate_output:
            issues = validate_epub(str(output_path), "novel")
            if issues:
                self.log("[Validation Warning] Output EPUB has issues:")
                for issue in issues:
                    self.log(f"  - {issue}")
            else:
                self.log("Output EPUB validation passed")

        return str(output_path)

    def _resolve_output_path(self, book: NovelBook, options: EpubConversionOptions) -> Path:
        if options.output_path:
            path = Path(options.output_path)
            if path.exists() and path.is_dir():
                return path / f"{_safe_filename(book.title)}.epub"
            if path.suffix.lower() != ".epub":
                return path / f"{_safe_filename(book.title)}.epub"
            return path
        if options.output_dir:
            return Path(options.output_dir) / f"{_safe_filename(book.title)}.epub"
        return Path.cwd() / "转换后" / f"{_safe_filename(book.title)}.epub"

    def _write_epub_tree(self, book: NovelBook, root: Path) -> None:
        oebps = root / "OEBPS"
        text_dir = oebps / "Text"
        style_dir = oebps / "Styles"
        image_dir = oebps / "Images"
        meta_dir = root / "META-INF"
        for directory in (text_dir, style_dir, image_dir, meta_dir):
            directory.mkdir(parents=True, exist_ok=True)

        (root / "mimetype").write_text("application/epub+zip", encoding="ascii")
        (meta_dir / "container.xml").write_text(CONTAINER_XML, encoding="utf-8")
        (style_dir / "style.css").write_text(STYLE_CSS, encoding="utf-8")

        assets = self._write_assets(book, image_dir)
        manifest_items: list[tuple[str, str, str, str]] = [
            ("nav", "nav.xhtml", "application/xhtml+xml", "nav"),
            ("ncx", "toc.ncx", "application/x-dtbncx+xml", ""),
            ("style", "Styles/style.css", "text/css", ""),
        ]
        for asset_id, href in assets.items():
            asset_properties = "cover-image" if book.cover and asset_id == book.cover.id else ""
            manifest_items.append((f"asset-{_slug(asset_id)}", href, _media_type_for_path(href), asset_properties))

        spine_ids: list[str] = []
        nav_points: list[tuple[int, str, str]] = []
        nav_items: list[tuple[str, str, bool]] = []

        intro_href = "Text/intro.xhtml"
        intro_body = self._book_intro_html(book)
        (oebps / intro_href).write_text(
            self._chapter_document("书籍信息", intro_body, intro_href, book.language, assets, show_heading=False),
            encoding="utf-8",
        )
        manifest_items.append(("intro", intro_href, "application/xhtml+xml", ""))
        spine_ids.append("intro")
        nav_points.append((1, "书籍信息", intro_href))
        nav_items.append(("书籍信息", intro_href, False))

        chapter_index = 0
        for entry in book.chapters:
            if entry.is_volume:
                continue

            chapter_index += 1
            item_id = f"chapter-{chapter_index:04d}"
            href = f"Text/chapter-{chapter_index:04d}-{_slug(entry.title, 'chapter')}.xhtml"
            (oebps / href).write_text(
                self._chapter_document(entry.title, entry.content_html, href, book.language, assets),
                encoding="utf-8",
            )
            manifest_items.append((item_id, href, "application/xhtml+xml", ""))
            spine_ids.append(item_id)
            nav_points.append((len(nav_points) + 1, entry.title, href))
            nav_items.append((entry.title, href, False))

        self._write_nav(oebps / "nav.xhtml", book, nav_items)
        self._write_ncx(oebps / "toc.ncx", book, nav_points)
        self._write_opf(oebps / "content.opf", book, manifest_items, spine_ids)

    def _write_assets(self, book: NovelBook, image_dir: Path) -> dict[str, str]:
        hrefs: dict[str, str] = {}
        seen_filenames: set[str] = set()

        all_assets = list(book.assets)
        if book.cover is not None:
            all_assets.insert(0, book.cover)

        for asset in all_assets:
            normalised = _normalise_image_asset(asset)
            filename = _safe_filename(normalised.filename, normalised.id)
            stem = Path(filename).stem
            suffix = Path(filename).suffix or ".bin"
            candidate = filename
            counter = 2
            while candidate.lower() in seen_filenames:
                candidate = f"{stem}-{counter}{suffix}"
                counter += 1
            seen_filenames.add(candidate.lower())

            path = image_dir / candidate
            path.write_bytes(normalised.data)
            hrefs[normalised.id] = f"Images/{candidate}"

        return hrefs

    def _book_intro_html(self, book: NovelBook) -> str:
        parts = []
        if book.cover is not None:
            parts.append(f'<p class="cover"><img src="asset:{html_lib.escape(book.cover.id)}" alt="cover"/></p>')
        if book.intro_html:
            parts.append(book.intro_html)
        if book.kind:
            parts.append(f"<p>分类：{html_lib.escape(book.kind)}</p>")
        if book.word_count:
            parts.append(f"<p>字数：{html_lib.escape(book.word_count)}</p>")
        if book.latest_chapter:
            parts.append(f"<p>最新章节：{html_lib.escape(book.latest_chapter)}</p>")
        if book.source_url:
            parts.append(f"<p>来源：{html_lib.escape(book.source_url)}</p>")
        return "\n".join(parts) or "<p></p>"

    def _chapter_document(
        self,
        title: str,
        body_html: str,
        owner_href: str,
        language: str,
        assets: dict[str, str],
        show_heading: bool = True,
    ) -> str:
        body = self._normalise_body_html(body_html, owner_href, assets)
        return XHTML_TEMPLATE.format(
            language=html_lib.escape(language or "zh-CN"),
            title=html_lib.escape(title),
            heading=f"  <h1>{html_lib.escape(title)}</h1>" if show_heading else "",
            body=body,
        )

    def _normalise_body_html(self, body_html: str, owner_href: str, assets: dict[str, str]) -> str:
        wrapper = lxml_html.fragment_fromstring(f"<div>{body_html or '<p></p>'}</div>", create_parent=False)
        for bad in wrapper.xpath(".//script|.//style|.//iframe|.//form"):
            parent = bad.getparent()
            if parent is not None:
                parent.remove(bad)

        for element in wrapper.iter():
            if not isinstance(element.tag, str):
                continue
            for attr in list(element.attrib):
                if attr.lower().startswith("on"):
                    element.attrib.pop(attr, None)

        for element in wrapper.xpath(".//*[@src] | .//*[@href]"):
            for attr in ("src", "href"):
                value = element.get(attr)
                if not value or not value.startswith("asset:"):
                    continue
                asset_id = value.split(":", 1)[1]
                target_href = assets.get(asset_id)
                if target_href:
                    element.set(attr, _relative_href(owner_href, target_href))
                else:
                    element.attrib.pop(attr, None)

        return _inner_xml(wrapper)

    def _write_nav(self, path: Path, book: NovelBook, nav_items: list[tuple[str, str, bool]]) -> None:
        lines = [
            '<?xml version="1.0" encoding="utf-8"?>',
            "<!DOCTYPE html>",
            f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{html_lib.escape(book.language)}" xml:lang="{html_lib.escape(book.language)}">',
            "<head>",
            f"<title>{html_lib.escape(book.title)} - 目录</title>",
            '<meta name="viewport" content="width=device-width, initial-scale=1.0"/>',
            '<link rel="stylesheet" type="text/css" href="Styles/style.css"/>',
            "</head><body>",
            '<nav epub:type="toc" id="toc"><h1>目录</h1><ol>',
        ]
        for title, href, is_volume in nav_items:
            if is_volume or not href:
                continue
            lines.append(f'<li><a href="{html_lib.escape(href)}">{html_lib.escape(title)}</a></li>')
        lines.extend(["</ol></nav>", "</body></html>"])
        path.write_text("\n".join(lines), encoding="utf-8")

    def _write_ncx(self, path: Path, book: NovelBook, nav_points: list[tuple[int, str, str]]) -> None:
        lines = [
            '<?xml version="1.0" encoding="utf-8"?>',
            '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">',
            "<head>",
            f'<meta name="dtb:uid" content="{html_lib.escape(_book_uuid(book.source_url))}"/>',
            "</head>",
            f"<docTitle><text>{html_lib.escape(book.title)}</text></docTitle>",
            "<navMap>",
        ]
        for play_order, title, href in nav_points:
            lines.extend(
                [
                    f'<navPoint id="navPoint-{play_order}" playOrder="{play_order}">',
                    f"<navLabel><text>{html_lib.escape(title)}</text></navLabel>",
                    f'<content src="{html_lib.escape(href)}"/>',
                    "</navPoint>",
                ]
            )
        lines.extend(["</navMap>", "</ncx>"])
        path.write_text("\n".join(lines), encoding="utf-8")

    def _write_opf(
        self,
        path: Path,
        book: NovelBook,
        manifest_items: list[tuple[str, str, str, str]],
        spine_ids: list[str],
    ) -> None:
        metadata = [
            '<?xml version="1.0" encoding="utf-8"?>',
            '<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="3.0">',
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">',
            f'<dc:identifier id="bookid">{html_lib.escape(_book_uuid(book.source_url))}</dc:identifier>',
            f"<dc:title>{html_lib.escape(book.title)}</dc:title>",
            f"<dc:creator>{html_lib.escape(book.author or '未知作者')}</dc:creator>",
            f"<dc:language>{html_lib.escape(book.language or 'zh-CN')}</dc:language>",
            f'<dc:source>{html_lib.escape(book.source_url)}</dc:source>',
            f'<meta property="dcterms:modified">{time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}</meta>',
        ]
        if book.cover is not None:
            metadata.append(f'<meta name="cover" content="asset-{html_lib.escape(_slug(book.cover.id))}"/>')
        metadata.append("</metadata>")

        manifest = ["<manifest>"]
        for item_id, href, media_type, properties in manifest_items:
            properties_attr = f' properties="{properties}"' if properties else ""
            manifest.append(
                f'<item id="{html_lib.escape(item_id)}" href="{html_lib.escape(href)}" '
                f'media-type="{html_lib.escape(media_type)}"{properties_attr}/>'
            )
        manifest.append("</manifest>")

        spine = ['<spine toc="ncx">']
        for item_id in spine_ids:
            spine.append(f'<itemref idref="{html_lib.escape(item_id)}"/>')
        spine.append("</spine>")
        path.write_text("\n".join(metadata + manifest + spine + ["</package>"]), encoding="utf-8")

    def _zip_epub(self, root: Path, epub_path: Path) -> None:
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.write(root / "mimetype", "mimetype", compress_type=zipfile.ZIP_STORED)
            for path in sorted(root.rglob("*")):
                if path.name == "mimetype" or path.is_dir():
                    continue
                arcname = path.relative_to(root).as_posix()
                zf.write(path, arcname, compress_type=zipfile.ZIP_DEFLATED)


CONTAINER_XML = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


STYLE_CSS = """@charset "utf-8";
body {
  font-family: sans-serif;
  line-height: 1.72;
  margin: 0 5%;
}
h1 {
  font-family: serif;
  font-size: 1.35em;
  line-height: 1.35;
  margin: 1.2em 0;
  text-align: center;
}
p {
  margin: 0.45em 0;
}
.scene-break {
  line-height: 1;
  margin: 1.25em 0;
  text-align: center;
}
.cover {
  text-align: center;
}
img {
  max-width: 100%;
  height: auto;
}
blockquote {
  border-left: 0.25em solid #aaa;
  margin: 1em 0;
  padding-left: 1em;
}
"""


XHTML_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="{language}" xml:lang="{language}">
<head>
  <title>{title}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <link rel="stylesheet" type="text/css" href="../Styles/style.css"/>
</head>
<body>
{heading}
  {body}
</body>
</html>
"""
