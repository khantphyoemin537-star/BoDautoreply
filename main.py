import asyncio
import os
import time
import threading
from datetime import datetime
from flask import Flask
from telethon import TelegramClient, events, Button
from telethon.tl.types import ChannelParticipantsAdmins
from pymongo import MongoClient

# ==========================================
# 🌐 0. FLASK SERVER FOR RENDER PORT BINDING
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "Admin Survey Manager Bot is Fully Online!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# ==========================================
# ⚙️ CONFIGURATION & TOKENS
# ==========================================
BOT_TOKEN = "8704743008:AAEpZ39-YyrziDy2DK7XmGoMDG5pAbc_h8Y"
API_ID = 35766004
API_HASH = 'd15b4226b81724722279bae6af69e22d'
OWNER_ID = 7693106830
TARGET_CHAT_ID = -1003580630981

# 🍃 MONGO DB CONNECTION
MONGO_URI = "mongodb+srv://khantphyoemin537_db_user:9VRKiaeZkz7rJdpz@cluster0.w6tgi8j.mongodb.net/?appName=Cluster0&tlsAllowInvalidCertificates=true"
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["cluster0"]
survey_col = db["admin_survey"] 

bot = TelegramClient('admin_survey_session', API_ID, API_HASH)

print("⚡ Admin Survey & Monitor System Initializing...")

# ==========================================
# 🕒 HELPER: GET CURRENT MYANMAR TIME SLOT
# ==========================================
def get_current_time_slot():
    current_hour = datetime.now().hour
    
    if 6 <= current_hour < 12:
        return "morning", "မနက်ပိုင်း (6AM - 12PM)"
    elif 12 <= current_hour < 16:
        return "afternoon", "နေ့လည်ပိုင်း (12PM - 4PM)"
    elif 16 <= current_hour < 19:
        return "evening", "ညနေပိုင်း (4PM - 7PM)"
    else:
        return "night", "ညပိုင်း (7PM - 6AM)"

# ==========================================
# 🛡️ HELPER: CHECK IF USER IS ADMIN
# ==========================================
async def is_group_admin(user_id):
    if user_id == OWNER_ID:
        return True
    try:
        permissions = await bot.get_permissions(TARGET_CHAT_ID, user_id)
        return permissions.is_admin
    except Exception:
        return False

# ==========================================
# 📢 TRIGGER SURVEY WITH ADJACENT MENTIONS (/survey)
# ==========================================
@bot.on(events.NewMessage(pattern=r'^/survey$'))
async def send_survey(event):
    if event.sender_id != OWNER_ID:
        return
        
    try:
        admins = await bot.get_participants(TARGET_CHAT_ID, filter=ChannelParticipantsAdmins)
        mention_list = []
        for adm in admins:
            if adm.bot:
                continue
            if adm.username:
                mention_list.append(f"@{adm.username}")
            else:
                mention_list.append(f"[{adm.first_name}](tg://user?id={adm.id})")
        
        adjacent_mentions = " ".join(mention_list) if mention_list else "Admin များအားလုံး"
    except Exception as e:
        print(f"Error fetching admins: {e}")
        adjacent_mentions = "Admin များအားလုံး"
        
    survey_text = (
        f"📊 **⚙️ ADMIN DAILY AVAILABILITY SURVEY** 📊\n\n"
        f"ဟေ့ကောင်တို့ရေ... ချက်ချင်း ထနှိပ်ကြစမ်း! 👇\n{adjacent_mentions}\n\n"
        f"ဒီနေ့အတွက် မင်းတို့ ဘယ်အချိန်တွေ အားကြလဲ? အားတဲ့အချိန်ကို အောက်က Button မှာ နှိပ်ပေးထားပါ။\n"
        f"နှိပ်ထားတဲ့အချိန်ကျလို့ Gp ထဲ စာမလာရိုက်ရင် ၃ ခါ တိတိ Mention အော်ပြီး အလှုပ်ခံရမယ်နော်! ⏳"
    )
    
    buttons = [
        [
            Button.inline("🌅 မနက်ပိုင်း", data="slot_morning"),
            Button.inline("☀️ နေ့လည်ပိုင်း", data="slot_afternoon")
        ],
        [
            Button.inline("🌆 ညနေပိုင်း", data="slot_evening"),
            Button.inline("🌃 ညပိုင်း", data="slot_night")
        ]
    ]
    
    await bot.send_message(TARGET_CHAT_ID, survey_text, buttons=buttons)
    if event.is_private:
        await event.reply("✅ Group ထဲကို စစ်တမ်း ထပ်မံပေးပို့လိုက်ပြီ ဆရာကြီး!")

