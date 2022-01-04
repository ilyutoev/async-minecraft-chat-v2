import argparse
import asyncio
import logging
import os
import time
from datetime import datetime
from tkinter import messagebox

import aiofiles

import gui
from chat_helpers import InvalidToken
from chat_helpers import authorise
from chat_helpers import authorise_or_register
from chat_helpers import read_message_str
from chat_helpers import submit_message
from connection_helper import open_connection


logger = logging.getLogger(__name__)

DEFAULT_SERVER_HOST = os.getenv('MINECHAT_SERVER_HOST', 'minechat.dvmn.org')
DEFAULT_SERVER_PORT = os.getenv('MINECHAT_SERVER_PORT', 5000)
DEFAULT_REGISTER_SERVER_PORT = os.getenv('MINECHAT_SERVER_PORT', 5050)
DEFAULT_FILE_PATH = os.getenv('MINECHAT_FILE_PATH', 'minechat.history')
DEFAULT_TOKEN = os.getenv('MINECHAT_TOKEN')
DEFAULT_USERNAME = os.getenv('MINECHAT_USERNAME')


def get_arguments():
    """Получаем аргументы командной строки, переданные скрипту."""
    parser = argparse.ArgumentParser(description='Script save minechat messages to file.')
    parser.add_argument('--host', type=str, default=DEFAULT_SERVER_HOST, help='Minechat server host.')
    parser.add_argument('--port', type=int, default=DEFAULT_SERVER_PORT, help='Minechat server port.')
    parser.add_argument('--register-port', type=int, default=DEFAULT_REGISTER_SERVER_PORT, help='Minechat register server port.')
    parser.add_argument('--history', type=str, default=DEFAULT_FILE_PATH, help="Path to save minechat history.")
    parser.add_argument('--token', type=str, default=DEFAULT_TOKEN, help="User token.")
    parser.add_argument('--username', type=str, default=DEFAULT_USERNAME, help="Username for registration.")
    return parser.parse_args()


async def read_msgs(host, port, messages_queue, messages_to_file_queue, status_updates_queue):
    """Получаем сообщения из чата и пишем в очередь сообщений"""

    connect_attempts = 0
    while True:
        try:
            status_updates_queue.put_nowait(gui.ReadConnectionStateChanged.INITIATED)
            async with open_connection(host, port) as (reader, writer):
                status_updates_queue.put_nowait(gui.ReadConnectionStateChanged.ESTABLISHED)
                while True:
                    data = await reader.readline()
                    if not data:
                        break
                    messages_queue.put_nowait(data.decode())
                    messages_to_file_queue.put_nowait(data.decode())

        except Exception as e:
            status_updates_queue.put_nowait(gui.ReadConnectionStateChanged.CLOSED)
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


async def send_msgs(host, port, sending_queue, status_updates_queue, token):
    """Вывод введенных сообщений в консоль"""
    connect_attempts = 0
    while True:
        try:
            status_updates_queue.put_nowait(gui.SendingConnectionStateChanged.INITIATED)
            async with open_connection(host, port) as (reader, writer):
                status_updates_queue.put_nowait(gui.SendingConnectionStateChanged.ESTABLISHED)
                # Получаем первое сообщение из чата
                await read_message_str(reader)

                # Авторизуемся
                _, nickname = await authorise(writer, reader, token)
                status_updates_queue.put_nowait(gui.NicknameReceived(nickname))

                while True:
                    msg = await sending_queue.get()
                    if msg:
                        await submit_message(writer, msg)
        except Exception as e:
            status_updates_queue.put_nowait(gui.SendingConnectionStateChanged.CLOSED)
            time.sleep(connect_attempts)
            connect_attempts += 1


async def main():
    args = get_arguments()

    messages_queue = asyncio.Queue()
    messages_to_file_queue = asyncio.Queue()
    sending_queue = asyncio.Queue()
    status_updates_queue = asyncio.Queue()

    try:
        token = await authorise_or_register(args.host, args.register_port, args.token, args.username)
    except InvalidToken:
        messagebox.showinfo(
            'Неверный токен',
            'Проверьте токен, сервер его не узнал.'
        )
        return

    async with aiofiles.open(args.history, mode='r') as f:
        async for line in f:
            messages_queue.put_nowait(line.strip())

    await asyncio.gather(
        gui.draw(messages_queue, sending_queue, status_updates_queue),
        read_msgs(
            args.host,
            args.port,
            messages_queue,
            messages_to_file_queue,
            status_updates_queue
        ),
        save_msgs(args.history, messages_to_file_queue),
        send_msgs(
            args.host,
            args.register_port,
            sending_queue,
            status_updates_queue,
            token
        ),
    )


if __name__ == '__main__':
    asyncio.run(main())



