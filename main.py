import os
import time
import asyncio
import random
import logging
import re
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from motor.motor_asyncio import AsyncIOMotorClient
from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest, InviteToChannelRequest
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.contacts import GetContactsRequest
from telethon.utils import get_peer_id
from telethon.tl.functions.phone import JoinGroupCallRequest
from telethon.tl.types import InputGroupCall, UpdateGroupCall, MessageEntityMention, MessageEntityMentionName, MessageEntityTextUrl

# Setup basic logging to see bot activity
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ==========================================
# ⚙️ CONFIGURATION (Credentials)
# ==========================================
MONGO_URI = "mongodb+srv://khantphyoemin537_db_user:9VRKiaeZkz7rJdpz@cluster0.w6tgi8j.mongodb.net/telegram_bot?appName=Cluster0&tlsAllowInvalidCertificates=true"
APP_ID = 39584681
APP_HASH = 'c8c0685d6dd5b9e546093ea90d27733b'
BOT_TOKEN = '8111794244:AAGpkLE7h5x_IYFvjkVCbJosDC1TFbCGxcQ'

OWNER_ID = 7693106830
TARGET_GROUP = -1003940667453 

# MongoDB Connections
client_mongo = AsyncIOMotorClient(MONGO_URI)
db = client_mongo["telegram_bot"]
talk_col = db["random_talk"]         
reply_save_col = db["reply_save_col"] 
usertalking_col = db["usertalking"]  

# Global Runtime States
talking_clients = {}            
pytgcalls_clients = {}          
is_crosstalk_active = False     
is_random_reply_active = False  
is_scraping_active = False      
should_stop_scraping = False    
last_processed_msg_id = None  
last_message_time = time.time() 
last_send_timestamp = 0         # Global Flood Control
is_autodelete_active = False    # Auto-delete state for /ဖျက်မည်
current_speed = 2  

# Initialize Official Control Bot
bot = TelegramClient('official_crosstalk_bot', APP_ID, APP_HASH)

# ==========================================
# 🌍 DUMMY HTTP SERVER FOR RENDER HEALTH CHECK
# ==========================================
async def handle_render_health_check(reader, writer):
    await reader.read(100)
    response = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\nOK"
    writer.write(response.encode('utf-8'))
    await writer.drain()
    writer.close()

async def start_dummy_web_server():
    port = int(os.environ.get("PORT", 10000))
    try:
        server = await asyncio.start_server(handle_render_health_check, '0.0.0.0', port)
        logging.info(f"🌍 Render Web Server started on port {port}")
        async with server:
            await server.serve_forever()
    except Exception as e:
        logging.error(f"❌ Web Server Error: {e}")

# ==========================================
# 🎙️ 24/7 VOICE CHAT JOINER ENGINE
# ==========================================
async def join_voice_chat(client_id, client, chat_id):
    try:
        full_chat = await client.get_peer_info(chat_id)
        if hasattr(full_chat, 'full_chat') and full_chat.full_chat.call:
            input_call = InputGroupCall(
                id=full_chat.full_chat.call.id,
                access_hash=full_chat.full_chat.call.access_hash
            )
            await client(JoinGroupCallRequest(
                call=input_call,
                join_as=await client.get_input_entity('me'),
                muted=True
            ))
            logging.info(f"🎙️ Userbot {client_id} joined VC via Telethon Native Native!")
    except Exception as e:
        logging.error(f"❌ Telethon VC Join Error: {e}")

@bot.on(events.Raw())
async def handle_voice_chat_updates(event):
    global TARGET_GROUP, talking_clients
    if isinstance(event, UpdateGroupCall):
        if event.chat_id == TARGET_GROUP and not event.call.discarded:
            logging.info("🚨 Voice Chat detected in Target Group! Connecting userbots...")
            for cl_id, cl in talking_clients.items():
                asyncio.create_task(join_voice_chat(cl_id, cl, TARGET_GROUP))
                await asyncio.sleep(1.0)

# ==========================================
# 🔍 BULLETPROOF MENTION FILTER FUNCTION
# ==========================================
def has_mention(message):
    """ HTML Format၊ Text Link နှင့် Native Entities ပုံစံမျိုးစုံဖြင့် Mention Tag ခေါ်ထားမှုများကို အကုန်စစ်ဆေးခြင်း """
    if not message or not message.text:
        return False
        
    # ၁။ Telethon Entities စစ်ဆေးခြင်း
    if message.entities:
        for entity in message.entities:
            if isinstance(entity, (MessageEntityMention, MessageEntityMentionName)):
                return True
            if isinstance(entity, MessageEntityTextUrl):
                if entity.url and ("tg://user" in entity.url or "t.me/" in entity.url):
                    return True
                
    # ၂။ Raw String နှင့် HTML Clean-up စစ်ဆေးခြင်း
    clean_text = re.sub(r'<[^>]+>', '', message.text)
    if '@' in clean_text:
        return True
        
    return False

