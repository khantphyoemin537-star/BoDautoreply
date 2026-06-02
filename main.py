import os
import time
import asyncio
import random
import logging
import re
import telethon.utils
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from motor.motor_asyncio import AsyncIOMotorClient
from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest

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
    global is_crosstalk_active, talking_clients, TARGET_GROUP, last_processed_msg_id
    
    if not is_crosstalk_active:
        return
        
    if event.chat_id != TARGET_GROUP:
        return

    # ⚠️ String Session ထဲက Useraccount အချင်းချင်းပို့သော စာဖြစ်မှသာ ဆက်လုပ်မည်
    if event.sender_id not in talking_clients:
        return

    if last_processed_msg_id == event.id:
        return
    last_processed_msg_id = event.id

    user_text = event.message.text.strip().lower() if event.message.text else ""
    if not user_text:
        return

    available_ids = [uid for uid in talking_clients.keys() if uid != event.sender_id]
    if not available_ids:
        available_ids = list(talking_clients.keys())
        
    chosen_id = random.choice(available_ids)
    client = talking_clients[chosen_id]

    try:
        reply_text = None
        # 🎲 90% Reply ပြန်မည် ၊ 10% အလွတ်ဝင်ပြောမည်
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
            cursor_match = reply_save_col.aggregate(match_pipeline)
            matched_docs = await cursor_match.to_list(length=1)

            if matched_docs and matched_docs[0].get("responses"):
                reply_text = random.choice(matched_docs[0]["responses"])
            else:
                pipeline_fallback = [{"$sample": {"size": 1}}]
                cursor_fallback = reply_save_col.aggregate(pipeline_fallback)
                random_docs = await cursor_fallback.to_list(length=1)
                
                if random_docs and random_docs[0].get("responses"):
                    reply_text = random.choice(random_docs[0]["responses"])
                else:
                    cursor_talk = talk_col.aggregate(pipeline_fallback)
                    random_talk_docs = await cursor_talk.to_list(length=1)
                    reply_text = random_talk_docs[0].get("text") if random_talk_docs else None
        else:
            cursor_talk = talk_col.aggregate([{"$sample": {"size": 1}}])
            random_talk_docs = await cursor_talk.to_list(length=1)
            reply_text = random_talk_docs[0].get("text") if random_talk_docs else None

        if reply_text:
            # ⚡ [TURBO MODE] - စုစုပေါင်း ၅ စက္ကန့် ဝန်းကျင်ဖြစ်စေရန် ညှိထားသောအပိုင်း
            # Cooldown (၂.၅ မှ ၃.၅ စက္ကန့်) -> ပျှမ်းမျှ ၃ စက္ကန့်
            await asyncio.sleep(random.uniform(2.5, 3.5))
            
            # Typing Status (၁.၅ မှIDI ၂.၅ စက္ကန့်) -> ပျှမ်းမျှ ၂ စက္ကန့်
            async with client.action(TARGET_GROUP, 'typing'):
                await asyncio.sleep(random.uniform(1.5, 2.5))
            
            if should_reply:
                await client.send_message(TARGET_GROUP, reply_text, reply_to=event.id)
            else:
                await client.send_message(TARGET_GROUP, reply_text)

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
    global talking_clients, is_crosstalk_active, TARGET_GROUP
    
    cmd = event.message.text.strip() if event.message.text else ""

    # 📥 MULTI-BOT /string MANAGEMENT
    if cmd == "/string" and event.is_reply:
        reply_msg = await event.get_reply_message()
        if reply_msg and reply_msg.text:
            session_str = reply_msg.text.strip()
            
            current_count = await usertalking_col.count_documents({})
            if current_count >= 10:
                await event.reply("❌ **Chief! အကောင့်အရေအတွက် အများဆုံး (၁၀) ခု ပြည့်နေပါပြီဗျာ။**")
                return
                
            status_msg = await event.reply("⏳ String Session ကို စစ်ဆေးပြီး ချိတ်ဆက်နေပါသည် Chief...")
            
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

    # 🎯 GROUP ပြောင်းရွှေ့ပြီး ဝင်ရောက်ခြင်း (JOIN) စနစ်
    elif cmd.startswith("/သွားမယ်"):
        parts = cmd.split(maxsplit=1)
        target_link = ""
        
        if len(parts) > 1:
            target_link = parts[1].strip()
        elif event.is_reply:
            reply_msg = await event.get_reply_message()
            if reply_msg and reply_msg.text:
                target_link = reply_msg.text.strip()
                
        if not target_link:
            await event.reply("❌ **ကျေးဇူးပြု၍ Group Link ထည့်ပေးပါဗျာ Chief!**")
            return
            
        status_msg = await event.reply("⏳ Group Link ကို စစ်ဆေးပြီး အကောင့်များအားလုံး ဝင်ရောက်ရန် (Join) ကြိုးစားနေပါသည် Chief...")
        
        if not talking_clients:
            await status_msg.edit("❌ **Active ဖြစ်နေတဲ့ Userbot မရှိသေးပါဘူး Chief!**")
            return
            
        first_cl = list(talking_clients.values())[0]
        resolved_id = None
        
        try:
            if '+' in target_link or 'joinchat/' in target_link:
                hash_match = re.search(r'(?:\+|\/joinchat\/)([\w-]+)', target_link)
                if hash_match:
                    invite_hash = hash_match.group(1)
                    invite_info = await first_cl(CheckChatInviteRequest(invite_hash))
                    if hasattr(invite_info, 'chat') and invite_info.chat:
                        resolved_id = telethon.utils.get_peer_id(invite_info.chat)
            else:
                username = target_link.split('/')[-1].replace('@', '')
                entity = await first_cl.get_entity(username)
                resolved_id = telethon.utils.get_peer_id(entity)
        except Exception as ex:
            logging.error(f"Group Link Resolution Error: {ex}")
            
        joined_count = 0
        for uid, cl in talking_clients.items():
            try:
                if '+' in target_link or 'joinchat/' in target_link:
                    hash_match = re.search(r'(?:\+|\/joinchat\/)([\w-]+)', target_link)
                    if hash_match:
                        invite_hash = hash_match.group(1)
                        try:
                            await cl(ImportChatInviteRequest(invite_hash))
                            joined_count += 1
                        except errors.rpcerrorlist.UserAlreadyParticipantError:
                            joined_count += 1
                else:
                    username = target_link.split('/')[-1].replace('@', '')
                    await cl(JoinChannelRequest(username))
                    joined_count += 1
                await asyncio.sleep(2.0)
            except Exception as join_err:
                logging.error(f"Bot {uid} failed to join group: {join_err}")
                
        if resolved_id:
            TARGET_GROUP = resolved_id
            is_crosstalk_active = True 
            
            await status_msg.edit(f"✅ **Join ခြင်း အောင်မြင်ပါသည် Chief!**\n📊 အကောင့်ပေါင်း `{joined_count}` ခု ဝင်ရောက်ပြီးပါပြီ။\n🎯 Target ID: `{TARGET_GROUP}`\n⏳ စကားဝိုင်း အလိုအလျောက် စတင်ရန် Seed Message ပို့နေပါသည်...")
            
            try:
                await asyncio.sleep(3.0) 
                chosen_id = random.choice(list(talking_clients.keys()))
                client = talking_clients[chosen_id]
                cursor_talk = talk_col.aggregate([{"$sample": {"size": 1}}])
                random_talk_docs = await cursor_talk.to_list(length=1)
                seed_text = random_talk_docs[0].get("text") if random_talk_docs else "ဟယ်လို... အားလုံးပဲ မင်္ဂလာပါဗျာ။"
                await client.send_message(TARGET_GROUP, seed_text)
                await bot.send_message(OWNER_ID, "💬 🔥 **Seed Message အောင်မြင်စွာ ပို့ပြီးပါပြီ။ စကားဝိုင်း အရှိန်ပြင်းပြင်းဖြင့် လည်ပတ်နေပါပြီ Chief!**")
            except Exception as seed_err:
                logging.error(f"❌ Seed send error: {seed_err}")
                await bot.send_message(OWNER_ID, "⚠️ **Group ပြောင်းလဲမှု အောင်မြင်သော်လည်း စကားစရန် အခက်အခဲရှိသဖြင့် `/စကားပြော` ဟု တိုက်ရိုက်တစ်ချက် ရိုက်ပေးပါဗျာ။**")
        else:
            await status_msg.edit("❌ **Group ID ကို မရှာဖွေနိုင်ပါဘူးဗျာ။ Link ပြန်စစ်ပေးပါ Chief!**")

    # 💬 CROSSTALK START COMMAND
    elif cmd == "/စကားပြော":
        is_crosstalk_active = True
        await event.reply(f"💬 🔥 **Multi-Bot Perpetual Cross-Talk စနစ်ကို ID: `{TARGET_GROUP}` တွင် အမြန်နှုန်းဖြင့် အသစ်ပြန်လည် စတင်လိုက်ပါပြီ Chief!**")
        
        try:
            chosen_id = random.choice(list(talking_clients.keys()))
            client = talking_clients[chosen_id]
            cursor_talk = talk_col.aggregate([{"$sample": {"size": 1}}])
            random_talk_docs = await cursor_talk.to_list(length=1)
            seed_text = random_talk_docs[0].get("text") if random_talk_docs else "ဟယ်လို... အားလုံးပဲ မင်္ဂလာပါဗျာ။"
            await client.send_message(TARGET_GROUP, seed_text)
        except Exception as e:
            logging.error(f"❌ Failed to send starter seed message: {e}")

    # 🛑 CROSSTALK STOP COMMAND
    elif cmd == "/နား":
        if not is_crosstalk_active:
            await event.reply("⚠️ **စကားပြောစနစ်သည် ပိတ်ထားပြီးသား ဖြစ်ပါသည် Chief!**")
            return
            
        is_crosstalk_active = False
        await event.reply("🛑 **Chief ရဲ့ အမိန့်အရ စကားပြောစနစ်ကို ချက်ချင်း ရပ်တန့်လိုက်ပါပြီဗျာ။**")

# ==========================================
# 🚀 SYSTEM STARTUP LOGIC
# ==========================================
async def startup():
    global talking_clients
    logging.info("⏳ System starting up and loading Cross-Talk Simulator Engine...")
    
    asyncio.create_task(start_dummy_web_server())

    logging.info("⏳ Loading Simulator Accounts from MongoDB...")
    cursor_talkers = usertalking_col.find({})
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

