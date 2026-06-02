import os
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
talk_col = db["random_talk"]     # စကားပြောစာသားရင်းမြစ် ၁
filters_col = db["filters"]       # စကားပြောစာသားရင်းမြစ် ၂
usertalking_col = db["usertalking"]  # 👈 စကားပြောမည့် အကောင့် (၂-၁၀) ခုအား သိမ်းဆည်းမည့် New Collection

# Global Runtime States
talking_clients = {}            # Live ဖြစ်နေသော Userbot Client object များကို Memory ထဲ သိမ်းဆည်းရန်
is_crosstalk_active = False     # Cross-Talk စနစ် ပွင့်/ပိတ် Status
crosstalk_task = None           # Background Loop လုပ်ဆောင်ချက်ကို ထိန်းချုပ်ရန် တာဝန်ခံ

# Initialize Official Bot
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
# 💬 BACKEND AUTOMATED CROSSTALK SIMULATOR LOOP
# ==========================================
async def run_crosstalk_loop():
    global is_crosstalk_active, talking_clients
    logging.info("💬 Cross-talk background loop successfully activated.")
    
    last_msg_id = None
    
    while is_crosstalk_active:
        bot_count = len(talking_clients)
        
        # အကောင့် (၂) ခုအောက် နည်းနေပါက ဆက်မပြောဘဲ စနစ်ရပ်တန့်မည်
        if bot_count < 2:
            await bot.send_message(SPECIFIC_GROUP, "⚠️ **Chief! စကားပြောရန် အနည်းဆုံး အကောင့် (၂) ခု လိုအပ်ပါသည်။**\nကျေးဇူးပြု၍ `/string` ဖြင့် ထပ်မံဖြည့်စွက်ပေးပါ။")
            is_crosstalk_active = False
            break
        
        # Active ဖြစ်နေတဲ့ Bot ထဲက တစ်ခုကို ကျပန်း ရွေးချယ်ခိုင်းခြင်း
        chosen_id = random.choice(list(talking_clients.keys()))
        client = talking_clients[chosen_id]
        
        try:
            # DB col ၂ ခုထဲက တစ်ခုခုကနေ ကျပန်းစာသား ဆွဲထုတ်ယူခြင်း
            chosen_col = random.choice([talk_col, filters_col])
            pipeline = [{"$sample": {"size": 1}}]
            cursor = chosen_col.aggregate(pipeline)
            docs = await cursor.to_list(length=1)
            
            reply_text = "🎯"  # Default fallback text
            if docs:
                # Field အမျိုးအစား မတူညီမှုများကို လိုက်ညှိဖတ်ခြင်း
                raw_text = docs[0].get("text") or docs[0].get("word") or docs[0].get("responses")
                if isinstance(raw_text, list) and raw_text:
                    reply_text = random.choice(raw_text)
                elif isinstance(raw_text, str) and raw_text:
                    reply_text = raw_text
            
            # Group ထဲက နောက်ဆုံး စာသား ID ကို ဆွဲထုတ်ပြီး Reply Chain စဉ်ဆက်မပြတ် ဆက်သွားစေရန်
            if not last_msg_id:
                async for m in client.iter_messages(SPECIFIC_GROUP, limit=1):
                    last_msg_id = m.id
            
            # ⚡ Dynamic Typing Delay Tuning (လူအစစ်တွေ စာရိုက်နေသလို ပုံစံဖမ်းခြင်း)
            # အကောင့်များလေ စကားပြောနှုန်း သွက်စေပြီး၊ အကောင့်နည်းရင် Flood မမိအောင် ပိုစောင့်ပါမည်
            base_typing_delay = max(2.5, 7.0 / bot_count)
            async with client.action(SPECIFIC_GROUP, 'typing'):
                await asyncio.sleep(random.uniform(base_typing_delay, base_typing_delay + 1.2))
            
            # စာသားကို အရှေ့က စာအပေါ် Reply ထောက်ပြီး လှမ်းပို့ခြင်း
            sent_msg = await client.send_message(
                SPECIFIC_GROUP,
                reply_text,
                reply_to=last_msg_id
            )
            last_msg_id = sent_msg.id  # နောက်ထပ် Bot က Reply ပြန်ထောက်နိုင်ရန် ID ကို Update လုပ်ခြင်း
            
        except errors.rpcerrorlist.FloodWaitError as e:
            logging.warning(f"⚠️ FloodWait Error Caught! Sleeping for {e.seconds} seconds.")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logging.error(f"❌ Crosstalk Interaction Error: {e}")
            last_msg_id = None  # Loop မပြတ်သွားစေရန် ID ကို reset လုပ်ပြီး ပြန်ချိတ်ခိုင်းခြင်း
            await asyncio.sleep(3)
            
        # 🛡️ Anti-Flood Global Cooldown Calculation (Telegram Group Spam filter ကျော်ရန်)
        # အကောင့် ၁၀ ခုအထိ အများဆုံးရှိရင် ၃ စက္ကန့်ကျော်စီနားပြီး၊ အကောင့် ၂ ခုပဲရှိရင် ၅ စက္ကန့်ကျော်စီ နားပေးပါမည်
        global_cooldown = max(3.0, random.uniform(4.5, 7.0) - (bot_count * 0.35))
        await asyncio.sleep(global_cooldown)

