import os
import time
import asyncio
import random
import logging
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from motor.motor_asyncio import AsyncIOMotorClient

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
SPECIFIC_GROUP = -1003940667453


# MongoDB Connections
client_mongo = AsyncIOMotorClient(MONGO_URI)
db = client_mongo["telegram_bot"]
talk_col = db["random_talk"]         # Fallback စကားပြောစာသားရင်းမြစ်
reply_save_col = db["reply_save_col"] # 👈 Keyword & Triggers အဓိကသိမ်းဆည်းမည့် New Collection
usertalking_col = db["usertalking"]  # စကားပြောမည့် အကောင့်များသိမ်းဆည်းရာ Collection

# Global Runtime States
talking_clients = {}            # Live ဖြစ်နေသော Userbot Client object များ
is_crosstalk_active = False     # Cross-Talk စနစ် ပွင့်/ပိတ် Status

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
# 💬 🧠 INTELLIGENT CROSSTALK ENGINE (EVENT-DRIVEN)
# ==========================================
@bot.on(events.NewMessage(chats=SPECIFIC_GROUP))
async def on_group_discussion(event):
    global is_crosstalk_active, talking_clients
    
    # ၁။ စနစ်ပိတ်ထားလျှင် ဘာမှမလုပ်ပါ
    if not is_crosstalk_active:
        return

    # ၂။ စာသားမပါလျှင် ကျော်မည်
    user_text = event.message.text.strip().lower() if event.message.text else ""
    if not user_text:
        return

    # ၃။ Telegram Bot API (စက်ရုပ်တွေ) ပို့တဲ့စာဆိုလျှင် လျစ်လျူရှုမည်
    sender = await event.get_sender()
    if sender and sender.bot:
        return

    # ၄။ စကားပြောမည့် Active Userbot အနည်းဆုံး ၂ ခုရှိမှ အလုပ်လုပ်မည်
    bot_count = len(talking_clients)
    if bot_count < 2:
        return

    # ၅။ Active ဖြစ်နေသော အကောင့်များထဲမှ ကျပန်း တစ်ကောင့်ကို ရွေးချယ်၍ Reply ပြန်ခိုင်းမည်
    chosen_id = random.choice(list(talking_clients.keys()))
    client = talking_clients[chosen_id]

    # အကယ်၍ လက်ရှိစာပို့လိုက်သူက ၎င်းရွေးချယ်ခံရသည့် Bot ကိုယ်တိုင်ဖြစ်နေပါက (Self-reply မဖြစ်စေရန်) အခြား Bot တစ်ခုသို့ ပြောင်းမည်
    if sender and sender.id == chosen_id:
        available_ids = [uid for uid in talking_clients.keys() if uid != chosen_id]
        if available_ids:
            chosen_id = random.choice(available_ids)
            client = talking_clients[chosen_id]
        else:
            return

    try:
        reply_text = None
        
        # 🔍 STEP A: Trigger Keyword အား `reply_save_col` ထဲတွင် ရှာဖွေခြင်း (Length >= 3 & Regex Match)
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
            # 🔍 STEP B: အကယ်၍ Keyword မကိုက်ညီပါက 20% Chance Fallback Logic ဖြင့် စာသားကျပန်းဆွဲထုတ်မည်
            if random.random() < 0.20:  
                pipeline_fallback = [{"$sample": {"size": 1}}]
                cursor_fallback = reply_save_col.aggregate(pipeline_fallback)
                random_docs = await cursor_fallback.to_list(length=1)
                
                if random_docs and random_docs[0].get("responses"):
                    reply_text = random.choice(random_docs[0]["responses"])
                else:
                    # `reply_save_col` တွင်မရှိပါက `talk_col` မှ `text` ကို ဆွဲယူမည်
                    cursor_talk = talk_col.aggregate(pipeline_fallback)
                    random_talk_docs = await cursor_talk.to_list(length=1)
                    reply_text = random_talk_docs[0].get("text") if random_talk_docs else None
            else:
                return

        # ၆။ စာသားရရှိပါက လူအစစ်ကဲ့သို့ အချိန်ဆွဲပြီး Reply လှမ်းထောက်ပို့မည်
        if reply_text:
            # 🛡️ Anti-Flood & Natural Pacing Delay (စကားဝိုင်း အလွန်အမင်း မမြန်စေရန် ၄ မှ ၇ စက္ကန့်ကြား နားပေးမည်)
            await asyncio.sleep(random.uniform(4.0, 7.0))
            
            # စာရိုက်နေသည့် ပုံစံ (Typing status) ကို ပြသပေးခြင်း
            async with client.action(SPECIFIC_GROUP, 'typing'):
                await asyncio.sleep(random.uniform(1.5, 3.0))
            
            # ရွေးချယ်ခံရသည့် Userbot အကောင့်မှ စာကို တိုက်ရိုက် Reply ပြန်ထောက်၍ ပို့လိုက်ခြင်း
            await client.send_message(SPECIFIC_GROUP, reply_text, reply_to=event.id)

    except errors.rpcerrorlist.FloodWaitError as e:
        logging.warning(f"⚠️ FloodWait မိသွားပါပြီ။ {e.seconds} စက္ကန့် စောင့်ဆိုင်းနေပါသည်...")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        logging.error(f"❌ Auto-Reply Cross-Talk Error: {e}")

