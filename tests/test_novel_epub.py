from __future__ import annotations

import base64
import tempfile
import unittest
import zipfile
from pathlib import Path

import lxml.etree as etree

from src.novel_epub import EpubConversionOptions, KindleNovelEpubConverter
from src.novel_source import NovelAsset, NovelBook, NovelChapter


OPF_NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
}


class NovelEpubMetadataTests(unittest.TestCase):
    def test_writes_metadata_and_standard_cover_page(self) -> None:
        cover = NovelAsset(
            id="cover",
            filename="cover.png",
            data=base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            ),
            media_type="image/png",
        )
        book = NovelBook(
            title="测试小说",
            author="测试作者",
            source_url="https://masiro.me/admin/novelView?novel_id=1",
            description="这是小说简介。",
            subjects=("异世界", "奇幻"),
            translators=("译者甲", "译者乙"),
            publisher="Masiro",
            status="连载中",
            kind="连载中 / 异世界 / 奇幻",
            cover=cover,
            chapters=[NovelChapter(title="第一话", content_html="<p>正文</p>")],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "book.epub"
            KindleNovelEpubConverter(lambda message: None).convert(
                book,
                EpubConversionOptions(output_path=str(output_path), validate_output=False),
            )

            with zipfile.ZipFile(output_path) as epub:
                names = set(epub.namelist())
                opf = etree.fromstring(epub.read("OEBPS/content.opf"))
                cover_page = etree.fromstring(epub.read("OEBPS/Text/cover.xhtml"))
                intro_page = etree.fromstring(epub.read("OEBPS/Text/intro.xhtml"))

        self.assertIn("OEBPS/Images/cover.png", names)
        self.assertEqual(opf.xpath("string(opf:metadata/dc:title)", namespaces=OPF_NS), "测试小说")
        self.assertEqual(opf.xpath("string(opf:metadata/dc:creator)", namespaces=OPF_NS), "测试作者")
        self.assertEqual(opf.xpath("string(opf:metadata/dc:description)", namespaces=OPF_NS), "这是小说简介。")
        self.assertEqual(opf.xpath("string(opf:metadata/dc:publisher)", namespaces=OPF_NS), "Masiro")
        self.assertEqual(
            opf.xpath("opf:metadata/dc:subject/text()", namespaces=OPF_NS),
            ["异世界", "奇幻"],
        )
        self.assertEqual(
            opf.xpath("opf:metadata/dc:contributor/text()", namespaces=OPF_NS),
            ["译者甲", "译者乙"],
        )
        self.assertEqual(
            opf.xpath("string(opf:manifest/opf:item[@properties='cover-image']/@href)", namespaces=OPF_NS),
            "Images/cover.png",
        )
        self.assertEqual(
            opf.xpath("string(opf:manifest/opf:item[@id='cover-page']/@href)", namespaces=OPF_NS),
            "Text/cover.xhtml",
        )
        self.assertEqual(
            opf.xpath("string(opf:spine/opf:itemref[1]/@idref)", namespaces=OPF_NS),
            "cover-page",
        )
        self.assertEqual(
            opf.xpath("string(opf:guide/opf:reference[@type='cover']/@href)", namespaces=OPF_NS),
            "Text/cover.xhtml",
        )
        self.assertEqual(
            cover_page.xpath("string(//*[local-name()='img']/@src)"),
            "../Images/cover.png",
        )
        self.assertFalse(intro_page.xpath("//*[local-name()='img']"))
        intro_text = "".join(intro_page.itertext())
        self.assertIn("状态：连载中", intro_text)
        self.assertIn("翻译：译者甲、译者乙", intro_text)


if __name__ == "__main__":
    unittest.main()