# ==========================================
# 🤖 OFFICIAL BOT COMMAND HANDLERS
# ==========================================
@bot.on(events.NewMessage(chats=SPECIFIC_GROUP, from_users=OWNER_ID))
async def handle_admin_commands(event):
    global talking_clients, is_crosstalk_active, crosstalk_task
    
    cmd = event.message.text.strip() if event.message.text else ""

    # 📥 MULTI-BOT /string MANAGEMENT (အနည်းဆုံး ၂ ခုမှ အများဆုံး ၁၀ ခုအထိ သိမ်းဆည်းရန်)
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
                
                # Database (usertalking_col) သို့ အသစ် သိမ်းဆည်း/အပ်ဒိတ် လုပ်ခြင်း
                await usertalking_col.update_one(
                    {"user_id": me.id},
                    {"$set": {"session": session_str, "username": me.username, "user_id": me.id}},
                    upsert=True
                )
                
                # Active Memory Map ထဲ ထည့်သွင်းခြင်း
                talking_clients[me.id] = new_client
                
                updated_count = await usertalking_col.count_documents({})
                await status_msg.edit(f"✅ **Account ချိတ်ဆက်မှု အောင်မြင်ပါသည် Chief!**\n👤 အကောင့်: @{me.username}\n📊 စုစုပေါင်းအကောင့်အရေအတွက်: `{updated_count}`/10 ခု ရှိသွားပါပြီ။")
            except Exception as e:
                await status_msg.edit(f"❌ Userbot ချိတ်ဆက်မှု ကျရှုံးပါသည်: {e}")

    # 💬 CROSSTALK START COMMAND
    elif cmd == "/စကားပြော":
        if is_crosstalk_active:
            await event.reply("⚠️ **စကားပြောစနစ်သည် လက်ရှိတွင် Run နေပါသည် Chief!**")
            return
            
        if len(talking_clients) < 2:
            await event.reply("❌ **စကားပြောရန် အနည်းဆုံး အကောင့် (၂) ခု လိုအပ်ပါသည်။**\nကျေးဇူးပြု၍ `/string` ဖြင့် အကောင့်များ အရင်ထည့်ပေးပါဗျာ Chief။")
            return
            
        is_crosstalk_active = True
        crosstalk_task = asyncio.create_task(run_crosstalk_loop())
        await event.reply("💬 🔥 **Multi-Bot Cross-Talk စနစ်ကို စတင်လိုက်ပါပြီ Chief!**\nအကောင့်များ အချင်းချင်း အဆက်မပြတ် Reply ထောက်ပြီး စကားပြောနေပါလိမ့်မည်။")

    # 🛑 CROSSTALK STOP COMMAND
    elif cmd == "/နား":
        if not is_crosstalk_active:
            await event.reply("⚠️ **စကားပြောစနစ်သည် ပိတ်ထားပြီးသား ဖြစ်ပါသည် Chief!**")
            return
            
        is_crosstalk_active = False
        if crosstalk_task:
            crosstalk_task.cancel()
        await event.reply("🛑 **Chief ရဲ့ အမိန့်အရ စကားပြောစနစ်ကို ချက်ချင်း ရပ်တန့်လိုက်ပါပြီဗျာ။**")

# ==========================================
# 🚀 SYSTEM STARTUP LOGIC
# ==========================================
async def startup():
    global talking_clients
    logging.info("⏳ System starting up and loading Cross-Talk Simulator Engine...")
    
    # Render Web Server ကို Background မှာ အရင်မောင်းထားမည်
    asyncio.create_task(start_dummy_web_server())

    # 📥 Database (usertalking) ထဲမှာ ရှိပြီးသား အကောင့်များအားလုံးကို Startup မှာ Auto-Login လုပ်ပြီး အဆင်သင့်ပြင်ခြင်း
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
