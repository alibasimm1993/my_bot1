# -*- coding: utf-8 -*-

import os
import logging
import asyncio
import sqlite3
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from dotenv import load_dotenv

# ==================== الإعداد ====================
load_dotenv()

# يجب أن تكون هذه المتغيرات في ملف .env
BOT_TOKEN = os.getenv('8351114047:AAEeEdEal9GldcY1nwRyQtIF5pOBDAemMVs')
ADMIN_ID_STR = os.getenv('133464343')

# تحويل ADMIN_ID إلى رقم صحيح
try:
    ADMIN_ID = int(ADMIN_ID_STR) if ADMIN_ID_STR and ADMIN_ID_STR.isdigit() else 0
except (ValueError, AttributeError):
    ADMIN_ID = 0
    
DB_PATH = "clinic.db"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== قاعدة البيانات (مع تحسينات الأمان) ====================
def db_execute(query, params=(), fetch=False):
    """تنفيذ استعلام قاعدة البيانات مع ضمان إغلاق الاتصال."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute(query, params)
            result = c.fetchall() if fetch else None
            conn.commit()
            return result
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return None

def init_db():
    """تهيئة جداول قاعدة البيانات."""
    db_execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        state TEXT,
        last_message TIMESTAMP
    )''')
    db_execute('''CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        phone TEXT,
        date TEXT,
        time TEXT,
        created_at TIMESTAMP
    )''')
    db_execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        message_text TEXT,
        message_type TEXT,
        created_at TIMESTAMP
    )''')


# ==================== وظائف مساعدة ====================
def set_user_state(user_id, state):
    db_execute("INSERT OR REPLACE INTO users (user_id, state, last_message) VALUES (?, ?, ?)",
               (user_id, state, datetime.now()))

def get_user_state(user_id):
    res = db_execute("SELECT state FROM users WHERE user_id=?", (user_id,), fetch=True)
    return res[0][0] if res else None

def clear_user_state(user_id):
    db_execute("UPDATE users SET state=NULL WHERE user_id=?", (user_id,))

def update_last_message(user_id):
    db_execute("UPDATE users SET last_message=? WHERE user_id=?", (datetime.now(), user_id))

def save_booking(user_id, name, phone, date, time):
    db_execute(
        "INSERT INTO bookings (user_id, name, phone, date, time, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, name, phone, date, time, datetime.now())
    )

def save_message(user_id, username, message_text, message_type):
    """حفظ الرسالة في قاعدة البيانات"""
    db_execute(
        "INSERT INTO messages (user_id, username, message_text, message_type, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, username, message_text, message_type, datetime.now())
    )

def is_valid_phone(phone):
    """تحقق بسيط من رقم الهاتف: يجب أن يحتوي على 7 أرقام على الأقل."""
    # يزيل أي مسافات أو رموز
    cleaned_phone = re.sub(r'[^\d]', '', phone)
    return len(cleaned_phone) >= 7

# ==================== رسالة الترحيب ====================
def get_welcome_message():
    """رسالة الترحيب الطويلة"""
    return """مرحبًا بيك في بوت الاستفسارات الخاص بعيادة B Healthy 🌿

هنا نسمعك، ونتابع وياك… لأن إحنا نؤمن إن كل تغيير كبير يبدأ بخطوة وعي صغيرة.

🔸 البوت هذا مصمَّم للإجابة على استفساراتك الغذائية والعلاجية المتعلقة بحالتك الصحية، وتشمل:

– أسئلتك عن النظام الغذائي الخاص بيك

– تطوّر الأعراض أو التحسّن اللي تحس بيه

– أي توجيه تحتاجه ضمن الخطة العلاجية اللي تتبعها ويانا

❗️إذا ده تعاني من أعراض جديدة أو حالة مرضية جديدة، ضروري تراجع الطبيب مباشرة، لأن التشخيص الطبي ما يتم عن طريق الرسائل.

