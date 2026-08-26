# 项目结构与开发

> [返回索引](index.md) · [项目简介](../../README.zh.md)

```text
geass/
  geass/          # 后端（纯 Python）
    agent.py      # Agent 循环与 pyautogui 工具集
    tasks.py      # 自判难度的任务计划（plan 工具的数据模型）
    memory.py     # 跨任务持久记忆（JSON 文件存储）
    evolution.py  # 空闲进化引擎：自动把高频使用模式写成 SKILL
    safety.py     # 高危命令黑名单策略
    check.py      # 环境自检命令（python -m geass.check）
    ocr.py        # PaddleOCR AI Studio 远程 API 后端
    skills.py     # SKILL 种子同步、运行时加载与渐进披露
    asyncutil.py  # 终端/OCR 阻塞调用的异步桥接
    server/       # FastAPI、WebSocket、认证、人工审核网关
    screen.py     # mss 抓屏与帧流
    io/backend.py # 输入后端抽象（PyAutoGUI 实现）
    io/accessibility.py # Linux AT-SPI 控件与窗口查找（find_element / window_info）
    io/terminal.py# 可见终端会话与输出捕获
    io/browser.py # 默认浏览器打开页面/新标签页/新窗口
  skills/         # SKILL 种子目录：启动时同步到 ~/.geass/.skill/.system（见 skills/README.md）
  web/            # React PWA（手机端薄壳）
  docs/DESIGN.md  # 完整设计文档与路线图
  config.toml     # 配置文件
  geass.yml       # 锁定的 conda 环境（给他人一键安装用）
  scripts/
    setup.sh      # clone 仓库并调用 install.sh 配置环境
    install.sh    # 按 geass.yml 一键安装/更新依赖
    run.sh        # 启动服务
    run_tests.sh  # 运行全部测试
    remote.sh     # Tailscale/Cloudflare 异地访问助手
```

## 开发与测试

```bash
pytest                     # 自动发现并运行 tests/ 下全部用例（见 pytest.ini）
./scripts/run_tests.sh     # 运行全部测试并把完整输出（含报错）记录到 test.log
python -m geass serve      # 后端 :8765（等价 python -m geass.main）
python -m geass.check      # 检查环境与配置是否就绪（密钥只显示是否配置）
cd web && npm run dev      # 前端热更新 :5173（自动代理到 8765）
```

## 已知限制

- 仅支持 Linux X11；Windows/macOS/Wayland 适配在路线图中
- 不支持视觉输入的模型（如 `deepseek-v4-flash`）：配置好 PaddleOCR AI Studio Token 就能拿到屏幕文本 + 文本框中心坐标，保留鼠标点击能力；没有 OCR 时才退化为键盘-only 工具
- PaddleOCR 截图会上传到 AI Studio API，需要自行配置 Token
- DeepSeek 等不提供语音转写接口的端点：把 `voice.fallback_model` 留空以禁用兜底转写，手机端识别仍可用
- 中文等非 ASCII 文本自动改走剪贴板粘贴；Linux 下需要 `xclip`/`xsel` 之一，缺失时退回逐键输入（IME 支持差）
- 局域网 HTTP 下 Web Speech API 与 Service Worker 不可用：语音会自动走录音上传转写，PWA 退化为普通网页
- 安全边界 v1 只审核 `open_terminal` 带命令的调用；`terminal_type` 流式输入与键鼠工具不在审核范围，理论上仍存在绕过路径，后续版本再扩展
- `find_element` 依赖 Linux 的 AT-SPI 无障碍树；Electron 或自绘界面的应用可能不暴露控件，找不到时退回截图估计坐标
- 截图会发送到你配置的模型服务商（OpenAI/DeepSeek 等），敏感内容请自行规避
- 空闲进化会在后台调用模型并产生少量 token 消耗，且会把记忆与最近任务
  发送给模型；不需要时在 `config.toml` 设置 `agent.evolution_enabled = false`

完整设计与后续路线图见 [DESIGN.md](DESIGN.md)。
