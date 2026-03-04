#!/bin/bash

# Claude Code Skills 安装脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET_DIR="$HOME/.claude/skills"

echo "=== Claude Code Skills 安装脚本 ==="
echo ""

# 创建目标目录
if [ ! -d "$TARGET_DIR" ]; then
    echo "创建目录: $TARGET_DIR"
    mkdir -p "$TARGET_DIR"
fi

# 复制 skills
echo "复制 skills..."
for skill_dir in "$SCRIPT_DIR/skills/"*/; do
    skill_name=$(basename "$skill_dir")
    mkdir -p "$TARGET_DIR/$skill_name"
    cp -r "$skill_dir"* "$TARGET_DIR/$skill_name/"
    echo "  已安装: /$skill_name"
done

echo ""
echo "已安装的 Skills:"
echo "----------------"
for skill_dir in "$TARGET_DIR/"*/; do
    name=$(basename "$skill_dir")
    if [ "$name" != "*" ]; then
        echo "  /$name"
    fi
done

echo ""
echo "安装完成！"
echo ""
echo "依赖检查:"

# 检查 yt-dlp
if command -v yt-dlp &> /dev/null; then
    echo "  [OK] yt-dlp 已安装"
else
    echo "  [!] yt-dlp 未安装 - 运行: brew install yt-dlp"
fi

# 检查 gh
if command -v gh &> /dev/null; then
    echo "  [OK] gh (GitHub CLI) 已安装"
else
    echo "  [!] gh 未安装 - 运行: brew install gh"
fi

echo ""
echo "现在可以在 Claude Code 中使用这些 skills 了！"
