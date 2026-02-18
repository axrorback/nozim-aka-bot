import os

from django.core.files.base import ContentFile
from dotenv import load_dotenv
load_dotenv()
import django
from django.utils import timezone
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from telebot import TeleBot, types
from main.models import BotUsers
from main.models import RegisterTravel, TravelParticipants
from bot.states import USER_STATE, RegState

bot = TeleBot(os.environ.get('TELEGRAM_BOT_TOKEN'), parse_mode="HTML")


def kb_passport_choice():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Pasport bor (rasm yuboraman)", callback_data="pass:yes"))
    kb.add(types.InlineKeyboardButton("❌ Pasport yo‘q", callback_data="pass:no"))
    return kb


def passport_advice_text() -> str:
    return (
        "❗️Sizda xorijga chiqish pasporti yo‘q ekan.\n\n"
        "🇺🇿 O‘zbekistonda pasport olish bo‘yicha qisqa yo‘riqnoma:\n"
        "1) <b>my.gov.uz</b> orqali “Xorijga chiqish pasportini rasmiylashtirishga ariza berish” xizmatiga ariza topshiring.\n"
        "2) Davlat boji to‘lanadi (miqdori “Davlat boji to‘g‘risida”gi qonun bo‘yicha belgilanadi).\n"
        "3) Sizni fotosurat va barmoq izlari (biometriya) uchun chaqirishadi.\n"
        "4) Odatda xizmat ko‘rsatish muddati ~ <b>10 ish kuni</b> deb ko‘rsatiladi.\n\n"
        "✅ Pasport tayyor bo‘lgach, botga qaytib pasport rasmini yuborib profilni to‘ldirishingiz mumkin.\n"
        "Agar xohlasangiz, admin siz bilan bog‘lanib bosqichlarni tushuntirib beradi."
    )


@bot.message_handler(commands=["start"])
def start(message):
    first_name = message.from_user.first_name or ""
    last_name = message.from_user.last_name or ""

    user, created = BotUsers.objects.get_or_create(
        user_id=message.from_user.id,
        defaults={"first_name": first_name, "last_name": last_name},
    )

    if not created and (user.first_name != first_name or user.last_name != last_name):
        user.first_name = first_name
        user.last_name = last_name
        user.save(update_fields=["first_name", "last_name"])

    bot.send_message(
        message.chat.id,
        "Assalomu alaykum! Bizning Umra safari botimizga xush kelibsiz.\n\n"
        "📌 Buyruqlar:\n"
        "/about — Bot haqida\n"
        "/travels — Active safarlar\n"
        "/cancel — Ro‘yxatdan o‘tishni bekor qilish"
    )


@bot.message_handler(commands=["about"])
def about(message):
    bot.send_message(
        message.chat.id,
        "Assalomu alaykum!\n\n"
        "Bu bot orqali Umra safarlariga ro‘yxatdan o‘tishingiz mumkin.\n"
        "📌 Safarlar ro‘yxati: /travels\n"
        "📝 Ro‘yxatdan o‘tish: safarni tanlab «Ro‘yxatdan o‘tish» tugmasini bosing.\n"
        "❌ Bekor qilish: /cancel"
    )


@bot.message_handler(commands=["travels"])
def travels(message):
    travels_qs = RegisterTravel.objects.filter(is_active=True).order_by("start_date")
    if not travels_qs.exists():
        bot.send_message(message.chat.id, "Hozircha active safarlar yo‘q.")
        return

    kb = types.InlineKeyboardMarkup()
    for t in travels_qs:
        kb.add(
            types.InlineKeyboardButton(
                text=f"{t.from_city} → {t.to_city} ({t.start_date} - {t.end_date})",
                callback_data=f"travel:{t.id}",
            )
        )

    bot.send_message(message.chat.id, "✅ Active safarlar ro‘yxati:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("travel:"))
def travel_detail(call):
    travel_id = call.data.split(":", 1)[1]

    try:
        t = RegisterTravel.objects.get(id=travel_id, is_active=True)
    except RegisterTravel.DoesNotExist:
        bot.answer_callback_query(call.id, "Safar topilmadi yoki active emas.")
        return

    text = (
        f"🕌 <b>Umra safari</b>\n\n"
        f"<b>Yo‘nalish:</b> {t.from_city} → {t.to_city}\n"
        f"<b>Sanalar:</b> {t.start_date} — {t.end_date}\n"
        f"<b>Rahbar:</b> {t.leader_person}\n"
        f"<b>Narx:</b> {t.price}$\n"
    )

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📝 Ro‘yxatdan o‘tish", callback_data=f"reg:{t.id}"))

    bot.send_message(call.message.chat.id, text, reply_markup=kb)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("reg:"))
def reg_start(call):
    travel_id = call.data.split(":", 1)[1]

    if TravelParticipants.objects.filter(travel_id=travel_id, user_id=call.from_user.id).exists():
        bot.answer_callback_query(call.id, "Siz allaqachon ro‘yxatdan o‘tgansiz.")
        return

    USER_STATE[call.from_user.id] = {
        "step": "first_name",
        "travel_id": travel_id,
        "first_name": "",
        "last_name": "",
        "father_name": "",
        "phone_number": "",
    }

    bot.send_message(call.message.chat.id, "Ismingizni kiriting:")
    bot.answer_callback_query(call.id)


