"""Geass 服务入口。"""

from __future__ import annotations

import logging
import socket
import struct
import sys

import uvicorn

from .config import load_config
from .server.app import create_app
from .server.state import build_state


def lan_ips() -> list[str]:
    """枚举本机局域网 IPv4 地址（不含 127.0.0.0/8）。

    优先解析主机名，失败时再逐网卡读 IPv4 地址；网络不可用时返回空列表。
    """
    ips: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = str(info[4][0])
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass

    try:
        import fcntl

        names = [name for _, name in socket.if_nameindex()]
    except (ImportError, OSError):
        names = []
    for name in names:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                # Linux SIOCGIFADDR
                packed = fcntl.ioctl(
                    sock.fileno(),
                    0x8915,
                    struct.pack("256s", name.encode()[:15]),
                )
                ip = socket.inet_ntoa(packed[20:24])
        except OSError:
            continue
        if ip and not ip.startswith("127.") and ip not in ips:
            ips.append(ip)
    return ips


def main() -> None:
    extra = [arg for arg in sys.argv[1:] if not arg.startswith("-")]
    if extra:
        print(
            "提示：geass 现在是统一命令入口。查看全部命令请运行 "
            "`geass commands`（或 `python -m geass help`）；"
            "启动服务请运行 `geass serve` 或不带任何参数。",
            file=sys.stderr,
        )
        raise SystemExit(2)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    config = load_config(persist=True)
    state = build_state(config)
    app = create_app(state)

    host_label = "localhost" if config.server.host in ("0.0.0.0", "::") else config.server.host
    print("=" * 56)
    print("  Geass 服务已启动")
    print(f"  手机访问:  http://{host_label}:{config.server.port}")
    print(f"  访问 Token: {config.server.token}")
    print(f"  Agent 模型: {config.agent.model}")
    if state.mcp is not None:
        print("  MCP 管理:   手机资源面板「MCP」页签 / 终端 `geass mcp` 命令")
    if config.agent.base_url:
        print(f"  接口地址:  {config.agent.base_url}")
    for ip in lan_ips():
        print(f"  局域网访问:  http://{ip}:{config.server.port}")
    if not config.agent.ocr_token:
        print("  提示: 未配置 PaddleOCR token，非视觉模型将退化为键盘-only")
    if state.capture.monitor_count() > 1:
        print("  提示: 检测到多显示器，当前只操作主屏，其他屏幕请手动直控")
    print("  异地访问:  ./scripts/remote.sh（无需同一 Wi-Fi，见 README）")
    print("=" * 56)

    uvicorn.run(app, host=config.server.host, port=config.server.port, log_level="info")


if __name__ == "__main__":
    main()
