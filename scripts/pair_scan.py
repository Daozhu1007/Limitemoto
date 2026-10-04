#!/usr/bin/env python3
"""pair_scan.py — 手元素材目录的 照片↔视频 配对扫描器

原理（2026-10-03 实测验证）：
  - 小米互传/相册导出的图片，文件名和 mtime 都是传输时刻，唯一可信的是 EXIF DateTimeOriginal
  - 相机视频文件名 VID_YYYYMMDD_HHMMSS = 录制开始时刻；mvhd 时长可得结束时刻
  - 用户习惯：录完视频紧接着截图/拍照，照片时间 ≈ 视频结束后 1~6 秒
  - 视频的文件 mtime 恰为录制结束时刻，可作交叉验证（若目录整体被复制且未保留 mtime 则失效）

用法:
  python pair_scan.py <目录>                     # 结果 JSON 打印到 stdout
  python pair_scan.py <目录> --out scan.json     # 同时写入文件
  python pair_scan.py <目录> --tolerance 15      # 放宽配对窗口（默认: 照片 ∈ [视频结束-3s, +10s]）

输出 JSON: images[] / videos[] / pairs[] / unpaired_images / unpaired_videos
依赖: pillow (EXIF)；视频时长为纯 Python mvhd 解析，无 ffmpeg 依赖。
"""

import argparse
import datetime
import json
import os
import re
import struct
import sys

IMG_EXTS = {".jpg", ".jpeg", ".png"}
VID_EXTS = {".mp4", ".mov"}
VID_RE = re.compile(r"VID_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})")


def exif_datetime(path):
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
    except ImportError:
        sys.exit("需要 pillow:  pip install pillow")
    try:
        img = Image.open(path)
        raw = img._getexif() or {}
    except Exception as e:
        return None, f"EXIF读取失败: {e}"
    tags = {TAGS.get(k, k): v for k, v in raw.items()}
    for key in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
        v = tags.get(key)
        if v:
            return v, None
    return None, "无EXIF时间"


def parse_exif_dt(s):
    try:
        return datetime.datetime.strptime(s, "%Y:%m:%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def mp4_duration(path):
    """纯 Python 解析 moov/mvhd 得到时长（秒），失败返回 None。"""
    try:
        with open(path, "rb") as f:
            fsize = os.path.getsize(path)
            pos = 0
            while pos < fsize:
                f.seek(pos)
                hdr = f.read(8)
                if len(hdr) < 8:
                    break
                size, typ = struct.unpack(">I4s", hdr)
                typ = typ.decode("latin1")
                if size == 1:
                    size = struct.unpack(">Q", f.read(8))[0]
                elif size == 0:
                    size = fsize - pos
                if size < 8:
                    break
                if typ == "moov":
                    end, cpos = pos + size, pos + 8
                    while cpos < end:
                        f.seek(cpos)
                        ch = f.read(8)
                        if len(ch) < 8:
                            break
                        csize, ctyp = struct.unpack(">I4s", ch)
                        ctyp = ctyp.decode("latin1")
                        if csize == 1:
                            csize = struct.unpack(">Q", f.read(8))[0]
                        if csize < 8:
                            break
                        if ctyp == "mvhd":
                            f.seek(cpos + 8)
                            data = f.read(min(csize - 8, 64))
                            ver = data[0]
                            if ver == 1:
                                timescale = struct.unpack(">I", data[20:24])[0]
                                dur = struct.unpack(">Q", data[24:32])[0]
                            else:
                                timescale = struct.unpack(">I", data[12:16])[0]
                                dur = struct.unpack(">I", data[16:20])[0]
                            if timescale:
                                return dur / timescale
                        cpos += csize
                pos += size
    except OSError:
        return None
    return None


def iso(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def main():
    ap = argparse.ArgumentParser(description="手元照片↔视频配对扫描")
    ap.add_argument("directory")
    ap.add_argument("--out", help="同时把 JSON 写入此路径")
    ap.add_argument("--tolerance", type=float, default=10.0,
                    help="照片晚于视频结束的最大秒数 (默认 10)")
    args = ap.parse_args()
    d = args.directory
    if not os.path.isdir(d):
        sys.exit(f"目录不存在: {d}")

    images, videos, notes = [], [], []
    for name in sorted(os.listdir(d)):
        p = os.path.join(d, name)
        if not os.path.isfile(p):
            continue
        ext = os.path.splitext(name)[1].lower()
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(p))
        if ext in IMG_EXTS:
            ex_s, err = exif_datetime(p)
            if err:
                notes.append(f"{name}: {err}")
            images.append({"file": name, "exif_time": ex_s,
                           "dt": parse_exif_dt(ex_s), "mtime": iso(mtime)})
        elif ext in VID_EXTS:
            m = VID_RE.search(name)
            dur = mp4_duration(p)
            if m and dur:
                start = datetime.datetime(*map(int, m.groups()))
                end = start + datetime.timedelta(seconds=dur)
                src = "filename+mvhd"
            elif dur:
                # 已改名/无时间戳文件名: mtime ≈ 录制结束时刻（复制保留 mtime 时成立）
                end = mtime
                start = end - datetime.timedelta(seconds=dur)
                src = "mtime-mvhd"
            else:
                start = end = None
                src = None
            entry = {"file": name, "start_time": iso(start),
                     "duration_s": round(dur, 1) if dur else None,
                     "end_time": iso(end), "mtime": iso(mtime)}
            if src == "mtime-mvhd":
                notes.append(f"{name}: 文件名无时间戳，end 取自 mtime（要求复制保留 mtime）")
            if end and mtime and src == "filename+mvhd" and abs((mtime - end).total_seconds()) > 30:
                notes.append(f"{name}: mtime 与 推算结束时刻差 >30s，mtime 可能未保留")
            videos.append(entry)

    # 贪心就近配对: delta = 照片EXIF - 视频结束时刻, 要求 -3 <= delta <= tolerance
    cands = []
    for im in images:
        if not im["dt"]:
            continue
        for vid in videos:
            if not vid["end_time"]:
                continue
            ve = datetime.datetime.strptime(vid["end_time"], "%Y-%m-%d %H:%M:%S")
            delta = (im["dt"] - ve).total_seconds()
            if -3.0 <= delta <= args.tolerance:
                cands.append((abs(delta), delta, im, vid))
    cands.sort(key=lambda x: x[0])
    used_img, used_vid, pairs = set(), set(), []
    for _, delta, im, vid in cands:
        if im["file"] in used_img or vid["file"] in used_vid:
            continue
        used_img.add(im["file"]); used_vid.add(vid["file"])
        pairs.append({"image": im["file"], "video": vid["file"],
                      "delta_s": round(delta, 1)})

    result = {
        "directory": os.path.abspath(d),
        "scanned_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "tolerance_s": args.tolerance,
        "images": [{k: v for k, v in im.items() if k != "dt"} for im in images],
        "videos": videos,
        "pairs": pairs,
        "unpaired_images": [im["file"] for im in images if im["file"] not in used_img],
        "unpaired_videos": [vid["file"] for vid in videos if vid["file"] not in used_vid],
        "notes": notes,
    }
    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"written: {args.out}", file=sys.stderr)
    print(out)


if __name__ == "__main__":
    main()
