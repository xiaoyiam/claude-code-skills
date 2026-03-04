# Download Video

Download video from URL using yt-dlp.

## Usage

Provide a video URL to download. Supports YouTube, Bilibili, Twitter, and many other platforms.

## Instructions

1. Use yt-dlp to download the video from the provided URL
2. By default, download to the current working directory
3. Use best quality available unless user specifies otherwise
4. Show download progress

## Arguments

- `$ARGUMENTS` - The video URL to download, and any additional options

## Example Commands

```bash
# Basic download
yt-dlp "$ARGUMENTS"

# Download with best quality
yt-dlp -f "bestvideo+bestaudio/best" "$ARGUMENTS"

# Download audio only
yt-dlp -x --audio-format mp3 "$ARGUMENTS"

# List available formats
yt-dlp -F "$ARGUMENTS"
```

When the user provides a URL, analyze it and run the appropriate yt-dlp command. If the user wants specific options (like audio only, specific format, etc.), adjust the command accordingly.
