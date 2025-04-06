from hikkatl.types import Message
from .. import loader
import re

@loader.tds
class BrainfuckMod(loader.Module):
    """Интерпретатор Brainfuck"""
    strings = {"name": "Brainfuck",  "desc": "🔹 Этот модуль исполняет BrainF*ck код \n не знаю зачем он вам"}

    @loader.command()
    async def bfcmd(self, message: Message):
        """Запустить Brainfuck код. Использование: .bf <код> [ввод]"""
        args = re.split(r'\s+', message.raw_text, 2)
        if len(args) < 2:
            await message.edit("<b>Нужен код Brainfuck!</b>")
            return

        code = args[1]
        input_data = args[2] if len(args) > 2 else ""
        
        result = await self.execute_bf(code, input_data)
        await message.edit(f"<b>Результат:</b>\n<code>{result}</code>")

    async def execute_bf(self, code: str, input_data: str = "") -> str:
        """Исполнитель"""
        code = re.sub(r'[^><+\-.,[\]]', '', code)
        tape = [0] * 30000
        ptr = 0
        code_ptr = 0
        output = []
        input_ptr = 0
        loop_stack = []
        loops = {}


        for i, c in enumerate(code):
            if c == '[':
                loop_stack.append(i)
            elif c == ']':
                if not loop_stack:
                    return "Ошибка: несбалансированные скобки"
                start = loop_stack.pop()
                loops[start] = i
                loops[i] = start

        while code_ptr < len(code):
            cmd = code[code_ptr]

            if cmd == '>':
                ptr = (ptr + 1) % 30000
            elif cmd == '<':
                ptr = (ptr - 1) % 30000
            elif cmd == '+':
                tape[ptr] = (tape[ptr] + 1) % 256
            elif cmd == '-':
                tape[ptr] = (tape[ptr] - 1) % 256
            elif cmd == '.':
                output.append(chr(tape[ptr]))
            elif cmd == ',':
                if input_ptr < len(input_data):
                    tape[ptr] = ord(input_data[input_ptr])
                    input_ptr += 1
                else:
                    tape[ptr] = 0
            elif cmd == '[':
                if tape[ptr] == 0:
                    code_ptr = loops[code_ptr]
            elif cmd == ']':
                if tape[ptr] != 0:
                    code_ptr = loops[code_ptr]

            code_ptr += 1


            if len(output) > 1000:
                return "Превышен лимит вывода (1000 символов)"
            
        return ''.join(output) or "Нет вывода"