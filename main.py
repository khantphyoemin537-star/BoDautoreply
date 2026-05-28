import asyncio
import random
import json
import time
import requests
import os
import threading
from flask import Flask
from datetime import datetime
from telethon import TelegramClient, events
from pymongo import MongoClient

# ==========================================
# 🌐 0. DUMMY FLASK SERVER FOR RENDER PORT BINDING
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "Chaos Master Bot is fully online and keeping the loop alive!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# ==========================================
# ⚙️ CONFIGURATION & TOKENS
# ==========================================
MAIN_BOT_TOKEN = "8704743008:AAEpZ39-YyrziDy2DK7XmGoMDG5pAbc_h8Y"
API_ID = 35766004
API_HASH = 'd15b4226b81724722279bae6af69e22d'
OWNER_ID = 7693106830             # ✅ မင်းရဲ့ Telegram ID
TARGET_CHAT_ID = -1003580630981  # ✅ မင်းရဲ့ 8k Group ID

# 🐙 GitHub Models API Configuration (GPT-4o-mini)
AI_API_KEY = "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" 
AI_URL = "https://models.inference.ai.azure.com/chat/completions"
MODEL_NAME = "gpt-4o-mini"

# 🍃 MONGO DB
MONGO_URI = "mongodb+srv://khantphyoemin537_db_user:9VRKiaeZkz7rJdpz@cluster0.w6tgi8j.mongodb.net/?appName=Cluster0&tlsAllowInvalidCertificates=true"
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["cluster0"]

talker_col = db["talker"]
bots_col = db["bot_tokens"] 

bot = TelegramClient('chaos_master_bot', API_ID, API_HASH)
style_guide = "မြန်မာဆန်ဆန်၊ လူငယ်ဆန်ဆန် စကားပြောပါ။ စာလုံးပေါင်း သိပ်မမှန်လည်း ရသည်။"
LAST_MESSAGE_TIME = time.time()  

print("🍃 Database and Main Bot Initialized...")

# ==========================================
# 🛠️ HELPER FUNCTION: BOT API SENDER
# ==========================================
async def bot_speak(token, chat_id, text, typing_time=3):
    loop = asyncio.get_event_loop()
    
    action_url = f"https://api.telegram.org/bot{token}/sendChatAction"
    try:
        await loop.run_in_executor(None, lambda: requests.post(action_url, json={"chat_id": chat_id, "action": "typing"}, timeout=5))
    except Exception:
        pass
        
    await asyncio.sleep(typing_time) 
    
    msg_url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        await loop.run_in_executor(None, lambda: requests.post(msg_url, json={"chat_id": chat_id, "text": text}, timeout=10))
    except Exception as e:
        print(f"❌ Bot Send Message Error: {e}")

# ==========================================
# 📥 ၁။ ADD NEW BOT TOKEN (/addbot)
# ==========================================
@bot.on(events.NewMessage(pattern=r'^/addbot\s+(.+)$'))
async def add_bot_token(event):
    if not event.is_private or event.sender_id != OWNER_ID:
        return
        
    new_token = event.pattern_match.group(1).strip()
    if ":" not in new_token:
        await event.reply("❌ Bot Token ပုံစံ မှားနေပါတယ် ဆရာကြီး။")
        return
        
    bot_id = int(new_token.split(":")[0])
    
    bots_col.update_one(
        {"bot_id": bot_id},
        {"$set": {"bot_id": bot_id, "token": new_token, "active": True}},
        upsert=True
    )
    await event.reply("✅ Bot Token အသစ်ကို Database ထဲ သေသေချာချာ မှတ်သားလိုက်ပြီ ငါ့ကောင်!")

# ==========================================
# 📝 ၂။ LEARN CONVERSATION STYLE (/learnon)
# ==========================================
@bot.on(events.NewMessage(pattern=r'^/learnon$'))
async def learn_style(event):
    if event.sender_id != OWNER_ID:
        return
        
    global style_guide
    await event.reply("🔄 talker collection ထဲက ဒေတာတွေကို AI က ခေါင်းထဲ ထည့်နေပါတယ်...")
    
    samples = list(talker_col.find({}, {"user_message": 1}).sort("_id", -1).limit(50))
    
    if samples:
        phrases = [doc.get("user_message", "") for doc in samples if doc.get("user_message")]
        style_guide = f"မြန်မာလူငယ်တွေရဲ့ စကားပြောဟန် နမူနာများ- {', '.join(phrases[:30])}။ ဒီလို ပုံစံအတိုင်း ရောနှောပြီး ပေါ့ပေါ့ပါးပါး ရေးပါ။"
        await event.reply("🎯 အတုယူစနစ် (Learning Style) အောင်မြင်စွာ Update ဖြစ်သွားပြီ!")
    else:
        await event.reply("⚠️ talker collection ထဲမှာ ဒေတာရှာမတွေ့လို့ ပုံမှန် ပုံစံအတိုင်းပဲ သွားပါမယ်။")

