import json
import logging

from connection_helper import open_connection

logger = logging.getLogger(__name__)


async def authorise_or_register(host, port, token, username):
    """Проверка авторизации или регистрация в чате"""
    if all((username, token)):
        logger.error('Необходимо передать в скрипт токен (или имя пользователя) и сообщение.')
        return

    async with open_connection(host, port) as (reader, writer):
        # Получаем первое сообщение из чата
        await read_message_str(reader)

        # Авторизуемся
        is_authorised = False
        nickname = None

        if token:
            is_authorised, nickname = await authorise(writer, reader, token)

        # Регистрируем нового пользователя, если не удалось авторизоваться и передано имя пользователя
        if not is_authorised and username:
            if not token:
                # Отправляем пустую строку вместо токена
                await _submit_message(writer, '')
            nickname, token = await _register(writer, reader, username)

            # Вычитываем строку о вводе нового сообщения
            await read_message_str(reader)

            is_authorised = True

        if not is_authorised:
            logger.warning('Для отправки сообщения необходимо авторизоваться: '
                           'передать валидный токен или зарегистрировать нового пользователя.')

        print(f'Выполнена авторизация. Пользователь {nickname}')

        return is_authorised, token


async def authorise(writer, reader, token):
    """Функция для авторизации пользователя по токену."""

    await _submit_message(writer, token)

    # Получаем сообщение и проверяем верно ли авторизовались
    received_message = await _read_json_message_and_deserialize(reader)
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
