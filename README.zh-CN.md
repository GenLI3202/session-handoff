# session-handoff

[English](README.md)

一个 agent 技能：让一个编程 agent **接着另一个 agent 里的对话继续聊**。比如 Claude 额度用完了，想在 Codex 里接着刚才的会话做，反过来也一样。

你说“接着聊 Codex 里叫「迁移方案」的会话”，技能会在本机的记录里找到这段对话，整理成接续材料（目标、最近几轮全文、更早的轮次摘录、保留压缩摘要），然后 agent 从最后一个未完成的问题继续。

- **只读**：不会修改其他 agent 的文件，也不会把会话转成别的平台的格式。唯一的写入是 `~/.cache/session-handoff/` 下的标题缓存。
- **纯本地**：技能本身不上传任何内容。（接续材料当然会发给你*当前*使用的 agent 所对应的模型服务，这正是接续的目的。）
- **零依赖**：Python 3.9+ 标准库。

## 支持的来源

| 来源 | 读取位置 |
|---|---|
| Claude Code、Claude 桌面版（Code 标签页与本地 agent 会话） | `~/.claude/projects/**.jsonl` 和桌面版的会话元数据 |
| Codex（命令行与桌面版） | `~/.codex/sessions/**/rollout-*.jsonl` 和 `session_index.jsonl` |

任何能加载 `SKILL.md` 技能、并能运行 Python 的 agent 都可以使用它：Claude Code、Codex、Gemini CLI 等。不支持 claude.ai / ChatGPT 网页对话和云端会话（它们不在你的电脑上）。其他 agent 可以通过添加来源模块来支持，见下文。

在 macOS 上测试过；Linux 和 Windows 的路径按常见位置做了兼容，但没有实机验证（见 [adapting.md](skills/session-handoff/references/adapting.md)）。首次使用请先运行 `doctor`，并欢迎反馈结果。

## 安装

```sh
git clone https://github.com/GenLI3202/session-handoff.git
cd session-handoff
python3 install.py
```

`install.py` 会把技能复制到检测到的每个 agent 的技能目录（`~/.claude/skills`、Codex 的 `~/.agents/skills`、`~/.gemini/skills`），并运行自检。可用参数：`--dry-run`；其他 agent 用 `--target <技能目录>`。也可以手动把 `skills/session-handoff/` 复制到 agent 的技能目录。

## 使用

在你当前使用的 agent 里直接说：

> 接着聊 Claude 里叫「预算复盘」的会话。
> Continue my Codex conversation "migration plan" here.
> 接续 Codex 的会话 `3f9a1c2e`。

如果有多个会话匹配，agent 会列出候选让你选。也可以自己运行脚本：

```sh
python3 skills/session-handoff/scripts/handoff.py list --query 预算
python3 skills/session-handoff/scripts/handoff.py --lang zh show "预算复盘" --source claude -n 6
```

## 适配你的电脑

这个技能的设计是：装好之后，agent 可以根据本机情况自行微调。

1. `handoff.py doctor` 会报告哪些 agent 的记录存在、在哪里找的、最新的会话是否还能解析。
2. 记录不在默认位置时，用 `CODEX_HOME`、`CLAUDE_CONFIG_DIR`、`CLAUDE_DESKTOP_DIR` 或 `~/.config/session-handoff/config.json` 指定。
3. agent 升级后改了记录格式时，`doctor` 会提示，agent 按“Format drift”流程修补适配器。
4. 支持新的 agent 只需在 `scripts/sources/` 里加一个文件（自动发现）。

详见 [skills/session-handoff/references/adapting.md](skills/session-handoff/references/adapting.md)。

## 开发

```sh
python3 -m unittest discover -s tests -v
```

测试在临时目录里生成合成的会话文件，不会读取你真实的对话。

## 许可证

MIT