# ==========================================
# 🔮 ၃။ CORE DEBATE ENGINE
# ==========================================
async def generate_and_run_debate(chat_id, topic, trigger_event=None):
    active_bots = list(bots_col.find({"active": True}))
    if not active_bots:
        if trigger_event:
            await trigger_event.reply("❌ စကားပြောဖို့ Bot တွေ မရှိသေးပါဘူး။")
        return
        
    num_bots = len(active_bots)
    if trigger_event:
        await trigger_event.reply(f"🚀 Bot {num_bots} ကောင်နဲ့ စကားဝိုင်းကို ဇာတ်ညွှန်းဆွဲနေပြီ...")

    prompt = f"""
    You are a professional simulation engine. Generate a realistic group chat debate in Burmese script between {num_bots} distinct bot users.
    Topic: {topic}
    Style Guide (Mimic these typing manners): {style_guide}
    
    Rules:
    1. Output MUST be valid JSON only. Do not include any conversational text outside JSON.
    2. Total messages should be between 5 to 8 messages (Keep it short and punchy so it doesn't flood).
    3. It must have a clean conclusion at the end where they finish the topic naturally.
    4. Format must look exactly like this:
    [
        {{"bot_index": 0, "text": "စကားသား"}},
        {{"bot_index": 1, "text": "ပြန်ငြင်းတဲ့စာသား"}},
        {{"bot_index": 0, "text": "နိဂုံးချုပ်စာသား"}}
    ]
    """
    
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"}
    }
    
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: requests.post(AI_URL, headers=headers, json=payload, timeout=30))
        res_data = response.json()
        
        # 🔍 [အသစ်ပြင်ဆင်ချက်] GitHub က ဘာ Error ပေးလဲဆိုတာ ဖော်ထုတ်စစ်ဆေးသည့်အပိုင်း
        if "choices" not in res_data:
            error_details = res_data.get("error", res_data)
            print(f"❌ GitHub API Raw Error: {res_data}")
            if trigger_event:
                await trigger_event.reply(f"❌ GitHub AI ကနေ အကြောင်းပြန်ချက် ငြင်းပယ်ခံရသည် -\n`{error_details}`")
            return
            
        raw_content = res_data['choices'][0]['message']['content']
        script_data = json.loads(raw_content)
        conversation = script_data.get("conversation", script_data) if isinstance(script_data, dict) else script_data
        
    except Exception as e:
        print(f"❌ AI Model Query Error: {e}")
        if trigger_event:
            await trigger_event.reply(f"❌ AI Model Query စနစ် ချို့ယွင်းချက်- {e}")
        return

    for turn in conversation:
        bot_idx = turn.get("bot_index", 0)
        msg_text = turn.get("text", "")
        
        if bot_idx >= num_bots or not msg_text:
            continue
            
        current_bot_token = active_bots[bot_idx]["token"]
        await bot_speak(current_bot_token, chat_id, msg_text, typing_time=random.randint(2, 4))
        await asyncio.sleep(random.randint(6, 12))

# ==========================================
# ⚔️ ၄။ TRIGGER DRAMA DISCUSSION (/letstalk)
# ==========================================
@bot.on(events.NewMessage(pattern=r'^/letstalk\s+(.+)$'))
async def let_s_talk(event):
    if event.sender_id != OWNER_ID:
        return
    topic = event.pattern_match.group(1).strip()
    await generate_and_run_debate(event.chat_id, topic, trigger_event=event)

