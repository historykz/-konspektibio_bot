import os
import logging
import shutil
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from keyboards import (
    admin_main_kb, admins_kb, edit_conspect_kb, back_kb, cancel_kb
)

logger = logging.getLogger(__name__)
router = Router()

FILES_DIR = "files"
os.makedirs(FILES_DIR, exist_ok=True)


# ─── FSM States ────────────────────────────────────────────────────────────────

class AddConspect(StatesGroup):
    waiting_pdf = State()
    waiting_topic = State()
    waiting_number = State()


class EditConspect(StatesGroup):
    waiting_number = State()          # which conspect to edit
    waiting_what = State()            # sub-action chosen via callback
    waiting_new_topic = State()
    waiting_new_pdf = State()
    waiting_new_number = State()


class DeleteConspect(StatesGroup):
    waiting_number = State()


class AddAdmin(StatesGroup):
    waiting_id = State()


class RemoveAdmin(StatesGroup):
    waiting_id = State()


class BlockUser(StatesGroup):
    waiting_id = State()
    waiting_reason = State()


class UnblockUser(StatesGroup):
    waiting_id = State()


# ─── Helpers ───────────────────────────────────────────────────────────────────

async def check_admin(message_or_query) -> bool:
    uid = (
        message_or_query.from_user.id
        if hasattr(message_or_query, "from_user")
        else message_or_query.from_user.id
    )
    return await db.is_admin(uid)


async def admin_only(message: Message) -> bool:
    if not await db.is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return False
    return True


def parse_serial_strict(text: str):
    import re
    m = re.match(r"^[#№]?(\d+)$", text.strip())
    return int(m.group(1)) if m else None


# ─── /admin ────────────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    if not await admin_only(message):
        return
    await state.clear()
    await message.answer(
        "👮 <b>Панель администратора</b>",
        reply_markup=admin_main_kb(),
        parse_mode="HTML",
    )


# ─── /backup ───────────────────────────────────────────────────────────────────

@router.message(Command("backup"))
async def cmd_backup(message: Message):
    if not await admin_only(message):
        return
    try:
        backup_path = await db.create_backup()
        doc = FSInputFile(backup_path, filename=os.path.basename(backup_path))
        await message.answer_document(doc, caption="✅ Резервная копия базы данных")
        await db.log_admin_action(message.from_user.id, "backup", backup_path)
    except Exception as e:
        logger.error(f"Backup error: {e}")
        await message.answer(f"❌ Ошибка при создании бэкапа: {e}")


# ─── CANCEL ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "❌ Операция отменена.",
        reply_markup=None,
    )
    await callback.answer()


@router.callback_query(F.data == "admin:back")
async def cb_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "👮 <b>Панель администратора</b>",
        reply_markup=admin_main_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


