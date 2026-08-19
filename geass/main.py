"""Geass 服务入口。"""
from __future__ import annotations

import logging

import uvicorn

from .config import load_config
from .server.app import create_app
from .server.state import build_state


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    config = load_config()
    state = build_state(config)
    app = create_app(state)

    host_label = "localhost" if config.server.host in ("0.0.0.0", "::") else config.server.host
    print("=" * 56)
    print("  Geass 服务已启动")
    print(f"  手机访问:  http://{host_label}:{config.server.port}")
    print(f"  访问 Token: {config.server.token}")
    print(f"  Agent 模型: {config.agent.model}")
    if config.agent.base_url:
        print(f"  接口地址:  {config.agent.base_url}")
    print("  局域网设备请用电脑的局域网 IP 代替 localhost")
    print("=" * 56)

    uvicorn.run(app, host=config.server.host, port=config.server.port, log_level="info")


if __name__ == "__main__":
    main()
