import argparse
import asyncio
import os
import time
from datetime import datetime

import aiofiles

import gui
from connection_helper import open_connection

DEFAULT_SERVER_HOST = os.getenv('MINECHAT_SERVER_HOST', 'minechat.dvmn.org')
DEFAULT_SERVER_PORT = os.getenv('MINECHAT_SERVER_PORT', 5000)
DEFAULT_FILE_PATH = os.getenv('MINECHAT_FILE_PATH', 'minechat.history')


def get_arguments():
    """Получаем аргументы командной строки, переданные скрипту."""
    parser = argparse.ArgumentParser(description='Script save minechat messages to file.')
    parser.add_argument('--host', type=str, default=DEFAULT_SERVER_HOST, help='Minechat server host.')
    parser.add_argument('--port', type=int, default=DEFAULT_SERVER_PORT, help='Minechat server port.')
    parser.add_argument('--history', type=str, default=DEFAULT_FILE_PATH, help="Path to save minechat history.")
    return parser.parse_args()


async def read_msgs(host, port, messages_queue, messages_to_file_queue):
    """Получаем сообщения из чата и пишем в очередь сообщений"""

    connect_attempts = 0
    while True:
        try:
            async with open_connection(host, port) as (reader, writer):
                while True:
                    data = await reader.readline()
                    if not data:
                        break
                    messages_queue.put_nowait(data.decode())
                    messages_to_file_queue.put_nowait(data.decode())

        except Exception as e:
            # Непонятно какой ловить эксепшен при орыве соединения, тк отключив сеть локально, скрипт продолжает работать
            time.sleep(connect_attempts)
            connect_attempts += 1


async def save_msgs(filepath, messages_to_file_queue):
    """Сохраняем сообщения в файл"""

    async with aiofiles.open(filepath, mode='a') as f:
        while True:
            msg = await messages_to_file_queue.get()
            if not msg:
                break

            await f.write(f'[{datetime.now().strftime("%d.%m.%Y %H:%M")}] {msg}')


async def send_msgs(host, port, sending_queue):
    """Вывод введенных сообщений в консоль"""
    while True:
        msg = await sending_queue.get()
        print(msg)


async def main():
    args = get_arguments()

    messages_queue = asyncio.Queue()
    messages_to_file_queue = asyncio.Queue()
    sending_queue = asyncio.Queue()
    status_updates_queue = asyncio.Queue()

    async with aiofiles.open(args.history, mode='r') as f:
        async for line in f:
            messages_queue.put_nowait(line.strip())

    await asyncio.gather(
        gui.draw(messages_queue, sending_queue, status_updates_queue),
        read_msgs(args.host, args.port, messages_queue, messages_to_file_queue),
        save_msgs(args.history, messages_to_file_queue),
        send_msgs(args.host, args.port, sending_queue),
    )


if __name__ == '__main__':
    asyncio.run(main())



