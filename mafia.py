from .. import loader, utils
from telethon.tl.types import Message
from aiogram.types import CallbackQuery
import random
import asyncio
from typing import Dict, List, Optional

@loader.tds
class MafiaGameMod(loader.Module):
    """Интерактивная игра в Мафию с автоматическим управлением"""
    strings = {
        "name": "MafiaGame",
        "join": "🎮 Присоединиться к игре",
        "start": "🚀 Начать игру (мин. 5 игроков)",
        "players": "👥 Игроки:",
        "role_mafia": "🔫 Вы мафия! Узнай своих: {}",
        "role_civilian": "👨🌾 Вы мирный житель",
        "role_sheriff": "⭐ Вы шериф",
        "role_doctor": "💊 Вы доктор",
        "night_start": "🌙 Ночь наступила! Мафия просыпается...",
        "day_start": "☀️ День наступил! Обсуждение начинается...",
        "vote": "🗳 Проголосовать за",
        "no_game": "❌ Активная игра не найдена",
        "alive": "Живые игроки:",
        "win_mafia": "🎉 Мафия победила!",
        "win_civilians": "🎉 Мирные жители победили!",
    }

    def __init__(self):
        self.games: Dict[int, dict] = {}
        self.config = loader.ModuleConfig(
            "night_duration",
            60,
            "Длительность ночной фазы (сек)",
            "day_duration",
            120,
            "Длительность дневной фазы (сек)",
        )

    async def client_ready(self, client, db):
        self._client = client

    @loader.command()
    async def mafia(self, message: Message):
        """Запустить меню игры в Мафию"""
        chat_id = utils.get_chat_id(message)
        if chat_id not in self.games:
            self.games[chat_id] = {
                "players": {},
                "phase": "lobby",
                "votes": {},
                "actions": {}
            }

        await self._show_lobby(message)

    async def _show_lobby(self, message: Message):
        chat_id = utils.get_chat_id(message)
        game = self.games[chat_id]
        
        buttons = [
            [{"text": self.strings("join"), "callback": self._join_game}],
            [{"text": self.strings("start"), "callback": self._start_game}]
        ] if len(game["players"]) >=5 else []

        text = f"{self.strings('players')}\n" + "\n".join([
            f"{i+1}. {name}" 
            for i, (_, name) in enumerate(game["players"].items())
        ])

        await utils.answer(
            message,
            text,
            reply_markup=self._client.build_reply_markup(buttons)
        )

    async def _join_game(self, call: CallbackQuery):
        user_id = call.from_user.id
        chat_id = utils.get_chat_id(call)
        
        if user_id not in self.games[chat_id]["players"]:
            self.games[chat_id]["players"][user_id] = (
                call.from_user.first_name
            )
        
        await self._show_lobby(call.message)

    async def _start_game(self, call: CallbackQuery):
        chat_id = utils.get_chat_id(call)
        game = self.games[chat_id]
        
        if len(game["players"]) < 5:
            await call.answer("❌ Недостаточно игроков!")
            return

        await self._assign_roles(chat_id)
        await self._start_night_phase(call.message)

    async def _assign_roles(self, chat_id: int):
        players = list(self.games[chat_id]["players"].items())
        random.shuffle(players)
        
        # Распределение ролей
        mafia_count = max(1, len(players) // 5)
        roles = ["mafia"]*mafia_count + ["sheriff", "doctor"]
        roles += ["civilian"]*(len(players)-len(roles))
        
        for (uid, name), role in zip(players, roles):
            self.games[chat_id]["players"][uid] = {
                "name": name,
                "role": role,
                "alive": True
            }
            
            # Отправка роли в ЛС
            if role == "mafia":
                mafia_names = [
                    p["name"] for p in self.games[chat_id]["players"].values() 
                    if p["role"] == "mafia"
                ]
                msg = self.strings("role_mafia").format(", ".join(mafia_names))
            else:
                msg = self.strings(f"role_{role}")
            
            await self._client.send_message(uid, msg)

    async def _start_night_phase(self, message: Message):
        chat_id = utils.get_chat_id(message)
        self.games[chat_id]["phase"] = "night"
        self.games[chat_id]["actions"] = {}
        
        await utils.answer(message, self.strings("night_start"))
        await self._send_night_actions(message)
        await asyncio.sleep(self.config["night_duration"])
        await self._process_night_actions(message)

    async def _send_night_actions(self, message: Message):
        chat_id = utils.get_chat_id(message)
        game = self.games[chat_id]
        
        for uid, player in game["players"].items():
            if not player["alive"]:
                continue
                
            if player["role"] == "mafia":
                buttons = self._build_player_buttons(uid, "kill")
                await self._client.send_message(
                    uid,
                    "🔪 Выберите жертву:",
                    buttons=buttons
                )
            elif player["role"] == "doctor":
                buttons = self._build_player_buttons(uid, "heal")
                await self._client.send_message(
                    uid,
                    "💊 Выберите кого лечить:",
                    buttons=buttons
                )
            elif player["role"] == "sheriff":
                buttons = self._build_player_buttons(uid, "check")
                await self._client.send_message(
                    uid,
                    "🕵️ Выберите кого проверить:",
                    buttons=buttons
                )

    def _build_player_buttons(self, uid: int, action: str):
        chat_id = next(k for k,v in self.games.items() if uid in v["players"])
        return [
            [{
                "text": player["name"],
                "callback": self._night_action,
                "args": (action, target_id)
            }]
            for target_id, player in self.games[chat_id]["players"].items()
            if player["alive"] and target_id != uid
        ]

    async def _night_action(self, call: CallbackQuery, action: str, target: int):
        chat_id = utils.get_chat_id(call)
        self.games[chat_id]["actions"][call.from_user.id] = (action, target)
        await call.answer("✅ Выбор сохранен!")

    async def _process_night_actions(self, message: Message):
        chat_id = utils.get_chat_id(message)
        game = self.games[chat_id]
        
        # Обработка действий
        kills = set()
        heals = set()
        
        for uid, (action, target) in game["actions"].items():
            if action == "kill":
                kills.add(target)
            elif action == "heal":
                heals.add(target)
        
        # Применение результатов
        killed = []
        for target in kills:
            if target not in heals:
                game["players"][target]["alive"] = False
                killed.append(game["players"][target]["name"])
        
        # Отправка результатов
        result = "Ночью ничего не произошло" if not killed else (
            "☠️ Убиты: " + ", ".join(killed)
        )
        await utils.answer(message, result)
        await self._check_win_condition(message)
        await self._start_day_phase(message)

    async def _start_day_phase(self, message: Message):
        chat_id = utils.get_chat_id(message)
        self.games[chat_id]["phase"] = "day"
        self.games[chat_id]["votes"] = {}
        
        await utils.answer(message, self.strings("day_start"))
        await self._send_voting_buttons(message)
        await asyncio.sleep(self.config["day_duration"])
        await self._process_votes(message)

    async def _send_voting_buttons(self, message: Message):
        chat_id = utils.get_chat_id(message)
        alive_players = [
            (uid, p["name"]) 
            for uid, p in self.games[chat_id]["players"].items() 
            if p["alive"]
        ]
        
        buttons = [
            [{
                "text": f"{self.strings('vote')} {name}",
                "callback": self._vote_player,
                "args": (uid,)
            }] 
            for uid, name in alive_players
        ]
        
        await utils.answer(
            message,
            f"{self.strings('alive')}\n" + "\n".join(
                [f"{i+1}. {name}" for i, (_, name) in enumerate(alive_players)]
            ),
            buttons=buttons
        )

    async def _vote_player(self, call: CallbackQuery, target: int):
        chat_id = utils.get_chat_id(call)
        self.games[chat_id]["votes"][call.from_user.id] = target
        await call.answer("✅ Голос учтен!")

    async def _process_votes(self, message: Message):
        chat_id = utils.get_chat_id(message)
        game = self.games[chat_id]
        
        # Подсчет голосов
        vote_count = {}
        for _, target in game["votes"].items():
            vote_count[target] = vote_count.get(target, 0) + 1
        
        if not vote_count:
            await utils.answer(message, "🗳️ Никто не проголосовал!")
            return
        
        max_votes = max(vote_count.values())
        candidates = [k for k,v in vote_count.items() if v == max_votes]
        
        if len(candidates) > 1:
            await utils.answer(message, "🤝 Ничья! Никто не исключен")
            return
        
        # Исключение игрока
        target = candidates[0]
        game["players"][target]["alive"] = False
        await utils.answer(
            message, 
            f"☠️ Исключен {game['players'][target]['name']}"
        )
        
        await self._check_win_condition(message)
        await self._start_night_phase(message)

    async def _check_win_condition(self, message: Message):
        chat_id = utils.get_chat_id(message)
        game = self.games[chat_id]
        
        alive = [p for p in game["players"].values() if p["alive"]]
        mafia = [p for p in alive if p["role"] == "mafia"]
        civilians = [p for p in alive if p["role"] != "mafia"]
        
        if len(mafia) >= len(civilians):
            await utils.answer(message, self.strings("win_mafia"))
            await self._end_game(message)
        elif not mafia:
            await utils.answer(message, self.strings("win_civilians"))
            await self._end_game(message)

    async def _end_game(self, message: Message):
        chat_id = utils.get_chat_id(message)
        del self.games[chat_id]
        await utils.answer(message, "🎮 Игра завершена!")

    @loader.watcher()
    async def watcher(self, message: Message):
        if "!debug_mafiastate" in message.raw_text:
            await self._debug_state(message)

    async def _debug_state(self, message: Message):
        chat_id = utils.get_chat_id(message)
        if chat_id not in self.games:
            await utils.answer(message, self.strings("no_game"))
            return
        
        game = self.games[chat_id]
        state = (
            f"Phase: {game['phase']}\n"
            "Players:\n" + 
            "\n".join([
                f"{p['name']} ({p['role']}) {'✅' if p['alive'] else '❌'}"
                for p in game["players"].values()
            ])
        )
        await utils.answer(message, f"<code>{state}</code>")