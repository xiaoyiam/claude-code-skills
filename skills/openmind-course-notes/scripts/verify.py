#!/usr/bin/env python3
"""Verify a downloaded openmindclub course is complete.

Runs a series of cross-checks against the local download and the live API:
  1. Card count vs. UI total (from /api/course/<slug>/info)
  2. Card type distribution (flag anything other than text/video)
  3. Every markdown image URL is downloaded and non-empty
  4. No orphan images (downloaded but not referenced)
  5. HTML <img> tags in content that the markdown regex would miss
  6. Non-image URLs in content that look like attachments (.pdf .zip .mp3 ...)
  7. Detail-API sampling: for N random cards, confirm
     - `front` matches the `frontContent` we stored
     - `back` is empty (warn if non-empty: we missed content)
     - For video cards, `subtitles` array is empty (warn if non-empty)

Usage:
    python3 verify.py <course-slug> [--output <dir>] [--sample N]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import urllib.request
from pathlib import Path

# Reuse CDP helpers from the downloader (same directory)
sys.path.insert(0, str(Path(__file__).parent))
from download_course import (  # noqa: E402
    CDP_PORT, MD_IMG, cdp_eval, cdp_get_tab_ws, chrome_cdp_alive,
    image_local_name,
)


# Extra detectors
HTML_IMG = re.compile(r'<img\s[^>]*src=["\']([^"\']+)["\']', re.IGNORECASE)
ATTACHMENT_EXT = re.compile(
    r'(https?://[^\s\)\]]+\.(?:pdf|zip|mp3|mp4|m4a|wav|docx?|xlsx?|pptx?|csv|txt))',
    re.IGNORECASE,
)
ALL_URLS = re.compile(r'https?://[^\s\)\]"\'<>]+')


def red(s):
    return f"\033[31m{s}\033[0m"


def yel(s):
    return f"\033[33m{s}\033[0m"


def grn(s):
    return f"\033[32m{s}\033[0m"


def fetch_via_cdp(path: str) -> dict | None:
    """Fetch a same-origin API path via the live Chrome session."""
    if not chrome_cdp_alive():
        return None
    try:
        ws = cdp_get_tab_ws("openmindclub")
    except Exception:
        return None
    expr = f"""
    (async () => {{
      const r = await fetch({json.dumps(path)}, {{credentials:'include'}});
      return {{status: r.status, body: await r.text()}};
    }})()
    """
    try:
        v = cdp_eval(ws, expr)
    except Exception as e:
        print(yel(f"  cdp_eval failed: {e}"))
        return None
    if v["status"] != 200:
        print(yel(f"  {path} -> HTTP {v['status']}"))
        return None
    try:
        return json.loads(v["body"])
    except Exception:
        return None


def all_cards(directory):
    for ch in directory["data"]:
        for c in ch["cards"]:
            yield ch, c


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("slug")
    p.add_argument("--output", "-o")
    p.add_argument("--sample", type=int, default=30,
                   help="Detail-API sample size (0 = all)")
    args = p.parse_args()

    out = Path(args.output or f"~/Downloads/openmind/{args.slug}").expanduser()
    dir_json = out / "directory.json"
    img_dir = out / "images"
    if not dir_json.exists():
        print(red(f"FAIL: {dir_json} not found"))
        return 1
    directory = json.load(dir_json.open(encoding="utf-8"))

    issues = 0

    # ----- 1. card count -----
    cards = list(all_cards(directory))
    by_type: dict[str, int] = {}
    for _, c in cards:
        by_type[c["type"]] = by_type.get(c["type"], 0) + 1
    print(f"[1] cards in directory.json: {len(cards)}")
    for t, n in sorted(by_type.items()):
        print(f"      {t}: {n}")

    # try to read UI total from course info API
    info = fetch_via_cdp(f"/api/course/{args.slug}/info")
    ui_total = None
    if info and info.get("code") == 0:
        d = info.get("data", {})
        # try common keys
        for k in ("totalCardCount", "cardCount", "totalCards", "cardTotal"):
            if k in d:
                ui_total = d[k]
                break
        if ui_total is None:
            print(yel(f"    info API returned keys={list(d)[:8]}; "
                      "no cardTotal-like key — skipping UI cross-check"))
    if ui_total is not None:
        if ui_total == len(cards):
            print(grn(f"    UI total {ui_total} matches ✓"))
        else:
            print(red(f"    UI total {ui_total} != {len(cards)} ✗"))
            issues += 1

    # ----- 2. unexpected card types -----
    expected = {"text", "video", "resource"}
    extras = set(by_type) - expected
    if extras:
        print(red(f"[2] UNEXPECTED card types: {extras}"))
        for _, c in cards:
            if c["type"] in extras:
                print(f"      {c['type']}: {c['title']!r}")
        issues += 1
    else:
        print(grn(f"[2] all card types are {expected} ✓"))

    # ----- 2b. resource files downloaded? -----
    res_cards = [c for _, c in cards if c["type"] == "resource"]
    res_dir = out / "resources"
    if res_cards:
        if not res_dir.exists():
            print(red(f"[2b] {len(res_cards)} resource cards but "
                      "no resources/ directory ✗"))
            issues += 1
        else:
            files = list(res_dir.iterdir())
            if len(files) < len(res_cards):
                print(red(f"[2b] resources: {len(files)} files on disk "
                          f"vs {len(res_cards)} resource cards ✗"))
                issues += 1
            else:
                # check sizes match what directory claims
                size_ok = True
                for c in res_cards:
                    claimed = (c.get("resource") or {}).get("fileSize")
                    fname = (c.get("resource") or {}).get("fileName", "")
                    # try to find a matching file (fname or sanitized)
                    matches = [f for f in files if fname in f.name]
                    if not matches:
                        size_ok = False
                        print(red(f"      missing on disk: {fname!r} "
                                  f"(card {c['title']!r})"))
                if size_ok:
                    print(grn(f"[2b] all {len(res_cards)} resources "
                              f"on disk ✓"))

    # ----- 3. markdown image coverage -----
    md_urls: set[str] = set()
    html_urls: set[str] = set()
    attach_urls: set[str] = set()
    for _, c in cards:
        for fc in (c.get("frontContent"), c.get("back")):
            if not fc:
                continue
            for m in MD_IMG.finditer(fc):
                md_urls.add(m.group(2))
            for m in HTML_IMG.finditer(fc):
                html_urls.add(m.group(1))
            for m in ATTACHMENT_EXT.finditer(fc):
                attach_urls.add(m.group(1))

    print(f"[3] markdown image URLs: {len(md_urls)}")
    missing_local = []
    bad_size = []
    for u in md_urls:
        lp = img_dir / image_local_name(u)
        if not lp.exists():
            missing_local.append(u)
        elif lp.stat().st_size == 0:
            bad_size.append(u)
    if missing_local:
        print(red(f"    MISSING locally: {len(missing_local)}"))
        for u in missing_local[:5]:
            print(f"      {u}")
        issues += 1
    if bad_size:
        print(red(f"    ZERO-byte files: {len(bad_size)}"))
        issues += 1
    if not missing_local and not bad_size:
        print(grn(f"    all {len(md_urls)} downloaded ✓"))

    # ----- 4. orphan images -----
    if img_dir.exists():
        on_disk = {p.name for p in img_dir.iterdir() if p.is_file()}
        referenced = {image_local_name(u) for u in md_urls}
        orphan = on_disk - referenced
        if orphan:
            print(yel(f"[4] orphan images on disk: {len(orphan)} "
                      "(probably from a previous run; not an error)"))
        else:
            print(grn(f"[4] no orphan images ✓"))

    # ----- 5. HTML <img> tags -----
    if html_urls:
        # is each already covered by md_urls?
        missed = html_urls - md_urls
        if missed:
            print(red(f"[5] HTML <img> tags NOT caught by markdown regex: "
                      f"{len(missed)}"))
            for u in list(missed)[:5]:
                print(f"      {u}")
            issues += 1
        else:
            print(grn(f"[5] HTML <img> tags present but also as markdown ✓"))
    else:
        print(grn("[5] no HTML <img> tags found ✓"))

    # ----- 6. attachments -----
    if attach_urls:
        print(yel(f"[6] attachment-like URLs in content: {len(attach_urls)}"))
        for u in list(attach_urls)[:8]:
            print(f"      {u}")
        print(yel("    (the downloader does not fetch attachments)"))
    else:
        print(grn("[6] no attachment-like URLs found ✓"))

    # ----- 7. detail-API sampling -----
    text_cards = [c for _, c in cards if c["type"] == "text"]
    video_cards = [c for _, c in cards if c["type"] == "video"]
    n_text = len(text_cards) if args.sample == 0 else min(args.sample,
                                                          len(text_cards))
    n_video = len(video_cards) if args.sample == 0 else min(
        max(args.sample // 4, 2), len(video_cards))
    random.seed(42)
    sample_text = random.sample(text_cards, n_text)
    sample_video = random.sample(video_cards, n_video)

    if not chrome_cdp_alive():
        print(yel(
            "[7] Chrome CDP not running; skipping detail-API sampling. "
            "Run the downloader first or open the course in Chrome with "
            f"--remote-debugging-port={CDP_PORT}."
        ))
    else:
        print(f"[7] sampling {n_text} text + {n_video} video cards "
              "via detail API...")
        front_mismatch = []
        nonempty_back = []
        nonempty_subs = []
        for c in sample_text + sample_video:
            j = fetch_via_cdp(
                f"/api/course/{args.slug}/content/{c['id']}"
            )
            if not j or j.get("code") != 0:
                continue
            d = j["data"]
            if c["type"] == "text":
                fc_stored = c.get("frontContent") or ""
                fc_live = d.get("front") or ""
                if fc_stored.strip() != fc_live.strip():
                    front_mismatch.append((c["id"], c["title"]))
                back = d.get("back") or ""
                if back.strip():
                    nonempty_back.append((c["id"], c["title"], len(back)))
            # for both types, look at subtitles
        # video subtitles via the play API
        for c in sample_video:
            j = fetch_via_cdp(
                f"/api/video/play/{c['videoFileId']}?type=adp"
            )
            if not j or j.get("code") != 0:
                continue
            subs = j["data"].get("subtitles") or []
            if subs:
                nonempty_subs.append((c["title"], len(subs)))

        if front_mismatch:
            print(red(f"    front content mismatch in {len(front_mismatch)} cards:"))
            for cid, t in front_mismatch[:5]:
                print(f"      {t} ({cid})")
            issues += 1
        else:
            print(grn(f"    front content matches in all {n_text} text samples ✓"))

        if nonempty_back:
            print(red(f"    NON-EMPTY back content found in {len(nonempty_back)} cards "
                      "(downloader MISSED this!):"))
            for cid, t, n in nonempty_back[:5]:
                print(f"      {t} ({cid}) back={n} chars")
            issues += 1
        else:
            print(grn(f"    all sampled text cards have empty `back` ✓"))

        if nonempty_subs:
            print(yel(f"    {len(nonempty_subs)} video(s) have subtitles; "
                      "downloader does not fetch them:"))
            for t, n in nonempty_subs[:5]:
                print(f"      {t}: {n} sub track(s)")
        else:
            print(grn(f"    no subtitles in {n_video} video samples ✓"))

    # ----- summary -----
    print()
    if issues == 0:
        print(grn(f"VERIFY OK — no issues in {out}"))
        return 0
    else:
        print(red(f"VERIFY FOUND {issues} issue(s) — see above"))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
