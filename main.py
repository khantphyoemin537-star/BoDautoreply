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
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.utils import get_peer_id  # ပြဿနာကင်းဝေးအောင် အသုံးပြုရန် Import လုပ်ထားသည်

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
is_crosstalk_active = False     
last_processed_msg_id = None  
current_speed = 2  # Default Speed: 2 (Normal), 1 = Slow, 3 = Fast

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
# 💬 🧠 FAST CROSSTALK ENGINE (USERBOT HANDLER)
# ==========================================
async def on_userbot_message(event):
    global is_crosstalk_active, talking_clients, TARGET_GROUP, last_processed_msg_id, current_speed, OWNER_ID
    
    if not is_crosstalk_active:
        return
        
    if event.chat_id != TARGET_GROUP:
        return

    # Owner ဆီကစာ သို့မဟုတ် Active ဖြစ်နေတဲ့ Userbot အချင်းချင်းဆီကစာ ဖြစ်မှ အလုပ်လုပ်မည်
    is_owner = (event.sender_id == OWNER_ID)
    is_userbot = (event.sender_id in talking_clients)
    
    if not (is_owner or is_userbot):
        return

    if last_processed_msg_id == event.id:
        return
    last_processed_msg_id = event.id

    user_text = event.message.text.strip().lower() if event.message.text else ""
    if not user_text:
        return

    # Admin command/speed command တွေကို စကားပြောထဲမထည့်ရန် ကျော်ပစ်မည်
    if user_text.startswith('.') or user_text.startswith('/'):
        return

    # စာပြန်မယ့် အကောင့်ထဲကနေ လက်ရှိစာပို့လိုက်တဲ့အကောင့်ကို ဖယ်ထုတ်ပြီး ကျန်တဲ့ကောင်တွေထဲက ရွေးမည်
    available_ids = [uid for uid in talking_clients.keys() if uid != event.sender_id]
    if not available_ids:
        available_ids = list(talking_clients.keys())
        
    if not available_ids:
        return
        
    chosen_id = random.choice(available_ids)
    client = talking_clients[chosen_id]

    try:
        reply_text = None
        should_reply = random.random() < 0.90
        
        if should_reply:
            match_pipeline = [
                {"$match": {
                    "$and": [
                        {"$expr": {"$gte": [{"$strLenCP": "$trigger"}, 3]}},
                        {"trigger": {"$regex": user_text, "$options": "i"}}
                    ]
                }},
                {"$sample": {"size": 1}}
            ]
            try:
                cursor_match = reply_save_col.aggregate(match_pipeline)
                matched_docs = await cursor_match.to_list(length=1)
                if matched_docs and matched_docs[0].get("responses"):
                    reply_text = random.choice(matched_docs[0]["responses"])
            except Exception:
                reply_text = None

            if not reply_text:
                try:
                    pipeline_fallback = [{"$sample": {"size": 1}}]
                    cursor_fallback = reply_save_col.aggregate(pipeline_fallback)
                    random_docs = await cursor_fallback.to_list(length=1)
                    if random_docs and random_docs[0].get("responses"):
                        reply_text = random.choice(random_docs[0]["responses"])
                except Exception:
                    reply_text = None
                    
            if not reply_text:
                try:
                    pipeline_fallback = [{"$sample": {"size": 1}}]
                    cursor_talk = talk_col.aggregate(pipeline_fallback)
                    random_talk_docs = await cursor_talk.to_list(length=1)
                    reply_text = random_talk_docs[0].get("text") if random_talk_docs else None
                except Exception:
                    reply_text = None
        else:
            try:
                cursor_talk = talk_col.aggregate([{"$sample": {"size": 1}}])
                random_talk_docs = await cursor_talk.to_list(length=1)
                reply_text = random_talk_docs[0].get("text") if random_talk_docs else None
            except Exception:
                reply_text = None

        if not reply_text:
            default_phrases = ["ဟုတ်ပဗျာ", "အေးပါဗျာ", "ဒါနဲ့လေ...", "ဟီးဟီး", "မဆိုးပါဘူး", "ဟုတ်လား Chief", "အော်... အင်း"]
            reply_text = random.choice(default_phrases)

        if reply_text:
            # ⚙️ Speed Level အလိုက် အချိန်စောင့်ဆိုင်းမှုကို တွက်ချက်ခြင်း
            if current_speed == 1:    # Slow
                initial_delay = random.uniform(4.0, 6.5)
                typing_delay = random.uniform(3.0, 5.0)
            elif current_speed == 3:  # Fast
                initial_delay = random.uniform(0.5, 1.2)
                typing_delay = random.uniform(0.5, 1.5)
            else:                     # Normal (Speed 2)
                initial_delay = random.uniform(2.0, 3.5)
                typing_delay = random.uniform(1.1, 2.5)

            await asyncio.sleep(initial_delay)
            
            # Peer Casting Bug မတက်စေရန် စာမပို့မီ Chat Entity ကို သေချာဆွဲထုတ်ပြီးမှ ပို့မည်
            chat_entity = await client.get_entity(TARGET_GROUP)
            
            async with client.action(chat_entity, 'typing'):
                await asyncio.sleep(typing_delay)
            
            if should_reply:
                await client.send_message(chat_entity, reply_text, reply_to=event.id)
            else:
                await client.send_message(chat_entity, reply_text)

    except errors.rpcerrorlist.FloodWaitError as e:
        logging.warning(f"⚠️ FloodWait မိသွားပါသည်။ {e.seconds} စက္ကန့် စောင့်ဆိုင်းနေပါသည်...")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        logging.error(f"❌ Crosstalk Loop Error: {e}")

