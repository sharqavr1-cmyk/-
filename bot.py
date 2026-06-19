import asyncio
import os
from pyrogram import Client, filters
from pyrogram.types import ReplyKeyboardMarkup
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat  
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
whitelisted_users = set()  
processing_users = set()  

# ================= روابط الإذاعات =================
STATIONS = {
    "إذاعة محمد المنشاوي": "https://backup.qurango.net/radio/mohammed_siddiq_alminshawi",
    "إذاعة عبدالباسط": "https://backup.qurango.net/radio/abdulbasit_abdulsamad_mojawwad",
    "إذاعة العجمي": "https://backup.qurango.net/radio/ahmad_alajmy",
    "إذاعة ياسر الدوسري": "https://backup.qurango.net/radio/yasser_aldosari",
    "إذاعة سعد الغامدي": "https://backup.qurango.net/radio/saad_alghamidi",
    "إذاعة عبدالرحمن السديس": "https://backup.qurango.net/radio/abdulrahman_alsudaes",
    "إذاعة ماهر المعيقلي": "https://backup.qurango.net/radio/maher_almuaiqly",
    "إذاعة فارس عباد": "https://backup.qurango.net/radio/fares_abbad",
    "إذاعة محمود الحصري": "https://backup.qurango.net/radio/mahmoud_khalil_alhussary",
    "إذاعة مشاري العفاسي": "https://backup.qurango.net/radio/mishary_alafasi"
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
        ["إضافة حساب مساعد", "حذف حساب مساعد"],
        ["زود", "نقص"]
    ], 
    resize_keyboard=True
)

stations_kb = ReplyKeyboardMarkup(
    [
        ["إذاعة محمد المنشاوي", "إذاعة عبدالباسط"],
        ["إذاعة العجمي", "إذاعة ياسر الدوسري"],
        ["إذاعة سعد الغامدي", "إذاعة عبدالرحمن السديس"],
        ["إذاعة ماهر المعيقلي", "إذاعة فارس عباد"],
        ["إذاعة محمود الحصري", "إذاعة مشاري العفاسي"],
        ["رجوع"]
    ],
    resize_keyboard=True
)

back_kb = ReplyKeyboardMarkup([["رجوع"]], resize_keyboard=True)

# ================= مراقب المكالمات الصوتية (العودة التلقائية) =================
async def vc_service_handler(event):
    global call_py
    if not call_py:
        return
    
    if getattr(event.message, 'action', None) and type(event.message.action).__name__ == "MessageActionGroupCall":
        c_id = event.chat_id
        
        for active_id, info in list(active_streams.items()):
            if str(abs(active_id)) == str(abs(c_id)):
                await asyncio.sleep(3) 
                try:
                    try:
                        await call_py.leave_call(active_id)
                        await asyncio.sleep(1)
                    except:
                        pass
                    
                    stream_url = STATIONS.get(info["station"])
                    await call_py.play(active_id, MediaStream(stream_url))
                except Exception:
                    pass

