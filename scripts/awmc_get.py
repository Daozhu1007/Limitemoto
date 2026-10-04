#!/usr/bin/env python3
"""awmc_get.py — AWMC-MaiArchive (download.wmc.pub) 单曲获取工具

站点路由(2026-10-04 摸清):
  GET /cdn/v1/data/songs                     全曲库 JSON (title/versionFolder/folderName/shortid...)
  GET /cdn/v1/data/downloads                 shortid -> 下载计数
  GET /s/{shortid}/maidata.txt|track.mp3|track.ogg|bg.png|bg.jpg|pv.mp4   单文件直链
  GET /api/download/{versionFolder}/{folderName}/zip[?novideo=1]          整包 (adx 同理)
shortid = "1" + 官方歌曲ID, 6位补零 (RED 1868 -> "011868")

用法:
  python awmc_get.py ロータス              # 搜索
  python awmc_get.py ビビデバ -o DIR       # 搜索(唯一命中自动下载) -> DIR/track.mp3 + maidata.txt
  python awmc_get.py -i 011836 -o DIR      # 按 shortid 直接下载
  python awmc_get.py RED -o DIR --zip      # 整包 zip (含 bg, --novideo 可去背景视频)
  python awmc_get.py --refresh             # 强制刷新曲库缓存
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://download.wmc.pub"
UA = {"User-Agent": "Mozilla/5.0 awmc_get/1.0"}
CACHE = os.path.join(os.path.expandvars(r"%TEMP%"), "awmc_songs_cache.json")
DEFAULT_PROXY = os.environ.get("AWMC_PROXY", "http://127.0.0.1:7897")


def fetch(url, proxy, timeout=90):
    handler = urllib.request.ProxyHandler(
        {"http": proxy, "https": proxy} if proxy else {}
    )
    opener = urllib.request.build_opener(handler)
    req = urllib.request.Request(url, headers=UA)
    with opener.open(req, timeout=timeout) as r:
        return r.read()


def load_songs(proxy, refresh=False):
    if not refresh and os.path.exists(CACHE):
        age = time.time() - os.path.getmtime(CACHE)
        if age < 7 * 86400:
            return json.load(open(CACHE, encoding="utf-8"))
    data = json.loads(fetch(f"{BASE}/cdn/v1/data/songs", proxy))
    songs = data if isinstance(data, list) else data.get("songs", [])
    json.dump(songs, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    return songs


def norm(s):
    return "".join(str(s).split()).casefold()


def search(songs, keywords, prefer_dx=True):
    kws = [norm(k) for k in keywords if k]
    hits = [s for s in songs if all(k in norm(s.get("title", "")) for k in kws)]
    if prefer_dx and len(hits) > 1:
        dx = [s for s in hits if "[dx]" in norm(s.get("folderName", ""))]
        if dx:
            hits = dx
    return hits


def save(path, data):
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(add_help=True, description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("keywords", nargs="*", help="曲名关键词（6位数字视为 shortid）")
    ap.add_argument("-i", "--id", help="shortid (6位, 如 011836)")
    ap.add_argument("-o", "--out", default=".", help="输出目录")
    ap.add_argument("--zip", action="store_true", help="下载整包 zip 代替散文件")
    ap.add_argument("--novideo", action="store_true", help="整包去背景视频")
    ap.add_argument("--adx", action="store_true", help="整包用 adx 格式")
    ap.add_argument("--all", action="store_true", help="多命中时全部下载")
    ap.add_argument("--proxy", default=DEFAULT_PROXY,
                    help=f"代理 (默认 {DEFAULT_PROXY}, 传 none 直连)")
    ap.add_argument("--refresh", action="store_true", help="强制刷新曲库缓存")
    args = ap.parse_args()

    proxy = None if args.proxy.lower() == "none" else args.proxy
    os.makedirs(args.out, exist_ok=True)

    try:
        songs = load_songs(proxy, args.refresh)
    except Exception as e:
        sys.exit(f"曲库获取失败(检查代理 {args.proxy}): {e}")
    print(f"曲库 {len(songs)} 首 (缓存: {CACHE})")

    if args.id:
        sid = args.id.zfill(6)
        hits = [s for s in songs if norm(s.get("shortid", "")) == norm(sid)]
        if not hits:
            sys.exit(f"shortid {sid} 不在曲库中")
    elif args.keywords:
        hits = search(songs, args.keywords)
    else:
        ap.print_usage()
        return

    if not hits:
        sys.exit("没有匹配的曲目（试试 --refresh 或换关键词）")
    for s in hits:
        print(f"  {s['shortid']}  {s['title']}  [{s.get('versionFolder')}] -> {s.get('folderName')}")

    if len(hits) > 1 and not args.all:
        print(f"\n{len(hits)} 个命中，用 -i <shortid> 指定，或 --all 全下。")
        return

    for s in hits:
        sid, folder = s["shortid"], s["folderName"]
        vf = urllib.parse.quote(s["versionFolder"])
        fn = urllib.parse.quote(folder)
        try:
            if args.zip or args.adx:
                fmt = "adx" if args.adx else "zip"
                q = "?novideo=1" if args.novideo else ""
                url = f"{BASE}/api/download/{vf}/{fn}/{fmt}{q}"
                out = os.path.join(args.out, f"{folder}.{fmt}")
                print(f"下载 {url}")
                save(out, fetch(url, proxy, timeout=300))
                print(f"  -> {out} ({os.path.getsize(out)//1024} KB)")
            else:
                url = f"{BASE}/s/{urllib.parse.quote(sid)}/maidata.txt"
                out = os.path.join(args.out, "maidata.txt")
                save(out, fetch(url, proxy))
                print(f"  -> {out}")
                audio = None
                for name in ("track.mp3", "track.ogg"):
                    try:
                        url = f"{BASE}/s/{urllib.parse.quote(sid)}/{name}"
                        data = fetch(url, proxy)
                        audio = name
                        out = os.path.join(args.out, name)
                        save(out, data)
                        print(f"  -> {out} ({len(data)//1024} KB)")
                        break
                    except Exception as e:
                        if "404" in str(e):
                            continue
                        raise
                if not audio:
                    print(f"  !! {sid} 没有音频文件")
                time.sleep(0.5)  # 对小站客气点
        except Exception as e:
            print(f"  !! {folder} 下载失败: {e}")


if __name__ == "__main__":
    main()
