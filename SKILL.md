---
name: github-skill-deploy
agent_created: true
description: |
  把一个第三方 Skill（GitHub 仓库 / 仓库 URL）部署到本地 WorkBuddy 技能目录，并做安全审计与可用性验证。
  触发词：「把 XX skill 部署到本地」「安装 XX 技能」「deploy this skill locally」「把 github.com/xxx/yyy-skill 装到本地」。
  产出：`~/.workbuddy/skills/<skill-name>/` 下最小功能可用包 + 审计结论 + 验证结果。
  仅用于「第三方 skill 落地」这一件事；不用于创作新 skill（那用 skill-creator）。
---

# github-skill-deploy — 第三方 Skill 本地化落地

把一个 GitHub 上的 Skill 仓库，**审计 → 最小化部署 → 适配 → 验证** 到本地 `~/.workbuddy/skills/`。

## 何时用

用户给出一个 skill 仓库地址（或让它去找），要求「部署到本地 / 安装 / 验证可用性」时。典型请求：
- 「将 XX skill 部署到本地，并验证可用性」
- 「把 https://github.com/<owner>/<repo> 装到本地」

## 硬性前置：安全审计（不可跳过）

**先审计，后落地。** 审计对象是仓库里所有会被执行的内容：`SKILL.md`、`scripts/*`、任何 `.py/.sh/.js`。
判定档位：**P0**（必须拒绝/强警告）／**P1**（警告+需明确确认）／**P2**（安全，可部署）。
重点排查：外联数据外泄、`os.system`/`eval`/`exec`、无边界 `rm -rf`/`shutil.rmtree`、下载执行远端脚本、读取凭据外传。
> 结论要写进给用户的报告里（例：「脚本均为良性工具链，风险 P2 安全」）。

## 部署原则：只装「功能必需子集」

一个 skill 仓库常混有示例产物、演示媒体、官网、评测数据。**只部署技能运行所需的部分**，别整包复制：
- 必需：`SKILL.md`、`references/`、`scripts/`、`templates/`、`schemas/`（按仓库而定）
- 通常可剔除：`examples/`、`books/`、`benchmarks/`、`website/`、`dist/`、`promo/`、`assets/*.gif|*.png|*.mp4`、`.github/`、多语言 README
- 保留 `LICENSE` + 一个 README 以便署名溯源

## 执行流程

### 1. 拿仓库内容

**优先**：`git clone --depth 1 <url> <工作区>/.audit-<name>`。
**若克隆被 SIGTERM 掐断（仓库含大素材，见下"坑 2"）**：改用 GitHub API 取文件树 + raw 下载。
第一步先列树（含字节大小）再决定下什么：

```bash
python scripts/fetch_repo_files.py <owner>/<repo> --list        # 列全树 + 大小
python scripts/fetch_repo_files.py <owner>/<repo> --out <dir> --files SKILL.md,references/a.md,scripts/b.py
python scripts/fetch_repo_files.py <owner>/<repo> --out <dir> --max-size 200   # 只下 <200KB 的文件
```

### 2. 审计

逐个读 `SKILL.md`（含 frontmatter 与正文有无可疑指令）与被执行脚本，按上文档位定风险，必要时用 Grep 扫危险模式：

```
os\.system|subprocess\.|shutil\.rmtree|eval\(|exec\(|__import__|socket\.|requests\.|urllib\.|os\.remove|unlink
```

### 3. 最小化部署

```bash
mkdir -p ~/.workbuddy/skills/<skill-name>
cp <audit>/SKILL.md <audit>/LICENSE <audit>/README.md ~/.workbuddy/skills/<skill-name>/
cp -r <audit>/references <audit>/scripts <audit>/templates <audit>/schemas ~/.workbuddy/skills/<skill-name>/  # 按实际存在
```

### 4. 平台适配（关键，否则"装了用不了"）

- **加 `agent_created: true`**：写进部署版 `SKILL.md` 的 frontmatter（`name:` 之后），便于日后管理。
- **改写平台耦合路径**：原为 Claude Code 写的 skill 常引用 `.claude/skills/`，在 WorkBuddy 下应改为 `~/.workbuddy/skills/`。
  先 Grep 统计：`\.claude/` → 再 `Edit(replace_all)` 替换。替换后复核：`grep -c '\.claude/skills/' file` 应为 0。

### 5. 验证可用性

按技能自带工具组合验证，至少覆盖「能加载 + 能执行」：
- frontmatter 可解析（YAML）+ 关键字段非空：
  ```python
  import yaml,pathlib; t=pathlib.Path("SKILL.md").read_text(encoding="utf-8")
  print(yaml.safe_load(t.split("---",2)[1]))
  ```
- 有自带自检命令就跑（如 `cangjie.py doctor`）。
- 逐个实跑脚本（`bash -n` 查 shell 语法；python 脚本造最小输入跑一遍）。
- 技能引用的相对文件（`references/...`）都存在。

### 6. 收尾

清理审计目录（`.audit-*`）；写工作日志；向用户报告：部署位置、文件数、审计结论、验证结果、适配改动（尤其是改过的路径）。

## 坑表（Windows + WorkBuddy 环境，实测）

1. **Shell PATH 可能缺 MSYS 工具**：`dirname/tail/rm/ls` 报 not found 时，在命令开头补
   `export PATH="/usr/bin:/bin:/mingw64/bin:$PATH"`（每个 Bash 调用都要加，shell 状态不跨调用保留）。
2. **大仓库 `git clone` 被沙箱 SIGTERM 掐断**：仓库含大媒体（hero.gif/mp4/pdf 等）时，整包克隆会中断，
   只落残缺 `.git`（`git log` 报 "current branch appears to be broken"）。→ 用 `fetch_repo_files.py` 只下功能文件；
   先用 `--list` 看大小，避开 MB 级素材。（小文件 raw 下载正常，如 17KB README 可下。）
3. **Git Bash 不翻译传给 python.exe 的路径**：`/c/Users/...`、`/tmp/x.srt` 传给 Windows python 会变成
   `C:\c\Users\...`、`\tmp\x.srt` 而找不到。→ 用**盘符路径** `C:/Users/...` 或**相对路径**。
4. **运行环境**：托管 Python `C:/Users/Silen/.workbuddy/binaries/python/envs/default/Scripts/python.exe`
   （已装 PyYAML；如缺包用其 `Scripts/pip.exe` 装到这个隔离 venv，勿装全局）。
5. **`rm -rf` 走 `/usr/bin/rm`**：PATH 补好后用 `/usr/bin/rm -rf` 明确调用，避免 shim 干扰。
