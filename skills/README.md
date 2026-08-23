# Geass SKILL 目录

这里的每个子目录都是一个 **SKILL 种子**。服务启动时会把本目录同步到
运行时目录的 `~/.geass/.skill/.system/`，Agent 实际从
`~/.geass/.skill/` 加载；空闲进化自动生成的技能则放在
`~/.geass/.skill/` 根目录（`.system/` 之外），同名时覆盖系统种子。

## 目录结构

```text
skills/
  desktop-automation/   # 通用桌面 GUI 操作 SOP
    SKILL.md            # 必需：技能说明
  terminal-automation/  # 终端执行 / 流式输入 / 输出监控
    SKILL.md
  web-search/           # 打开网页与搜索
    SKILL.md
  ...
```

## 内置基础技能

- **desktop-automation**：在图形界面里打开应用、点击按钮、填表、拖拽等
  通用 GUI 任务的「观察 → 定位 → 执行 → 验证 → 收尾」标准流程；
- **terminal-automation**：用 `open_terminal` 一键执行命令、用
  `terminal_type` 像人一样流式输入、用 `terminal_read` 监控长驻进程输出；
- **web-search**：用内置 `browser` 工具打开网页或搜索引擎，输入关键词并
  读取结果。

这些是可直接复用的基础 SOP；针对具体场景（如某个软件的操作）可以按同样的
格式新增目录，Agent 会在服务启动/下一条命令前自动发现。

SKILL 应该保持底层和通用：沉淀的是「跨场景可复用、需要多步判断的工作流」，
而不是单个工具能完成的事情。例如"打开浏览器 / 新建标签页"由内置的
`browser` 工具直接承担，不需要单独的浏览器 SKILL；同样地，`window_info`、
`find_element` 等验证能力也属于工具层。

## SKILL.md 格式

使用标准的 YAML frontmatter + Markdown 正文：

```markdown
---
name: my-skill
description: 一句话说明“什么时候该用这个技能”，Agent 据此做匹配
---

# 正文

写清目标、前置条件、具体工具调用步骤与验收标准。
```

## 给 SKILL 编写者的约定

- `name`：唯一、小写短横线命名，供 `read_skill` 引用；
- `description`：一句话说明“什么时候该用这个技能”，Agent 会根据它做匹配；
- 正文写清目标、前置条件、具体工具调用步骤与**可验证的验收标准**；
- 只允许调用 Geass 已暴露的工具（键鼠、终端、截图/OCR 等），不要假设有文件读写能力；
- 附件脚本应放在技能目录内，正文里用绝对路径引用；需要运行时让 Agent 使用 `open_terminal` 执行。

## 同步与热加载

服务启动时以及**每条命令开始前**都会把本目录同步到运行时的
`~/.geass/.skill/.system/`，然后重新扫描 `~/.geass/.skill/`。因此修改仓库里的
种子、或由空闲进化生成新技能后，
直接下达下一条命令即可生效，无需重启服务。删除某个种子目录也会让它在
运行时镜像中消失，但不会影响 `~/.geass/.skill/` 根目录下自动进化的技能。
