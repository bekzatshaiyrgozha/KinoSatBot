import os
import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, ConversationHandler
import psycopg2
import easyocr
from pdf2image import convert_from_path

TOKEN = "7904637967:AAFS7tS0Ca1cDyKEtwW_Of42vS8igVuIMhI"
VIDEO_PATH = "BAACAgIAAxkBAAM_aAZoOSAXaE6YIs8eAoD7Qe9J3A0AAiVyAAIFXjBIHKmqjEg9rEg2BA"

reader = easyocr.Reader(['ru', 'en'])

DATA_FILE = "used_data.json"
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({"users": [], "checks": []}, f)

# Логирование қосу
logging.basicConfig(level=logging.DEBUG)

def load_data():
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

# PostgreSQL деректер базасына қосылу функциясы
def get_db_connection():
    conn = psycopg2.connect(
        dbname="participants_db", 
        user="postgres", 
        password="adminpassword", 
        host="localhost", 
        port="5432"
    )
    return conn

def validate_text(text, user_id):
    if " 1 000т " and "алинур и." in text:
        return True, ""
    else:
        return False, "❌ Төлем туралы ақпарат табылмады. Чекті тексеріңіз."

# Пайдаланушының аты-жөнін енгізу
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    greeting_text = (
        "Сәлем! \n"
        "Сені өз ортамызда көргенімізге қуаныштымыз! 🔥\n\n"
        "Көктемдік көңіл күй сыйлайтын *KBTU* киносын көріп қана қоймай, төмендегі сыйлықтарды алуға мүмкіндігің бар👇🏻\n\n"
        "1. *БАСТЫ СЫЙЛЫҚ:* Mersides автокөлігі 🚀\n"
        "2. *Сіз қалайтын* IPhone 16 😍\n"
        "3. *Кез-келген үйде болуы тиіс* PlayStation 🎮\n"
        "4. *Сұлу қыздарға арналған* Dyson 💅🏻\n"
        "5. *500 000₸ ақшалай сыйақы* 💸\n\n"
        "🎬 *KBTU* киносын көру үшін, алдымен өз атыңды енгізіп тіркел!\n\n"
        "_Мысалы: Жанқожа Қанат_"
    )

    # Inline клавишаларын жасау
    keyboard = [
        [InlineKeyboardButton("🎟️ Билеттерімді көру", callback_data='show_ticket')]  # Кнопка мен оның callback_data
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(greeting_text, parse_mode="Markdown", reply_markup=reply_markup)
    logging.debug(f"User {update.message.from_user.id} started the process.")
    return "NAME_INPUT"

# Пайдаланушының аты-жөнін өңдеу
# Пайдаланушының аты-жөнін өңдеу
async def process_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    full_name = update.message.text.strip()

    if len(full_name.split()) < 2:
        await update.message.reply_text("❌ Атыңыз бен жөніңізді толық енгізіңіз. Мысалы: 'Жанқожа Қанат'. Қайта енгізіңіз.")
        return "NAME_INPUT"

    # Деректер базасына сақтау
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('INSERT INTO participants (full_name, telegram_id) VALUES (%s, %s) RETURNING id',
                    (full_name, update.message.from_user.id))
        participant_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"Database error: {e}")
        await update.message.reply_text("❌ Деректер базасына қосыла алмадық. Қайтадан әрекет етіңіз.")
        return "NAME_INPUT"

    await update.message.reply_text(f"✅ Атыңыз бен жөніңіз сақталды!")

    # 🎟️ Номероктарым кнопкасы бар сообщение
    keyboard = [
        [InlineKeyboardButton("🎟️ Номероктарым", callback_data='show_ticket')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Билеттеріңіз дайын! Төмендегі кнопканы басыңыз:", reply_markup=reply_markup)

    # Төлем жөнінде нұсқаулық
    instruction_text = (
        "⚙️ *Инструкция:*\n\n"
        "⚠️ Мұнда міндетті түрде *1000 теңге* төлену керек. "
        "Басқа сумма төлеп қойсаңыз, бот оқымайды және ақшаңыз қайтпайды. Қатесіз төлеңіз!\n\n"
        "1. Төлем жасап болған соң *чекті PDF файл* арқылы жіберіңіз (төмендегідей)\n"
        "2. *Төленетін сумма тек 1000 теңге болуы керек*\n"
        "3. Төлем расталғаннан кейін бот сізге *билет нөміріңіз бен киноны* жібереді\n\n"
        "💳 *Kaspi Gold:* `4400 4301 1234 5678`\n"
        "✅ Төлем жасап болған соң, чекті PDF немесе фото ретінде осы чатқа жіберіңіз:"
    )
    
    await update.message.reply_text(instruction_text, parse_mode="Markdown")
    return "CHECK_PROCESS"

# Чек суретін өңдеу
async def process_image(file_path, update: Update):
    await update.message.reply_text("🕐 Чек тексерілуде... Бұл бірнеше минутқа созылуы мүмкін. Өтініш, күте тұрыңыз 🙏")

    # Чек мәтінін тану
    result = reader.readtext(file_path, detail=0)
    text = " ".join(result).lower()

    logging.debug(f"Text recognized: {text}")

    is_valid, error = validate_text(text, update.message.from_user.id)

    if is_valid:
        # Төлем расталған кезде кино жіберу
        await update.message.reply_text("✅ Төлем расталды! Міне, сіздің кино 🎬:")
        await update.message.reply_video(video=VIDEO_PATH)
        logging.debug(f"User {update.message.from_user.id} received the video.")
    else:
        await update.message.reply_text(error)
        logging.debug(f"User {update.message.from_user.id} failed validation with error: {error}")

# Чек PDF файлының өңделуі
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file()
    file_path = f"{update.message.from_user.id}_check.pdf"
    await file.download_to_drive(file_path)

    images = convert_from_path(file_path, dpi=300)
    image_path = file_path.replace(".pdf", ".jpg")
    images[0].save(image_path, "JPEG")

    await process_image(image_path, update)

    os.remove(file_path)
    os.remove(image_path)

# Чек суретін өңдеу
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_path = f"{update.message.from_user.id}_check.jpg"
    await file.download_to_drive(file_path)

    await process_image(file_path, update)

    os.remove(file_path)

# Билетті көру функциясы
from telegram.ext import CallbackQueryHandler

async def show_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT id, full_name FROM participants WHERE telegram_id = %s', (user_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()

        if row:
            await query.answer()
            await query.message.reply_text(
                f"🎟️ Сіздің билет нөміріңіз: {row[0]}\n👤 Есіміңіз: {row[1]}"
            )
        else:
            await query.answer()
            await query.message.reply_text("❗ Сіз тіркелмегенсіз немесе төлем жасамағансыз.")
    except Exception as e:
        logging.error(f"DB error: {e}")
        await query.answer()
        await query.message.reply_text("🔌 Қате орын алды. Кейінірек қайталап көріңіз.")

# Ботты іске қосу
app = ApplicationBuilder().token(TOKEN).build()

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        "NAME_INPUT": [MessageHandler(filters.TEXT & ~filters.COMMAND, process_name)],
        "CHECK_PROCESS": [MessageHandler(filters.Document.PDF, handle_document),
                          MessageHandler(filters.PHOTO, handle_photo)],
    },
    fallbacks=[],
)

app.add_handler(CommandHandler("ticket", show_ticket))
app.add_handler(conv_handler)
app.add_handler(CallbackQueryHandler(show_ticket, pattern='show_ticket'))


print("🤖 Бот жұмыс істеуде...")
app.run_polling()
