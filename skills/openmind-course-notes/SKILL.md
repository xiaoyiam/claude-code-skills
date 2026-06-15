---
name: openmind-course-notes
description: Downloads text lessons, images, and resource files (zip/pdf attachments) from an openmindclub.com (开智元学) course as an offline Markdown bundle. Use when the user provides an openmindclub course URL like https://m.openmindclub.com/stu/<slug>/content and asks to download / archive / 整理 / 离线 the course notes / 讲义. Videos are DRM-protected and intentionally skipped. Includes a verify.py script to cross-check coverage.
---

# OpenMind Course Notes

Downloads the text portion of a 开智元学 (openmindclub.com) course as offline
Markdown — one file per chapter, with all referenced images downloaded locally
and links rewritten to relative paths so it renders on a phone with no network.

Videos on the platform use 腾讯云点播 (Tencent Cloud VOD) Private DRM with a
personal watermark embedded server-side. **Do not attempt to download them.**
This skill skips video content and leaves a placeholder card with the title.

## How to invoke

The user gives a course URL like:

- `https://m.openmindclub.com/stu/llmd01/content`
- `https://m.openmindclub.com/stu/<course-slug>/content`

The path segment after `/stu/` is the **course slug** (e.g. `llmd01`).

## Steps

1. **Extract the course slug** from the URL.
2. **Run the downloader script** (it handles Chrome CDP, login wait, API
   calls, image downloads, and Markdown assembly):

   ```bash
   python3 ${SKILL_DIR}/scripts/download_course.py <course-slug> [--output <dir>]
   ```

   - `<course-slug>`: e.g. `llmd01`
   - `--output`: defaults to `~/Downloads/openmind/<slug>`

3. **The script will pause and wait for login.** It launches a fresh Chrome
   window (separate `--user-data-dir` so it does not touch the user's normal
   browser) and opens the course page. When you see the prompt
   `LOGIN_READY?` on stdout, ask the user to confirm they have logged in, then
   send a newline to the script's stdin (use Bash with a here-string or
   `printf '\n'`).
4. **After login is confirmed**, the script fetches the directory API,
   downloads all images in parallel, writes one Markdown file per chapter,
   plus a `README.md` index, then prints a summary.

### Implementation note for step 3

The script reads a single line from stdin to proceed. Recommend running it in
the background and writing to its stdin once the user confirms login:

```bash
# Start in background
python3 ${SKILL_DIR}/scripts/download_course.py llmd01 &
# After user confirms login:
echo "" >> /dev/stdin   # or pipe to the running process
```

Easier pattern: invoke with a here-doc that blocks on user confirmation in
the conversation:

```bash
# Run interactively from a wrapper that waits for our explicit signal
( read -p "Waiting..."; ) | python3 ${SKILL_DIR}/scripts/download_course.py llmd01
```

In practice, just run with `run_in_background=true`, monitor stdout until you
see `LOGIN_READY?`, ask the user, then `echo > /proc/<pid>/fd/0` or kill+
restart with stdin piped — pick whichever is simplest in the current
environment. The script also accepts `--auto-login-wait <seconds>` if you
want a fixed wait instead of interactive (default 0 = wait for stdin).

## Output

```
<output-dir>/
├── README.md                 ← index with chapter links
├── directory.json            ← raw API response (for re-runs)
├── 01-<chapter-title>.md     ← one file per chapter, in order
├── 02-<chapter-title>.md
├── ...
├── images/                   ← all referenced images, hashed filenames
│   └── <sha1prefix>-<name>.<ext>
└── resources/                ← downloaded zip/pdf/etc resource cards
    └── <sanitized-original-filename>
```

Card prefixes in markdown:

| Type | Heading | Notes |
|---|---|---|
| `text` | `## <title>` | inline content as markdown |
| `video` | `## 🎬 <title>` | placeholder only — DRM, not downloaded |
| `resource` | `## 📦 <title>` | links to local file in `resources/` |
| unknown | `## ❓ <title>` | flags any new card type not seen before |

## Verifying coverage

The skill ships with a verification script that cross-checks the local
download against the live API:

```bash
python3 ${SKILL_DIR}/scripts/verify.py <course-slug> [--output <dir>] [--sample N]
```

Checks performed:

1. Card count + type distribution in `directory.json`
2. Unexpected card types (anything beyond text/video/resource)
3. Every markdown image URL has a non-empty local file
4. Orphan local images (cosmetic; from previous runs)
5. HTML `<img>` tags in content that the markdown regex would miss
6. Attachment-like URLs (`.pdf .zip .mp3 .mp4 ...`) in content
7. Detail-API sampling for N text + N/4 video cards:
   - `front` from detail API matches stored `frontContent`
   - `back` is empty (warn if non-empty — content was missed)
   - Video subtitles array is empty (warn if non-empty)

Exit code is non-zero if any issue is found.

**Run verify after every download** — the platform may add new card types
over time, and this is how the skill catches that.

## Re-runs

If `directory.json` already exists in the output folder, the script skips
the CDP/login dance and rebuilds Markdown + images from the cached JSON. To
force re-fetch, delete `directory.json` first.

## Prerequisites

- Google Chrome installed at `/Applications/Google Chrome.app`
- Python 3 with `websocket-client` (`pip3 install --user --break-system-packages websocket-client`)
- Port `9222` available for Chrome remote debugging

## What this skill does NOT do

- **No video download.** Videos are DRM-protected with personal watermarks.
  If the user wants offline video, suggest screen recording the browser
  playback instead. Do not attempt to bypass DRM.
- **No `back` content fetching.** Sampled cards show `back` is consistently
  empty in this platform; only `front` (in directory listing as
  `frontContent`) is used.
