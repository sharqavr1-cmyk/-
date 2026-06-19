import asyncio
import os
from pyrogram import Client, filters
from pyrogram.types import ReplyKeyboardMarkup, KeyboardButton
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream
from telethon import TelegramClient
from telethon.sessions import StringSession

# ================= إعدادات البوت من متغيرات البيئة =================
# نستخدم int() مع الـ IDs لأن مكتبة os بتسترجع البيانات كنصوص (Strings)
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))

# ================= المتغيرات العامة =================
app = Client("quran_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

assistant_client = None
call_py = None
assistant_session_string = None

# ... (باقي الكود كما هو بالظبط بدون أي تغيير) ...
# قواميس لتتبع الحالة والبثوث (تخزين مؤقت)
active_streams = {}   # {user_id: {"chat_id": 123, "station": "المنشاوي"}}
paused_streams = {}   # لتخزين البثوث التي تم إيقافها برمجياً لإعادة تشغيلها
user_steps = {}       # لتتبع خطوات المستخدم (مثل انتظار أيدي القناة أو الجلسة)

# روابط إذاعات حقيقية ومباشرة (لا يتم تحميلها)
STATIONS = {
    "إذاعة محمد المنشاوي": "https://backup.qurango.net/radio/mohammed_siddiq_alminshawi",
    "إذاعة عبدالباسط": "https://backup.qurango.net/radio/abdulbasit_abdulsamad_mojawwad",
    "إذاعة العجمي": "https://backup.qurango.net/radio/ahmad_alajmy",
    "إذاعة ياسر الدوسري": "https://backup.qurango.net/radio/yasser_aldosari"
}

# ================= لوحات المفاتيح =================
user_kb = ReplyKeyboardMarkup(
    [["بدء البث", "حالة البث"], ["إيقاف البث"]], 
    resize_keyboard=True
)

admin_kb = ReplyKeyboardMarkup(
    [
        ["بدء البث", "حالة البث"],
        ["إيقاف البث", "إحصائيات"],
        ["إيقاف البثوث الشغالة", "تشغيل البثوث"],
        ["إضافة حساب مساعد", "حذف حساب مساعد"]
    ], 
    resize_keyboard=True
)

stations_kb = ReplyKeyboardMarkup(
    [
        ["إذاعة محمد المنشاوي", "إذاعة عبدالباسط"],
        ["إذاعة العجمي", "إذاعة ياسر الدوسري"],
        ["إلغاء"]
    ],
    resize_keyboard=True
)

# ================= دوال التحكم =================

@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    user_steps.pop(message.from_user.id, None)
    kb = admin_kb if message.from_user.id == ADMIN_ID else user_kb
    await message.reply("مرحباً بك في بوت الإذاعات القرآنية.\nاختر من القائمة بالأسفل:", reply_markup=kb)

@app.on_message(filters.regex("^حالة البث$") & filters.private)
async def stream_status(client, message):
    user_id = message.from_user.id
    if user_id in active_streams:
        info = active_streams[user_id]
        await message.reply(f"✅ لديك بث شغال حالياً:\n- القناة: `{info['chat_id']}`\n- الإذاعة: {info['station']}")
    else:
        await message.reply("❌ لا يوجد لديك أي بث شغال حالياً.")

@app.on_message(filters.regex("^بدء البث$") & filters.private)
async def start_stream_request(client, message):
    user_id = message.from_user.id
    if user_id in active_streams:
        await message.reply("⚠️ لا يمكنك تشغيل أكثر من بث واحد في نفس الوقت. قم بإيقاف البث الحالي أولاً.")
        return
    
    if not call_py:
        await message.reply("❌ لم يتم إضافة حساب مساعد من قبل المطور بعد.")
        return

    user_steps[user_id] = "WAITING_FOR_CHAT_ID"
    await message.reply("يرجى إرسال أيدي (ID) القناة التي تريد تشغيل البث فيها:")

@app.on_message(filters.regex("^-?\d+$") & filters.private)
async def receive_chat_id(client, message):
    user_id = message.from_user.id
    if user_steps.get(user_id) == "WAITING_FOR_CHAT_ID":
        try:
            chat_id = int(message.text)
            user_steps[user_id] = {"step": "WAITING_FOR_STATION", "chat_id": chat_id}
            await message.reply(f"تم حفظ القناة: `{chat_id}`\nالآن اختر الإذاعة:", reply_markup=stations_kb)
        except ValueError:
            await message.reply("أيدي القناة غير صالح، تأكد من كتابة الأرقام فقط.")

@app.on_message(filters.regex("^إذاعة") & filters.private)
async def play_station(client, message):
    user_id = message.from_user.id
    step_data = user_steps.get(user_id)
    
    if isinstance(step_data, dict) and step_data.get("step") == "WAITING_FOR_STATION":
        station_name = message.text
        chat_id = step_data["chat_id"]
        stream_url = STATIONS.get(station_name)
        
        if not stream_url:
            return
        
        try:
            # تشغيل البث مباشرة من الرابط دون تحميل (MediaStream)
            await call_py.join_group_call(chat_id, MediaStream(stream_url))
            active_streams[user_id] = {"chat_id": chat_id, "station": station_name}
            
            kb = admin_kb if user_id == ADMIN_ID else user_kb
            await message.reply(f"✅ تم بدء بث **{station_name}** بنجاح في القناة المحددة.", reply_markup=kb)
            user_steps.pop(user_id, None)
        except Exception as e:
            await message.reply(f"❌ حدث خطأ أثناء تشغيل البث (تأكد أن البوت مشرف وأن المكالمة مفتوحة):\n`{e}`")

@app.on_message(filters.regex("^إيقاف البث$") & filters.private)
async def stop_user_stream(client, message):
    user_id = message.from_user.id
    if user_id in active_streams:
        chat_id = active_streams[user_id]["chat_id"]
        try:
            await call_py.leave_group_call(chat_id)
        except:
            pass
        del active_streams[user_id]
        await message.reply("تم إيقاف البث الخاص بك بنجاح.")
    else:
        await message.reply("ليس لديك بث لإيقافه.")

@app.on_message(filters.regex("^إلغاء$") & filters.private)
async def cancel_action(client, message):
    user_id = message.from_user.id
    user_steps.pop(user_id, None)
    kb = admin_kb if user_id == ADMIN_ID else user_kb
    await message.reply("تم الإلغاء.", reply_markup=kb)

# ================= أوامر المطور =================

@app.on_message(filters.regex("^إحصائيات$") & filters.user(ADMIN_ID) & filters.private)
async def show_stats(client, message):
    count = len(active_streams)
    await message.reply(f"📊 عدد القنوات التي يعمل فيها البث حالياً: **{count}**")

@app.on_message(filters.regex("^إضافة حساب مساعد$") & filters.user(ADMIN_ID) & filters.private)
async def ask_for_session(client, message):
    user_steps[ADMIN_ID] = "WAITING_FOR_SESSION"
    await message.reply("أرسل جلسة تليثون (String Session) الآن:")

@app.on_message(filters.text & filters.user(ADMIN_ID) & filters.private)
async def handle_admin_text(client, message):
    global assistant_client, call_py, assistant_session_string
    
    text = message.text
    
    # معالجة إضافة الجلسة
    if user_steps.get(ADMIN_ID) == "WAITING_FOR_SESSION":
        try:
            assistant_session_string = text
            assistant_client = TelegramClient(StringSession(assistant_session_string), API_ID, API_HASH)
            await assistant_client.start()
            
            call_py = PyTgCalls(assistant_client)
            await call_py.start()
            
            user_steps.pop(ADMIN_ID, None)
            await message.reply("✅ تم تشغيل الحساب المساعد وربطه بنجاح.")
        except Exception as e:
            await message.reply(f"❌ الجلسة غير صالحة أو حدث خطأ:\n`{e}`")
        return

    # إيقاف جميع البثوث
    if text == "إيقاف البثوث الشغالة":
        for uid, info in list(active_streams.items()):
            try:
                await call_py.leave_group_call(info["chat_id"])
            except:
                pass
            paused_streams[uid] = info
        active_streams.clear()
        await message.reply("تم إيقاف جميع البثوث النشطة وحفظها لإعادة التشغيل لاحقاً.")

    # تشغيل البثوث المتوقفة
    elif text == "تشغيل البثوث":
        if not paused_streams:
            await message.reply("لا توجد بثوث متوقفة لإعادة تشغيلها.")
            return
        
        for uid, info in list(paused_streams.items()):
            try:
                stream_url = STATIONS.get(info["station"])
                await call_py.join_group_call(info["chat_id"], MediaStream(stream_url))
                active_streams[uid] = info
            except:
                pass
        paused_streams.clear()
        await message.reply("تم إعادة تشغيل البثوث المتوقفة بنجاح.")

    # حذف الحساب المساعد
    elif text == "حذف حساب مساعد":
        if call_py:
            # إيقاف كل شيء أولاً
            for uid, info in list(active_streams.items()):
                try:
                    await call_py.leave_group_call(info["chat_id"])
                except:
                    pass
            active_streams.clear()
            
            await assistant_client.disconnect()
            assistant_client = None
            call_py = None
            assistant_session_string = None
            await message.reply("تم إيقاف وحذف الحساب المساعد وتوقيف كافة البثوث.")
        else:
            await message.reply("لا يوجد حساب مساعد مضاف حالياً.")

# ================= التشغيل الأساسي =================
async def main():
    print("جاري تشغيل البوت...")
    await app.start()
    print("البوت يعمل الآن! في انتظار الأوامر...")
    # إبقاء البوت يعمل
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