📌 نحب نوضح إن البوت مو بديل عن الزيارة الطبية، لكنه موجود حتى يدعمك، ويتابع وياك، ويخلي عندك إحساس إنك مو وحدك بالطريق.

🕒 تقدر تتواصل ويانا بأي وقت، البوت متاح 24/7 لخدمتك، وبإمكانك ترك سؤالك، وترد عليك اخصائية التغذية بأقرب وقت ممكن خلال 24-48 ساعة.

🫶 احنه نؤمن:

جسمك يستحق الدعم، وأنت تستحق تتحرر من الألم.

خلينا نكون جزء من رحلة تعافيك، خطوة بخطوة"""

async def show_welcome_message(context, chat_id):
    """عرض رسالة الترحيب"""
    welcome_msg = get_welcome_message()
    keyboard = [
        [InlineKeyboardButton("➡️ ابدأ", callback_data="show_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=chat_id, text=welcome_msg, reply_markup=reply_markup)

# ==================== أوامر المستخدم ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    set_user_state(user.id, None)
    
    # إرسال رسالة الترحيب أولاً (ثابتة)
    await show_welcome_message(context, update.effective_chat.id)

async def show_main_menu(context, chat_id, message_id=None):
    message = "🤔 شنو تحب تسوي اليوم؟\n\nاختر من الخيارات التالية:"
    keyboard = [
        [InlineKeyboardButton("1️⃣ 📝 استفسار جديد", callback_data="ask")],
        [InlineKeyboardButton("2️⃣ 🔄 أريد أعدل نظامي", callback_data="edit_diet")],
        [InlineKeyboardButton("3️⃣ 🔬 شرح تحليل", callback_data="explain_analysis")],
        [InlineKeyboardButton("4️⃣ 📅 أريد أحجز موعد مراجعة", callback_data="book")],
        [InlineKeyboardButton("5️⃣ 🏥 أريد برنامج غذائي لحالة طبية معينة", callback_data="medical_diet")],
        [InlineKeyboardButton("6️⃣ 👩‍⚕️ أحتاج متابعة يومية مع أخصائية التغذية", callback_data="daily_followup")],
        [InlineKeyboardButton("7️⃣ 📞 أريد التواصل مع الأخصائية مباشرة", callback_data="contact")],
        [InlineKeyboardButton("❓ الأسئلة المتكررة", callback_data="faq")],
        [InlineKeyboardButton("🗓 مواعيدي المحجوزة", callback_data="my_bookings")],
        [InlineKeyboardButton("🏠 الصفحة الرئيسية", callback_data="show_welcome")]
    ]
    reply = InlineKeyboardMarkup(keyboard)
    if message_id:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=message, reply_markup=reply)
    else:
        await context.bot.send_message(chat_id=chat_id, text=message, reply_markup=reply)

# ==================== خيارات المستخدم ====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    update_last_message(user_id)

    if data == "book":
        await show_booking_days(query, context)
    elif data.startswith("day_"):
        # day_YYYY-MM-DD
        await show_booking_times(query, context, data.split("_")[1])
    elif data.startswith("time_"):
        # time_YYYY-MM-DD_HH:MM
        _, date, time = data.split("_", 2)
        await confirm_booking(query, context, date, time)
    elif data == "ask":
        await query.edit_message_text("📝 اكتب سؤالك وسنرد بأقرب وقت ممكن خلال 24-48 ساعة.")
        set_user_state(user_id, "waiting_inquiry")
    elif data == "edit_diet":
        message_text = """🔄 تعديل النظام الغذائي

اذكر شنو المشاكل أو الأعراض اللي تمر بيها أو الأكلات اللي عندك مشكلة فيها.