# ==========================================
# 🤖 OFFICIAL BOT COMMAND HANDLERS
# ==========================================
@bot.on(events.NewMessage(from_users=OWNER_ID)) 
async def handle_admin_commands(event):
    global talking_clients, is_crosstalk_active, TARGET_GROUP, current_speed
    
    cmd = event.message.text.strip() if event.message.text else ""

    # ⚡ SPEED CONTROL COMMANDS (.spd 1, .spd 2, .spd 3)
    if cmd in [".spd 1", "spd 1"]:
        current_speed = 1
        await event.reply("⚡ **Crosstalk Speed ကို Slow (နှေးကွေးသောနှုန်း) သို့ ပြောင်းလဲလိုက်ပါပြီ Chief!**")
        return
    elif cmd in [".spd 2", "spd 2"]:
        current_speed = 2
        await event.reply("⚡ **Crosstalk Speed ကို Normal (ပုံမှန်နှုန်း) သို့ ပြောင်းလဲလိုက်ပါပြီ Chief!**")
        return
    elif cmd in [".spd 3", "spd 3"]:
        current_speed = 3
        await event.reply("⚡ **Crosstalk Speed ကို Fast (အမြန်နှုန်း) သို့ ပြောင်းလဲလိုက်ပါပြီ Chief!**")
        return

    # 📥 MULTI-BOT /string MANAGEMENT
    if cmd == "/string" and event.is_reply:
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

    # 💬 CROSSTALK START COMMAND
    elif cmd == "/စကားပြော":
        if not talking_clients:
            await event.reply("❌ **Chief! Active ဖြစ်နေတဲ့ Userbot တစ်ခုမှ မရှိသေးပါဘူးဗျာ။ အရင်ဆုံး String ထည့်ပေးပါဦး။**")
            return
            
        is_crosstalk_active = True
        await event.reply(f"💬 🔥 **Multi-Bot Perpetual Cross-Talk စနစ်ကို ID: `{TARGET_GROUP}` တွင် အမြန်နှုန်းဖြင့် အသစ်ပြန်လည် စတင်လိုက်ပါပြီ Chief!**")
        
        try:
            chosen_id = random.choice(list(talking_clients.keys()))
            client = talking_clients[chosen_id]
            cursor_talk = talk_col.aggregate([{"$sample": {"size": 1}}])
            random_talk_docs = await cursor_talk.to_list(length=1)
            seed_text = random_talk_docs[0].get("text") if random_talk_docs else "ဟယ်လို... အားလုံးပဲ မင်္ဂလာပါဗျာ။"
            
            # Peer casting error ကိုဖြေရှင်းရန် get_entity ကို သုံးထားပါသည်
            chat_entity = await client.get_entity(TARGET_GROUP)
            await client.send_message(chat_entity, seed_text)
        except Exception as e:
            logging.error(f"❌ Failed to send starter seed message: {e}")
            await event.reply(f"❌ **စကားစတင်ရန် Seed Message ပို့ခြင်း ကျရှုံးပါသည်- {e}**")

    # 🛑 CROSSTALK STOP COMMAND
    elif cmd == "/နား":
        if not is_crosstalk_active:
            await event.reply("⚠️ **စကားပြောစနစ်သည် ပိတ်ထားပြီးသား ဖြစ်ပါသည် Chief!**")
            return
            
        is_crosstalk_active = False
        await event.reply("🛑 **Chief ရဲ့ အမိန့်အရ စကားပြောစနစ်ကို ချက်ချင်း ရပ်တန့်လိုက်ပါပြီဗျာ။**")