# ==========================================
# 🔘 INLINE BUTTON CLICK HANDLER (FIXED)
# ==========================================
@bot.on(events.CallbackQuery(pattern=r'^slot_(.+)$'))
async def handle_survey_click(event):
    user_id = event.sender_id
    sender = await event.get_sender()
    
    if not await is_group_admin(user_id):
        await event.answer("❌ မင်း Admin မဟုတ်လို့ နှိပ်ခွင့်မရှိဘူး ငါ့ကောင်!", alert=True)
        return
        
    # 🎯 FIX: Telethon ရဲ့ Bytes Data ကို String အဖြစ်အသေပြောင်းလဲခြင်း
    try:
        raw_data = event.data.decode('utf-8') # e.g., "slot_morning"
        slot_key = raw_data.replace("slot_", "") # e.g., "morning"
    except Exception:
        slot_key = "unknown"
        
    slot_mapping = {
        "morning": "မနက်ပိုင်း",
        "afternoon": "နေ့လည်ပိုင်း",
        "evening": "ညနေပိုင်း",
        "night": "ညပိုင်း"
    }
    slot_text = slot_mapping.get(slot_key, "မသိရသောအချိန်")
    
    if slot_text == "မသိရသောအချိန်":
        # အပိုဆောင်း စစ်ဆေးချက်အရ တိုက်ရိုက် Regex Match ကိုပါ သုံးကြည့်မည်
        match_key = event.pattern_match.group(1)
        if isinstance(match_key, bytes):
            match_key = match_key.decode('utf-8')
        slot_text = slot_mapping.get(match_key, "မသိရသောအချိန်")
        slot_key = match_key
        
    today_str = datetime.now().strftime("%Y-%m-%d")
    username = sender.username if sender.username else ""
    display_name = sender.first_name if sender.first_name else "Admin"
    
    # DB ထဲ သမိုင်းမှတ်တမ်းသွင်းခြင်း
    survey_col.update_one(
        {"user_id": user_id, "date": today_str},
        {"$set": {
            "user_id": user_id,
            "username": username,
            "display_name": display_name,
            "chosen_slot": slot_key,
            "chosen_slot_text": slot_text,
            "warn_count": 0,
            "active_today": False,
            "last_warn_time": 0
        }},
        upsert=True
    )
    
    mention_str = f"@{username}" if username else f"[{display_name}](tg://user?id={user_id})"
    reply_msg = f"🎯 {mention_str} မင်း ဒီနေ့ **{slot_text}** အားတယ်လို့ မှတ်သားလိုက်ပြီ! အဲ့အချိန်ကျလို့ Gp ထဲ မလာရင် ၃ ခါ လှမ်းခေါ်မယ်။"
    
    await event.answer(f"✅ {slot_text} ကို မှတ်သားပြီးပြီ!", alert=False)
    await event.reply(reply_msg)

# ==========================================
# 💬 TRAFFIC MONITOR
# ==========================================
@bot.on(events.NewMessage(chats=TARGET_CHAT_ID))
async def monitor_admin_activity(event):
    user_id = event.sender_id
    today_str = datetime.now().strftime("%Y-%m-%d")
    current_slot, _ = get_current_time_slot()
    
    admin_record = survey_col.find_one({
        "user_id": user_id, 
        "date": today_str, 
        "chosen_slot": current_slot
    })
    
    if admin_record and not admin_record.get("active_today"):
        survey_col.update_one(
            {"_id": admin_record["_id"]},
            {"$set": {"active_today": True}}
        )

# ==========================================
# 🚨 ALERT ENGINE LOOP (LIVE ADMIN CHECK စနစ်ပါဝင်သည်)
# ==========================================
async def auto_alert_monitor_loop():
    while not bot.is_connected():
        await asyncio.sleep(5)
        
    print("⏰ Admin Monitoring Alert Engine Active with Live Verification...")
    
    while True:
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            current_slot, slot_text = get_current_time_slot()
            current_time = time.time()
            
            try:
                live_admins = await bot.get_participants(TARGET_CHAT_ID, filter=ChannelParticipantsAdmins)
                live_admin_ids = [adm.id for adm in live_admins if not adm.bot]
            except Exception as e:
                print(f"Error fetching live admins in loop: {e}")
                live_admin_ids = []

            unactive_admins = list(survey_col.find({
                "date": today_str,
                "chosen_slot": current_slot,
                "active_today": False,
                "warn_count": {"$lt": 3}
            }))
            
            to_mention_list = []
            
            for adm in unactive_admins:
                if live_admin_ids and (adm["user_id"] not in live_admin_ids):
                    continue
                    
                if current_time - adm.get("last_warn_time", 0) >= 2700:
                    new_warn_count = adm.get("warn_count", 0) + 1
                    
                    survey_col.update_one(
                        {"_id": adm["_id"]},
                        {"$set": {
                            "warn_count": new_warn_count,
                            "last_warn_time": current_time
                        }}
                    )
                    
                    if adm.get("username"):
                        m_str = f"@{adm['username']}"
                    else:
                        m_str = f"[{adm['display_name']}](tg://user?id={adm['user_id']})"
                        
                    to_mention_list.append(f"{m_str} ({new_warn_count}/3)")
            
            if to_mention_list:
                adjacent_mentions = " ".join(to_mention_list)
                alert_payload = (
                    f"🚨 **GP လာရမ်း သတိပေးချက်!**\n\n"
                    f"{adjacent_mentions}\n\n"
                    f"မင်းတို့တွေ ဒီအချိန် ({slot_text}) အားတယ်လို့ ပြောထားပြီး Gp ထဲ ပျောက်နေတယ်! ချက်ချင်း လာရမ်းကြတော့! ⚔️"
                )
                await bot.send_message(TARGET_CHAT_ID, alert_payload)
                
        except Exception as e:
            print(f"❌ Alert Loop Error: {e}")
            
        await asyncio.sleep(300)

# ==========================================
# 🏁 MAIN STARTUP
# ==========================================
async def main():
    await bot.start(bot_token=BOT_TOKEN)
    print("✅ Chaos Admin Survey Bot is fully live and listening!")
    
    asyncio.create_task(auto_alert_monitor_loop())
    await bot.run_until_disconnected()

if __name__ == '__main__':
    print("🌐 Starting Background Flask Server for Render Port Binding...")
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    asyncio.run(main())

