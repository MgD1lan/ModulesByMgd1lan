from hikkatl.types import Message
from hikkatl.utils import get_password
from .. import loader, utils
from aiogram.types import CallbackQuery
import hashlib
import os

@loader.tds
class SudoManager(loader.Module):
    """Менеджер sudo-паролей с защищенным хранилищем"""
    strings = {
        "name": "SudoManager",
        "pass_set": "🔐 <b>Sudo-пароль успешно установлен!</b>",
        "pass_required": "🛡️ <b>Требуется sudo-пароль:</b>",
        "pass_hidden": "••••••••",
        "button_show": "👁️ Показать пароль",
        "button_hide": "👁️ Скрыть пароль",
        "wrong_pass": "❌ Неверный пароль!",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            "sudo_password_hash",
            None,
            "Хеш sudo-пароля (автоматическая генерация)",
            validator=loader.validators.Hidden(),
        )
        self.salt = None

    async def client_ready(self, client, db):
        self._client = client
        if not self.salt:
            self.salt = os.urandom(32)
            self.config["sudo_password_hash"] = None

    @loader.command()
    async def setsudopass(self, message: Message):
        """Установить новый sudo-пароль"""
        password = await get_password(
            message, 
            "🔒 <b>Введите новый sudo-пароль:</b>", 
            confirm=True
        )
        self.config["sudo_password_hash"] = self._hash_password(password)
        await utils.answer(message, self.strings("pass_set"))

    @loader.watcher()
    async def terminal_watcher(self, message: Message):
        """Перехватчик запросов sudo в терминале"""
        if "sudo" in message.raw_text and "[sudo] password" in message.raw_text:
            await self._handle_sudo_request(message)

    async def _handle_sudo_request(self, message: Message):
        markup = [
            [{
                "text": self.strings("button_show"),
                "callback": self._toggle_password,
                "args": (message, False)
            }],
            [{
                "text": "✅ Ввести пароль",
                "callback": self._submit_password,
                "args": (message,)
            }]
        ]
        
        await utils.answer(
            message,
            self.strings("pass_required") + f"\n\n{self.strings('pass_hidden')}",
            reply_markup=utils.chat_id(message) if len(markup) else None,
            buttons=markup
        )

    async def _toggle_password(self, call: CallbackQuery, message: Message, show: bool):
        text = self.strings("pass_required") + "\n\n"
        text += utils.escape_html(self.config["sudo_password"]) if show else self.strings("pass_hidden")
        
        buttons = [
            [{
                "text": self.strings("button_hide" if show else "button_show"),
                "callback": self._toggle_password,
                "args": (message, not show)
            }],
            [{
                "text": "✅ Ввести пароль",
                "callback": self._submit_password,
                "args": (message,)
            }]
        ]
        
        await call.edit_message_text(
            text,
            reply_markup=self._client.build_reply_markup(buttons)
        )

    async def _submit_password(self, call: CallbackQuery, message: Message):
        if self.config["sudo_password_hash"]:
            await self._client.send_message(
                utils.get_chat_id(message),
                f"{self.config['sudo_password']}\n",
                reply_to=message.id
            )
            await call.delete()
        else:
            await call.answer(self.strings("wrong_pass"), show_alert=True)

    def _hash_password(self, password: str) -> str:
        return hashlib.pbkdf2_hmac(
            'sha256',
            password.encode(),
            self.salt,
            100000
        ).hex()

    def _verify_password(self, password: str) -> bool:
        new_hash = self._hash_password(password)
        return new_hash == self.config["sudo_password_hash"]