# ==========================================
# 🤖 OFFICIAL BOT COMMAND HANDLERS
# ==========================================
@bot.on(events.NewMessage(chats=SPECIFIC_GROUP, from_users=OWNER_ID))
async def handle_admin_commands(event):
    global talking_clients, is_crosstalk_active
    
    cmd = event.message.text.strip() if event.message.text else ""

    # 📥 MULTI-BOT /string MANAGEMENT
    if cmd == "/string" and event.is_reply:
        reply_msg = await event.get_reply_message()
        if reply_msg and reply_msg.text:
            session_str = reply_msg.text.strip()
            
            current_count = await usertalking_col.count_documents({})
            if current_count >= 10:
                await event.reply("❌ **Chief! စကားပြောမည့် အကောင့်အရေအတွက် အများဆုံး (၁၀) ခု ပြည့်နေပါပြီဗျာ။**")
                return
                
            status_msg = await event.reply("⏳ String Session ကို စစ်ဆေးပြီး ချိတ်ဆက်နေပါသည် Chief...")
            
            try:
                new_client = TelegramClient(StringSession(session_str), APP_ID, APP_HASH)
                await new_client.start()
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
        if is_crosstalk_active:
            await event.reply("⚠️ **စကားပြောစနစ်သည် လက်ရှိတွင် Active ဖြစ်နေပါသည် Chief!**")
            return
            
        if len(talking_clients) < 2:
            await event.reply("❌ **စကားပြောရန် အနည်းဆုံး အကောင့် (၂) ခု လိုအပ်ပါသည်။**\nကျေးဇူးပြု၍ `/string` ဖြင့် အကောင့်များ အရင်ထည့်ပေးပါဗျာ Chief။")
            return
            
        is_crosstalk_active = True
        await event.reply("💬 🔥 **Multi-Bot Intelligent Cross-Talk စနစ်ကို စတင်လိုက်ပါပြီ Chief!**\nယခုမှစ၍ အကောင့်များအချင်းချင်း Keyword အလိုက် အဆက်မပြတ် Reply ထောက်ပြီး စကားပြောပါတော့မည်။")
        
        # 🚀 စကားဝိုင်း အစပျိုး (Seed) ဖြစ်စေရန် Bot တစ်ခုဆီမှ ပထမဆုံးစာသားအား ကျပန်း စတင်ပို့ခိုင်းလိုက်ခြင်း
        try:
            chosen_id = random.choice(list(talking_clients.keys()))
            client = talking_clients[chosen_id]
            cursor_talk = talk_col.aggregate([{"$sample": {"size": 1}}])
            random_talk_docs = await cursor_talk.to_list(length=1)
            seed_text = random_talk_docs[0].get("text") if random_talk_docs else "ဟယ်လို... အားလုံးပဲ မင်္ဂလာပါဗျာ။"
            await client.send_message(SPECIFIC_GROUP, seed_text)
        except Exception as e:
            logging.error(f"❌ Failed to send starter seed message: {e}")

    # 🛑 CROSSTALK STOP COMMAND
    elif cmd == "/နား":
        if not is_crosstalk_active:
            await event.reply("⚠️ **စကားပြောစနစ်သည် ပိတ်ထားပြီးသား ဖြစ်ပါသည် Chief!**")
            return
            
        is_crosstalk_active = False
        await event.reply("🛑 **Chief ရဲ့ အမိန့်အရ စကားပြောစနစ် (Keyword Simulation) ကို ချက်ချင်း ရပ်တန့်လိုက်ပါပြီဗျာ။**")

# ==========================================
# 🚀 SYSTEM STARTUP LOGIC
# ==========================================
async def startup():
    global talking_clients
    logging.info("⏳ System starting up and loading Cross-Talk Simulator Engine...")
    
    # Render Web Server ကို Background မှာ မောင်းနှင်မည်
    asyncio.create_task(start_dummy_web_server())

    # Database ထဲမှ အကောင့်များအားလုံးကို Startup တွင် Auto-Login ပြုလုပ်ခြင်း
    logging.info("⏳ Loading Simulator Accounts from MongoDB (usertalking collection)...")
    cursor_talkers = usertalking_col.find({})
    async for doc in cursor_talkers:
        try:
            cl = TelegramClient(StringSession(doc["session"]), APP_ID, APP_HASH)
            await cl.start()
            talking_clients[doc["user_id"]] = cl
            logging.info(f"✅ Successfully loaded talker account: @{doc.get('username')}")
        except Exception as e:
            logging.error(f"⚠️ Failed to login talker account {doc.get('username')}: {e}")

    # Official Bot ကို စတင်လည်ပတ်ခြင်း
    await bot.start(bot_token=BOT_TOKEN)
    logging.info("🤖 Official Control Bot is running successfully...")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(startup())

