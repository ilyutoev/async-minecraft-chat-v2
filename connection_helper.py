import asyncio
from contextlib import asynccontextmanager


@asynccontextmanager
async def open_connection(host, port):
    """Контекстный менеджер для корректно закрытия подключения."""
    reader, writer = await asyncio.open_connection(host, port)
    try:
        yield reader, writer
    finally:
        writer.close()
        await writer.wait_closed()