@bot.message_handler(func=lambda m: m.from_user.id in USER_STATE and USER_STATE[m.from_user.id]["step"] in {
    "first_name", "last_name", "father_name", "phone_number"
})
def reg_text_steps(message):
    st = USER_STATE[message.from_user.id]
    text = (message.text or "").strip()

    if not text:
        bot.send_message(message.chat.id, "Iltimos, bo‘sh bo‘lmasin. Qayta kiriting:")
        return

    if st["step"] == "first_name":
        st["first_name"] = text
        st["step"] = "last_name"
        bot.send_message(message.chat.id, "Familiyangizni kiriting:")
        return

    if st["step"] == "last_name":
        st["last_name"] = text
        st["step"] = "father_name"
        bot.send_message(message.chat.id, "Otangizning ismini kiriting:")
        return

    if st["step"] == "father_name":
        st["father_name"] = text
        st["step"] = "phone_number"
        bot.send_message(message.chat.id, "Telefon raqamingizni kiriting (masalan: +998931004005):")
        return

    if st["step"] == "phone_number":
        if len(text) < 9:
            bot.send_message(message.chat.id, "Telefon raqam noto‘g‘ri ko‘rinadi. Qayta kiriting:")
            return

        st["phone_number"] = text
        st["step"] = "passport_choice"
        bot.send_message(message.chat.id, "Pasport holatini tanlang:", reply_markup=kb_passport_choice())
        return


@bot.callback_query_handler(func=lambda c: c.data in {"pass:yes", "pass:no"})
def passport_choice(call):
    uid = call.from_user.id
    if uid not in USER_STATE:
        bot.answer_callback_query(call.id, "Session topilmadi. /travels dan qayta boshlang.")
        return

    st = USER_STATE[uid]

    if st.get("step") != "passport_choice":
        bot.answer_callback_query(call.id)
        return

    if call.data == "pass:yes":
        st["step"] = "passport_upload"
        bot.send_message(call.message.chat.id, "Endi pasport rasmini yuboring (foto yoki fayl):")
        bot.answer_callback_query(call.id)
        return

    TravelParticipants.objects.create(
        travel_id=st["travel_id"],
        user_id=uid,
        first_name=st["first_name"],
        last_name=st["last_name"],
        father_name=st["father_name"],
        phone_number=st["phone_number"],
        has_passport=False,
        passport_image=None,
    )

    USER_STATE.pop(uid, None)

    bot.send_message(
        call.message.chat.id,
        "✅ Ro‘yxatdan o‘tish yakunlandi!\n"
        "❗️Pasport yo‘q deb belgilandi — admin siz bilan bog‘lanadi.\n\n"
        + passport_advice_text()
    )
    bot.answer_callback_query(call.id)


@bot.message_handler(content_types=["photo"])
def reg_passport_photo(message):
    uid = message.from_user.id
    if uid not in USER_STATE or USER_STATE[uid].get("step") != "passport_upload":
        return

    st = USER_STATE[uid]
    file_id = message.photo[-1].file_id

    tg_file = bot.get_file(file_id)
    file_bytes = bot.download_file(tg_file.file_path)

    filename = f"passport_{uid}_{timezone.now().strftime('%Y%m%d%H%M%S')}.jpg"

    participant = TravelParticipants(
        travel_id=st["travel_id"],
        user_id=uid,
        first_name=st["first_name"],
        last_name=st["last_name"],
        father_name=st["father_name"],
        phone_number=st["phone_number"],
        has_passport=True,
    )
    participant.passport_image.save(filename, ContentFile(file_bytes), save=True)

    USER_STATE.pop(uid, None)

    bot.send_message(
        message.chat.id,
        "✅ Ro‘yxatdan o‘tish yakunlandi! Adminlar siz bilan bog‘lanishadi.\n"
        "Quyidagi kanalimizga obuna bo‘lishni unutmang:\n\n@Iskandarqori_SafoMarva"
    )


@bot.message_handler(content_types=["document"])
def reg_passport_doc(message):
    uid = message.from_user.id
    if uid not in USER_STATE or USER_STATE[uid].get("step") != "passport_upload":
        return

    st = USER_STATE[uid]
    file_id = message.document.file_id

    tg_file = bot.get_file(file_id)
    file_bytes = bot.download_file(tg_file.file_path)

    ext = tg_file.file_path.split(".")[-1] if "." in tg_file.file_path else "bin"
    filename = f"passport_{uid}_{timezone.now().strftime('%Y%m%d%H%M%S')}.{ext}"

    participant = TravelParticipants(
        travel_id=st["travel_id"],
        user_id=uid,
        first_name=st["first_name"],
        last_name=st["last_name"],
        father_name=st["father_name"],
        phone_number=st["phone_number"],
        has_passport=True,
    )
    participant.passport_image.save(filename, ContentFile(file_bytes), save=True)

    USER_STATE.pop(uid, None)

    bot.send_message(message.chat.id, "✅ Ro‘yxatdan o‘tish yakunlandi! Adminlar siz bilan bog‘lanishadi.")


@bot.message_handler(commands=["cancel"])
def cancel(message):
    if USER_STATE.pop(message.from_user.id, None):
        bot.send_message(message.chat.id, "❌ Ro‘yxatdan o‘tish bekor qilindi.")
    else:
        bot.send_message(message.chat.id, "Sizda aktiv ro‘yxatdan o‘tish jarayoni yo‘q.")


if __name__ == "__main__":
    bot.infinity_polling(skip_pending=True)
