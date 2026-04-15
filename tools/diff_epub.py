#!/usr/bin/env python3
"""
对比原始 EPUB 与处理后 EPUB 的差异。
用法:
    python tools/diff_epub.py 原始.epub 处理后.epub
"""

import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


def _find_opf(zf: zipfile.ZipFile) -> str:
    c = ET.fromstring(zf.read("META-INF/container.xml"))
    for rf in c.iter():
        if rf.tag.endswith("rootfile"):
            fp = rf.get("full-path")
            if fp:
                return fp
    raise ValueError("container.xml 中未找到 rootfile")


def _get_meta_dict(zf: zipfile.ZipFile, opf_path: str) -> dict:
    opf = zf.read(opf_path).decode("utf-8")
    tree = ET.fromstring(opf)
    meta = {}
    for elem in tree.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag == "meta":
            name = elem.get("name") or elem.get("property") or ""
            val = elem.get("content") or (elem.text or "").strip()
            meta[name] = val
        elif tag == "language":
            meta["dc:language"] = (elem.text or "").strip()
    return meta


def _get_manifest_files(zf: zipfile.ZipFile, opf_path: str) -> set:
    opf = zf.read(opf_path).decode("utf-8")
    tree = ET.fromstring(opf)
    files = set()
    opf_dir = Path(opf_path).parent.as_posix()
    for elem in tree.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag == "item":
            href = elem.get("href")
            if href:
                resolved = (Path(opf_dir) / href).as_posix() if opf_dir and opf_dir != "." else href
                files.add(resolved)
    return files


def diff_epub(original: str, processed: str) -> None:
    print(f"=== Diff: {Path(original).name} -> {Path(processed).name} ===\n")

    with zipfile.ZipFile(original, "r") as z1, zipfile.ZipFile(processed, "r") as z2:
        opf1 = _find_opf(z1)
        opf2 = _find_opf(z2)

        meta1 = _get_meta_dict(z1, opf1)
        meta2 = _get_meta_dict(z2, opf2)

        files1 = set(z1.namelist())
        files2 = set(z2.namelist())

        # 1. 文件数量 / 大小
        size1 = sum(info.file_size for info in z1.infolist())
        size2 = sum(info.file_size for info in z2.infolist())
        print(f"文件数: {len(files1)} -> {len(files2)}")
        print(f"总大小: {size1 // 1024} KB -> {size2 // 1024} KB\n")

        # 2. 新增 / 删除的文件
        added = files2 - files1
        removed = files1 - files2
        if added:
            print(f"新增文件 ({len(added)}):")
            for f in sorted(added)[:20]:
                print(f"  + {f}")
            if len(added) > 20:
                print(f"  ... 等共 {len(added)} 个")
            print()
        if removed:
            print(f"删除文件 ({len(removed)}):")
            for f in sorted(removed)[:20]:
                print(f"  - {f}")
            if len(removed) > 20:
                print(f"  ... 等共 {len(removed)} 个")
            print()

        # 3. 元数据变化
        added_meta = {k: v for k, v in meta2.items() if meta1.get(k) != v}
        removed_meta = {k: v for k, v in meta1.items() if meta2.get(k) != v}

        if added_meta:
            print("新增/修改的元数据:")
            for k in sorted(added_meta):
                old = meta1.get(k, "<缺失>")
                new = added_meta[k]
                if old != new:
                    print(f"  {k}: {old} -> {new}")
                else:
                    print(f"  {k}={new}")
            print()
        if removed_meta and not added_meta:
            print("移除的元数据:")
            for k in sorted(removed_meta):
                print(f"  - {k}={removed_meta[k]}")
            print()

        # 4. manifest 中新增/删除的引用
        m1 = _get_manifest_files(z1, opf1)
        m2 = _get_manifest_files(z2, opf2)
        m_added = m2 - m1
        m_removed = m1 - m2
        if m_added:
            print(f"manifest 新增引用 ({len(m_added)}):")
            for f in sorted(m_added)[:10]:
                print(f"  + {f}")
            if len(m_added) > 10:
                print(f"  ... 等共 {len(m_added)} 个")
            print()
        if m_removed:
            print(f"manifest 移除引用 ({len(m_removed)}):")
            for f in sorted(m_removed)[:10]:
                print(f"  - {f}")
            if len(m_removed) > 10:
                print(f"  ... 等共 {len(m_removed)} 个")
            print()

        if not any([added, removed, added_meta, removed_meta, m_added, m_removed]):
            print("未发现显著差异。\n")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python tools/diff_epub.py <original.epub> <processed.epub>")
        sys.exit(1)
    diff_epub(sys.argv[1], sys.argv[2])
