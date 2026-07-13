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
            timeout=15,
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


def build_daily_prompt(lesson):
    vocab = ", ".join(f"{v.get('ru','')} ({v.get('uz','')})" for v in lesson.get("vocab", [])[:15])
    formulas = "; ".join(f.get("ru", "") for f in lesson.get("formulas", [])[:8])
    topic = lesson.get("topic", "")
    return (
        "Sen rus tili o'qituvchisisan (ismin Zamira). Faqat quyidagi darslik asosida gaplash. "
        f"Mavzu: {topic}. Foydalanuvchi darajasi: {lesson.get('level','')}. "
        f"Darslik so'zlari: {vocab}. Iboralar: {formulas}. "
        "MUHIM: bu suhbatning ENG BIRINCHI xabari. O'zingni tanishtirma, salomlashishdan boshlama. "
        f"Xabaringni aynan shu qolipda boshla: «Сегодня поговорим на тему «{topic}».» — so'ng darhol "
        "shu mavzudagi oddiy ruscha savol ber (bitta gap). Boshqa hech narsa qo'shma. "
        "Keyingi xabarlaringda: foydalanuvchiga shu so'z va iboralar bilan ruscha oddiy savol ber, javobini kut. "
        "Xato qilsa — yumshoq to'g'irla va rag'batlantir. Darajadan qiyin so'z ishlatma. Darslikdan chiqma. "
        "Har javobing 1-3 gap, oxirida bitta savol. Faqat ruscha yoz."
    )


def build_exam_prompt(lessons, level):
    topics = ", ".join(l.get("topic", "") for l in lessons)
    vocab_all = []
    for l in lessons:
        vocab_all += l.get("vocab", [])
    vocab = ", ".join(v.get("ru", "") for v in vocab_all[:25])
    return (
        f"Bu hafta yakuni og'zaki imtihoni. Daraja: {level}. Mavzular: {topics}. "
        f"Shu so'zlardan foydalan: {vocab}. "
        "MUHIM: bu suhbatning ENG BIRINCHI xabari. O'zingni tanishtirma, uzoq salomlashma. "
        "Darhol birinchi savolni ber (bitta gap). "
        "Foydalanuvchiga bittadan ketma-ket og'zaki savol ber (bir vaqtda faqat bitta savol). "
        "Har javobni qisqa baholang, keyin keyingi savolga o'ting. Faqat ruscha yoz."
    )
