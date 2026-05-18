import os
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from keyboards import export_filter_kb, stats_filter_kb, back_kb, cancel_kb, admin_main_kb

logger = logging.getLogger(__name__)
router = Router()

EXPORTS_DIR = "exports"
os.makedirs(EXPORTS_DIR, exist_ok=True)


class ExportByConspect(StatesGroup):
    waiting_number = State()


class ExportByUser(StatesGroup):
    waiting_id = State()


# ─── STATS ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:stats")
async def cb_stats_menu(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    summary = await db.get_stats_summary()
    text = (
        "📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: <b>{summary['total_users']}</b>\n"
        f"📚 Конспектов: <b>{summary['total_conspects']}</b>\n"
        f"📥 Скачиваний всего: <b>{summary['total_downloads']}</b>\n"
        f"📥 Сегодня: <b>{summary['today_downloads']}</b>\n\n"
        "Выберите период для детального просмотра:"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=stats_filter_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("stats:"))
async def cb_stats_period(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    period = callback.data.split(":")[1]
    period_labels = {
        "today": "сегодня",
        "week": "за неделю",
        "month": "за месяц",
        "all": "за всё время",
    }
    rows = await db.get_downloads(period=period)
    label = period_labels.get(period, period)

    if not rows:
        await callback.message.edit_text(
            f"📊 Скачиваний {label}: <b>0</b>",
            parse_mode="HTML", reply_markup=back_kb("admin:stats")
        )
        await callback.answer()
        return

    lines = [f"📊 <b>Скачивания {label} ({len(rows)}):</b>\n"]
    for r in rows[:30]:
        uname = f"@{r['username']}" if r.get("username") else f"ID:{r['telegram_id']}"
        lines.append(
            f"• {r['downloaded_at'][:16]} | {uname} | "
            f"<b>#{r['serial_number']}</b> {r['conspect_topic']}"
        )
    if len(rows) > 30:
        lines.append(f"\n<i>...и ещё {len(rows)-30}. Используйте экспорт для полного списка.</i>")

    await callback.message.edit_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=back_kb("admin:stats")
    )
    await callback.answer()


# ─── EXPORT ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:export")
async def cb_export_menu(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    await callback.message.edit_text(
        "📄 Выберите фильтр для экспорта статистики:",
        reply_markup=export_filter_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("export:") & ~F.data.in_({"export:by_conspect", "export:by_user"}))
async def cb_export_period(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    period = callback.data.split(":")[1]
    await callback.answer("⏳ Генерирую PDF...")
    rows = await db.get_downloads(period=period)
    period_labels = {
        "today": "Сегодня",
        "week": "За неделю",
        "month": "За месяц",
        "all": "За всё время",
    }
    title = f"Статистика скачиваний — {period_labels.get(period, period)}"
    path = await generate_stats_pdf(rows, title)
    doc = FSInputFile(path, filename=os.path.basename(path))
    await callback.message.answer_document(doc, caption=f"📄 {title} ({len(rows)} записей)")
    await db.log_admin_action(callback.from_user.id, "export_pdf", period)


@router.callback_query(F.data == "export:by_conspect")
async def cb_export_by_conspect(callback: CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    await state.set_state(ExportByConspect.waiting_number)
    await callback.message.edit_text(
        "📖 Введите серийный номер конспекта для экспорта:",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "export:by_user")
async def cb_export_by_user(callback: CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.", show_alert=True)
        return
    await state.set_state(ExportByUser.waiting_id)
    await callback.message.edit_text(
        "👤 Введите Telegram ID пользователя для экспорта:",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


from aiogram.types import Message


@router.message(ExportByConspect.waiting_number)
async def export_by_conspect_got(message: Message, state: FSMContext):
    import re
    m = re.match(r"^[#№]?(\d+)$", (message.text or "").strip())
    if not m:
        await message.answer("❌ Неверный формат.", reply_markup=cancel_kb())
        return
    serial = int(m.group(1))
    await state.clear()
    rows = await db.get_downloads(serial_number=serial)
    conspect = await db.get_conspect_by_number(serial)
    topic = conspect["topic"] if conspect else str(serial)
    title = f"Скачивания конспекта #{serial} — {topic}"
    path = await generate_stats_pdf(rows, title)
    doc = FSInputFile(path, filename=os.path.basename(path))
    await message.answer_document(doc, caption=f"📄 {title} ({len(rows)} записей)")
    await db.log_admin_action(message.from_user.id, "export_pdf", f"conspect #{serial}")


@router.message(ExportByUser.waiting_id)
async def export_by_user_got(message: Message, state: FSMContext):
    try:
        tid = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Неверный ID.", reply_markup=cancel_kb())
        return
    await state.clear()
    rows = await db.get_downloads(telegram_id=tid)
    title = f"Скачивания пользователя {tid}"
    path = await generate_stats_pdf(rows, title)
    doc = FSInputFile(path, filename=os.path.basename(path))
    await message.answer_document(doc, caption=f"📄 {title} ({len(rows)} записей)")
    await db.log_admin_action(message.from_user.id, "export_pdf", f"user {tid}")


# ─── PDF GENERATION ────────────────────────────────────────────────────────────

async def generate_stats_pdf(rows: list, title: str) -> str:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import io

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(EXPORTS_DIR, f"stats_{ts}.pdf")

    doc = SimpleDocTemplate(
        path,
        pagesize=landscape(A4),
        leftMargin=1*cm, rightMargin=1*cm,
        topMargin=1.5*cm, bottomMargin=1*cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title", parent=styles["Heading1"],
        fontSize=14, spaceAfter=12,
    )
    normal = styles["Normal"]
    normal.fontSize = 8

    elements = []
    elements.append(Paragraph(title, title_style))
    elements.append(Paragraph(
        f"Дата создания: {datetime.now().strftime('%d.%m.%Y %H:%M')} | Записей: {len(rows)}",
        styles["Normal"]
    ))
    elements.append(Spacer(1, 0.5*cm))

    headers = ["Дата и время", "Имя", "Username", "Telegram ID", "№", "Тема"]
    table_data = [headers]

    for r in rows:
        dt_raw = r.get("downloaded_at", "")
        try:
            dt = datetime.fromisoformat(dt_raw).strftime("%d.%m.%Y %H:%M")
        except Exception:
            dt = dt_raw[:16]

        table_data.append([
            dt,
            r.get("username") or "—",
            f"@{r['username']}" if r.get("username") else "—",
            str(r.get("telegram_id", "")),
            f"#{r.get('serial_number', '')}",
            r.get("conspect_topic") or "—",
        ])

    col_widths = [3.5*cm, 3*cm, 3*cm, 3.5*cm, 1.5*cm, 8*cm]
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(table)

    doc.build(elements)
    logger.info(f"PDF exported: {path}")
    return path
