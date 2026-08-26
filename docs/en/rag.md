# RAG source retrieval

> [Back to index](index.md) · [Project overview](../../README.md)

RAG lets the Agent retrieve relevant material from files/folders you register
before answering or acting, injected like memory into each task; an on-demand
search tool is also available.

## Registering a source

```bash
# folders are read recursively; --ext replaces the default allowlist
python -m geass.rag add ~/notes --name notes
python -m geass.rag add ~/manual.md --ext .md
```

Default extensions: `md/txt/py/ts/tsx/js/json/yaml/yml/toml/csv/log/html/css`.
Chunk mirrors keep the same relative path and name as the original files;
re-running `add` reconciles the manifest, so deleting one chunk file and
re-importing restores only that file without duplicating the others.

## Management

```bash
python -m geass.rag list                        # list sources and types
python -m geass.rag remove notes                # remove the whole source mirror
python -m geass.rag remove-file notes a.md      # remove one file's mirror
python -m geass.rag disable notes               # disable (keep data)
python -m geass.rag enable notes
python -m geass.rag disable-all                # disable all sources
python -m geass.rag enable-all                 # enable all sources
python -m geass.rag reindex notes               # rebuild after model change
```

You can also manage sources conversationally through the Agent's `rag_add` /
`rag_search` / `rag_list` / `rag_remove` tools.

## Retrieval modes

- With `agent.embedding_base_url + agent.embedding_model` configured (any
  OpenAI-compatible embeddings endpoint), import probes and upgrades to
  **vector retrieval** (cosine; FAISS accelerates when importable, pure
  Python otherwise);
- Without an endpoint, or if probing fails, retrieval automatically falls back
  to **local lexical search** (BM25-style + Chinese n-grams);
- Each source records the embedding-model fingerprint; switching models marks
  it `needs_reindex`, retrieval degrades to lexical, and `rag reindex` rebuilds.

## Switches

```text
agent.rag_enabled            # master switch
agent.rag_inject_enabled     # auto-inject switch (rag_search stays available)
agent.rag_inject_min_score   # minimum injection score (default 0.25)
agent.rag_path               # storage root (default ~/.geass/.rag)
```

Each source can be `enable`/`disable`d individually; disabled sources are
excluded from search and injection but their data is kept.