حتى نساعدك بالتعديل المناسب."""
        await query.edit_message_text(message_text)
        set_user_state(user_id, "waiting_diet_edit")
    elif data == "explain_analysis":
        await query.edit_message_text("🔬 أرسل صورة أو تفاصيل التحليل الذي تريد شرحه، وسنقوم بشرحه لك.")
        set_user_state(user_id, "waiting_analysis")
    elif data == "medical_diet":
        await query.edit_message_text("🏥 أرسل تفاصيل الحالة الطبية والبرنامج الغذائي المطلوب:")
        set_user_state(user_id, "waiting_medical_diet")
    elif data == "daily_followup":
        await query.edit_message_text("📆 أرسل تفاصيل حالتك الصحية والهدف من المتابعة اليومية:")
        set_user_state(user_id, "waiting_daily_followup")
    elif data == "contact":
        await query.edit_message_text("📞 تواصل معنا عبر واتساب: 07727292075")
    elif data == "show_menu":
        await show_main_menu(context, query.message.chat.id, query.message.message_id)
    elif data == "show_welcome":
        welcome_msg = get_welcome_message()
        keyboard = [
            [InlineKeyboardButton("➡️ ابدأ", callback_data="show_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=welcome_msg, reply_markup=reply_markup)
    elif data == "faq":
        await show_faq_menu(query, context)
    elif data.startswith("faq_"):
        await show_faq_answer(query, context, data.split("_")[1])
    elif data == "back_menu":
        await show_main_menu(context, query.message.chat.id, query.message.message_id)
    elif data == "my_bookings":
        await show_user_bookings(query, context)


# ==================== الأسئلة المتكررة (لم يتم تغييرها) ====================
async def show_faq_menu(query, context):
    """عرض قائمة الأسئلة المتكررة"""
    message = "❓ الأسئلة المتكررة\n\nاختر السؤال اللي تريد تعرف إجابته:"
    keyboard = [
        [InlineKeyboardButton("🔸 زيادة الأعراض بعد العلاج المضاد للبكتيريا/الفطريات", callback_data="faq_1")],
        [InlineKeyboardButton("🔸 زيادة الأعراض بعد البروبيوتيك", callback_data="faq_2")],
        [InlineKeyboardButton("🔸 المتابعة الأسبوعية في العيادة", callback_data="faq_3")],
        [InlineKeyboardButton("🔸 مراجعة العلاجات", callback_data="faq_4")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=message, reply_markup=reply_markup)

async def show_faq_answer(query, context, faq_id):
    """عرض إجابة السؤال المختار"""
    answers = {
        "1": """🔸 زيادة الأعراض بعد العلاج المضاد للبكتيريا/الفطريات

ج/ عند بدء استخدام علاج مضاد للبكتيريا أو الفطريات، من الطبيعي نلاحظ زيادة مؤقتة في الأعراض.

هذا لأن البكتيريا والفطريات هي كائنات دقيقة مغلّفة مثل الفقاعة، تحتوي بداخلها على بروتينات وسموم.

لما نبدأ العلاج، هاي الكائنات تموت وتتحلل، وتفرز محتواها داخل الجسم – وهذا الشي يسبب ما نسمّيه علميًا "die-off reaction" أو تفاعل تحلل الكائنات الممرضة.

هذا التفاعل ممكن يسبب أعراض مثل التعب، الانتفاخ، أو زيادة بسيطة بالأعراض السابقة، لكنه علامة إيجابية تدل على استجابة الجسم للعلاج.

غالبًا تستقر الأعراض خلال ٣ أيام إلى أسبوع كحد أقصى.

ولتقليل الانزعاج، يُنصح بدعم الجسم بمضادات أكسدة طبيعية مثل:

• شاي الكركم مع الليمون 🍋
• أو الشاي الأخضر ☕

لأنها تساعد الجسم على التخلص من السموم بشكل أسرع. 

ولا تنسى تغذي جسمك بالمغذيات المكتوبه بنظامك الغذائي (ماء كسور البقر، شوربة الخضار) اللحوم الحمراء والبيضاء والدهون الصحية""",
        
        "2": """🔸 زيادة الأعراض بعد البروبيوتيك

ج/ أفهم تمامًا شنو تحس، وصدقني، مو غريب أبدًا اللي ديصير وياك.

بالعكس، اللي تمر بيه الآن ممكن يكون علامة إن الجسم دا يتغير للأفضل، حتى لو بدا الأمر مُتعب بالبداية.

