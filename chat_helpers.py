import json
import logging

logger = logging.getLogger(__name__)


async def authorise(writer, reader, token):
    """Функция для авторизации пользователя по токену."""

    await _submit_message(writer, token)

    # Получаем сообщение и проверяем верно ли авторизовались
    nickname = None
    received_message = await _read_json_message_and_deserialize(reader)
    if received_message:
        nickname = received_message.get('nickname')
    return bool(received_message), nickname


async def _register(writer, reader, username):
    """Регистрируем нового пользователя и возвращем токен."""
    # Получаем строку о вводе логина нового пользователя
    await read_message_str(reader)

    # Регистрируем нового пользователя
    await _submit_message(writer, username)

    # Получаем сообщение и сохранем хеш
    received_message = await _read_json_message_and_deserialize(reader)

    token = received_message.get('account_hash')
    logger.info(f'Ваш новый токен: {token}')
    nickname = received_message.get('nickname')
    return nickname, token


async def _submit_message(writer, message):
    """Отправялем сообщение в чат"""
    message = message.replace("\n", "\\n")
    sent_message = f'{message}\n'
    logger.debug(sent_message)
    writer.write(sent_message.encode())
    await writer.drain()


async def read_message_str(reader):
    """Читаем сообщение из чата и возвращаем строковое представление."""
    data = await reader.readline()
    received_message = data.decode()
    logger.debug(received_message)
    return data


async def _read_json_message_and_deserialize(reader):
    """Читаем сообщение в json формате и десереализуем."""
    received_message_str = await read_message_str(reader)
    return json.loads(received_message_str)


async def submit_message(writer, message):
    """Отправялем сообщение в чат"""
    message = message.replace("\n", "\\n")
    sent_message = f'{message}\n\n'
    logger.debug(sent_message)
    writer.write(sent_message.encode())
    await writer.drain()
