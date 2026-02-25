将所有 Claude Code Skills 推送到 GitHub 仓库。

## 任务

1. 收集所有 skills 文件（全局 + 项目级）
2. 推送到 GitHub 仓库 `claude-code-skills`
3. 生成安装说明文档

## 执行步骤

### 1. 检查环境
- 确认 `gh` CLI 已安装且已登录
- 如未登录，提示用户运行 `gh auth login`

### 2. 准备仓库
- 检查本地是否已有 `~/.claude-code-skills-repo` 目录
- 如果没有，检查 GitHub 上是否已有 `claude-code-skills` 仓库
- 如果都没有，创建新仓库

### 3. 同步文件
将以下内容同步到仓库：
- `commands/` 目录：存放所有 skill 文件（从 `~/.claude/commands/` 复制）
- `README.md`：自动生成的安装和使用说明
- `install.sh`：一键安装脚本

### 4. 生成 README.md
README 应包含：
- 项目介绍
- Skills 列表和功能说明
- 安装方法（克隆仓库 + 运行安装脚本）
- 如何在其他电脑上使用

### 5. 生成 install.sh
安装脚本应：
- 创建 `~/.claude/commands/` 目录（如不存在）
- 将所有 skill 文件复制到该目录
- 显示安装成功信息

### 6. 提交并推送
- git add 所有文件
- git commit
- git push

## 仓库结构

```
claude-code-skills/
├── README.md          # 使用说明
├── install.sh         # 安装脚本
└── commands/          # Skills 文件
    ├── download-video.md
    ├── 下载.md
    ├── 更新skill文档.md
    └── push.md
```

## 输出

完成后告诉用户：
- 仓库地址
- 如何在其他电脑上安装（克隆 + 运行 install.sh）