# ─── ADD CONSPECT ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:add")
async def cb_add_start(callback: CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    await state.set_state(AddConspect.waiting_pdf)
    await callback.message.edit_text(
        "📎 Отправьте PDF-файл конспекта:",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(AddConspect.waiting_pdf, F.document)
async def add_got_pdf(message: Message, state: FSMContext):
    doc = message.document
    if not doc.file_name.lower().endswith(".pdf"):
        await message.answer("❌ Пожалуйста, отправьте файл в формате PDF.", reply_markup=cancel_kb())
        return

    await state.update_data(
        file_id=doc.file_id,
        original_filename=doc.file_name,
        tmp_file_id=doc.file_id,
    )
    await state.set_state(AddConspect.waiting_topic)
    await message.answer("✏️ Введите тему конспекта:", reply_markup=cancel_kb())


@router.message(AddConspect.waiting_pdf)
async def add_pdf_wrong(message: Message):
    await message.answer("❌ Нужен PDF-файл. Прикрепите документ.", reply_markup=cancel_kb())


@router.message(AddConspect.waiting_topic)
async def add_got_topic(message: Message, state: FSMContext):
    topic = message.text.strip()
    if not topic:
        await message.answer("❌ Тема не может быть пустой.", reply_markup=cancel_kb())
        return
    await state.update_data(topic=topic)
    await state.set_state(AddConspect.waiting_number)
    await message.answer(
        "🔢 Введите серийный номер конспекта:\n"
        "<i>Например: <code>28</code> или <code>#28</code></i>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


@router.message(AddConspect.waiting_number)
async def add_got_number(message: Message, state: FSMContext):
    serial = parse_serial_strict(message.text or "")
    if serial is None:
        await message.answer(
            "❌ Неверный формат. Введите число, например <code>28</code> или <code>#28</code>",
            parse_mode="HTML",
            reply_markup=cancel_kb(),
        )
        return

    if await db.conspect_number_exists(serial):
        await message.answer(
            f"❌ Конспект с номером <b>#{serial}</b> уже существует.\n"
            "Выберите другой номер или измените существующий конспект.",
            parse_mode="HTML",
            reply_markup=cancel_kb(),
        )
        return

    data = await state.get_data()
    file_id = data["file_id"]
    topic = data["topic"]
    original_filename = data.get("original_filename", f"conspect_{serial}.pdf")

    # Download and save file
    from aiogram import Bot
    _bot = Bot.get_current()
    file_info = await _bot.get_file(file_id)
    dest_path = os.path.join(FILES_DIR, f"{serial}_{original_filename}")
    await _bot.download_file(file_info.file_path, dest_path)

    success = await db.add_conspect(
        serial_number=serial,
        topic=topic,
        file_id=file_id,
        file_path=dest_path,
        original_filename=original_filename,
        uploaded_by=message.from_user.id,
    )

    await state.clear()

    if success:
        await db.log_admin_action(
            message.from_user.id, "add_conspect",
            f"#{serial} — {topic}"
        )
        await message.answer(
            f"✅ <b>Сохранено!</b>\n\n"
            f"📖 Тема: <b>{topic}</b>\n"
            f"🔢 Номер: <b>#{serial}</b>",
            parse_mode="HTML",
            reply_markup=admin_main_kb(),
        )
    else:
        await message.answer("❌ Ошибка при сохранении. Возможно, номер уже занят.")


# ─── LIST CONSPECTS ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:list")
async def cb_list(callback: CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    conspects = await db.get_all_conspects()
    if not conspects:
        text = "📭 Конспекты отсутствуют."
    else:
        lines = ["📚 <b>Все конспекты:</b>\n"]
        for c in conspects:
            lines.append(
                f"  <b>#{c['serial_number']}</b> — {c['topic']}\n"
                f"    📁 <code>{c['original_filename']}</code>"
            )
        text = "\n".join(lines)

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_kb())
    await callback.answer()


# ─── EDIT CONSPECT ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:edit")
async def cb_edit_start(callback: CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    await state.set_state(EditConspect.waiting_number)
    await callback.message.edit_text(
        "✏️ Введите серийный номер конспекта, который хотите изменить:",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(EditConspect.waiting_number)
async def edit_got_number(message: Message, state: FSMContext):
    serial = parse_serial_strict(message.text or "")
    if serial is None:
        await message.answer("❌ Неверный формат номера.", reply_markup=cancel_kb())
        return
    conspect = await db.get_conspect_by_number(serial)
    if not conspect:
        await message.answer(
            f"❌ Конспект <b>#{serial}</b> не найден.", parse_mode="HTML",
            reply_markup=cancel_kb()
        )
        return
    await state.update_data(edit_serial=serial)
    await state.set_state(EditConspect.waiting_what)
    await message.answer(
        f"✏️ Конспект <b>#{serial} — {conspect['topic']}</b>\n\nЧто изменить?",
        parse_mode="HTML",
        reply_markup=edit_conspect_kb(),
    )


@router.callback_query(EditConspect.waiting_what, F.data == "edit:topic")
async def edit_choose_topic(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EditConspect.waiting_new_topic)
    await callback.message.edit_text("✏️ Введите новую тему:", reply_markup=cancel_kb())
    await callback.answer()


@router.message(EditConspect.waiting_new_topic)
async def edit_save_topic(message: Message, state: FSMContext):
    new_topic = message.text.strip()
    data = await state.get_data()
    serial = data["edit_serial"]
    ok = await db.update_conspect_topic(serial, new_topic)
    await state.clear()
    if ok:
        await db.log_admin_action(message.from_user.id, "edit_topic", f"#{serial} → {new_topic}")
        await message.answer(
            f"✅ Тема конспекта <b>#{serial}</b> обновлена: <b>{new_topic}</b>",
            parse_mode="HTML", reply_markup=admin_main_kb()
        )
    else:
        await message.answer("❌ Не удалось обновить.", reply_markup=admin_main_kb())


@router.callback_query(EditConspect.waiting_what, F.data == "edit:file")
async def edit_choose_file(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EditConspect.waiting_new_pdf)
    await callback.message.edit_text("📎 Отправьте новый PDF-файл:", reply_markup=cancel_kb())
    await callback.answer()


@router.message(EditConspect.waiting_new_pdf, F.document)
async def edit_save_file(message: Message, state: FSMContext):
    doc = message.document
    if not doc.file_name.lower().endswith(".pdf"):
        await message.answer("❌ Нужен PDF-файл.", reply_markup=cancel_kb())
        return
    data = await state.get_data()
    serial = data["edit_serial"]

    from aiogram import Bot
    _bot = Bot.get_current()
    file_info = await _bot.get_file(doc.file_id)
    dest_path = os.path.join(FILES_DIR, f"{serial}_{doc.file_name}")
    await _bot.download_file(file_info.file_path, dest_path)

    old_path = await db.update_conspect_file(serial, doc.file_id, dest_path, doc.file_name)
    await state.clear()

    if old_path is not None:
        if old_path != dest_path and os.path.exists(old_path):
            try:
                os.remove(old_path)
            except Exception:
                pass
        await db.log_admin_action(message.from_user.id, "edit_file", f"#{serial}")
        await message.answer(
            f"✅ PDF конспекта <b>#{serial}</b> обновлён.",
            parse_mode="HTML", reply_markup=admin_main_kb()
        )
    else:
        await message.answer("❌ Конспект не найден.", reply_markup=admin_main_kb())


@router.callback_query(EditConspect.waiting_what, F.data == "edit:number")
async def edit_choose_number(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EditConspect.waiting_new_number)
    await callback.message.edit_text("🔢 Введите новый серийный номер:", reply_markup=cancel_kb())
    await callback.answer()


@router.message(EditConspect.waiting_new_number)
async def edit_save_number(message: Message, state: FSMContext):
    new_serial = parse_serial_strict(message.text or "")
    if new_serial is None:
        await message.answer("❌ Неверный формат.", reply_markup=cancel_kb())
        return
    data = await state.get_data()
    old_serial = data["edit_serial"]
    result = await db.update_conspect_number(old_serial, new_serial)
    await state.clear()
    if result == "ok":
        await db.log_admin_action(message.from_user.id, "edit_number", f"#{old_serial}→#{new_serial}")
        await message.answer(
            f"✅ Номер изменён: <b>#{old_serial}</b> → <b>#{new_serial}</b>",
            parse_mode="HTML", reply_markup=admin_main_kb()
        )
    elif result == "duplicate":
        await message.answer(
            f"❌ Конспект с номером <b>#{new_serial}</b> уже существует.",
            parse_mode="HTML", reply_markup=admin_main_kb()
        )
    else:
        await message.answer("❌ Конспект не найден.", reply_markup=admin_main_kb())


# ─── DELETE CONSPECT ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:delete")
async def cb_delete_start(callback: CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    await state.set_state(DeleteConspect.waiting_number)
    await callback.message.edit_text(
        "🗑 Введите серийный номер конспекта для удаления:",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(DeleteConspect.waiting_number)
async def delete_got_number(message: Message, state: FSMContext):
    serial = parse_serial_strict(message.text or "")
    if serial is None:
        await message.answer("❌ Неверный формат.", reply_markup=cancel_kb())
        return
    file_path = await db.delete_conspect(serial)
    await state.clear()
    if file_path is None:
        await message.answer(
            f"❌ Конспект <b>#{serial}</b> не найден.", parse_mode="HTML",
            reply_markup=admin_main_kb()
        )
        return
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass
    await db.log_admin_action(message.from_user.id, "delete_conspect", f"#{serial}")
    await message.answer(
        f"🗑 Конспект <b>#{serial}</b> удалён.", parse_mode="HTML",
        reply_markup=admin_main_kb()
    )


# ─── ADMINS ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:admins")
async def cb_admins(callback: CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    admins = await db.get_all_admins()
    lines = ["👮 <b>Администраторы:</b>\n"]
    for a in admins:
        uname = f"@{a['username']}" if a.get("username") else "—"
        lines.append(f"  • <code>{a['telegram_id']}</code> {uname}")
    await callback.message.edit_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=admins_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "admin:add_admin")
async def cb_add_admin_start(callback: CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    await state.set_state(AddAdmin.waiting_id)
    await callback.message.edit_text(
        "➕ Введите Telegram ID нового администратора:",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(AddAdmin.waiting_id)
async def add_admin_got_id(message: Message, state: FSMContext):
    try:
        tid = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Неверный ID. Введите число.", reply_markup=cancel_kb())
        return
    ok = await db.add_admin(tid, "", message.from_user.id)
    await state.clear()
    if ok:
        await db.log_admin_action(message.from_user.id, "add_admin", str(tid))
        await message.answer(
            f"✅ Администратор <code>{tid}</code> добавлен.",
            parse_mode="HTML", reply_markup=admin_main_kb()
        )
    else:
        await message.answer("❌ Не удалось добавить.", reply_markup=admin_main_kb())


@router.callback_query(F.data == "admin:remove_admin")
async def cb_remove_admin_start(callback: CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    await state.set_state(RemoveAdmin.waiting_id)
    await callback.message.edit_text(
        "➖ Введите Telegram ID администратора для удаления:",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(RemoveAdmin.waiting_id)
async def remove_admin_got_id(message: Message, state: FSMContext):
    try:
        tid = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Неверный ID.", reply_markup=cancel_kb())
        return
    ok = await db.remove_admin(tid)
    await state.clear()
    if ok:
        await db.log_admin_action(message.from_user.id, "remove_admin", str(tid))
        await message.answer(
            f"✅ Администратор <code>{tid}</code> удалён.",
            parse_mode="HTML", reply_markup=admin_main_kb()
        )
    else:
        await message.answer(
            "❌ Невозможно удалить: это последний администратор или ID не найден.",
            reply_markup=admin_main_kb()
        )


# ─── BLOCK / UNBLOCK ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:block")
async def cb_block_start(callback: CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    await state.set_state(BlockUser.waiting_id)
    await callback.message.edit_text(
        "🚫 Введите Telegram ID пользователя для блокировки:",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(BlockUser.waiting_id)
async def block_got_id(message: Message, state: FSMContext):
    try:
        tid = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Неверный ID.", reply_markup=cancel_kb())
        return
    await state.update_data(block_tid=tid)
    await state.set_state(BlockUser.waiting_reason)
    await message.answer("📝 Введите причину блокировки (или /skip):", reply_markup=cancel_kb())


@router.message(BlockUser.waiting_reason)
async def block_got_reason(message: Message, state: FSMContext):
    reason = "" if message.text == "/skip" else (message.text or "").strip()
    data = await state.get_data()
    tid = data["block_tid"]
    await db.block_user(tid, "", reason, message.from_user.id)
    await state.clear()
    await db.log_admin_action(message.from_user.id, "block_user", f"{tid}: {reason}")
    await message.answer(
        f"🚫 Пользователь <code>{tid}</code> заблокирован.",
        parse_mode="HTML", reply_markup=admin_main_kb()
    )


@router.callback_query(F.data == "admin:unblock")
async def cb_unblock_start(callback: CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    await state.set_state(UnblockUser.waiting_id)
    await callback.message.edit_text(
        "✅ Введите Telegram ID пользователя для разблокировки:",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(UnblockUser.waiting_id)
async def unblock_got_id(message: Message, state: FSMContext):
    try:
        tid = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Неверный ID.", reply_markup=cancel_kb())
        return
    await db.unblock_user(tid)
    await state.clear()
    await db.log_admin_action(message.from_user.id, "unblock_user", str(tid))
    await message.answer(
        f"✅ Пользователь <code>{tid}</code> разблокирован.",
        parse_mode="HTML", reply_markup=admin_main_kb()
    )