async def delete_after_delay(client, chat_entity, msg_id, delay=3.0):
    """ Bot စာသားများအား သတ်မှတ်စက္ကန့်ပြည့်ပါက အလိုအလျောက် ပြန်ဖျက်ပေးမည့် Helper """
    await asyncio.sleep(delay)
    try:
        await client.delete_messages(chat_entity, msg_id)
        logging.info(f"🗑️ Auto-deleted bot message: {msg_id}")
    except Exception as e:
        logging.error(f"❌ Auto-delete execution failed: {e}")

# ==========================================
# 🧠 DB SEARCH UTILITY FUNCTION
# ==========================================
async def fetch_smart_reply(user_text, should_reply=True):
    """ DB ထဲမှ ဆွဲထုတ်ရာတွင်လည်း Mention ပါသော စာသားများအား ညှပ်ထုတ်သန့်စင်ပေးသည့် စနစ်ဆန်း """
    reply_text = None
    
    def is_clean(text):
        if not text or '@' in text or 't.me/' in text:
            return False
        return True

    if should_reply:
        match_pipeline = [
            {"$match": {
                "$expr": {
                    "$and": [
                        {"$gte": [{"$strLenCP": "$trigger"}, 3]},
                        {"$ne": [{"$indexOfCP": [user_text.lower(), {"$toLower": "$trigger"}]}, -1]}
                    ]
                }
            }},
            {"$sample": {"size": 3}} # Backup ယူရန် ပိုဆွဲမည်
        ]
        try:
            cursor_match = reply_save_col.aggregate(match_pipeline)
            matched_docs = await cursor_match.to_list(length=3)
            for doc in matched_docs:
                if doc.get("responses"):
                    chosen = random.choice(doc["responses"])
                    if is_clean(chosen):
                        reply_text = chosen
                        break
        except Exception:
            reply_text = None

        if not reply_text:
            try:
                cursor_fallback = reply_save_col.aggregate([{"$sample": {"size": 3}}])
                random_docs = await cursor_fallback.to_list(length=3)
                for doc in random_docs:
                    if doc.get("responses"):
                        chosen = random.choice(doc["responses"])
                        if is_clean(chosen):
                            reply_text = chosen
                            break
            except Exception:
                reply_text = None
                
        if not reply_text:
            try:
                cursor_talk = talk_col.aggregate([{"$sample": {"size": 3}}])
                random_talk_docs = await cursor_talk.to_list(length=3)
                for doc in random_talk_docs:
                    chosen = doc.get("text")
                    if is_clean(chosen):
                        reply_text = chosen
                        break
            except Exception:
                reply_text = None
    else:
        try:
            cursor_talk = talk_col.aggregate([{"$sample": {"size": 3}}])
            random_talk_docs = await cursor_talk.to_list(length=3)
            for doc in random_talk_docs:
                chosen = doc.get("text")
                if is_clean(chosen):
                    reply_text = chosen
                    break
        except Exception:
            reply_text = None

    if not reply_text:
        default_phrases = ["ဟုတ်ပဗျာ", "အေးပါဗျာ", "ဒါနဲ့လေ...", "ဟီးဟီး", "မဆိုးပါဘူး", "ဟုတ်လား Chief", "အော်... အင်း"]
        reply_text = random.choice(default_phrases)
        
    return reply_text

# ==========================================
# 🎯 No.1 ရမ်းစနစ်အတွက် ပြင်ပလူများကို တုံ့ပြန်မှု Engine
# ==========================================
async def handle_random_people_reply(event):
    global talking_clients, TARGET_GROUP, is_autodelete_active
    
    # အခြား Admin Bot များဖြစ်ပါက လုံးဝမတုံ့ပြန်ရန်
    sender = await event.get_sender()
    if sender and sender.bot:
        return

    user_text = event.message.text.strip() if event.message.text else ""
    if not user_text or has_mention(event.message):
        return

    available_ids = list(talking_clients.keys())
    if not available_ids:
        return
    
    # 💥 စည်းမျဉ်းအသစ်အရ အတိအကျ ၁ ကောင်တည်းသာ ရမ်းတုံ့ပြန်မည်
    chosen_id = random.choice(available_ids)
    bot1 = talking_clients[chosen_id]
    chat_entity = await bot1.get_entity(TARGET_GROUP)

    try:
        reply_1 = await fetch_smart_reply(user_text, should_reply=True)
        await asyncio.sleep(random.uniform(1.5, 3.0))
        async with bot1.action(chat_entity, 'typing'):
            await asyncio.sleep(random.uniform(1.0, 2.0))
        msg1 = await bot1.send_message(chat_entity, reply_1, reply_to=event.id)

        # /ဖျက်မည် စနစ် On ထားပါက ၃ စက္ကန့်အကြာတွင် ဖျက်ပစ်ခြင်း
        if is_autodelete_active:
            asyncio.create_task(delete_after_delay(bot1, chat_entity, msg1.id, delay=3.0))
            
    except Exception as e:
        logging.error(f"❌ Error in Random People Reply System: {e}")

