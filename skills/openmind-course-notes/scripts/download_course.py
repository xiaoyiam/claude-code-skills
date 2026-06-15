#!/usr/bin/env python3
"""Download text lessons and images from an openmindclub.com course.

Workflow:
  1. Launch Chrome with CDP on port 9222 (in a separate user-data-dir).
  2. Open https://m.openmindclub.com/stu/<slug>/content.
  3. Print LOGIN_READY? on stdout and read one line from stdin to wait
     for the user to log in.
  4. Fetch /api/course/<slug>/directory via fetch() inside the page (so
     auth cookies are sent).
  5. Save directory.json, download all images in parallel, write one
     Markdown file per chapter plus a README.md index.

Re-runs: if <output>/directory.json exists, skip Chrome and rebuild only.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

CDP_PORT = 9222
DEFAULT_USER_DATA_DIR = "/tmp/chrome-cdp-openmind"
CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 Chrome/149"
    ),
    "Referer": "https://m.openmindclub.com/",
}

MD_IMG = re.compile(
    r'(!\[[^\]]*\]\()(https?://[^\) ]+)(\s+"[^"]*")?(\))'
)


# Card types we know how to render
KNOWN_CARD_TYPES = {"text", "video", "resource"}


# ---------------------------------------------------------------------------
# CDP helpers (vendored so the script is self-contained)
# ---------------------------------------------------------------------------

def cdp_get_tab_ws(url_contains: str) -> str:
    req = urllib.request.Request(
        f"http://127.0.0.1:{CDP_PORT}/json/list",
        headers={"Host": "localhost"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        tabs = json.load(r)
    for t in tabs:
        if t.get("type") == "page" and url_contains in t.get("url", ""):
            ws = t["webSocketDebuggerUrl"]
            if "://localhost/" in ws:
                ws = ws.replace("://localhost/", f"://localhost:{CDP_PORT}/")
            return ws
    raise RuntimeError(f"No tab matching {url_contains!r}")


def cdp_eval(ws_url: str, expression: str, timeout: float = 60) -> object:
    import websocket  # type: ignore

    ws = websocket.create_connection(
        ws_url, timeout=timeout, header=["Host: localhost"]
    )
    try:
        ws.send(json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        }))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                if "error" in msg:
                    raise RuntimeError(f"CDP error: {msg['error']}")
                return msg["result"]["result"].get("value")
    finally:
        ws.close()


# ---------------------------------------------------------------------------
# Chrome lifecycle
# ---------------------------------------------------------------------------

def chrome_cdp_alive() -> bool:
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{CDP_PORT}/json/version",
            headers={"Host": "localhost"},
        )
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def launch_chrome(target_url: str, user_data_dir: str) -> None:
    os.makedirs(user_data_dir, exist_ok=True)
    args = [
        CHROME_PATH,
        f"--remote-debugging-port={CDP_PORT}",
        "--remote-allow-origins=*",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        target_url,
    ]
    subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    for _ in range(20):
        if chrome_cdp_alive():
            return
        time.sleep(0.5)
    raise RuntimeError("Chrome CDP did not come up on port " + str(CDP_PORT))


# ---------------------------------------------------------------------------
# Build markdown + images
# ---------------------------------------------------------------------------

def safe_name(s: str, max_len: int = 80) -> str:
    s = re.sub(r'[\\/:*?"<>|]', "_", s)
    return s[:max_len].strip()


def image_local_name(url: str) -> str:
    base = os.path.basename(url.split("?")[0]) or "img"
    h = hashlib.sha1(url.encode()).hexdigest()[:10]
    return f"{h}-{safe_name(base, 60)}"


def download_image(url: str, img_dir: Path) -> tuple[str, bool, str]:
    fname = image_local_name(url)
    out = img_dir / fname
    if out.exists() and out.stat().st_size > 0:
        return fname, True, "cached"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        out.write_bytes(data)
        return fname, True, f"{len(data)}B"
    except Exception as e:
        # one curl-based retry for SSL flakes
        try:
            r = subprocess.run(
                ["curl", "-sfL", "--retry", "3",
                 "-A", HEADERS["User-Agent"],
                 "-H", f"Referer: {HEADERS['Referer']}",
                 "-o", str(out), url],
                timeout=60,
            )
            if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
                return fname, True, "curl-retry"
        except Exception:
            pass
        return fname, False, str(e)


def collect_image_urls(chapters) -> list[str]:
    urls = set()
    for ch in chapters:
        for c in ch["cards"]:
            for fc in (c.get("frontContent"), c.get("back")):
                if fc:
                    for m in MD_IMG.finditer(fc):
                        urls.add(m.group(2))
    return sorted(urls)


def rewrite_images(text: str, url_map: dict) -> str:
    def repl(m):
        url = m.group(2)
        fname = url_map.get(url)
        if not fname:
            return m.group(0)
        title = m.group(3) or ""
        return f"{m.group(1)}images/{fname}{title}{m.group(4)}"
    return MD_IMG.sub(repl, text)


def fetch_resource_url(slug: str, card_id: str) -> tuple[str, str] | None:
    """Returns (download_url, file_name) or None."""
    ws = cdp_get_tab_ws("openmindclub")
    expr = f"""
    (async () => {{
      const r = await fetch(
        '/api/course/{slug}/card/{card_id}/download',
        {{credentials:'include'}}
      );
      return {{status: r.status, body: await r.text()}};
    }})()
    """
    try:
        v = cdp_eval(ws, expr)
    except Exception as e:
        print(f"  cdp_eval failed for {card_id}: {e}")
        return None
    if v["status"] != 200:
        return None
    try:
        obj = json.loads(v["body"])
        d = obj.get("data") or {}
        url = d.get("downloadUrl")
        name = d.get("fileName") or "resource.bin"
        if url:
            return url, name
    except Exception:
        return None
    return None


def download_resource(url: str, file_name: str, res_dir: Path) -> tuple[str, bool, str]:
    safe = safe_name(file_name, 120)
    out = res_dir / safe
    if out.exists() and out.stat().st_size > 0:
        return safe, True, "cached"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        out.write_bytes(data)
        return safe, True, f"{len(data)}B"
    except Exception as e:
        try:
            r = subprocess.run(
                ["curl", "-sfL", "--retry", "3",
                 "-A", HEADERS["User-Agent"],
                 "-H", f"Referer: {HEADERS['Referer']}",
                 "-o", str(out), url],
                timeout=120,
            )
            if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
                return safe, True, "curl-retry"
        except Exception:
            pass
        return safe, False, str(e)


def build_outputs(directory: dict, slug: str, out_dir: Path) -> dict:
    chapters = directory["data"]
    img_dir = out_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    res_dir = out_dir / "resources"

    # 1. images
    urls = collect_image_urls(chapters)
    print(f"[images] downloading {len(urls)} images...", flush=True)
    url_map: dict[str, str] = {}
    fails: list[tuple[str, str]] = []
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(download_image, u, img_dir): u for u in urls}
        done = 0
        for fut in cf.as_completed(futs):
            url = futs[fut]
            fname, ok, msg = fut.result()
            done += 1
            if ok:
                url_map[url] = fname
            else:
                fails.append((url, msg))
            if done % 20 == 0 or done == len(urls):
                print(f"  {done}/{len(urls)}", flush=True)
    if fails:
        print(f"[images] FAILED {len(fails)}:", flush=True)
        for u, m in fails[:5]:
            print(f"  {u} -> {m}")

    # 1b. resource cards (zip/pdf attachments)
    resource_cards = [c for _, c in
                      ((ch, c) for ch in chapters for c in ch["cards"])
                      if c["type"] == "resource"]
    resource_map: dict[str, str] = {}
    res_ok = res_fail = 0
    if resource_cards:
        res_dir.mkdir(parents=True, exist_ok=True)
        print(f"[resources] downloading {len(resource_cards)} resource files...",
              flush=True)
        if not chrome_cdp_alive():
            print("  Chrome CDP not running; resources will be skipped",
                  flush=True)
        else:
            for i, c in enumerate(resource_cards, 1):
                info = fetch_resource_url(slug, c["id"])
                if not info:
                    print(f"  [{i}/{len(resource_cards)}] "
                          f"{c['title']!r}: no download URL")
                    res_fail += 1
                    continue
                url, fname = info
                local, ok, msg = download_resource(url, fname, res_dir)
                if ok:
                    resource_map[c["id"]] = local
                    res_ok += 1
                else:
                    res_fail += 1
                print(f"  [{i}/{len(resource_cards)}] {c['title']!r} -> "
                      f"{local} ({msg})")

    # 2. chapter markdown + index
    print("[markdown] writing chapter files...", flush=True)
    index = [
        "# " + directory.get("courseTitle", "OpenMind 课程讲义"),
        "",
        "> 文字讲义离线版（视频受 DRM 保护，未下载）",
        "",
        "## 章节目录",
        "",
    ]
    stats = {"chapters": len(chapters), "text": 0, "video": 0,
             "resource": 0, "unknown": 0,
             "images_ok": len(url_map), "images_fail": len(fails),
             "resources_ok": res_ok, "resources_fail": res_fail}

    for i, ch in enumerate(chapters, 1):
        ch_title = ch["title"]
        ch_slug = f"{i:02d}-{safe_name(ch_title)}"
        ch_file = out_dir / f"{ch_slug}.md"

        lines = [f"# {ch_title}", ""]
        text_n = vid_n = res_n = unk_n = 0
        for c in ch["cards"]:
            title = c["title"]
            ctype = c["type"]
            content = c.get("frontContent") or ""
            content = rewrite_images(content, url_map) if content else ""

            if ctype == "video":
                vid_n += 1
                lines += [f"## 🎬 {title}", ""]
                lines += [
                    f"> 视频卡片（受 DRM 保护，不可下载）· "
                    f"`fileId={c.get('videoFileId')}`",
                    "",
                ]
                if content:
                    lines += [content, ""]
            elif ctype == "resource":
                res_n += 1
                res = c.get("resource") or {}
                fname = res.get("fileName", title)
                fsize = res.get("fileSize")
                size_h = f"{fsize/1024:.1f} KB" if fsize else ""
                lines += [f"## 📦 {title}", ""]
                local = resource_map.get(c["id"])
                if local:
                    lines += [
                        f"> 资源文件：[{fname}](resources/{local})"
                        + (f" · {size_h}" if size_h else ""),
                        "",
                    ]
                else:
                    lines += [
                        f"> 资源文件 `{fname}`（下载失败或未抓取）"
                        + (f" · {size_h}" if size_h else ""),
                        "",
                    ]
                if content:
                    lines += [content, ""]
            elif ctype == "text":
                text_n += 1
                lines += [f"## {title}", ""]
                if content:
                    lines += [content, ""]
                else:
                    lines += ["_（无内容）_", ""]
            else:
                unk_n += 1
                lines += [f"## ❓ {title}", ""]
                lines += [
                    f"> 未知卡片类型 `{ctype}` — 请人工查看 directory.json",
                    "",
                ]
                if content:
                    lines += [content, ""]
        ch_file.write_text("\n".join(lines), encoding="utf-8")
        stats["text"] += text_n
        stats["video"] += vid_n
        stats["resource"] += res_n
        stats["unknown"] += unk_n
        parts = []
        if text_n: parts.append(f"{text_n}文字")
        if vid_n: parts.append(f"{vid_n}视频")
        if res_n: parts.append(f"{res_n}资源")
        if unk_n: parts.append(f"{unk_n}未知")
        summary = " / ".join(parts) if parts else "0 张卡片"
        index.append(f"- [{ch_title}]({ch_slug}.md) — {summary}")
        print(f"  -> {ch_file.name}  ({summary})", flush=True)

    (out_dir / "README.md").write_text("\n".join(index) + "\n",
                                       encoding="utf-8")
    return stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def fetch_directory(slug: str) -> dict:
    ws_url = cdp_get_tab_ws("openmindclub")
    expr = f"""
    (async () => {{
      const r = await fetch('/api/course/{slug}/directory',
                            {{credentials: 'include'}});
      return {{status: r.status, body: await r.text()}};
    }})()
    """
    v = cdp_eval(ws_url, expr)
    if v["status"] != 200:
        raise RuntimeError(
            f"directory API HTTP {v['status']}: {v['body'][:200]}"
        )
    obj = json.loads(v["body"])
    if obj.get("code") != 0:
        raise RuntimeError(f"directory API code={obj.get('code')}: "
                           f"{obj.get('msg')}")
    return obj


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("slug", help="Course slug, e.g. llmd01")
    p.add_argument(
        "--output", "-o",
        help="Output directory (default: ~/Downloads/openmind/<slug>)",
    )
    p.add_argument(
        "--user-data-dir", default=DEFAULT_USER_DATA_DIR,
        help="Chrome user-data-dir (cookies cached here between runs)",
    )
    p.add_argument(
        "--auto-login-wait", type=int, default=0,
        help="Seconds to wait for login automatically (0 = wait for stdin)",
    )
    args = p.parse_args()

    slug = args.slug
    out_dir = Path(
        args.output or f"~/Downloads/openmind/{slug}"
    ).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    dir_json_path = out_dir / "directory.json"

    if dir_json_path.exists():
        print(f"[cache] using existing {dir_json_path}", flush=True)
        directory = json.load(dir_json_path.open(encoding="utf-8"))
    else:
        target_url = f"https://m.openmindclub.com/stu/{slug}/content"
        if not chrome_cdp_alive():
            print(f"[chrome] launching with --user-data-dir={args.user_data_dir}",
                  flush=True)
            launch_chrome(target_url, args.user_data_dir)
        else:
            print("[chrome] reusing existing CDP on port 9222", flush=True)
            # navigate the active tab to target_url
            ws_url = cdp_get_tab_ws("")
            cdp_eval(ws_url, f"location.href = {json.dumps(target_url)};")
            time.sleep(2)

        if args.auto_login_wait > 0:
            print(
                f"[login] sleeping {args.auto_login_wait}s for login...",
                flush=True,
            )
            time.sleep(args.auto_login_wait)
        else:
            print("LOGIN_READY?", flush=True)
            print(
                "  -> log in to openmindclub in the new Chrome window, "
                "navigate to the course, then press ENTER here",
                flush=True,
            )
            try:
                sys.stdin.readline()
            except KeyboardInterrupt:
                return 130

        print(f"[api] fetching directory for course={slug}", flush=True)
        directory = fetch_directory(slug)
        dir_json_path.write_text(
            json.dumps(directory, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[api] saved {dir_json_path}", flush=True)

    stats = build_outputs(directory, slug, out_dir)
    print()
    print(f"DONE  output={out_dir}")
    print(f"  chapters: {stats['chapters']}")
    print(f"  text cards: {stats['text']}")
    print(f"  video cards: {stats['video']} (skipped, DRM)")
    print(f"  resource cards: {stats['resource']} "
          f"({stats['resources_ok']} downloaded, "
          f"{stats['resources_fail']} failed)")
    if stats["unknown"]:
        print(f"  UNKNOWN cards: {stats['unknown']} — check chapter files")
    print(f"  images: {stats['images_ok']} ok, {stats['images_fail']} failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