# ================= الموجه الرئيسي للنصوص والأزرار =================
@app.on_message(filters.text & filters.private)
async def main_router(client, message):
    global assistant_client, call_py, assistant_session_string, whitelisted_users, processing_users
    
    user_id = message.from_user.id
    
    if user_id in processing_users:
        return
    
    processing_users.add(user_id)
    
    try:
        text = message.text
        is_admin = (user_id == ADMIN_ID)
        kb = admin_kb if is_admin else user_kb
        
        if text == "رجوع":
            user_steps.pop(user_id, None)
            await message.reply("✅ تم التراجع والعودة للقائمة الرئيسية.", reply_markup=kb)
            return

        step_data = user_steps.get(user_id)

        # 1. حالة انتظار جلسة الحساب المساعد
        if step_data == "WAITING_FOR_SESSION" and is_admin:
            wait_msg = await message.reply("⏳ جاري فحص الجلسة والاتصال...")
            try:
                assistant_session_string = text
                assistant_client = TelegramClient(StringSession(assistant_session_string), API_ID, API_HASH)
                await assistant_client.connect()
                
                if not await assistant_client.is_user_authorized():
                    await wait_msg.delete()
                    await message.reply("❌ الجلسة غير صالحة أو منتهية. يرجى استخراج جلسة جديدة وإضافتها.", reply_markup=kb)
                    await assistant_client.disconnect()
                    assistant_client = None
                    user_steps.pop(user_id, None)
                    return
                
                # تفعيل مراقب المكالمات بالطريقة الصحيحة
                assistant_client.add_event_handler(vc_service_handler, events.NewMessage())
                
                call_py = PyTgCalls(assistant_client)
                await call_py.start()
                
                user_steps.pop(user_id, None)
                await wait_msg.delete()
                await message.reply("✅ تم تفعيل الحساب المساعد وربطه بنجاح. البوت جاهز الآن للعمل!", reply_markup=kb)
            except Exception as e:
                await wait_msg.delete()
                await message.reply(f"❌ حدث خطأ أثناء تشغيل الجلسة:\n`{e}`", reply_markup=kb)
                if assistant_client:
                    await assistant_client.disconnect()
                    assistant_client = None
                user_steps.pop(user_id, None)
            return

        # 2. حالة انتظار أيدي لتزويد صلاحياته
        if step_data == "WAITING_FOR_WHITELIST_ID" and is_admin:
            try:
                target_id = int(text.strip())
                whitelisted_users.add(target_id)
                user_steps.pop(user_id, None)
                await message.reply(f"✅ تم بنجاح إضافة المستخدم `{target_id}` إلى قائمة الصلاحيات. يمكنه الآن تشغيل أي عدد من البثوث!", reply_markup=kb)
            except ValueError:
                await message.reply("❌ عذراً، يجب إرسال الأيدي كـ أرقام فقط! أعد إرساله بشكل صحيح أو اضغط 'رجوع':", reply_markup=back_kb)
            return

        # 3. حالة انتظار أيدي لحذف صلاحياته
        if step_data == "WAITING_FOR_UNWHITELIST_ID" and is_admin:
            try:
                target_id = int(text.strip())
                if target_id in whitelisted_users:
                    whitelisted_users.remove(target_id)
                    await message.reply(f"✅ تم بنجاح إزالة المستخدم `{target_id}` من قائمة الصلاحيات وعاد للحد الطبيعي.", reply_markup=kb)
                else:
                    await message.reply("⚠️ هذا الأيدي ليس موجوداً في قائمة الصلاحيات من الأساس.", reply_markup=kb)
                user_steps.pop(user_id, None)
            except ValueError:
                await message.reply("❌ عذراً، يجب إرسال الأيدي كـ أرقام فقط! أعد إرساله بشكل صحيح أو اضغط 'رجوع':", reply_markup=back_kb)
            return

        # 4. حالة انتظار رابط القناة/الجروب
        if step_data == "WAITING_FOR_CHAT_ID":
            user_steps[user_id] = {"step": "WAITING_FOR_STATION", "chat_input": text}
            await message.reply(f"✅ تم حفظ الرابط بنجاح.\nالآن اختر الإذاعة التي تريد تشغيلها في الكول:", reply_markup=stations_kb)
            return

        # 5. حالة انتظار اختيار الإذاعة وتجهيز البث
        if isinstance(step_data, dict) and step_data.get("step") == "WAITING_FOR_STATION":
            station_name = text
            original_link = step_data["chat_input"].strip()
            stream_url = STATIONS.get(station_name)
            
            if not stream_url:
                await message.reply("❌ الرجاء اختيار إذاعة صحيحة من الأزرار أو اضغط 'رجوع'.")
                return
            
            wait_msg = await message.reply("⏳ جاري الانضمام وفحص المكالمة وتنشيط الصوت...")
            
            try:
                chat_input_str = original_link.replace("https://", "").replace("http://", "")
                entity = None

                try:
                    if "t.me/+" in chat_input_str or "t.me/joinchat/" in chat_input_str:
                        hash_str = chat_input_str.split("/")[-1].replace("+", "")
                        try:
                            updates = await assistant_client(ImportChatInviteRequest(hash_str))
                            entity = updates.chats[0]
                        except Exception:
                            try:
                                invite = await assistant_client(CheckChatInviteRequest(hash_str))
                                entity = invite.chat
                            except Exception:
                                pass
                    else:
                        username = chat_input_str.split("/")[-1]
                        if "?" in username:
                            username = username.split("?")[0]
                        try:
                            await assistant_client(JoinChannelRequest(username))
                        except Exception: 
                            pass
                        entity = await assistant_client.get_entity(username)
                except Exception as e:
                    await wait_msg.delete()
                    await message.reply(f"❌ لم يتمكن الحساب المساعد من دخول الجروب عبر الرابط المرسل.\nالسبب: `{e}`", reply_markup=kb)
                    user_steps.pop(user_id, None)
                    return

                if not entity:
                    await wait_msg.delete()
                    await message.reply("❌ لم يتم التعرف على الرابط أو الجروب بشكل صحيح. تأكد من صحة الرابط.", reply_markup=kb)
                    user_steps.pop(user_id, None)
                    return

                chat_title = getattr(entity, 'title', 'غير معروف')

                if isinstance(entity, Channel):
                    actual_chat_id = int(f"-100{entity.id}")
                elif isinstance(entity, Chat):
                    actual_chat_id = -entity.id
                else:
                    actual_chat_id = entity.id

                try:
                    try:
                        await call_py.leave_call(actual_chat_id)
                        await asyncio.sleep(0.5)
                    except:
                        pass

                    await call_py.play(actual_chat_id, MediaStream(stream_url))
                    
                    active_streams[actual_chat_id] = {
                        "user_id": user_id, 
                        "station": station_name,
                        "link": original_link
                    }
                    
                    await wait_msg.delete()
                    await message.reply(f"✅ تم بدء بث **{station_name}** بنجاح عبر حساب المساعد.", reply_markup=kb)
                    
                    # إرسال إشعار للمطور
                    if user_id != ADMIN_ID:
                        user_name = message.from_user.first_name or 'مستخدم'
                        user_mention = f"[{user_name}](tg://user?id={user_id})"
                        notify_text = (
                            f"🔔 **إشعار تشغيل بث جديد**\n\n"
                            f"👤 **المستخدم:** {user_mention}\n"
                            f"📻 **الإذاعة:** **{station_name}**\n"
                            f"📌 **اسم الجروب:** {chat_title}\n"
                            f"🔗 **الرابط المدخل:** {original_link}\n"
                            f"🆔 **أيدي الجروب:** `{actual_chat_id}`"
                        )
                        try:
                            await app.send_message(ADMIN_ID, notify_text, disable_web_page_preview=True)
                        except Exception:
                            pass

                except Exception as call_error:
                    error_str = str(call_error)
                    await wait_msg.delete()
                    if "CreateGroupCallRequest" in error_str or "privileges are required" in error_str or "GroupCallNotFound" in error_str:
                        await message.reply("❌ المكالمة مقفولة! يرجى فتح المكالمة الصوتية (الكول) في الجروب أولاً ثم أعد المحاولة لتشغيل البث.", reply_markup=kb)
                    else:
                        await message.reply(f"❌ حدث خطأ أثناء تشغيل البث:\n`{call_error}`", reply_markup=kb)

                user_steps.pop(user_id, None)

            except Exception as e:
                await wait_msg.delete()
                await message.reply(f"❌ حدث خطأ عام:\n`{e}`", reply_markup=kb)
                user_steps.pop(user_id, None)
            return

        # 6. حالة انتظار لتحديد القناة لإيقافها
        if step_data == "WAITING_FOR_STOP_CHAT_ID":
            chat_input_str = text.strip()
            user_chats = {c_id: info for c_id, info in active_streams.items() if info["user_id"] == user_id}
            
            target_chat_id = None
            for c_id in user_chats.keys():
                if str(c_id) == chat_input_str or chat_input_str in str(c_id):
                    target_chat_id = c_id
                    break
            
            if target_chat_id:
                try:
                    await call_py.leave_call(target_chat_id)
                except:
                    pass
                del active_streams[target_chat_id]
                user_steps.pop(user_id, None)
                await message.reply("✅ تم إيقاف البث في القناة المحددة بنجاح.", reply_markup=kb)
            else:
                await message.reply("❌ لم يتم العثور على بث بهذا الأيدي. تأكد من الأيدي وأرسله مجدداً أو اضغط 'رجوع'.", reply_markup=back_kb)
            return


        # ----------------- الأوامر الأساسية والأزرار -----------------
        if text == "/start":
            user_steps.pop(user_id, None)
            await message.reply("مرحباً بك في بوت الإذاعات القرآنية.\nاختر من القائمة بالأسفل لتتحكم في البث:", reply_markup=kb)

        elif text == "حالة البث":
            user_chats = {c_id: info for c_id, info in active_streams.items() if info["user_id"] == user_id}
            if user_chats:
                msg = "✅ البثوث التي قمت بتشغيلها وتعمل حالياً:\n\n"
                for c_id, info in user_chats.items():
                    link = info.get('link', 'غير متوفر')
                    msg += f"- الأيدي: `{c_id}`\n- الرابط: {link}\n- الإذاعة: **{info['station']}**\n\n"
                await message.reply(msg, reply_markup=kb, disable_web_page_preview=True)
            else:
                await message.reply("❌ لا يوجد لديك أي بث شغال حالياً.", reply_markup=kb)

        elif text == "بدء البث":
            user_stream_count = sum(1 for info in active_streams.values() if info["user_id"] == user_id)
            if not is_admin and user_id not in whitelisted_users and user_stream_count >= 1:
                await message.reply("⚠️ عذراً، مسموح للمستخدمين بتشغيل بث واحد فقط في نفس الوقت. قم بإيقاف البث الحالي أولاً.", reply_markup=kb)
                return
            
            if not call_py:
                await message.reply("❌ البوت غير جاهز! يجب على المطور إضافة حساب مساعد أولاً.", reply_markup=kb)
                return

            user_steps[user_id] = "WAITING_FOR_CHAT_ID"
            await message.reply("يرجى إرسال رابط الجروب أو القناة الآن لتشغيل البث فيه:\n(اضغط 'رجوع' للإلغاء)", reply_markup=back_kb)

        elif text == "إيقاف البث":
            user_chats = [c_id for c_id, info in active_streams.items() if info["user_id"] == user_id]
            
            if not user_chats:
                await message.reply("❌ ليس لديك أي بث شغال لإيقافه.", reply_markup=kb)
                return
            
            if len(user_chats) == 1:
                chat_to_stop = user_chats[0]
                try:
                    await call_py.leave_call(chat_to_stop)
                except:
                    pass
                del active_streams[chat_to_stop]
                await message.reply("✅ تم إيقاف البث ومغادرة المكالمة بنجاح.", reply_markup=kb)
            else:
                user_steps[user_id] = "WAITING_FOR_STOP_CHAT_ID"
                msg = "أنت تقوم بتشغيل أكثر من بث حالياً.\nإليك القنوات التي تعمل:\n"
                for c in user_chats:
                    msg += f"- `{c}`\n"
                msg += "\nيرجى إرسال أيدي القناة التي تريد إيقاف البث فيها:\n(أو اضغط 'رجوع' للإلغاء)"
                await message.reply(msg, reply_markup=back_kb)


        # ----------------- أوامر التحكم الخاصة بالمطور فقط -----------------
        elif is_admin:
            if text == "زود":
                user_steps[user_id] = "WAITING_FOR_WHITELIST_ID"
                await message.reply("يرجى إرسال أيدي (ID) الشخص الذي تريد السماح له بتشغيل بثوث متعددة بدون قيود:\n(اضغط 'رجوع' للتراجع عن العملية)", reply_markup=back_kb)

            elif text == "نقص":
                user_steps[user_id] = "WAITING_FOR_UNWHITELIST_ID"
                await message.reply("يرجى إرسال أيدي (ID) الشخص الذي تريد سحب الصلاحيات الإضافية منه:\n(اضغط 'رجوع' للتراجع عن العملية)", reply_markup=back_kb)

            elif text == "إحصائيات":
                count = len(active_streams)
                await message.reply(f"📊 إحصائيات البوت:\n- إجمالي البثوث الشغالة حالياً في كل القنوات: **{count}** بث\n- عدد المستخدمين المستثنين المسموح لهم ببثوث متعددة: **{len(whitelisted_users)}**", reply_markup=kb)

            elif text == "إضافة حساب مساعد":
                user_steps[user_id] = "WAITING_FOR_SESSION"
                await message.reply("يرجى إرسال كود الجلسة (String Session) الخاص بتليثون الآن:\n(اضغط 'رجوع' للإلغاء)", reply_markup=back_kb)

            elif text == "إيقاف البثوث الشغالة":
                if not active_streams:
                    await message.reply("❌ لا يوجد أي بث شغال حالياً لإيقافه.", reply_markup=kb)
                    return
                for c_id, info in list(active_streams.items()):
                    try:
                        await call_py.leave_call(c_id)
                    except:
                        pass
                    paused_streams[c_id] = info
                active_streams.clear()
                await message.reply("✅ تم إيقاف جميع البثوث النشطة مؤقتاً وحفظ شيوخ الإذاعات لإعادة تشغيلها لاحقاً.", reply_markup=kb)

            elif text == "تشغيل البثوث":
                if not paused_streams:
                    await message.reply("❌ لا توجد بثوث متوقفة لإعادة تشغيلها.", reply_markup=kb)
                    return
                
                success_count = 0
                wait_reply = await message.reply("⏳ جاري تنشيط الاتصال الفريش وإعادة تشغيل البثوث بصوت شيوخها...")
                
                for c_id, info in list(paused_streams.items()):
                    try:
                        try:
                            await call_py.leave_call(c_id)
                            await asyncio.sleep(0.5)
                        except:
                            pass
                            
                        stream_url = STATIONS.get(info["station"])
                        await call_py.play(c_id, MediaStream(stream_url))
                        active_streams[c_id] = info
                        success_count += 1
                    except:
                        pass
                paused_streams.clear()
                await wait_reply.edit_text(f"✅ تم بنجاح إعادة تشغيل ({success_count}) بث بالكامل بصوت نفس القراء وبأعلى استقرار للصوت بدون أي تعليق!", reply_markup=kb)

            elif text == "حذف حساب مساعد":
                if call_py:
                    for c_id, info in list(active_streams.items()):
                        try:
                            await call_py.leave_call(c_id)
                        except:
                            pass
                    active_streams.clear()
                    
                    try:
                        assistant_client.remove_event_handler(vc_service_handler)
                    except:
                        pass
                        
                    await assistant_client.disconnect()
                    assistant_client = None
                    call_py = None
                    assistant_session_string = None
                    await message.reply("✅ تم إيقاف كافة البثوث، وتسجيل الخروج، وحذف الحساب المساعد بنجاح.", reply_markup=kb)
                else:
                    await message.reply("❌ لا يوجد حساب مساعد مسجل حالياً لحذفه.", reply_markup=kb)

    finally:
        processing_users.discard(user_id)

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
