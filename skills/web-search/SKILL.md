---
name: web-search
description: 当用户要求用浏览器搜索信息、打开网页或访问指定网址查看页面内容时使用
---

# web-search

## 目标

用默认浏览器打开网页或搜索引擎，输入关键词、提交查询并读取结果。

## 工作流

### 打开指定网址

1. 调用 `browser` 工具，`action="open"`，`url` 用 https:// 完整地址；
   没有 `browser` 工具时退回 `open_terminal` 执行 `xdg-open "URL"`；
2. `wait` 1~3 秒等页面加载；
3. `window_info` 确认浏览器窗口已打开，再 `screenshot` 观察页面内容
   （视觉模式）或读 OCR 文本转写（文本模式）；
4. 页面没加载出来时再 `wait` 重试，不要反复 `xdg-open`。

### 搜索引擎搜索

1. `browser` 工具 `action="open"`，url 填
   `https://www.google.com/search?q=关键词`
   （可用 `bing.com/search?q=` 或 `baidu.com/s?wd=`；关键词含空格用 `%20` 或 `+`）；
2. `wait` 2~4 秒后 `screenshot` 读取结果列表；
3. 若要进入某个结果：观察结果标题旁的坐标，`click` 打开，再 `wait` +
   `window_info` + `screenshot` 验证新页面；
4. 需要翻页或滚动时用 `scroll`（dy<0 向下滚），之后重新观察。

### 在页面里交互搜索

1. 先用 `click` 聚焦地址栏或搜索框（依据屏幕文本定位）；
2. `type_text` 输入关键词，`key_press` 按 `enter`；
3. `wait` 后 `screenshot` 验证结果。

## 验收标准

- 打开的 URL 与查询词明确，不依赖记忆中的网址；
- 关键信息（标题、摘要）来自实际看到的页面文本/截图；
- 页面无法访问时改用备用搜索引擎，并在 `finish` 中说明。

## 注意事项

- `xdg-open` 是异步返回的：终端显示已启动不代表页面已加载，必须 `wait` + 观察；
- 中文关键词建议直接放在 URL 里（xdg-open 会按 URL 编码处理），逐字输入更易被 IME 干扰；
- 不要点击广告/无关链接；只浏览与任务相关的内容。