# ==========================================
# 💬 🧠 FAST CROSSTALK ENGINE (USERBOT HANDLER)
# ==========================================
async def on_userbot_message(event):
    global is_crosstalk_active, is_random_reply_active, talking_clients, TARGET_GROUP, last_processed_msg_id, current_speed, OWNER_ID, last_message_time, last_send_timestamp, is_autodelete_active
    
    if event.chat_id != TARGET_GROUP:
        return

    # စကားပြောလာသူသည် Bot ဖြစ်နေပါက ချက်ချင်းကျော်မည် (မတုံ့ပြန်ပါ)
    sender = await event.get_sender()
    if sender and sender.bot:
        return

    is_owner = (event.sender_id == OWNER_ID)
    is_userbot = (event.sender_id in talking_clients)
    
    # 🎯 No.1 ရမ်းစနစ် အလုပ်လုပ်ပုံ
    if is_random_reply_active and not (is_owner or is_userbot):
        asyncio.create_task(handle_random_people_reply(event))
        return

    if not is_crosstalk_active:
        return

    if not (is_owner or is_userbot):
        return

    if is_userbot:
        if random.random() > 0.90:
            return

    if last_processed_msg_id == event.id:
        return
    last_processed_msg_id = event.id

    user_text = event.message.text.strip().lower() if event.message.text else ""
    if not user_text:
        return

    # ✨ Mention ပါဝင်နေပါက မပြောရန်၊ Reply မပြန်ရန် ချက်ချင်းကျော်မည်
    if has_mention(event.message):
        return

    if user_text.startswith('.') or user_text.startswith('/'):
        return

    # 🛑 MULTI-BOT CASCADE FLOOD PROTECTION (လိုင်းနင်းကန်ထွက်ခြင်းကို ထိန်းချုပ်သည့် စမတ်ကုဒ်)
    now = time.time()
    if current_speed == 1:    
        min_interval = 7.0   # Speed 1 ဆိုလျှင် စကားတစ်ခွန်းကြား အနည်းဆုံး ၇ စက္ကန့် ခြားမည်
    elif current_speed == 3:  
        min_interval = 1.5   
    else:                     
        min_interval = 3.5   
        
    if now - last_send_timestamp < min_interval:
        return # သတ်မှတ်စက္ကန့်မပြည့်မချင်း အခြား Userbot များ ဝင်မပြောရအောင် Event ကို ချနင်းလိုက်ခြင်း
        
    last_send_timestamp = now  # Lock ချလိုက်ပြီ
    last_message_time = now

    available_ids = [uid for uid in talking_clients.keys() if uid != event.sender_id]
    if not available_ids:
        available_ids = list(talking_clients.keys())
    if not available_ids:
        return
        
    chosen_id = random.choice(available_ids)
    client = talking_clients[chosen_id]

    try:
        should_reply = random.random() < 0.90
        reply_text = await fetch_smart_reply(user_text, should_reply=should_reply)

        if current_speed == 1:    
            initial_delay = random.uniform(4.0, 6.5)
            typing_delay = random.uniform(3.0, 5.0)
        elif current_speed == 3:  
            initial_delay = random.uniform(0.5, 1.2)
            typing_delay = random.uniform(0.5, 1.5)
        else:                     
            initial_delay = random.uniform(2.0, 3.5)
            typing_delay = random.uniform(1.1, 2.5)

        await asyncio.sleep(initial_delay)
        chat_entity = await client.get_entity(TARGET_GROUP)
        
        async with client.action(chat_entity, 'typing'):
            await asyncio.sleep(typing_delay)
        
        if should_reply:
            sent_msg = await client.send_message(chat_entity, reply_text, reply_to=event.id)
        else:
            sent_msg = await client.send_message(chat_entity, reply_text)
            
        last_message_time = time.time() 

        # /ဖျက်မည် စနစ် On ထားပါက ၃ စက္ကန့်အကြာတွင် ဖျက်ပစ်ခြင်း
        if is_autodelete_active:
            asyncio.create_task(delete_after_delay(client, chat_entity, sent_msg.id, delay=3.0))

    except errors.rpcerrorlist.FloodWaitError as e:
        await asyncio.sleep(e.seconds)
    except Exception as e:
        logging.error(f"❌ Crosstalk Loop Error: {e}")

