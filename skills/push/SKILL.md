将所有 Claude Code Skills 推送到 GitHub 仓库。

## 仓库信息

- **GitHub**: https://github.com/xiaoyiam/claude-code-skills
- **本地路径**: `/Users/xiaoyi/xiaoyi.com/github-repos/claude-code-skills`

## 执行步骤

### 1. 同步 skills 文件
```bash
# 复制所有 skills 目录到仓库
cp -r ~/.claude/skills/* "/Users/xiaoyi/xiaoyi.com/github-repos/claude-code-skills/skills/"
```

### 2. 更新 README.md
读取所有 skill 文件，更新 README.md 中的 skills 列表

### 3. 提交并推送
```bash
cd "/Users/xiaoyi/xiaoyi.com/github-repos/claude-code-skills"
git add -A
git commit -m "Update skills"
git push
```

## 输出

完成后告诉用户：
- 已推送的文件
- 仓库地址：https://github.com/xiaoyiam/claude-code-skills
- 如何在其他电脑上安装：
  ```bash
  git clone https://github.com/xiaoyiam/claude-code-skills.git
  cd claude-code-skills
  ./install.sh
  ```
