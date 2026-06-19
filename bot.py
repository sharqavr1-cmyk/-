import asyncio
import os
from pyrogram import Client, filters
from pyrogram.types import ReplyKeyboardMarkup
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest

# ================= إعدادات البوت من متغيرات البيئة =================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))

# ================= المتغيرات العامة =================
app = Client("quran_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

assistant_client = None
call_py = None
assistant_session_string = None

active_streams = {}   
paused_streams = {}   
user_steps = {}       

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

# ================= الموجه الرئيسي للنصوص والأزرار =================
@app.on_message(filters.text & filters.private)
async def main_router(client, message):
    global assistant_client, call_py, assistant_session_string
    
    text = message.text
    user_id = message.from_user.id
    is_admin = (user_id == ADMIN_ID)
    
    # لوحة المفاتيح الافتراضية للمستخدم الحالي
    kb = admin_kb if is_admin else user_kb

    # ----------------- فحص حالة المستخدم (State Machine) -----------------
    step_data = user_steps.get(user_id)

    # 1. حالة انتظار جلسة الحساب المساعد
    if step_data == "WAITING_FOR_SESSION" and is_admin:
        wait_msg = await message.reply("⏳ جاري فحص الجلسة والاتصال...")
        try:
            assistant_session_string = text
            # نستخدم connect بدلاً من start لتجنب تجميد البوت إذا كانت الجلسة خاطئة
            assistant_client = TelegramClient(StringSession(assistant_session_string), API_ID, API_HASH)
            await assistant_client.connect()
            
            if not await assistant_client.is_user_authorized():
                await wait_msg.edit_text("❌ الجلسة غير صالحة أو منتهية. يرجى استخراج جلسة جديدة وإضافتها.", reply_markup=kb)
                await assistant_client.disconnect()
                assistant_client = None
                user_steps.pop(user_id, None)
                return
            
            call_py = PyTgCalls(assistant_client)
            await call_py.start()
            
            user_steps.pop(user_id, None)
            await wait_msg.edit_text("✅ تم تفعيل الحساب المساعد وربطه بنجاح. البوت جاهز الآن للعمل!", reply_markup=kb)
        except Exception as e:
            await wait_msg.edit_text(f"❌ حدث خطأ أثناء تشغيل الجلسة:\n`{e}`", reply_markup=kb)
            if assistant_client:
                await assistant_client.disconnect()
                assistant_client = None
            user_steps.pop(user_id, None)
        return

    # 2. حالة انتظار أيدي أو رابط القناة
    if step_data == "WAITING_FOR_CHAT_ID":
        if text == "إلغاء":
            user_steps.pop(user_id, None)
            await message.reply("✅ تم الإلغاء.", reply_markup=kb)
            return
        
        user_steps[user_id] = {"step": "WAITING_FOR_STATION", "chat_input": text}
        await message.reply(f"✅ تم حفظ القناة/الجروب: `{text}`\nالآن اختر الإذاعة التي تريد تشغيلها:", reply_markup=stations_kb)
        return

    # 3. حالة انتظار اختيار الإذاعة
    if isinstance(step_data, dict) and step_data.get("step") == "WAITING_FOR_STATION":
        if text == "إلغاء":
            user_steps.pop(user_id, None)
            await message.reply("✅ تم الإلغاء.", reply_markup=kb)
            return
            
        station_name = text
        chat_input = step_data["chat_input"]
        stream_url = STATIONS.get(station_name)
        
        if not stream_url:
            await message.reply("❌ الرجاء اختيار إذاعة صحيحة من الأزرار أو اضغط 'إلغاء'.")
            return
        
        wait_msg = await message.reply("⏳ جاري دخول الحساب المساعد وتجهيز البث...")
        
        try:
            chat_input_str = str(chat_input).strip()
            actual_chat_id = None

            # معالجة المدخلات (رقم، يوزرنيم، أو رابط) والانضمام
            try:
                if chat_input_str.lstrip("-").isdigit():
                    chat_to_resolve = int(chat_input_str)
                    entity = await assistant_client.get_entity(chat_to_resolve)
                    actual_chat_id = entity.id
                elif "t.me/+" in chat_input_str or "t.me/joinchat/" in chat_input_str:
                    hash_str = chat_input_str.split("/")[-1].replace("+", "")
                    try:
                        updates = await assistant_client(ImportChatInviteRequest(hash_str))
                        actual_chat_id = updates.chats[0].id
                    except Exception:
                        invite = await assistant_client(CheckChatInviteRequest(hash_str))
                        actual_chat_id = invite.chat.id
                else:
                    username = chat_input_str.split("/")[-1] if "t.me/" in chat_input_str else chat_input_str
                    try:
                        await assistant_client(JoinChannelRequest(username))
                    except Exception: 
                        pass
                    entity = await assistant_client.get_entity(username)
                    actual_chat_id = entity.id
            except Exception as e:
                await wait_msg.edit_text(f"❌ لم يتمكن الحساب المساعد من الانضمام أو العثور على القناة.\nالسبب: `{e}`", reply_markup=kb)
                user_steps.pop(user_id, None)
                return

            if not actual_chat_id:
                await wait_msg.edit_text("❌ لم يتمكن الحساب المساعد من التعرف على القناة. تأكد من الرابط أو المعرف.", reply_markup=kb)
                user_steps.pop(user_id, None)
                return

            await call_py.play(actual_chat_id, MediaStream(stream_url))
            active_streams[user_id] = {"chat_id": actual_chat_id, "station": station_name}
            
            await wait_msg.edit_text(f"✅ تم بدء بث **{station_name}** بنجاح في القناة المحددة.", reply_markup=kb)
            user_steps.pop(user_id, None)

        except Exception as e:
            await wait_msg.edit_text(f"❌ حدث خطأ أثناء تشغيل البث:\n`{e}`", reply_markup=kb)
            user_steps.pop(user_id, None)
        return

    # ----------------- الأوامر الأساسية والأزرار -----------------
    if text == "/start":
        user_steps.pop(user_id, None)
        await message.reply("مرحباً بك في بوت الإذاعات القرآنية.\nاختر من القائمة بالأسفل لتتحكم في البث:", reply_markup=kb)

    elif text == "حالة البث":
        if user_id in active_streams:
            info = active_streams[user_id]
            await message.reply(f"✅ لديك بث شغال حالياً:\n- القناة: `{info['chat_id']}`\n- الإذاعة: {info['station']}", reply_markup=kb)
        else:
            await message.reply("❌ لا يوجد لديك أي بث شغال حالياً.", reply_markup=kb)

    elif text == "بدء البث":
        if user_id in active_streams:
            await message.reply("⚠️ لا يمكنك تشغيل أكثر من بث واحد في نفس الوقت. قم بإيقاف البث الحالي أولاً.", reply_markup=kb)
            return
        
        if not call_py:
            await message.reply("❌ البوت غير جاهز! يجب على المطور إضافة حساب مساعد أولاً من زر 'إضافة حساب مساعد'.", reply_markup=kb)
            return

        user_steps[user_id] = "WAITING_FOR_CHAT_ID"
        await message.reply("يرجى إرسال أيدي (ID)، أو معرف (اليوزرنيم)، أو رابط القناة/الجروب لتشغيل البث فيه:\n(يمكنك إرسال 'إلغاء' للتراجع)", reply_markup=ReplyKeyboardMarkup([["إلغاء"]], resize_keyboard=True))

    elif text == "إيقاف البث":
        if user_id in active_streams:
            chat_id = active_streams[user_id]["chat_id"]
            try:
                await call_py.leave_call(chat_id)
            except:
                pass
            del active_streams[user_id]
            await message.reply("✅ تم إيقاف البث ومغادرة المكالمة بنجاح.", reply_markup=kb)
        else:
            await message.reply("❌ ليس لديك أي بث شغال لإيقافه.", reply_markup=kb)

    elif text == "إلغاء":
        user_steps.pop(user_id, None)
        await message.reply("✅ تم إلغاء العملية الحالية.", reply_markup=kb)

    # ----------------- أوامر المطور فقط -----------------
    elif is_admin:
        if text == "إحصائيات":
            count = len(active_streams)
            await message.reply(f"📊 إحصائيات البوت:\n- البثوث الشغالة حالياً: **{count}**", reply_markup=kb)

        elif text == "إضافة حساب مساعد":
            user_steps[user_id] = "WAITING_FOR_SESSION"
            await message.reply("يرجى إرسال كود الجلسة (String Session) الخاص بتليثون الآن:\n(يمكنك إرسال 'إلغاء' للتراجع)", reply_markup=ReplyKeyboardMarkup([["إلغاء"]], resize_keyboard=True))

        elif text == "إيقاف البثوث الشغالة":
            if not active_streams:
                await message.reply("❌ لا يوجد أي بث شغال حالياً لإيقافه.", reply_markup=kb)
                return
            for uid, info in list(active_streams.items()):
                try:
                    await call_py.leave_call(info["chat_id"])
                except:
                    pass
                paused_streams[uid] = info
            active_streams.clear()
            await message.reply("✅ تم إيقاف جميع البثوث النشطة مؤقتاً وحفظها لإعادة التشغيل لاحقاً.", reply_markup=kb)

        elif text == "تشغيل البثوث":
            if not paused_streams:
                await message.reply("❌ لا توجد بثوث متوقفة لإعادة تشغيلها.", reply_markup=kb)
                return
            
            success_count = 0
            for uid, info in list(paused_streams.items()):
                try:
                    stream_url = STATIONS.get(info["station"])
                    await call_py.play(info["chat_id"], MediaStream(stream_url))
                    active_streams[uid] = info
                    success_count += 1
                except:
                    pass
            paused_streams.clear()
            await message.reply(f"✅ تم إعادة تشغيل ({success_count}) بث بنجاح.", reply_markup=kb)

        elif text == "حذف حساب مساعد":
            if call_py:
                for uid, info in list(active_streams.items()):
                    try:
                        await call_py.leave_call(info["chat_id"])
                    except:
                        pass
                active_streams.clear()
                
                await assistant_client.disconnect()
                assistant_client = None
                call_py = None
                assistant_session_string = None
                await message.reply("✅ تم إيقاف كافة البثوث، وتسجيل الخروج، وحذف الحساب المساعد بنجاح.", reply_markup=kb)
            else:
                await message.reply("❌ لا يوجد حساب مساعد مسجل حالياً لحذفه.", reply_markup=kb)

# ================= التشغيل الأساسي =================
async def main():
    print("جاري تشغيل البوت...")
    await app.start()
    print("البوت يعمل الآن! في انتظار الأوامر...")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
