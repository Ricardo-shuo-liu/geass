# RAG 数据源检索

> [返回索引](index.md) · [项目简介](../../README.zh.md)

RAG 让 Agent 在回答和执行任务前，先从你指定的文件/文件夹中检索相关资料，
与记忆一样注入到任务上下文；也提供按需检索工具。

## 锁定数据源

```bash
# 文件夹会递归读取；--ext 可整体替换默认后缀白名单
python -m geass.rag add ~/notes --name notes
python -m geass.rag add ~/手册.md --ext .md
```

默认支持：`md/txt/py/ts/tsx/js/json/yaml/yml/toml/csv/log/html/css`。
分块镜像与原始文件**同名同相对路径**，重复执行 `add` 是对账式重导入：
删除某个分块后再导入只恢复该文件，不会重复导入其他文件。

## 管理

```bash
python -m geass.rag list                        # 查看全部数据源与类型
python -m geass.rag remove notes                # 删除整个源的 RAG 镜像
python -m geass.rag remove-file notes a.md      # 删除单个文件的镜像
python -m geass.rag disable notes               # 停用（保留数据）
python -m geass.rag enable notes
python -m geass.rag disable-all                # 停用全部数据源
python -m geass.rag enable-all                 # 启用全部数据源
python -m geass.rag reindex notes               # 嵌入模型变化后重建
```

也可以直接对 Agent 说“把 ~/notes 加入 RAG 数据源”“查一下 RAG 里关于 X 的
内容”，由 `rag_add` / `rag_search` / `rag_list` / `rag_remove` 工具完成。

## 检索模式

- 配置 `agent.embedding_base_url + agent.embedding_model`（任意 OpenAI 兼容
  embeddings 端点）后，导入时自动探测并升级为**向量检索**（余弦；faiss 可用
  时自动加速，否则纯 Python）；
- 未配置或端点失败时自动降级**本地词法检索**（BM25 风格 + 中文 n-gram），
  RAG 照常可用；
- 每个源记录嵌入模型指纹；切换模型后标记 `needs_reindex`，检索自动降级词法，
  用 `rag reindex <source>` 重建向量。

## 开关

```text
agent.rag_enabled            # 总开关
agent.rag_inject_enabled     # 自动注入开关（rag_search 仍可用）
agent.rag_inject_min_score   # 注入最低相似度（默认 0.25）
agent.rag_path               # 存储根（默认 ~/.geass/.rag）
```

每个数据源可单独 `enable/disable`；停用后不参与检索与注入，但数据保留。