كأنما دا يعيد ترتيب داخلي شامل: البكتيريا المفيدة تبدي تطغى على الضارة، وبهالعملية تطلع سموم مؤقتة بسبب موت البكتيريا الضارة.

وهالشي ممكن يسبب:

• نفخة
• غازات
• تغيّرات بالإخراج
• تعب عام مفاجئ

وهاي الحالة نسميها أحيانًا "probiotic adjustment reaction"، وهي حالة مؤقتة، ويدل إن جسمك قاعد يتفاعل ويتأقلم.

🥄 حتى تساعد نفسك بهالفترة:

• خفّف على نفسك، خذ الأمور بهدوء
• اشرب سوائل دافئة مثل النعناع، الزنجبيل أو الشاي الأخضر
• وكمّل البروبيوتيك بجرعة منتظمة

غالبًا، هاي الأعراض تخف خلال ٣ إلى ٧ أيام

🛑 وإذا كانت التقلصات قوية جدًا، أو التعب فوق طاقتك، لا بأس أبدًا إن توقف البروبيوتيك مؤقتًا وترجع له بعد أسبوع.

الراحة جزء من الخطة، وماكو شيء أغلى من راحة بالك وجسمك.

🫶 إنت مو وحدك بهالرحلة، إحنا ويّاك، خطوة بخطوة، حتى نوصل لتحسن حقيقي ومستدام.""",
        
        "3": """🔸 المتابعة الأسبوعية في العيادة

إحنا جدًا فخورين بجهودك واهتمامك بصحتك 🌿

الالتزام بالمتابعة هو خطوة قوية تعكس وعيك، ويخلينا نكون شركاء حقيقيين وياك برحلة العلاج.

نعم، من المهم جدًا الالتزام بالمراجعة الأسبوعية داخل العيادة، لأن المتابعة تُعتبر جزء أساسي من خطة العلاج.

كل زيارة نتابع بيها استجابة الجسم للنظام الغذائي، نقيّم التحسّن، نعدّل الجرعات أو نوعية الأطعمة حسب تطور الحالة، ونحل أي مشكلة تظهر حتى نستمر بالتقدم.

📍 أما إذا كان الحضور الأسبوعي صعب — سواء بسبب السفر أو البعد أو ظروف خاصة — نطلب الالتزام بالمتابعة عن طريق تليجرام بشكل منتظم، مع الحضور لمراجعة شهرية داخل العيادة.

المراجعة الشهرية ضرورية وبيها متابعة الطبيب واخصائية التغذية حتى نقدر نحدث الخطة الغذائية أو العلاجية حسب الحاجة.

📌 موعد مراجعتك مكتوب بوضوح داخل البرنامج الغذائي، يرجى الالتزام به والتواصل ويانا لتأكيد الحجز""",
        
        "4": """🔸 مراجعة العلاجات

ج/ شكرًا لإرسال صور علاجاتك، راح نراجعها بأقرب وقت ونتواصل وياك.

اذا تأخرنا عليك بالرد لا تتردد واتصل بينا او راسلنا على واتس اب العيادة 07727292075 🌱

