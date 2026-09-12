"""Geass 服务入口。"""

from __future__ import annotations

import argparse
import io
import logging
import socket
import struct
import sys

import uvicorn

from .config import load_config
from .server.app import create_app
from .server.pairing import DEFAULT_TTL, MAX_TTL, MIN_TTL, PairingManager, normalize_ttl
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


def default_route_ip() -> str | None:
    """探测默认出口网卡的 IPv4（仅用 UDP connect，不产生实际流量）。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("1.1.1.1", 80))
            address = str(sock.getsockname()[0])
    except OSError:
        return None
    return address if address and not address.startswith("127.") else None


def candidate_ips() -> list[str]:
    """局域网候选地址；默认出口网卡排在最前，减少选到虚拟网卡的概率。"""
    ips = lan_ips()
    preferred = default_route_ip()
    if preferred is None:
        return ips
    return [preferred, *[ip for ip in ips if ip != preferred]]


def qr_base_url(config, host_override: str = "") -> tuple[str, bool]:
    """返回 (基础地址, 手机是否可达)；优先显式覆盖，其次公网地址/局域网 IP。"""
    override = str(host_override or "").strip().rstrip("/")
    if override:
        if "://" in override:
            return override, True
        return f"http://{override}:{config.server.port}", True
    public_url = str(config.server.public_url or "").strip().rstrip("/")
    if public_url:
        return public_url, True
    ips = candidate_ips()
    if ips:
        return f"http://{ips[0]}:{config.server.port}", True
    return f"http://127.0.0.1:{config.server.port}", False


def render_terminal_qr(url: str) -> str | None:
    """返回可在终端打印的二维码文本；segno 不可用时返回 None。"""
    try:
        import segno
    except ImportError:  # pragma: no cover - segno 已列入依赖
        return None
    try:
        buffer = io.StringIO()
        segno.make(url, error="m").terminal(out=buffer, compact=True)
    except Exception:  # pragma: no cover - 渲染失败时降级为链接
        return None
    return buffer.getvalue()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="geass",
        description="Geass 服务；启动后可用手机扫码或输入 Token 连接",
    )
    parser.add_argument("--qr", action="store_true", help="启动时打印扫码配对二维码")
    parser.add_argument(
        "--qr-ttl",
        type=float,
        default=DEFAULT_TTL,
        help=f"配对码有效期秒数（{MIN_TTL:.0f}~{MAX_TTL:.0f}，默认 {DEFAULT_TTL:.0f}）",
    )
    parser.add_argument(
        "--qr-host",
        default="",
        help="二维码使用的主机名或完整地址（多网卡/自动识别不准时手动指定）",
    )
    args, extra = parser.parse_known_args(argv)
    if extra:
        print(
            "提示：geass 现在是统一命令入口。查看全部命令请运行 "
            "`geass commands`（或 `python -m geass help`）；"
            "启动服务请运行 `geass serve` 或不带任何参数。",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if not (MIN_TTL <= float(args.qr_ttl) <= MAX_TTL):
        parser.error(f"--qr-ttl 必须在 {MIN_TTL:.0f}~{MAX_TTL:.0f} 秒之间")
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    config = load_config(persist=True)
    state = build_state(config)
    pairing_link: str | None = None
    pairing_reachable = True
    if args.qr:
        state.pairing = PairingManager(normalize_ttl(args.qr_ttl))
        entry = state.pairing.create()
        base, pairing_reachable = qr_base_url(config, args.qr_host)
        pairing_link = f"{base}/#pair={entry.code}"
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

    if pairing_link is not None:
        print()
        print(f"  扫码配对:  {normalize_ttl(args.qr_ttl):.0f} 秒内有效、仅可使用一次")
        qr_text = render_terminal_qr(pairing_link)
        if qr_text:
            print(qr_text)
        else:
            print("  （未安装 segno，无法渲染二维码，请使用下方链接）")
        print(f"  配对链接:  {pairing_link}")
        if not config.server.public_url and not args.qr_host:
            others = [ip for ip in candidate_ips() if f"http://{ip}:{config.server.port}" != base]
            if others:
                print(
                    "  其他局域网地址: "
                    + "、".join(f"http://{ip}:{config.server.port}" for ip in others)
                )
        if not pairing_reachable:
            print("  提示: 未检测到局域网 IP 且未配置 server.public_url，手机可能无法访问")
        print(
            f"  提示: 手机打不开时请检查电脑防火墙是否放行 {config.server.port} 端口，"
            "或改用 --qr-host 指定可达地址"
        )
        print("=" * 56)

    uvicorn.run(app, host=config.server.host, port=config.server.port, log_level="info")


if __name__ == "__main__":
    main()
