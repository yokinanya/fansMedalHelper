"""
获取 B 站 access_key。
"""
import argparse
import asyncio

import aiohttp
import qrcode

from src.login import DEFAULT_POLL_SECONDS, TvLogin

QR_BLACK = "\033[30m"
QR_RESET = "\033[0m"
QR_UPPER = "\u2580"
QR_LOWER = "\u2584"
QR_FULL = "\u2588"
QR_EMPTY = " "
MIN_QR_SCALE = 1
MAX_QR_SCALE = 4


async def login(timeout_seconds: int, qr_scale: int) -> None:
    async with aiohttp.ClientSession() as session:
        client = TvLogin(session)
        qr_url, auth_code = await client.get_qr_code()
        print("请用 B 站客户端扫码登录：", flush=True)
        print_qr_code(qr_url, qr_scale)
        print("登录 URL：", flush=True)
        print(qr_url, flush=True)
        access_key = await client.poll_access_key(auth_code, timeout_seconds)

    print("access_key:", flush=True)
    print(access_key, flush=True)


def print_qr_code(data: str, scale: int) -> None:
    qr = qrcode.QRCode(border=1)
    qr.add_data(data)
    qr.make(fit=True)

    matrix = qr.get_matrix()
    for index in range(0, len(matrix), 2):
        upper = matrix[index]
        lower = matrix[index + 1] if index + 1 < len(matrix) else [False] * len(upper)
        line = "".join(qr_cell(top, bottom) * scale for top, bottom in zip(upper, lower))
        for _ in range(scale):
            print(f"{line}", flush=True)


def qr_cell(top: bool, bottom: bool) -> str:
    if top and bottom:
        return QR_FULL
    if top:
        return QR_UPPER
    if bottom:
        return QR_LOWER
    return QR_EMPTY


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TV扫码登录并打印 access_key")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_POLL_SECONDS,
        help="等待扫码秒数",
    )
    parser.add_argument(
        "--qr-scale",
        type=int,
        choices=range(MIN_QR_SCALE, MAX_QR_SCALE + 1),
        default=1,
        metavar=f"{MIN_QR_SCALE}-{MAX_QR_SCALE}",
        help="终端二维码缩放倍数，默认 1",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(login(args.timeout, args.qr_scale))


if __name__ == "__main__":
    main()