عندك العافية💕🪴"""
    }
    
    answer = answers.get(faq_id, "عذراً، السؤال غير موجود.")
    keyboard = [
        [InlineKeyboardButton("🔙 رجوع للأسئلة", callback_data="faq")],
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=answer, reply_markup=reply_markup)


# ========== خطوات الحجز (مع تحسينات الأيام الديناميكية) ==========
def get_next_working_days(num_days=5):
    """يحسب الأيام الخمسة القادمة من الأحد إلى الخميس."""
    today = datetime.now().date()
    working_days = []
    
    # أسماء الأيام بالعربية
    day_names = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    
    # الأيام التي لا تعمل فيها العيادة (الجمعة والسبت)
    non_working_days = [4, 5] # 4=الجمعة, 5=السبت (0=الاثنين, 6=الأحد)
    
    current_date = today
    while len(working_days) < num_days:
        # weekday() يعطي 0 للإثنين و 6 للأحد
        # نحتاج لضبطه ليتوافق مع أسماء الأيام العربية
        # 0=الاثنين, 1=الثلاثاء, 2=الأربعاء, 3=الخميس, 4=الجمعة, 5=السبت, 6=الأحد
        day_index = current_date.weekday()
        
        # إذا كان اليوم ليس جمعة أو سبت
        if day_index not in non_working_days:
            # اسم اليوم (نستخدم 6 للأحد، 0 للإثنين... 3 للخميس)
            # نستخدم day_names[day_index] مباشرة
            day_name = day_names[day_index]
            
            # تنسيق التاريخ لـ callback_data
            date_str = current_date.strftime("%Y-%m-%d")
            
            working_days.append((f"{day_name} ({current_date.day}/{current_date.month})", date_str))
        
        current_date += timedelta(days=1)
        
    return working_days

async def show_booking_days(query, context):
    days = get_next_working_days(5)
    keyboard = []
    for day_name, date_str in days:
        keyboard.append([InlineKeyboardButton(day_name, callback_data=f"day_{date_str}")])
        
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_menu")])
    await query.edit_message_text("📅 اختر اليوم المناسب (الأيام القادمة):", reply_markup=InlineKeyboardMarkup(keyboard))

async def show_booking_times(query, context, date_str):
    # تحويل التاريخ من string إلى object للحصول على اسم اليوم
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        # أسماء الأيام بالعربية
        day_names = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
        day_name = day_names[date_obj.weekday()]
    except ValueError:
        day_name = "التاريخ المحدد"
        
    times = ["13:00 ظهراً", "15:00 عصراً", "17:00 عصراً"]
    keyboard = []
    for t in times:
        # نستخدم الوقت بتنسيق HH:MM في callback_data لسهولة المعالجة
        time_code = t.split()[0]
        keyboard.append([InlineKeyboardButton(t, callback_data=f"time_{date_str}_{time_code}")])
        
    keyboard.append([InlineKeyboardButton("🔙 رجوع لاختيار اليوم", callback_data="book")])
    await query.edit_message_text(f"⏰ اختر الوقت ليوم {day_name} ({date_obj.day}/{date_obj.month}):", reply_markup=InlineKeyboardMarkup(keyboard))

async def confirm_booking(query, context, date, time):
    user_id = query.from_user.id
    # يتم تخزين التاريخ والوقت بتنسيق YYYY-MM-DD و HH:MM
    await query.edit_message_text("🧾 أرسل اسمك الثلاثي:")
    set_user_state(user_id, f"waiting_name_{date}_{time}")

# ==================== عرض حجوزات المستخدم ====================
async def show_user_bookings(query, context):
    user_id = query.from_user.id
    bookings = db_execute("SELECT date, time FROM bookings WHERE user_id=? ORDER BY date DESC, time DESC LIMIT 5", (user_id,), fetch=True)
    
    if not bookings:
        text = "❌ لم تقم بحجز أي مواعيد بعد."
    else:
        text = "📅 آخر 5 مواعيد حجزتها:\n\n"
        for date, time in bookings:
            text += f"موعدك في: {date} الساعة {time}\n"
            
    keyboard = [
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=text, reply_markup=reply_markup)


# ==================== استقبال الرسائل (مع تحسينات التحقق والإشعارات) ====================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or "غير معروف"
    state = get_user_state(user_id)
    text = update.message.text

    # حفظ الرسالة في قاعدة البيانات
    save_message(user_id, username, text, state or "general")

    # إرسال نسخة إلى الأدمن (مع تسجيل الخطأ)
    if ADMIN_ID:
        try:
            # نستخدم HTML لتنسيق الرسالة للأدمن
            admin_message = f"<b>📩 رسالة جديدة</b>\n"
            admin_message += f"👤 المستخدم: <a href='tg://user?id={user_id}'>{user.full_name}</a> (@{username})\n"
            admin_message += f"💬 الرسالة:\n{text}"
            await context.bot.send_message(ADMIN_ID, admin_message, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Failed to send message to ADMIN_ID {ADMIN_ID}: {e}")

    if state and state.startswith("waiting_name_"):
        _, date, time = state.split("_", 2)
        # حفظ الاسم في الـ state
        set_user_state(user_id, f"waiting_phone_{date}_{time}_{text}")
        await update.message.reply_text("📞 شكراً لك. الآن أرسل رقم هاتفك:")
        
    elif state and state.startswith("waiting_phone_"):
        _, date, time, name = state.split("_", 3)
        phone = text
        
        if not is_valid_phone(phone):
            await update.message.reply_text("❌ رقم الهاتف غير صحيح. يرجى إدخال رقم هاتف صالح (7 أرقام على الأقل):")
            # لا نغير الـ state لإعادة المحاولة
            return
            
        save_booking(user_id, name, phone, date, time)
        clear_user_state(user_id)
        
        # رسالة تأكيد للمستخدم
        await update.message.reply_text(f"✅ تم حجز موعدك بنجاح!\n\nموعدك هو: {date} الساعة {time}\nشكراً لك 💚")
        await show_main_menu(context, update.effective_chat.id)
        
        # إشعار حجز جديد للأدمن بتنسيق HTML
        if ADMIN_ID:
            admin_booking_message = f"<b>📅 حجز موعد جديد!</b>\n"
            admin_booking_message += f"👤 الاسم: {name}\n"
            admin_booking_message += f"📞 الهاتف: {phone}\n"
            admin_booking_message += f"🗓 التاريخ: {date}\n"
            admin_booking_message += f"⏰ الوقت: {time}\n"
            admin_booking_message += f"🔗 المستخدم: <a href='tg://user?id={user_id}'>{user.full_name}</a> (@{username})"
            
            try:
                await context.bot.send_message(ADMIN_ID, admin_booking_message, parse_mode='HTML')
            except Exception as e:
                logger.error(f"Failed to send booking notification to ADMIN_ID {ADMIN_ID}: {e}")
                
    elif state == "waiting_inquiry":
        clear_user_state(user_id)
        save_message(user_id, username, text, "inquiry")
        await update.message.reply_text("🙏 تم استلام استفسارك، سنرد بأقرب وقت ممكن.")
        await show_main_menu(context, update.effective_chat.id)
        
    elif state == "waiting_diet_edit":
        clear_user_state(user_id)
        save_message(user_id, username, text, "diet_edit")
        await update.message.reply_text("✅ تم استلام طلب تعديل النظام الغذائي، سنقوم بمراجعته.")
        await show_main_menu(context, update.effective_chat.id)
        
    elif state == "waiting_analysis":
        clear_user_state(user_id)
        save_message(user_id, username, text, "analysis")
        await update.message.reply_text("✅ تم استلام التحليل، سنقوم بشرحه وإرسال التفسير.")
        await show_main_menu(context, update.effective_chat.id)
        
    elif state == "waiting_medical_diet":
        clear_user_state(user_id)
        save_message(user_id, username, text, "medical_diet")
        await update.message.reply_text("✅ تم استلام طلب البرنامج الغذائي الطبي، سنقوم بإعداده وإرساله.")
        await show_main_menu(context, update.effective_chat.id)
        
    elif state == "waiting_daily_followup":
        clear_user_state(user_id)
        save_message(user_id, username, text, "daily_followup")
        await update.message.reply_text("✅ تم استلام طلب المتابعة اليومية، سنقوم بترتيب جدول المتابعة مع الأخصائية.")
        await show_main_menu(context, update.effective_chat.id)
        
    else:
        # رسالة عامة للمستخدمين الذين يرسلون رسائل نصية دون أن يكونوا في حالة انتظار
        await update.message.reply_text("عذراً، لم أفهم طلبك. يرجى استخدام الأزرار في القائمة الرئيسية.")
        await show_main_menu(context, update.effective_chat.id)


# ==================== لوحة تحكم الأدمن ====================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    keyboard = [
        [InlineKeyboardButton("📋 عرض المواعيد", callback_data="admin_bookings")],
        [InlineKeyboardButton("📩 عرض الرسائل", callback_data="admin_messages")],
        [InlineKeyboardButton("👥 عدد المستخدمين", callback_data="admin_users")],
    ]
    await update.message.reply_text("🧑‍💻 لوحة تحكم الأدمن:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return
    
    # إضافة زر الرجوع إلى قائمة الأدمن
    back_to_admin_menu = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_menu")]])
    
    if query.data == "admin_menu":
        await admin_panel(update, context)
        return
        
    elif query.data == "admin_bookings":
        bookings = db_execute("SELECT name, phone, date, time FROM bookings ORDER BY created_at DESC LIMIT 10", fetch=True)
        if not bookings:
            await query.edit_message_text("لا توجد مواعيد حالياً.", reply_markup=back_to_admin_menu)
            return
        
        text = "📅 آخر 10 مواعيد:\n\n"
        for name, phone, date, time in bookings:
            text += f"👤 {name}\n"
            text += f"📞 {phone}\n"
            text += f"🗓 {date} - ⏰ {time}\n\n"
            
        await query.edit_message_text(text, reply_markup=back_to_admin_menu)
        
    elif query.data == "admin_messages":
        messages = db_execute("SELECT username, message_text, message_type, created_at FROM messages ORDER BY created_at DESC LIMIT 15", fetch=True)
        if not messages:
            await query.edit_message_text("لا توجد رسائل حالياً.", reply_markup=back_to_admin_menu)
            return
            
        text = "📩 آخر 15 رسالة:\n\n"
        msg_type_names = {
            "inquiry": "استفسار",
            "diet_edit": "تعديل نظام",
            "analysis": "تحليل",
            "medical_diet": "برنامج طبي",
            "daily_followup": "متابعة يومية",
            "general": "عام",
            "waiting_inquiry": "انتظار استفسار",
            "waiting_diet_edit": "انتظار تعديل نظام",
            "waiting_analysis": "انتظار تحليل",
            "waiting_medical_diet": "انتظار برنامج طبي",
            "waiting_daily_followup": "انتظار متابعة",
        }
        
        for msg in messages:
            username, message_text, message_type, created_at = msg
            msg_type = msg_type_names.get(message_type, message_type)
            
            text += f"👤 @{username or 'غير معروف'}\n"
            text += f"📝 {msg_type}\n"
            text += f"💬 {message_text[:50]}{'...' if len(message_text) > 50 else ''}\n"
            text += f"⏰ {created_at}\n\n"
            
        await query.edit_message_text(text, reply_markup=back_to_admin_menu)
        
    elif query.data == "admin_users":
        users = db_execute("SELECT COUNT(*) FROM users", fetch=True)
        user_count = users[0][0] if users else 0
        await query.edit_message_text(f"👥 عدد المستخدمين المسجلين: {user_count}", reply_markup=back_to_admin_menu)


# ==================== تشغيل البوت ====================
def main():
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN is not set. Please create a .env file and add BOT_TOKEN.")
        return

    init_db()
    
    # إزالة حلقة إعادة التشغيل التلقائية غير الفعالة
    try:
        app = Application.builder().token(BOT_TOKEN).build()

        # أوامر المستخدم
        app.add_handler(CommandHandler("start", start))
        
        # أوامر الأدمن
        app.add_handler(CommandHandler("admin", admin_panel))
        
        # معالجة الأزرار
        app.add_handler(CallbackQueryHandler(button_handler, pattern=r'^(?!admin_)'))
        app.add_handler(CallbackQueryHandler(admin_handler, pattern=r'^admin_'))
        
        # معالجة الرسائل النصية
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

        logger.info("✅ البوت يعمل الآن: Be Healthy Clinic")
        
        # تشغيل البوت
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
    except Exception as e:
        logger.error(f"❌ خطأ في تشغيل البوت: {e}")

if __name__ == "__main__":
    main()
