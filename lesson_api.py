import os
import logging
import requests

logger = logging.getLogger(__name__)

ILOVA_URL = os.environ.get("ILOVA_URL", "").rstrip("/")
BOT_API_SECRET = os.environ.get("BOT_API_SECRET", "zamira2024")


def get_lesson(level, day):
    if not ILOVA_URL:
        logger.error("ILOVA_URL o'rnatilmagan")
        return None
    try:
        r = requests.get(
            f"{ILOVA_URL}/api/lesson-brief",
            params={"level": level, "day": day, "secret": BOT_API_SECRET},
            timeout=45,  # 15 dan 45 ga oshirildi — katta/sekin PDF'li kunlarda "timeout" tufayli
                         # noto'g'ri "dars tayyor emas" chiqishining oldini oladi
        )
        d = r.json()
        return d if d.get("ok") else None
    except Exception as e:
        logger.error(f"get_lesson({level},{day}): {e}")
        return None


def get_week_lessons(level, week):
    start = (week - 1) * 7 + 1
    lessons = []
    for day in range(start, start + 6):
        l = get_lesson(level, day)
        if l:
            lessons.append(l)
    return lessons


# ===== Daraja bo'yicha grammatik chegara =====
LEVEL_RULES = {
    "a1": (
        "DARAJA CHEGARASI (A1 — qattiq rioya qil): "
        "FAQAT hozirgi zamon fe'llari. O'tgan/kelasi zamon ishlatma. "
        "Faqat sodda gaplar (ega+kesim+to'ldiruvchi). Bo'ysunuvchi gap (потому что, если, когда, который) ISHLATMA. "
        "Faqat darslikdagi so'zlar va eng oddiy kundalik so'zlar. Bitta savolda faqat bitta fikr so'ra."
    ),
    "b1": (
        "DARAJA CHEGARASI (B1): "
        "O'tgan va kelasi zamon erkin ishlatiladi. Bo'ysunuvchi gaplar (потому что, если, когда, который, чтобы) "
        "bemalol ishlatiladi. Fe'l aspekti (NSV/SV) farqini savollarda tabiiy ishlat. "
        "Mavhumroq mavzular (fikr, sabab, taqqoslash) so'rash mumkin."
    ),
}

# ===== Tabiiy, gapirtiruvchi suhbat uslubi (barcha darajalarga umumiy) =====
CONVO_STYLE = (
    "SUHBAT USLUBI (juda muhim, har doim rioya qil):\n"
    "1. Savollaring HECH QACHON 'ha/yo'q' bilan javob olinadigan bo'lmasin. Doim 'расскажи', 'какой', "
    "'почему', 'как ты думаешь', 'что ты обычно...' kabi ochiq savol qurilmalaridan foydalan.\n"
    "2. Agar foydalanuvchi qisqa (1-3 so'z) javob bersa — DARHOL keyingi mavzuga o'tma. Avval o'sha javobiga "
    "qiziqish bildirib, aniqlashtiruvchi savol ber (masalan javob 'Хорошо' bo'lsa — 'А что именно было хорошо? Расскажи!').\n"
    "3. Har javobdan keyin qisqa tabiiy reaksiya ber ('Понятно!', 'Интересно!', 'Ого!', 'Здорово!') — keyin savol. "
    "Robot kabi to'g'ridan-to'g'ri savolga o'tma.\n"
    "4. Suhbat davomida grammatik xatoni HECH QACHON tuzatma va eslatma — bu alohida tugma orqali ko'rsatiladi. "
    "Faqat mazmunga e'tibor ber, tabiiy suhbatdosh kabi javob ber.\n"
    "5. Rasmiy/darslik tiliga o'xshamasin — jonli so'zlashuv uslubi ('ну', 'кстати', 'слушай' kabi so'zlar me'yorida bo'lsin).\n"
    "6. Har xabaring — 1-2 gap reaksiya + 1 ta ochiq savol. Uzun ma'ruza qilma.\n"
    "7. TINISH BELGILARI — ovoz sintezi shu belgilarga qarab intonatsiya qiladi, shuning uchun har doim to'g'ri qo'y: "
    "vergul (,) — qisqa pauza; nuqta (.) — gap tugashi, pastroq ohang; savol belgisi (?) — ko'tariluvchi ohang; "
    "undov belgisi (!) — quvonch/hayajon; ko'p nuqta (...) — o'ylanish yoki kutish pauzasi. "
    "Har gapni albatta shu belgilardan biri bilan tugat, hech qachon belgisiz qoldirma."
)


def build_daily_prompt(lesson):
    vocab = ", ".join(f"{v.get('ru','')} ({v.get('uz','')})" for v in lesson.get("vocab", [])[:15])
    formulas = "; ".join(f.get("ru", "") for f in lesson.get("formulas", [])[:8])
    grammar_items = lesson.get("grammar", [])[:3]
    grammar_txt = "; ".join(
        f"{g.get('title','')} — {g.get('sub','')}" for g in grammar_items if g.get("title")
    )
    topic = lesson.get("topic", "")
    level = (lesson.get("level") or "a1").lower()
    level_rule = LEVEL_RULES.get(level, LEVEL_RULES["a1"])

    grammar_line = f"Shu darsning grammatikasi (imkon qadar shu qurilmalardan foydalan): {grammar_txt}. " if grammar_txt else ""

    return (
        "Sen rus tili o'qituvchisisan (ismin Zamira), lekin o'qituvchidan ko'ra qiziqarli suhbatdoshga o'xshaysan. "
        "Faqat quyidagi darslik asosida gaplash. "
        f"Mavzu: {topic}. Foydalanuvchi darajasi: {level.upper()}. "
        f"Darslik so'zlari: {vocab}. Iboralar: {formulas}. {grammar_line}\n\n"
        f"{level_rule}\n\n"
        f"{CONVO_STYLE}\n\n"
        "MUHIM: bu suhbatning ENG BIRINCHI xabari. O'zingni tanishtirma, salomlashishdan boshlama. "
        f"Xabaringni aynan shu qolipda boshla: «Сегодня поговорим на тему «{topic}».» — so'ng darhol "
        "shu mavzudagi ochiq (расскажи/какой/почему turidagi) savol ber. Boshqa hech narsa qo'shma. "
        "Faqat ruscha yoz."
    )


def build_exam_prompt(lessons, level):
    topics = ", ".join(l.get("topic", "") for l in lessons)
    vocab_all = []
    for l in lessons:
        vocab_all += l.get("vocab", [])
    vocab = ", ".join(v.get("ru", "") for v in vocab_all[:25])
    level_l = (level or "a1").lower()
    level_rule = LEVEL_RULES.get(level_l, LEVEL_RULES["a1"])

    return (
        f"Bu hafta yakuni og'zaki imtihoni. Daraja: {level_l.upper()}. Mavzular: {topics}. "
        f"Shu so'zlardan foydalan: {vocab}.\n\n"
        f"{level_rule}\n\n"
        f"{CONVO_STYLE}\n\n"
        "MUHIM: bu suhbatning ENG BIRINCHI xabari. O'zingni tanishtirma, uzoq salomlashma. "
        "Darhol birinchi ochiq savolni ber. "
        "Foydalanuvchiga bittadan ketma-ket ochiq savol ber (bir vaqtda faqat bitta savol, ha/yo'q savol emas). "
        "Qisqa javob bersa — aniqlashtiruvchi savol bilan chuqurlashtir, keyin bahoga o't. "
        "Har javobni qisqa (baholovchi so'z bermasdan, tabiiy) qabul qil, keyin keyingi savolga o't. Faqat ruscha yoz."
    )
