扫描并更新 Claude Code Skills 文档。

## 任务

扫描所有 Skills（包括全局和项目级），生成完整的文档。

## Skills 存放位置

Claude Code 的 skills 有两种类型：

| 类型 | 存放位置 | 作用范围 |
|------|----------|----------|
| 全局 | `~/.claude/commands/` | 所有项目都可用 |
| 项目级 | `<项目>/.claude/commands/` | 仅该项目可用 |

## 执行步骤

1. 扫描全局 skills：`~/.claude/commands/*.md`
2. 扫描当前工作目录的项目级 skills：`./.claude/commands/*.md`（如果存在）
3. 读取每个 skill 文件的内容
4. 按类型分类整理
5. 在 `/Users/xiaoyi/xiaoyi.com/2. Area/2.1 All-in-AI/Claude-Code-Skills.md` 创建或更新文档

## 文档格式

生成的文档应包含：

- 文档标题和更新时间
- Skills 总数统计（分全局/项目级）
- 按类型分组展示每个 skill：
  - 名称（即调用命令）
  - 类型（全局/项目级）
  - 所属项目路径（如为项目级）
  - 功能描述
  - 使用方法和示例
  - 相关依赖（如需要安装的工具）

请确保文档清晰易读，方便日后查阅。
