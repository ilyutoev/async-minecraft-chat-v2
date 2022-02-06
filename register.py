import json
import os
import socket
from tkinter import *
from tkinter import messagebox as mb


DEFAULT_SERVER_HOST = os.getenv('MINECHAT_SERVER_HOST', 'minechat.dvmn.org')
DEFAULT_WRITE_SERVER_PORT = os.getenv('MINECHAT_SERVER_PORT', 5050)


def register(root_frame, input_field):
    """Регистрация пользователя"""
    nickname = input_field.get()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((DEFAULT_SERVER_HOST, DEFAULT_WRITE_SERVER_PORT))
            # Получаем первое пустое сообщение
            s.recv(1024)
            s.sendall('\n'.encode())
            # Вычитываем пустое сообщение
            s.recv(1024)
            s.sendall(f'{nickname}\n'.encode())
            data = s.recv(1024)

            # Получаем токен
            token = json.loads(data.decode().split('\n')[0])['account_hash']
            with open('token.txt', 'w') as f:
                f.write(token)
            message = f"Ваш токен сохранен в файл token.txt"
    except Exception as e:
        message = f'Ошибка при регистрации, повторите позже.\n Текст ошибки: {e}'

    mb.showinfo(
        title="Токен",
        message=message
    )
    root_frame.quit()


if __name__ == '__main__':
    root = Tk()
    root.title('Регистрация нового пользователя в Чате Майнкрафтера')

    Label(text="Для регистрации в Чате Майнкрафтера введите имя пользователя").pack()
    entry = Entry(width=50)
    entry.pack()
    Button(text="Зарегистрировать", command=lambda: register(root, entry)).pack()
    root.mainloop()
