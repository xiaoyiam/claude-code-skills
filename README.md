# Claude Code Skills

我的 Claude Code 自定义 Skills 集合。

## Skills 列表

| 命令 | 功能 |
|------|------|
| `/download-video` | 使用 yt-dlp 下载视频（支持多种选项） |
| `/下载` | 快速下载视频到当前目录 |
| `/更新skill文档` | 扫描所有 skills 并更新文档 |
| `/push` | 将 skills 推送到 GitHub |

## 在其他电脑上安装

### 方法一：运行安装脚本

```bash
git clone https://github.com/xiaoyiam/claude-code-skills.git
cd claude-code-skills
chmod +x install.sh
./install.sh
```

### 方法二：手动安装

```bash
# 克隆仓库
git clone https://github.com/xiaoyiam/claude-code-skills.git

# 创建 Claude commands 目录（如不存在）
mkdir -p ~/.claude/commands

# 复制所有 skills
cp claude-code-skills/commands/*.md ~/.claude/commands/
```

## 依赖

部分 skills 需要安装额外工具：

| Skill | 依赖 | 安装命令 |
|-------|------|----------|
| `/download-video`, `/下载` | yt-dlp | `brew install yt-dlp` |
| `/push` | gh (GitHub CLI) | `brew install gh` |

## 目录结构

```
claude-code-skills/
├── README.md          # 本文件
├── install.sh         # 安装脚本
└── commands/          # Skills 文件
    ├── download-video.md
    ├── push.md
    ├── 下载.md
    └── 更新skill文档.md
```

## 更新 Skills

在安装了这些 skills 的电脑上，运行 `/push` 即可将最新的 skills 同步到 GitHub。

在其他电脑上，运行以下命令拉取更新：

```bash
cd /path/to/claude-code-skills
git pull
./install.sh
```
