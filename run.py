import argparse
import asyncio
import logging
import os
import socket
from datetime import datetime
from tkinter import messagebox

import aiofiles
from anyio import create_task_group
from async_timeout import timeout

import gui
from chat_helpers import authorise
from chat_helpers import read_message_str
from chat_helpers import submit_message
from connection_helper import open_connection


logger = logging.getLogger(__name__)
watchdog_logger = logging.getLogger(__name__)

DEFAULT_SERVER_HOST = os.getenv('MINECHAT_SERVER_HOST', 'minechat.dvmn.org')
DEFAULT_READ_SERVER_PORT = os.getenv('DEFAULT_READ_SERVER_PORT', 5000)
DEFAULT_WRITE_SERVER_PORT = os.getenv('DEFAULT_WRITE_SERVER_PORT', 5050)
DEFAULT_FILE_PATH = os.getenv('MINECHAT_FILE_PATH', 'minechat.history')
DEFAULT_TOKEN = os.getenv('MINECHAT_TOKEN')
DEFAULT_USERNAME = os.getenv('MINECHAT_USERNAME')


PING_PONG_TIMEOUT = 5
PING_PONG_SLEEP = 10
WATCH_TIMEOUT = 5


def get_arguments():
    """Получаем аргументы командной строки, переданные скрипту."""
    parser = argparse.ArgumentParser(description='Script save minechat messages to file.')
    parser.add_argument('--host', type=str, default=DEFAULT_SERVER_HOST, help='Minechat server host.')
    parser.add_argument('--read-port', type=int, default=DEFAULT_READ_SERVER_PORT, help='Minechat server port.')
    parser.add_argument('--write-port', type=int, default=DEFAULT_WRITE_SERVER_PORT, help='Minechat register server port.')
    parser.add_argument('--history', type=str, default=DEFAULT_FILE_PATH, help="Path to save minechat history.")
    parser.add_argument('--token', type=str, default=DEFAULT_TOKEN, help="User token.")
    parser.add_argument('--username', type=str, default=DEFAULT_USERNAME, help="Username for registration.")
    return parser.parse_args()


async def get_token_from_file():
    """Получаем токен из файла token.txt"""
    file_name = 'token.txt'
    if not os.path.exists(file_name):
        return None, f'Файла {file_name} с токеном не существует. Создайте токен в программе регистрации'

    async with aiofiles.open('token.txt', mode='r') as f:
        token = await f.readline()
    return token.strip(), None


async def ping_pong(writer, watchdog_queue):
    """Отправка пустых сообщений для поддержания коннекта"""
    while True:
        try:
            async with timeout(PING_PONG_TIMEOUT):
                await submit_message(writer, '')

            await asyncio.sleep(PING_PONG_SLEEP)
            watchdog_queue.put_nowait('Ping message sent')

        except socket.gaierror:
            watchdog_logger.info(f'[{datetime.now().timestamp()}] No internet connection')
            raise ConnectionError()
        except asyncio.TimeoutError:
            watchdog_logger.info(f'[{datetime.now().timestamp()}] {PING_PONG_TIMEOUT}s timeout is elapsed')
            raise ConnectionError()


async def read_msgs(reader, messages_queue, messages_to_file_queue, watchdog_queue):
    """Получаем сообщения из чата и пишем в очередь сообщений"""

    while True:
        data = await reader.readline()
        if not data:
            break
        watchdog_queue.put_nowait('New message in chat')
        messages_queue.put_nowait(data.decode())
        messages_to_file_queue.put_nowait(data.decode())


async def save_msgs(filepath, messages_to_file_queue):
    """Сохраняем сообщения в файл"""

    async with aiofiles.open(filepath, mode='a') as f:
        while True:
            msg = await messages_to_file_queue.get()
            if not msg:
                break

            await f.write(f'[{datetime.now().strftime("%d.%m.%Y %H:%M")}] {msg}')


async def send_msgs(writer, sending_queue, watchdog_queue):
    """Вывод введенных сообщений в консоль"""
    while True:
        msg = await sending_queue.get()
        if msg:
            await submit_message(writer, msg)
            watchdog_queue.put_nowait('Message sent')


async def watch_for_connection(watchdog_queue):
    while True:
        try:
            async with timeout(WATCH_TIMEOUT) as cm:
                msg = await watchdog_queue.get()
                watchdog_logger.info(f'[{datetime.now().timestamp()}] Connection is alive. {msg}')
        except asyncio.TimeoutError:
            watchdog_logger.info(f'[{datetime.now().timestamp()}] {WATCH_TIMEOUT}s timeout is elapsed')
            raise ConnectionError()


async def handle_connection(
    host, read_port, write_port, token,
    messages_queue, messages_to_file_queue, sending_queue, status_updates_queue, watchdog_queue
):
    if not token:
        token, error = await get_token_from_file()
        if error:
            messagebox.showinfo(message=error)
            return
    if not token:
        messagebox.showinfo(
            message='Для работы необходим токен пользователя. Воспользуйтесь программой регистрации.'
        )
        return

    while True:
        try:
            status_updates_queue.put_nowait(gui.SendingConnectionStateChanged.INITIATED)
            status_updates_queue.put_nowait(gui.ReadConnectionStateChanged.INITIATED)

            async with open_connection(host, read_port) as (read_reader, read_writer), \
                       open_connection(host, write_port) as (write_reader, write_writer):

                status_updates_queue.put_nowait(gui.SendingConnectionStateChanged.ESTABLISHED)
                status_updates_queue.put_nowait(gui.ReadConnectionStateChanged.ESTABLISHED)

                # Получаем первое сообщение из чата
                await read_message_str(write_reader)

                # Авторизуемся
                watchdog_queue.put_nowait('Prompt before auth')
                is_authorize, nickname = await authorise(write_writer, write_reader, token)
                if not is_authorize:
                    messagebox.showinfo(message='Предоставленный токен неверен')
                    return

                status_updates_queue.put_nowait(gui.NicknameReceived(nickname))
                watchdog_queue.put_nowait('Authorization done')

                async with create_task_group() as tg:
                    tg.start_soon(
                        read_msgs,
                        read_reader, messages_queue, messages_to_file_queue, watchdog_queue
                    )
                    tg.start_soon(
                        send_msgs,
                        write_writer, sending_queue, watchdog_queue
                    )
                    tg.start_soon(
                        watch_for_connection,
                        watchdog_queue
                    )
                    tg.start_soon(
                        ping_pong,
                        write_writer, watchdog_queue
                    )

        except ConnectionError:
            status_updates_queue.put_nowait(gui.ReadConnectionStateChanged.CLOSED)
            status_updates_queue.put_nowait(gui.SendingConnectionStateChanged.CLOSED)
        else:
            break


async def main():
    args = get_arguments()

    messages_queue = asyncio.Queue()
    messages_to_file_queue = asyncio.Queue()
    sending_queue = asyncio.Queue()
    status_updates_queue = asyncio.Queue()
    watchdog_queue = asyncio.Queue()

    async with aiofiles.open(args.history, mode='r') as f:
        async for line in f:
            messages_queue.put_nowait(line.strip())

    async with create_task_group() as tg:
        tg.start_soon(
            gui.draw,
            messages_queue, sending_queue, status_updates_queue
        )
        tg.start_soon(
            handle_connection,
            args.host, args.read_port, args.write_port, args.token,
            messages_queue, messages_to_file_queue, sending_queue, status_updates_queue, watchdog_queue

        )
        tg.start_soon(
            save_msgs,
            args.history, messages_to_file_queue
        )


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, gui.TkAppClosed):
        pass