# ==========================================
# 🔄 ၅။ TRAFFIC MONITOR (စာဝင်မှု စောင့်ကြည့်ခြင်း + 3% Chime-in)
# ==========================================
@bot.on(events.NewMessage(chats=TARGET_CHAT_ID))
async def monitor_group_activity(event):
    global LAST_MESSAGE_TIME
    
    active_bots = list(bots_col.find({"active": True}, {"bot_id": 1}))
    our_bot_ids = [b["bot_id"] for b in active_bots]
    
    if event.sender_id not in our_bot_ids:
        LAST_MESSAGE_TIME = time.time()
        
        if random.random() < 0.03: 
            asyncio.create_task(random_chime_in(event.chat_id, active_bots))

# ==========================================
# 🤫 ၆။ RANDOM CHIME-IN (လူရှုပ်ချိန် ကြားဖြတ် ဝင်ပြောခြင်း)
# ==========================================
async def random_chime_in(chat_id, active_bots):
    if not active_bots: return
    
    random_doc = list(talker_col.aggregate([{"$sample": {"size": 1}}]))
    if not random_doc: return
    
    db_phrase = random_doc[0].get("user_message", "")
    if not db_phrase: return
    
    prompt = f"မင်းက Telegram Group ထဲက အဖွဲ့ဝင် Bot တစ်ခုပဲ။ ဒီစာသားရဲ့ စကားပြောဟန်အတိုင်း မြန်မာလူငယ်စတိုင် တိုတိုတုတ်တုတ် စာတစ်ကြောင်းပဲ ပြန်တုံ့ပြန်ပေးပါ (စာသားသက်သက်ပဲပေးပါ)- '{db_phrase}'"
    
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}]
    }
    
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: requests.post(AI_URL, headers=headers, json=payload, timeout=15))
        res_data = response.json()
        
        if "choices" in res_data:
            ai_reply = res_data['choices'][0]['message']['content'].strip()
            chosen_bot_data = random.choice(active_bots)
            full_bot = bots_col.find_one({"bot_id": chosen_bot_data["bot_id"]})
            
            if full_bot:
                await bot_speak(full_bot["token"], chat_id, ai_reply, typing_time=random.randint(2, 3))
    except Exception as e:
        print(f"Chime-in Error: {e}")

# ==========================================
# ⏰ ၇။ BACKGROUND IDLE CHATTER LOOP (လူရှင်းချိန် စကားစမြည်ပြောခြင်း)
# ==========================================
async def background_chatter_loop():
    global LAST_MESSAGE_TIME 
    
    while not bot.is_connected():
        await asyncio.sleep(5)
        
    print("⏰ Background Idle Chatter Loop Started Successfully...")
    
    while True:
        current_time = time.time()
        idle_duration = current_time - LAST_MESSAGE_TIME
        
        if idle_duration >= 120: 
            print("💤 Group is dead. Triggering AI conversation to revive it...")
            
            random_docs = list(talker_col.aggregate([{"$sample": {"size": 3}}]))
            seeds = [d.get("user_message", "") for d in random_docs if d.get("user_message")]
            
            if seeds:
                seed_topic = f"မြန်မာလူငယ်တွေ စိတ်ဝင်စားတတ်တဲ့ အကြောင်းအရာများ နှင့် စကားစုများ- {', '.join(seeds)}"
                await generate_and_run_debate(TARGET_CHAT_ID, seed_topic)
                
            LAST_MESSAGE_TIME = time.time()
            
        await asyncio.sleep(300) 

# ==========================================
# 🏁 ၈။ MAIN STARTUP EXTRACTION WITH AUTO-SEED
# ==========================================
async def main():
    await bot.start(bot_token=MAIN_BOT_TOKEN)
    print("✅ Chaos Catalyst Master Bot is fully online!")
    
    provided_tokens = [
        "8704743008:AAEpZ39-YyrziDy2DK7XmGoMDG5pAbc_h8Y",
        "8111794244:AAGpkLE7h5x_IYFvjkVCbJosDC1TFbCGxcQ"
    ]
    for t in provided_tokens:
        b_id = int(t.split(":")[0])
        bots_col.update_one({"bot_id": b_id}, {"$set": {"bot_id": b_id, "token": t, "active": True}}, upsert=True)
    print("📦 Database pre-seeded with your 2 Bot Tokens.")
    
    asyncio.create_task(background_chatter_loop()) 
    await bot.run_until_disconnected()

if __name__ == '__main__':
    print("🌐 Starting Background Flask Server for Render...")
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    asyncio.run(main())

