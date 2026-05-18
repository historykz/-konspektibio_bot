import re
import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, FSInputFile

import database as db

logger = logging.getLogger(__name__)
router = Router()

SERIAL_RE = re.compile(r"^[#№]?(\d+)$")


def parse_serial(text: str) -> int | None:
    text = text.strip()
    m = SERIAL_RE.match(text)
    if m:
        return int(m.group(1))
    return None


async def send_conspect_list(message: Message):
    conspects = await db.get_all_conspects()
    if not conspects:
        await message.answer(
            "📭 Конспекты пока не добавлены.\nОбратитесь к администратору."
        )
        return

    lines = ["📚 <b>Доступные конспекты:</b>\n"]
    for c in conspects:
        lines.append(f"  <b>#{c['serial_number']}</b> — {c['topic']}")
    lines.append("\n<i>Чтобы получить конспект, отправьте его номер.</i>")
    lines.append("<i>Например: <code>28</code>, <code>#28</code>, <code>№28</code></i>")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(CommandStart())
async def cmd_start(message: Message):
    await db.upsert_user(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.first_name or "",
        message.from_user.last_name or "",
    )

    if await db.is_blocked(message.from_user.id):
        await message.answer("🚫 Доступ к боту ограничен.")
        return

    name = message.from_user.first_name or "пользователь"
    await message.answer(
        f"👋 Привет, <b>{name}</b>!\n\n"
        "Я помогу вам получить нужный конспект в PDF.\n"
        "Отправьте серийный номер конспекта, чтобы скачать его.\n",
        parse_mode="HTML",
    )
    await send_conspect_list(message)


@router.message(Command("list"))
async def cmd_list(message: Message):
    await db.upsert_user(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.first_name or "",
        message.from_user.last_name or "",
    )
    if await db.is_blocked(message.from_user.id):
        await message.answer("🚫 Доступ к боту ограничен.")
        return
    await send_conspect_list(message)


@router.message(F.text)
async def handle_text(message: Message):
    await db.upsert_user(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.first_name or "",
        message.from_user.last_name or "",
    )

    if await db.is_blocked(message.from_user.id):
        await message.answer("🚫 Доступ к боту ограничен.")
        return

    serial = parse_serial(message.text or "")
    if serial is None:
        await message.answer(
            "❓ Не понял вас. Отправьте номер конспекта.\n"
            "Например: <code>28</code>, <code>#28</code>, <code>№28</code>\n\n"
            "Посмотреть список: /start",
            parse_mode="HTML",
        )
        return

    conspect = await db.get_conspect_by_number(serial)
    if not conspect:
        await message.answer(
            f"❌ Конспект с номером <b>#{serial}</b> не найден.\n"
            "Проверьте список доступных конспектов через /start.",
            parse_mode="HTML",
        )
        return

    # Send the PDF
    try:
        file_path = conspect["file_path"]
        caption = (
            f"📄 <b>#{conspect['serial_number']} — {conspect['topic']}</b>"
        )

        if conspect.get("file_id"):
            await message.answer_document(
                document=conspect["file_id"],
                caption=caption,
                parse_mode="HTML",
            )
        else:
            doc = FSInputFile(file_path, filename=conspect["original_filename"] or f"conspect_{serial}.pdf")
            sent = await message.answer_document(
                document=doc,
                caption=caption,
                parse_mode="HTML",
            )
            # cache the file_id for faster future sends
            new_file_id = sent.document.file_id
            async with __import__("aiosqlite").connect("database.db") as conn:
                await conn.execute(
                    "UPDATE conspects SET file_id=? WHERE serial_number=?",
                    (new_file_id, serial)
                )
                await conn.commit()

        # Log download
        users = await db.get_all_users()
        user_row = next((u for u in users if u["telegram_id"] == message.from_user.id), None)
        user_id = user_row["id"] if user_row else 0
        await db.log_download(
            user_id=user_id,
            telegram_id=message.from_user.id,
            username=message.from_user.username or "",
            serial_number=serial,
            conspect_topic=conspect["topic"],
            conspect_id=conspect["id"],
        )

        logger.info(f"User {message.from_user.id} downloaded conspect #{serial}")

    except FileNotFoundError:
        await message.answer(
            f"⚠️ Файл конспекта <b>#{serial}</b> не найден на сервере.\n"
            "Обратитесь к администратору.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Error sending conspect #{serial}: {e}")
        await message.answer("⚠️ Произошла ошибка при отправке файла. Попробуйте позже.")
