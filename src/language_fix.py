import os
import re
from pathlib import Path
from typing import Optional

from lxml import etree

from .constants import NS_OPF, NS_XHTML
from .epub_io import opf_dir
from .text_io import read_text_file
from .utils import write_xhtml_doc


# 简体/繁体差异字（在另一种文体中几乎不会出现）
_SC_DIFF_CHARS = set(
    "这来个为从见说时会长们与门书后过对让应该问听写点爱电话里么"
    "国兴卫习产买亏云亚仓儿党兰关养军农决冻净击处务协厂厅历压参"
    "发变台叶吓启员园场坏块坚坛垫壳壶备复头夹夺奖奥妆妇妈妩姗孙"
    "学宝实宠审宫宽宾对寻导寿将尔尝层属岗岛峡币帅师帐帧帮常干并"
    "广庄庆库应废开异弃张弥弯弹强归当录彦彻征径忆忏志忧念总怼怃"
    "怅恳恶恼悬悫悦悮悯惊惨惩惫惭惮惯愤愿憔"
)
_TC_DIFF_CHARS = set(
    "這來個為從見說時會長們與門書後過對讓應該問聽寫點愛電話裡麼"
    "國興衛習產買虧雲亞倉兒黨蘭關養軍農決凍淨擊處務協廠廳歷壓參"
    "發變臺葉嚇啟員園場壞塊堅壇墊殼壺備復頭夾奪獎奧妝婦媽嫵姍孫"
    "學寶實寵審宮寬賓對尋導壽將爾嘗層屬崗島峽幣帥師帳幀幫常幹並"
    "廣莊慶庫應廢開異棄張彌彎彈強歸當錄彥徹徵徑憶懺誌憂唸總懟憮"
    "悵懇惡惱懸慤悅悞憫驚慘懲憊慚憚慣憤願憭"
)


def _detect_language(text: str) -> Optional[str]:
    """
    根据文本字符范围粗略判断语言，并在中文内进一步区分简体/繁体。
    返回 'zh-CN' | 'zh-TW' | 'ja' | 'ko' | None
    """
    if not text:
        return None

    # 只取 CJK / 假名 / 韩文相关字符做判断
    hiragana = re.findall(r"[\u3040-\u309F]", text)
    katakana = re.findall(r"[\u30A0-\u30FF]", text)
    hangul = re.findall(r"[\uAC00-\uD7A3\u1100-\u11FF\u3130-\u318F]", text)
    cjk = re.findall(r"[\u4E00-\u9FFF\u3400-\u4DBF]", text)

    ja_count = len(hiragana) + len(katakana)
    ko_count = len(hangul)
    zh_count = len(cjk)
    total = len(text)

    # 日文：假名足够多
    if ja_count >= 10 and ja_count / max(total, 1) > 0.02:
        return "ja"

    # 韩文：Hangul 足够多
    if ko_count >= 10 and ko_count / max(total, 1) > 0.02:
        return "ko"

    # 中文：CJK 汉字足够多（且假名极少）
    if zh_count >= 50 or (zh_count >= 10 and ja_count < 5):
        sc_count = sum(1 for c in text if c in _SC_DIFF_CHARS)
        tc_count = sum(1 for c in text if c in _TC_DIFF_CHARS)
        # 繁体差异字显著多于简体
        if tc_count > sc_count * 2:
            return "zh-TW"
        # 简体差异字显著多于繁体
        if sc_count > tc_count * 2:
            return "zh-CN"
        # 无法明确区分时回退到通用中文
        return "zh"

    return None


def _get_all_xhtml_text(opf_path: str) -> str:
    base_dir = Path(opf_dir(opf_path))
    tree = etree.parse(opf_path)
    items = tree.xpath(
        "//opf:manifest/opf:item[@media-type='application/xhtml+xml']",
        namespaces={"opf": NS_OPF},
    )
    chunks: list[str] = []
    for item in items:
        href = item.get("href")
        if not href:
            continue
        fp = base_dir / href.replace("/", os.sep)
        if not fp.exists():
            continue
        try:
            doc = etree.parse(str(fp))
            body = doc.getroot().find(f".//{{{NS_XHTML}}}body")
            if body is not None:
                chunks.append("".join(body.itertext()))
        except etree.XMLSyntaxError:
            # 若解析失败，回退到正则提取文本
            try:
                raw = read_text_file(fp)
                txt = re.sub(r"<[^>]+>", "", raw)
                chunks.append(txt)
            except Exception:
                pass
    return "\n".join(chunks)


def fix_language_tags(opf_path: str) -> bool:
    """
    检测全书实际语言，并修正 OPF 中的 dc:language 以及所有 XHTML 中的 xml:lang/lang。
    返回是否进行了修改。
    """
    detected = _detect_language(_get_all_xhtml_text(opf_path))
    if not detected:
        return False

    base_dir = Path(opf_dir(opf_path))
    tree = etree.parse(opf_path)
    root = tree.getroot()
    nsmap = {"opf": NS_OPF}
    modified = False

    metadata = root.find(f"{{{NS_OPF}}}metadata")
    if metadata is not None:
        # 查找 dc:language（带命名空间）
        dc_lang = metadata.find(f"{{{NS_OPF}}}language")
        # 查找无命名空间的 language（某些非标准 EPUB）
        if dc_lang is None:
            for child in metadata:
                if child.tag == "language" or child.tag.endswith("}language"):
                    dc_lang = child
                    break

        if dc_lang is not None:
            current = (dc_lang.text or "").strip().lower()
            if current != detected:
                dc_lang.text = detected
                modified = True
        else:
            # 没有 language 元素，创建一个
            dc_lang = etree.SubElement(metadata, f"{{{NS_OPF}}}language")
            dc_lang.text = detected
            modified = True

    if modified:
        tree.write(opf_path, encoding="utf-8", xml_declaration=True)

    # 同时修正所有 XHTML 文件的 html 标签语言属性
    items = tree.xpath(
        "//opf:manifest/opf:item[@media-type='application/xhtml+xml']",
        namespaces=nsmap,
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
        html_elem = doc.getroot()
        changed = False
        if html_elem.get("{http://www.w3.org/XML/1998/namespace}lang") not in (detected, f"{detected}-CN", f"{detected}-TW", f"{detected}-Hant", f"{detected}-Hans"):
            html_elem.set("{http://www.w3.org/XML/1998/namespace}lang", detected)
            changed = True
        if html_elem.get("lang") not in (detected, f"{detected}-CN", f"{detected}-TW", f"{detected}-Hant", f"{detected}-Hans"):
            html_elem.set("lang", detected)
            changed = True
        if changed:
            write_xhtml_doc(doc, fp)

    return modified