# ==========================================
# ♻️ No.3 PERPETUAL CROSSTALK SUPERVISOR
# ==========================================
async def crosstalk_supervisor():
    global is_crosstalk_active, talking_clients, TARGET_GROUP, last_message_time, is_autodelete_active
    while True:
        await asyncio.sleep(4)
        if is_crosstalk_active and talking_clients:
            if time.time() - last_message_time > 12:
                logging.info("♻️ Crosstalk stalled detector activated. Injecting dynamic seed message...")
                try:
                    chosen_id = random.choice(list(talking_clients.keys()))
                    client = talking_clients[chosen_id]
                    cursor_talk = talk_col.aggregate([{"$sample": {"size": 1}}])
                    random_talk_docs = await cursor_talk.to_list(length=1)
                    seed_text = random_talk_docs[0].get("text") if random_talk_docs else "ဒါနဲ့ ဘာတွေဆက်ပြောကြမလဲဗျာ..."
                    
                    if '@' in seed_text or 't.me/' in seed_text:
                        seed_text = "ဒါနဲ့ နောက်ဘာဆက်ပြောမလဲ..."

                    chat_entity = await client.get_entity(TARGET_GROUP)
                    sent_msg = await client.send_message(chat_entity, seed_text)
                    last_message_time = time.time()
                    
                    if is_autodelete_active:
                        asyncio.create_task(delete_after_delay(client, chat_entity, sent_msg.id, delay=3.0))
                except Exception as e:
                    logging.error(f"❌ Supervisor System Error: {e}")

# ==========================================
# 📊 No.2 SMART DB DATA SCRAPER TASK
# ==========================================
async def start_data_scraping(group_arg):
    global is_scraping_active, should_stop_scraping, talking_clients, OWNER_ID, reply_save_col, talk_col
    
    is_scraping_active = True
    should_stop_scraping = False
    
    scraper_client = list(talking_clients.values())[0]
    
    try:
        if "joinchat/" in group_arg or "t.me/+" in group_arg:
            invite_hash = group_arg.split("joinchat/")[-1] if "joinchat/" in group_arg else group_arg.split("t.me/+")[-1]
            entity = await scraper_client(ImportChatInviteRequest(invite_hash))
            target_entity = entity.chats[0]
        else:
            username = group_arg.replace("https://t.me/", "").replace("@", "").split('/')[0]
            target_entity = await scraper_client.get_entity(username)

        await bot.send_message(OWNER_ID, "📥 **ဒေတာဘေ့စ် စမတ်ကျကျ သိမ်းဆည်းခြင်းလုပ်ငန်းစဉ်ကို စတင်နေပါပြီ Chief...**")
        
        saved_count = 0
        msg_cache = {} 
        
        async for msg in scraper_client.iter_messages(target_entity, limit=20000):
            if should_stop_scraping:
                break
                
            if not msg.text:
                continue
                
            if has_mention(msg):
                continue
                
            text_clean = msg.text.strip()
            msg_cache[msg.id] = text_clean
        
            if msg.reply_to and msg.reply_to.reply_to_msg_id in msg_cache:
                parent_text = msg_cache[msg.reply_to.reply_to_msg_id]
                if len(parent_text) >= 3 and text_clean:
                    await reply_save_col.update_one(
                        {"trigger": parent_text},
                        {"$addToSet": {"responses": text_clean}},
                        upsert=True
                    )
                    saved_count += 1
            else:
                await talk_col.update_one(
                    {"text": text_clean},
                    {"$set": {"text": text_clean}},
                    upsert=True
                )
                saved_count += 1
                
            if saved_count > 0 and saved_count % 1000 == 0:
                await bot.send_message(
                    OWNER_ID, 
                    f"📊 **ဒေတာသိမ်းဆည်းမှု သတင်းပို့ချက်:**\n"
                    f"စာသားစုစုပေါင်း `{saved_count}` ခုအား စမတ်ကျကျ ခွဲခြားသိမ်းဆည်းပြီးပါပြီ Chief!\n\n"
                    f"လုပ်ငန်းစဉ် ဆက်လက်လည်ပတ်နေပါသည်။ ရပ်တန့်လိုပါက `/ရပ်` ဟု ပို့နိုင်ပါသည်။"
                )
            
            await asyncio.sleep(0.05) 
            
        await bot.send_message(OWNER_ID, f"✅ **ဒေတာသိမ်းဆည်းခြင်း လုပ်ငန်းစဉ် အောင်မြင်စွာ ပြီးဆုံးပါပြီ။ စုစုပေါင်း: {saved_count} ခု**")
    except Exception as e:
        await bot.send_message(OWNER_ID, f"❌ ဒေတာသိမ်းဆည်းမှု လုပ်ငန်းစဉ်တွင် အမှားတစ်ခုတက်သွားပါသည်- {e}")
    finally:
        is_scraping_active = False