# 🎯 [STANDALONE COMMAND] /သွားမယ် စနစ်အသစ်
@bot.on(events.NewMessage(from_users=OWNER_ID, pattern=r'^/သွားမယ်'))
async def go_to_group(event):
    global TARGET_GROUP, is_crosstalk_active
    
    text_parts = event.text.split(maxsplit=1)
    if len(text_parts) < 2:
        await event.respond("❌ ကျေးဇူးပြု၍ Group Link သို့မဟုတ် Username ထည့်ပေးပါ။\nဥပမာ - `/သွားမယ် https://t.me/example`")
        return
        
    argument = text_parts[1].strip()
    status_msg = await event.respond("🔄 Group Link ကို စစ်ဆေးပြီး Bot များ ဝင်ရောက်နေပါသည်...")
    
    if not talking_clients:
        await status_msg.edit("❌ အလုပ်လုပ်မယ့် Client Account မရှိသေးပါ။")
        return

    first_cl = list(talking_clients.values())[0]
    resolved_id = None

    try:
        # 1. Private Invite Link ဖြစ်ခဲ့ရင် (t.me/+... သို့မဟုတ် joinchat/)
        if "joinchat/" in argument or "t.me/+" in argument:
            invite_hash = argument.split("joinchat/")[-1] if "joinchat/" in argument else argument.split("t.me/+")[-1]
            
            try:
                invite_info = await first_cl(CheckChatInviteRequest(invite_hash))
                if hasattr(invite_info, 'chat') and invite_info.chat:
                    resolved_id = get_peer_id(invite_info.chat)
            except Exception:
                pass

            joined_count = 0
            for cl_id, cl in talking_clients.items():
                try:
                    updates = await cl(ImportChatInviteRequest(invite_hash))
                    if not resolved_id and updates and hasattr(updates, 'chats') and updates.chats:
                        resolved_id = get_peer_id(updates.chats[0])
                    joined_count += 1
                except errors.UserAlreadyParticipantError:
                    joined_count += 1
                except Exception:
                    pass
                await asyncio.sleep(1.5)

        # 2. Public Link သို့မဟုတ် Username ဖြစ်ခဲ့ရင် (@username)
        else:
            username = argument.replace("https://t.me/", "").replace("@", "").split('/')[0]
            entity = await first_cl.get_entity(username)
            resolved_id = get_peer_id(entity)
            
            joined_count = 0
            for cl_id, cl in talking_clients.items():
                try:
                    await cl(JoinChannelRequest(username))
                    joined_count += 1
                except errors.UserAlreadyParticipantError:
                    joined_count += 1
                except Exception:
                    pass
                await asyncio.sleep(1.5)

        if resolved_id:
            TARGET_GROUP = resolved_id
            is_crosstalk_active = True  
            await status_msg.edit(f"✅ **Join ခြင်း အောင်မြင်ပါသည် Chief!**\n📊 အကောင့်ပေါင်း `{joined_count}` ခု ဝင်ရောက်ပြီးပါပြီ။\n🎯 Target ID: `{TARGET_GROUP}`\n⏳ စကားဝိုင်း အလိုအလျောက် စတင်ရန် Seed Message ပို့နေပါသည်...")
        else:
            raise Exception("Group ID ကို ရှာမတွေ့ပါ။ Link မှန်မမှန် ပြန်စစ်ပေးပါ။")

    except Exception as e:
        await status_msg.edit(f"❌ Link ဖတ်ရတာ မအောင်မြင်ပါ- {e}")
        return

    # 3. Seed Message ပို့ခြင်း
    try:
        await asyncio.sleep(3.0)
        chosen_id = random.choice(list(talking_clients.keys()))
        client = talking_clients[chosen_id]
        
        cursor_talk = talk_col.aggregate([{"$sample": {"size": 1}}])
        random_talk_docs = await cursor_talk.to_list(length=1)
        seed_text = random_talk_docs[0].get("text") if random_talk_docs else "ဟယ်လို... အားလုံးပဲ မင်္ဂလာပါဗျာ။"
        
        # Peer Casting Error အတွက် get_entity ဖြင့် သေချာပြောင်းလဲပြီးမှ ပို့သည်
        chat_entity = await client.get_entity(TARGET_GROUP)
        await client.send_message(chat_entity, seed_text)
        await bot.send_message(OWNER_ID, "💬 🔥 **Seed Message အောင်မြင်စွာ ပို့ပြီးပါပြီ။ စကားဝိုင်း အရှိန်ပြင်းပြင်းဖြင့် လည်ပတ်နေပါပြီ Chief!**")
        
    except Exception as e:
        await bot.send_message(OWNER_ID, f"❌ စကားစတင်ရန် Seed Message ပို့ခြင်း ကျရှုံးပါသည်- {e}")


# ==========================================
# 🚀 SYSTEM STARTUP LOGIC
# ==========================================
async def startup():
    global talking_clients
    logging.info("⏳ System starting up and loading Cross-Talk Simulator Engine...")
    
    asyncio.create_task(start_dummy_web_server())

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
