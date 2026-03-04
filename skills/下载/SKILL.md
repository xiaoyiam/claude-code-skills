使用 yt-dlp 下载视频到当前目录。

$ARGUMENTS 是视频链接。

执行命令：
```bash
yt-dlp -o "%(title)s.%(ext)s" "$ARGUMENTS"
```

下载完成后告诉用户文件名和保存位置。