# ==========================================
# 🤖 OFFICIAL BOT COMMAND HANDLERS
# ==========================================
@bot.on(events.NewMessage(from_users=OWNER_ID)) 
async def handle_admin_commands(event):
    global talking_clients, is_crosstalk_active, is_random_reply_active, TARGET_GROUP, current_speed, should_stop_scraping, is_scraping_active, is_autodelete_active
    
    cmd = event.message.text.strip() if event.message.text else ""

    # ⚡ SPEED CONTROL COMMANDS
    if cmd in [".spd 1", "spd 1"]:
        current_speed = 1
        await event.reply("⚡ **Crosstalk Speed ကို Slow သို့ ပြောင်းလဲလိုက်ပါပြီ Chief! (၇ စက္ကန့် ခြားပါမည်)**")
        return
    elif cmd in [".spd 2", "spd 2"]:
        current_speed = 2
        await event.reply("⚡ **Crosstalk Speed ကို Normal သို့ ပြောင်းလဲလိုက်ပါပြီ Chief!**")
        return
    elif cmd in [".spd 3", "spd 3"]:
        current_speed = 3
        await event.reply("⚡ **Crosstalk Speed ကို Fast သို့ ပြောင်းလဲလိုက်ပါပြီ Chief!**")
        return

    # 🎯 No.1 /ရမ်း စနစ်ခလုတ်
    elif cmd in ["/ရမ်း", ".ရမ်း", "ရမ်း"]:
        is_random_reply_active = not is_random_reply_active
        status = "ဖွင့်လှစ်" if is_random_reply_active else "ပိတ်သိမ်း"
        await event.reply(f"🎯 **ပြင်ပလူများအား (အကောင့် ၁ ကောင်တည်းဖြင့်) တုံ့ပြန်မည့် ရမ်းစနစ်ကို {status}လိုက်ပါပြီ Chief!**")
        return

    # 🗑️ /ဖျက်မည် PERSISTENT AUTO-DELETE TOGGLE COMMAND
    elif cmd in ["/ဖျက်မည်", ".ဖျက်မည်", "ဖျက်မည်"]:
        is_autodelete_active = not is_autodelete_active
        status = "ဖွင့်လှစ်" if is_autodelete_active else "ပိတ်သိမ်း"
        await event.reply(f"🗑️ **ပို့ပြီးသား Bot စာများကို ၃ စက္ကန့်အကြာတွင် အလိုအလျောက်ဖျက်မည့် စနစ်ကို {status}လိုက်ပါပြီ Chief!**")
        return

    # 📥 No.2 /သိမ်းဆည်းမယ် နှင့် /ရပ် စနစ်များ
    elif cmd.startswith("/သိမ်းဆည်းမယ်"):
        if not talking_clients:
            await event.reply("❌ အလုပ်လုပ်မည့် Userbot တစ်ခုမှ မရှိသေးပါ Chief။")
            return
        if is_scraping_active:
            await event.reply("⚠️ ဒေတာသိမ်းဆည်းခြင်း လုပ်ငန်းစဉ်တစ်ခု လည်ပတ်နေနှင့်ပြီးသား ဖြစ်ပါသည် Chief။")
            return
        parts = cmd.split(maxsplit=1)
        if len(parts) < 2:
            await event.reply("❌ ကျေးဇူးပြု၍ Group Link ထည့်သွင်းပေးပါ။\nဥပမာ- `/သိမ်းဆည်းမယ် https://t.me/example`")
            return
        asyncio.create_task(start_data_scraping(parts[1].strip()))
        return

    elif cmd == "/ရပ်":
        if is_scraping_active:
            should_stop_scraping = True
            await event.reply("🛑 **Chief ၏ အမိန့်အရ ဒေတာသိမ်းဆည်းခြင်းလုပ်ငန်းစဉ်ကို ချက်ချင်း ရပ်တန့်နေပါသည်...**")
        else:
            await event.reply("⚠️ လက်ရှိတွင် မည်သည့် Scraping လုပ်ငန်းစဉ်မျှ လည်ပတ်ခြင်း မရှိပါ Chief။")
        return

    # 🎙️ VOICE CHAT CONTROLS
    elif cmd in [".vcon", "vcon"]:
        if not talking_clients:
            await event.reply("❌ **Chief! Active ဖြစ်နေတဲ့ Userbot မရှိသေးပါဘူးဗျာ။**")
            return
        status_msg = await event.reply("⏳ **Userbot အားလုံးကို Voice Chat ထဲ ပို့နေပါသည် Chief...**")
        for cl_id, cl in talking_clients.items():
            asyncio.create_task(join_voice_chat(cl_id, cl, TARGET_GROUP))
            await asyncio.sleep(1.0)
        await status_msg.edit(f"✅ **Userbot အားလုံးကို Target ID: `{TARGET_GROUP}` ရဲ့ Voice Chat ထဲ ထည့်သွင်းပြီးပါပြီ Chief!**")
        return

    elif cmd in [".vcoff", "vcoff"]:
        status_msg = await event.reply("⏳ **Userbot များကို Voice Chat ထဲမှ ပြန်ထုတ်နေပါသည်...**")
        for cl_id, call_cl in list(pytgcalls_clients.items()):
            try: await call_cl.leave_call(TARGET_GROUP)
            except: pass
        await status_msg.edit("🛑 **Userbot အားလုံး Voice Chat ထဲမှ ထွက်လိုက်ပါပြီ Chief!**")
        return

    # 📥 MULTI-BOT /string MANAGEMENT
    elif cmd == "/string" and event.is_reply:
        reply_msg = await event.get_reply_message()
        if reply_msg and reply_msg.text:
            session_str = reply_msg.text.strip()
            current_count = await usertalking_col.count_documents({})
            if current_count >= 10:
                await event.reply("❌ **Chief! အကောင့်အရေအတွက် အများဆုံး (၁၀) ခု ပြည့်နေပါပြီဗျာ။**")
                return
            status_msg = await event.reply("⏳ String Session ကို စစ်ဆေးပြီး ချဆက်နေပါသည် Chief...")
            try:
                new_client = TelegramClient(StringSession(session_str), APP_ID, APP_HASH)
                await new_client.start()
                new_client.add_event_handler(on_userbot_message, events.NewMessage)
                me = await new_client.get_me()
                await usertalking_col.update_one(
                    {"user_id": me.id},
                    {"$set": {"session": session_str, "username": me.username, "user_id": me.id}},
                    upsert=True
                )
                talking_clients[me.id] = new_client
                updated_count = await usertalking_col.count_documents({})
                await status_msg.edit(f"✅ **Account ချိတ်ဆက်မှု အောင်မြင်ပါသည် Chief!**\n👤 အကောင့်: @{me.username}\n📊 စုစုပေါင်းအကောင့်အရေအတွက်: `{updated_count}`/10 ခု ရှိသွားပါပြီ။")
            except Exception as e:
                await status_msg.edit(f"❌ Userbot ချိတ်ဆက်မှု ကျရှုံးပါသည်: {e}")
        return

    # 💬 CROSSTALK START COMMAND
    elif cmd == "/စကားပြော":
        if not talking_clients:
            await event.reply("❌ **Chief! Active ဖြစ်နေတဲ့ Userbot တစ်ခုမှ မရှိသေးပါဘူးဗျာ။ အရင်ဆုံး String ထည့်ပေးပါဦး။**")
            return
        is_crosstalk_active = True
        await event.reply(f"💬 🔥 **Multi-Bot Perpetual Cross-Talk စနစ်ကို ID: `{TARGET_GROUP}` တွင် စတင်လိုက်ပါပြီ Chief!**")
        try:
            chosen_id = random.choice(list(talking_clients.keys()))
            client = talking_clients[chosen_id]
            cursor_talk = talk_col.aggregate([{"$sample": {"size": 1}}])
            random_talk_docs = await cursor_talk.to_list(length=1)
            seed_text = random_talk_docs[0].get("text") if random_talk_docs else "ဟယ်လို... အားလုံးပဲ မင်္ဂလာပါဗျာ။"
            
            if '@' in seed_text or 't.me/' in seed_text:
                seed_text = "ဟယ်လို... အားလုံးပဲ မင်္ဂလာပါဗျာ။"

            chat_entity = await client.get_entity(TARGET_GROUP)
            sent_msg = await client.send_message(chat_entity, seed_text)
            
            if is_autodelete_active:
                asyncio.create_task(delete_after_delay(client, chat_entity, sent_msg.id, delay=3.0))
        except Exception as e:
            logging.error(f"❌ Failed to send starter seed message: {e}")
        return

    # 🛑 CROSSTALK STOP COMMAND
    elif cmd == "/နား":
        if not is_crosstalk_active:
            await event.reply("⚠️ **စကားပြောစနစ်သည် ပိတ်ထားပြီးသား ဖြစ်ပါသည် Chief!**")
            return
        is_crosstalk_active = False
        await event.reply("🛑 **Chief ရဲ့ အမိန့်အရ စကားပြောစနစ်ကို ချက်ချင်း ရပ်တန့်လိုက်ပါပြီဗျာ။**")
        return

    # 📢 No.5 /ပို့ စနစ်ထုတ်လွှင့်မှု စနစ်သစ်
    elif cmd.startswith("/ပို့"):
        parts = cmd.split(maxsplit=1)
        if len(parts) < 2:
            await event.reply("❌ ကျေးဇူးပြု၍ ပို့လိုသော Сာသားကို ထည့်သွင်းပေးပါ။\nဥပမာ- `/ပို့ မင်္ဂလာပါ`")
            return
        broadcast_text = parts[1].strip()
        await event.reply("⏳ **Userbots များရှိနေသော Group အားလုံးထံ စာသားဖြန့်ဝေနေပါသည်...**")
        
        async def broadcast_task():
            for uid, cl in talking_clients.items():
                try:
                    dialogs = await cl.get_dialogs()
                    for dialog in dialogs:
                        if dialog.is_group or dialog.is_channel:
                            try:
                                await cl.send_message(dialog.id, broadcast_text)
                                await asyncio.sleep(2.5) 
                            except Exception:
                                continue
                except Exception as e:
                    logging.error(f"Broadcast Error for client {uid}: {e}")
            await bot.send_message(OWNER_ID, "📢 **Group အားလုံးထံသို့ စာသားထုတ်လွှင့်မှု လုပ်ငန်းစဉ် ပြီးဆုံးပါပြီ Chief!**")
            
        asyncio.create_task(broadcast_task())
        return

    # 👤 No.6 PROFILE PROFILE & NAME UPDATE COMMANDS VIA REPLY
    elif (cmd.startswith("/bio") or cmd.startswith("/name")) and event.is_reply:
        reply_msg = await event.get_reply_message()
        target_bot_id = reply_msg.sender_id
        
        if target_bot_id not in talking_clients:
            await event.reply("❌ ဤ Command သည် စနစ်ထဲတွင် ချိတ်ဆက်ထားသော Userbot မက်ဆေ့ခ်ျများကိုသာ Reply ထောက်၍ သုံးနိုင်ပါသည် Chief။")
            return
            
        target_client = talking_clients[target_bot_id]
        parts = cmd.split(maxsplit=1)
        if len(parts) < 2:
            await event.reply("❌ ကျေးဇူးပြု၍ ပြောင်းလဲလိုသော စာသားကို ထည့်ပေးပါ။")
            return
        update_value = parts[1].strip()
        
        try:
            if cmd.startswith("/bio"):
                await target_client(UpdateProfileRequest(about=update_value))
                await event.reply(f"✅ Userbot {target_bot_id} ၏ **Bio အား ပြောင်းလဲပြီးပါပြီ Chief!**")
            else:
                name_parts = update_value.split(maxsplit=1)
                first_n = name_parts[0]
                last_n = name_parts[1] if len(name_parts) > 1 else ""
                await target_client(UpdateProfileRequest(first_name=first_n, last_name=last_n))
                await event.reply(f"✅ Userbot {target_bot_id} ၏ **နာမည်အား ပြောင်းလဲပြီးပါပြီ Chief!**")
        except Exception as e:
            await event.reply(f"❌ Profile Update Error: {e}")
        return

    # 👥 No.4 MEMBER ADDER VIA MENTION
    elif cmd.startswith("/add"):
        parts = cmd.split(maxsplit=1)
        target_client = None
        
        if event.is_reply:
            reply_msg = await event.get_reply_message()
            if reply_msg.sender_id in talking_clients:
                target_client = talking_clients[reply_msg.sender_id]
        elif len(parts) > 1:
            mention_arg = parts[1].strip().replace("@", "")
            for cl in talking_clients.values():
                me = await cl.get_me()
                if me.username == mention_arg:
                    target_client = cl
                    break
                    
        if not target_client:
            await event.reply("❌ Target Userbot ကို ရှာမတွေ့ပါ။ ဖုန်း Contact စာရင်းယူရန် Userbot အား Mention ခေါ်ပါ သို့မဟုတ် Reply ထောက်ပါ။")
            return
            
        current_group_id = event.chat_id
        await event.reply("⏳ **ရွေးချယ်ထားသော Userbot ၏ Contact မှ လူများအား လက်ရှိ Group သို့ ဆွဲထည့်နေပါသည်...**")
        
        async def add_members_task(cl_instance, group_id):
            try:
                contacts = await cl_instance(GetContactsRequest(hash=0))
                if not contacts.users:
                    await bot.send_message(OWNER_ID, "⚠️ ၎င်း Userbot တွင် မည်သည့် Contact မှ မရှိပါ Chief။")
                    return
                
                added_success = 0
                for user in contacts.users:
                    try:
                        await cl_instance(InviteToChannelRequest(channel=group_id, users=[user.id]))
                        added_success += 1
                        if added_success % 5 == 0:
                            await bot.send_message(OWNER_ID, f"👥 **အဖွဲ့ဝင်သစ် ထည့်သွင်းမှု သတင်းစကား:** လူဦးရေ `{added_success}` ဦး လက်ရှိ Group ထဲသို့ ထည့်သွင်းပြီးပါပြီ။")
                        await asyncio.sleep(4.5) 
                    except errors.rpcerrorlist.UserPrivacyRestrictedError:
                        continue
                    except errors.rpcerrorlist.FloodWaitError as e:
                        await asyncio.sleep(e.seconds + 2)
                    except Exception:
                        continue
                await bot.send_message(OWNER_ID, f"✅ **အဖွဲ့ဝင်ဖိတ်ခေါ်ခြင်း လုပ်ငန်းစဉ် ပြီးဆုံးပါပြီ။ စုစုပေါင်းထည့်သွင်းနိုင်မှု- {added_success} ဦး**")
            except Exception as e:
                await bot.send_message(OWNER_ID, f"❌ Add Member Error: {e}")
                
        asyncio.create_task(add_members_task(target_client, current_group_id))
        return

