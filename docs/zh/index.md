# Geass 详细文档（中文）

> 项目简介与快速开始见 [README.zh.md](../../README.zh.md)；
> 英文文档见 [docs/en](../en/index.md)；设计依据见 [DESIGN.md](../DESIGN.md)。

## 目录

- [快速开始](getting-started.md)：环境要求、安装依赖、模型与 OCR 配置、启动服务、手机连接、异地访问、前端构建
- [功能说明](features.md)：核心功能一览
- [任务系统与记忆](tasks-and-memory.md)：难度自判、规划与验证闭环、持久记忆
- [技能进化与运行时目录](skills-evolution.md)：运行时 SKILL 目录、空闲进化系统
- [手动直控（虚拟键鼠）](manual-control.md)：触屏、虚拟鼠标触摸板、虚拟键盘与手势
- [信任层（动作预览与隐私遮罩）](trust-layer.md)：可视化幽灵操作、分级审核与截图打码
- [定时任务](schedule.md)：指定时间执行指定命令，持久化与状态推送
- [RAG 数据源检索](rag.md)：锁定本地文件/文件夹、向量/词法检索、数据源管理
- [MCP 工具接口](mcp.md)：导入/测试/管理外部 MCP 工具，UI 与命令行双入口
- [POT 反思系统](pot.md)：Global-COT 与角色 ROT 模板、空闲反思
- [CLI 终端助手](cli-assistant.md)：light/deliberate 双模式，复用全部资产
- [命令行](cli.md)：统一命令入口、全命令查看、双确认重置
- [资源管理（手机端）](resources.md)：记忆/MCP/RAG/技能/POT/定时可视化管理
- [配置说明](configuration.md)：配置优先级、环境变量、CLI 与运行时接口
- [项目结构与开发](development.md)：模块结构、开发测试、已知限制
- [已知问题与功能边界](known-issues.md)：按功能域整理的代码现状问题、能力粒度与限制

## 相关文档

- [SKILL 编写说明](../../skills/README.md)
- [设计文档与路线图](../DESIGN.md)
- [英文详细文档](../en/index.md)
