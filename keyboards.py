from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def admin_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Добавить конспект", callback_data="admin:add"))
    builder.row(InlineKeyboardButton(text="📚 Список конспектов", callback_data="admin:list"))
    builder.row(
        InlineKeyboardButton(text="✏️ Изменить конспект", callback_data="admin:edit"),
        InlineKeyboardButton(text="🗑 Удалить конспект", callback_data="admin:delete"),
    )
    builder.row(InlineKeyboardButton(text="👮 Админы", callback_data="admin:admins"))
    builder.row(
        InlineKeyboardButton(text="🚫 Заблокировать", callback_data="admin:block"),
        InlineKeyboardButton(text="✅ Разблокировать", callback_data="admin:unblock"),
    )
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats"),
        InlineKeyboardButton(text="📄 Экспорт PDF", callback_data="admin:export"),
    )
    return builder.as_markup()


def admins_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin:add_admin"))
    builder.row(InlineKeyboardButton(text="➖ Удалить админа", callback_data="admin:remove_admin"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin:back"))
    return builder.as_markup()


def edit_conspect_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ Изменить тему", callback_data="edit:topic"))
    builder.row(InlineKeyboardButton(text="📎 Изменить PDF", callback_data="edit:file"))
    builder.row(InlineKeyboardButton(text="🔢 Изменить номер", callback_data="edit:number"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin:back"))
    return builder.as_markup()


def export_filter_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📅 Сегодня", callback_data="export:today"),
        InlineKeyboardButton(text="📅 Неделя", callback_data="export:week"),
    )
    builder.row(
        InlineKeyboardButton(text="📅 Месяц", callback_data="export:month"),
        InlineKeyboardButton(text="📅 Всё время", callback_data="export:all"),
    )
    builder.row(InlineKeyboardButton(text="📖 По конспекту", callback_data="export:by_conspect"))
    builder.row(InlineKeyboardButton(text="👤 По пользователю", callback_data="export:by_user"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin:back"))
    return builder.as_markup()


def stats_filter_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📅 Сегодня", callback_data="stats:today"),
        InlineKeyboardButton(text="📅 Неделя", callback_data="stats:week"),
    )
    builder.row(
        InlineKeyboardButton(text="📅 Месяц", callback_data="stats:month"),
        InlineKeyboardButton(text="📅 Всё время", callback_data="stats:all"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin:back"))
    return builder.as_markup()


def back_kb(callback: str = "admin:back") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data=callback))
    return builder.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()