# 🎯 [STANDALONE COMMAND] /သွားမယ် စနစ်
@bot.on(events.NewMessage(from_users=OWNER_ID, pattern=r'^/သွားမယ်'))
async def go_to_group(event):
    global TARGET_GROUP, is_crosstalk_active, last_message_time, is_autodelete_active
    text_parts = event.text.split(maxsplit=1)
    if len(text_parts) < 2:
        await event.respond("❌ ကျေးဇူးပြု၍ Group Link သို့မဟုတ် Username ထည့်ပေးပါ။")
        return
        
    argument = text_parts[1].strip()
    status_msg = await event.respond("🔄 Group Link ကို စစ်ဆေးပြီး Bot များ ဝင်ရောက်နေပါသည်...")
    if not talking_clients:
        await status_msg.edit("❌ အလုပ်လုပ်မယ့် Client Account မရှိသေးပါ။")
        return

    first_cl = list(talking_clients.values())[0]
    resolved_id = None

    try:
        if "joinchat/" in argument or "t.me/+" in argument:
            invite_hash = argument.split("joinchat/")[-1] if "joinchat/" in argument else argument.split("t.me/+")[-1]
            try:
                invite_info = await first_cl(CheckChatInviteRequest(invite_hash))
                if hasattr(invite_info, 'chat') and invite_info.chat:
                    resolved_id = get_peer_id(invite_info.chat)
            except Exception: pass

            joined_count = 0
            for cl_id, cl in talking_clients.items():
                try:
                    updates = await cl(ImportChatInviteRequest(invite_hash))
                    if not resolved_id and updates and hasattr(updates, 'chats') and updates.chats:
                        resolved_id = get_peer_id(updates.chats[0])
                    joined_count += 1
                except errors.UserAlreadyParticipantError: joined_count += 1
                except Exception: pass
                await asyncio.sleep(1.5)
        else:
            username = argument.replace("https://t.me/", "").replace("@", "").split('/')[0]
            entity = await first_cl.get_entity(username)
            resolved_id = get_peer_id(entity)
            joined_count = 0
            for cl_id, cl in talking_clients.items():
                try:
                    await cl(JoinChannelRequest(username))
                    joined_count += 1
                except errors.UserAlreadyParticipantError: joined_count += 1
                except Exception: pass
                await asyncio.sleep(1.5)

        if resolved_id:
            TARGET_GROUP = resolved_id
            is_crosstalk_active = True  
            last_message_time = time.time()
            await status_msg.edit(f"✅ **Join ခြင်း အောင်မြင်ပါသည် Chief!**\n📊 အကောင့်ပေါင်း `{joined_count}` ခု ဝင်ရောက်ပြီးပါပြီ။\n🎯 Target ID: `{TARGET_GROUP}`\n⏳ စကားဝိုင်း အလိုအလျောက် စတင်ရန် Seed Message ပို့နေပါသည်...")
        else:
            raise Exception("Group ID ကို ရှာမတွေ့ပါ။")

    except Exception as e:
        await status_msg.edit(f"❌ Link ဖတ်ရတာ မအောင်မြင်ပါ- {e}")
        return

    try:
        await asyncio.sleep(3.0)
        chosen_id = random.choice(list(talking_clients.keys()))
        client = talking_clients[chosen_id]
        cursor_talk = talk_col.aggregate([{"$sample": {"size": 1}}])
        random_talk_docs = await cursor_talk.to_list(length=1)
        seed_text = random_talk_docs[0].get("text") if random_talk_docs else "ဟယ်လို... အားလုံးပဲ မင်္ဂလာပါဗျာ။"
        
        if '@' in seed_text or 't.me/' in seed_text:
            seed_text = "ဟယ်လို... အားလုံးပဲ မင်္ဂလာပါဗျာ။"

        chat_entity = await client.get_entity(TARGET_GROUP)
        sent_msg = await client.send_message(chat_entity, seed_text)
        last_message_time = time.time()
        
        if is_autodelete_active:
            asyncio.create_task(delete_after_delay(client, chat_entity, sent_msg.id, delay=3.0))
            
        await bot.send_message(OWNER_ID, "💬 🔥 **Seed Message အောင်မြင်စွာ ပို့ပြီးပါပြီ။ စကားဝိုင်း လည်ပတ်နေပါပြီ Chief!**")
    except Exception as e:
        await bot.send_message(OWNER_ID, f"❌ စကားစတင်ရန် Seed Message ပို့ခြင်း ကျရှုံးပါသည်- {e}")

# ==========================================
# 🚀 SYSTEM STARTUP LOGIC
# ==========================================
async def startup():
    global talking_clients
    logging.info("⏳ System starting up and loading Cross-Talk Simulator Engine...")
    
    asyncio.create_task(start_dummy_web_server())
    asyncio.create_task(crosstalk_supervisor()) 

    logging.info("⏳ Loading Simulator Accounts from MongoDB...")
    cursor_talkers = usertalking_col.find({})
    async Gear = []
    async for doc in cursor_talkers:
        try:
            cl = TelegramClient(StringSession(doc["session"]), APP_ID, APP_HASH)
            await cl.start()
            cl.add_event_handler(on_userbot_message, events.NewMessage)
            talking_clients[doc["user_id"]] = cl
            logging.info(f"✅ Successfully loaded talker account: @{doc.get('username')}")
        except Exception as e:
            logging.error(f"⚠️ Failed to login talker account {doc.get('username')}: {e}")

    await bot.start(bot_token=BOT_TOKEN)
    logging.info("🤖 Official Control Bot is running successfully...")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(startup())

