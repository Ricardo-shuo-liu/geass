# Configuration

> [Back to index](index.md) · [Project overview](../../README.md)

Personal settings (including the API key) live in `~/.geass/env.toml` outside the repo; `config.toml` keeps neutral defaults so it is safe to commit. The **access Token is randomly regenerated on every startup** and never written to a file:

| Key | Default | Description |
| --- | --- | --- |
| `server.host` / `server.port` | `0.0.0.0` / `8765` | Listen address |
| `server.token` | random per startup | optional: set explicitly to pin it |
| `screen.fps` | `15` | Stream FPS |
| `screen.jpeg_quality` | `70` | JPEG quality |
| `screen.max_width` | `1920` | Max stream width |
| `security.enabled` | `true` | Manual review of high-risk shell commands |
| `security.approval_timeout` | `30` | Seconds to wait for the phone's decision; timeout auto-denies (min 5s) |
| `security.patterns` | empty | Custom blocklist regexes; empty uses the built-in list, non-empty replaces it |
| `agent.model` | `gpt-5.6-terra` | Vision model (e.g. `sol` / `luna`) |
| `agent.base_url` | empty | OpenAI-compatible endpoint; DeepSeek: `https://api.deepseek.com` |
| `agent.vision` | `true` | Whether the model accepts images; non-vision models auto-degrade to text mode |
| `agent.vision_whitelist` | empty | Whitelist of vision-capable models (comma-separated); when set, a model on the list gets screenshots, anything else is automatically paired with PaddleOCR |
| `agent.ocr` | `true` | Use PaddleOCR (remote API) to transcribe the screen for non-vision models (text + normalized box coordinates) |
| `agent.ocr_token` | empty | AI Studio access token; set via `python -m geass.config set --ocr-token ...` |
| `agent.ocr_model` | `PaddleOCR-VL-1.6` | OCR model: `PaddleOCR-VL-1.6` or `PP-StructureV3` |
| `agent.ocr_base_url` | `https://paddleocr.aistudio-app.com` | OCR jobs API endpoint |
| `agent.ocr_timeout` | `90` | Seconds to wait for an OCR job (submit + poll) |
| `agent.terminal_timeout` | `15` | Seconds `open_terminal` waits for a command's output |
| `agent.skills_dir` | `skills` | Seed SKILL directory (relative to the project root), synced into `~/.geass/.skill/.system/` |
| `agent.skill_root` | empty | Runtime SKILL root; defaults to `~/.geass/.skill` |
| `agent.schedule_path` | empty | Scheduled-task directory; defaults to `~/.geass/.schedule` |
| `agent.rag_enabled` | `true` | RAG master switch |
| `agent.rag_inject_enabled` | `true` | Auto-inject RAG snippets at task start |
| `agent.rag_inject_min_score` | `0.25` | Minimum injection score (0-1) |
| `agent.rag_inject_hits` | `5` | Number of injected snippets |
| `agent.rag_inject_chars` | `3000` | Max injected characters |
| `agent.rag_path` | empty | RAG storage root; defaults to `~/.geass/.rag` |
| `agent.embedding_enabled` | `true` | Enable embedding vector retrieval |
| `agent.embedding_base_url` | empty | OpenAI-compatible embeddings endpoint; empty = lexical |
| `agent.embedding_model` | `text-embedding-3-small` | Embedding model name |
| `agent.pot_enabled` | `true` | POT reflection master switch |
| `agent.pot_inject_cot` | `true` | Always inject Global-COT |
| `agent.pot_inject_rot` | `true` | Inject relevant ROTs |
| `agent.pot_rot_hits` | `2` | Number of ROTs to inject (0-5) |
| `agent.pot_path` | empty | POT storage root; defaults to `~/.geass/.pot` |
| `agent.cli_rounds` | `3` | Deliberate debate rounds |
| `agent.cli_subagents` | `3` | Deliberate sub-agent count |
| `agent.background_enabled` | `true` | Background tasks master switch |
| `agent.background_max_tasks` | `10` | Background task concurrency cap |
| `agent.evolution_max_tokens` | `2000` | SKILL evolution generation token cap |
| `agent.pot_reflect_max_tokens` | `2500` | POT reflection generation token cap |
| `agent.context_compress_enabled` | `true` | Context compression switch |
| `agent.context_compress_after` | `18` | Message-count threshold for compression |
| `agent.context_compress_chars` | `20000` | Character threshold for compression |
| `agent.memory_enabled` | `true` | Enable persistent memory (`remember`/`recall`/`forget`) |
| `agent.memory_path` | empty | Memory directory; defaults to `~/.geass/.memory` (entries live in `entries.json`) |
| `agent.memory_max_entries` | `200` | Maximum number of stored entries |
| `agent.memory_context_entries` | `8` | Relevant entries injected into each task's system prompt |
| `agent.evolution_enabled` | `true` | Enable the idle evolution engine |
| `agent.evolution_idle_seconds` | `300` | Idle seconds before evolution runs (min 30) |
| `agent.evolution_interval` | `1800` | Minimum seconds between evolutions (min 60) |
| `agent.evolution_max_skills` | `20` | Cap on automatically generated skills (1-100) |
| `agent.max_steps` | `30` | Max steps per task |
| `agent.image_max_edge` | `1568` | Long edge cap for screenshots sent to the model |
| `voice.fallback_model` | `whisper-1` | Voice fallback transcription model |

Environment variables:

| Variable | Description |
| --- | --- |
| `GEASS_API_KEY` | API key |
| `GEASS_BASE_URL` | Overrides `agent.base_url` |
| `GEASS_MODEL` | Overrides `agent.model` |
| `GEASS_VISION_WHITELIST` | Comma-separated vision-model whitelist; overrides `agent.vision_whitelist` |
| `GEASS_TOKEN` | Optional: pin the Token (otherwise random per startup) |
| `GEASS_PADDLEOCR_TOKEN` | AI Studio OCR token (falls back to `PADDLEOCR_MCP_AISTUDIO_ACCESS_TOKEN`) |
| `GEASS_PADDLEOCR_MODEL` | Overrides `agent.ocr_model` |
| `GEASS_PADDLEOCR_BASE_URL` | Overrides `agent.ocr_base_url` |
| `GEASS_CONFIG` / `GEASS_HOME` | Project config path / user config dir (default `~/.geass`) |

### Persistence & management

Precedence: **env vars > `~/.geass/env.toml` > `config.toml` > defaults**.

- `GEASS_*` env vars used at startup are auto-saved to `~/.geass/env.toml` (mode 0600);
- CLI: `python -m geass.config show` (secrets masked); `python -m geass.config set sk-... https://api.deepseek.com deepseek-v4-flash --vision false`; OCR: `python -m geass.config set --ocr-token ... --ocr-model PaddleOCR-VL-1.6`; vision whitelist: `--vision-whitelist gpt-5.6-terra,sol`; memory: `--memory-enabled false` / `--memory-path ...`; skills & evolution: `--skill-root ...` / `--evolution-enabled false` / `--evolution-idle-seconds 600`; safety: `--security-enabled false` / `--approval-timeout 60`;
- Runtime API: `GET /api/config` (masked) and `POST /api/config` (e.g. `{"model":"...","base_url":"...","api_key":"...","vision":false}`) — applied and persisted immediately.
