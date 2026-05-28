import asyncio
import random
import logging
import os
import threading
from flask import Flask
from telethon import TelegramClient, events
from openai import OpenAI

# ==========================================
# 🌐 FLASK KEEP-ALIVE FOR RENDER (Port Fix)
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "BoD AI System is Active!"

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

# ==========================================
# ⚙️ CONFIGURATION & TOKENS
# ==========================================
GROQ_API_KEY = "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"
BOT_TOKEN = "8704743008:AAEpZ39-YyrziDy2DK7XmGoMDG5pAbc_h8Y"

# Telegram API Credentials
API_ID = 35766004
API_HASH = 'd15b4226b81724722279bae6af69e22d'

# Groq AI Client setup
ai_client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
)

# Bot Client Initialize
bot = TelegramClient('bod_ai_bot', API_ID, API_HASH)

# Group Status Memory
talk_status = {}
active_chats = set()  

logging.basicConfig(level=logging.INFO)

# ==========================================
# 🛡️ ADMIN CHECK FUNCTION
# ==========================================
async def is_admin(event):
    if event.is_private:
        return True
    try:
        permissions = await event.client.get_permissions(event.chat_id, event.sender_id)
        return permissions.is_admin or permissions.is_creator
    except Exception as e:
        print(f"Admin Check Error: {e}")
        return False

# ==========================================
# 💬 COMMANDS HANDLERS (/talkon & /talkoff)
# ==========================================
@bot.on(events.NewMessage(pattern=r'^/talkon'))
async def talk_on_handler(event):
    if not await is_admin(event):
        return  
        
    chat_id = event.chat_id
    talk_status[chat_id] = True
    active_chats.add(chat_id)
    
    border_on = (
        "┏━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        "┃    🤖 𝗕𝗼Ｄ 𝗔𝗜 𝗦𝗬𝗦𝗧𝗘𝗠 𝗢𝗡   ┃\n"
        "┗━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        "• Status: [ ENABLED ]\n"
        "• Notice: AI Chatbot is now active.\n"
        "• Action: Ready to engage in conversation."
    )
    await event.reply(border_on)

@bot.on(events.NewMessage(pattern=r'^/talkoff'))
async def talk_off_handler(event):
    if not await is_admin(event):
        return  
        
    chat_id = event.chat_id
    talk_status[chat_id] = False
    active_chats.add(chat_id)
    
    border_off = (
        "┏━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        "┃   📴 𝗕𝗼Ｄ 𝗔𝗜 𝗦𝗬𝗦𝗧𝗘𝗠 𝗢𝗙𝗙   ┃\n"
        "┗━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        "• Status: [ DISABLED ]\n"
        "• Notice: AI Chatbot is now muted.\n"
        "• Automated status report loop: 3 Hours."
    )
    await event.reply(border_off)

# ==========================================
# ⏰ 3-HOUR STATUS REMINDER LOOP
# ==========================================
async def reminder_loop():
    await bot.wait_until_ready()
    while True:
        # Wait for 3 Hours (3 * 3600 Seconds)
        await asyncio.sleep(3 * 3600)
        
        for chat_id in list(active_chats):
            status = talk_status.get(chat_id, False)
            
            if status:
                remind_msg = (
                    "╔══════════════════════════╗\n"
                    "  🔔 𝗕𝗼Ｄ 𝗦𝗬𝗦𝗧𝗘𝗠 👑𝗘𝗠𝗜𝗡𝗗𝗘𝗥\n"
                    "╚══════════════════════════╝\n"
                    "📢 Current Status: [ 🟢 TALK ON ]\n"
                    "🤖 AI Engine is running smoothly and listening."
                )
            else:
                remind_msg = (
                    "╔══════════════════════════╗\n"
                    "  🔔 𝗕𝗼Ｄ 𝗦𝗬𝗦𝗧𝗘𝗠 👑𝗘𝗠𝗜𝗡𝗗𝗘𝗥\n"
                    "╚══════════════════════════╝\n"
                    "📢 Current Status: [ 🔴 TALK OFF ]\n"
                    "📴 AI Engine is currently sleeping. Use /talkon to activate."
                )
                
            try:
                await bot.send_message(chat_id, remind_msg)
            except Exception as e:
                print(f"Reminder Error to {chat_id}: {e}")

# ==========================================
# 🤖 AI AUTO REPLY HANDLER
# ==========================================
@bot.on(events.NewMessage(incoming=True))
async def ai_chat_handler(event):
    if event.is_private:
        return
        
    if event.text and event.text.startswith('/'):
        return
        
    chat_id = event.chat_id
    
    if not talk_status.get(chat_id, False):
        return
        
    me = await bot.get_me()
    
    is_mentioned = event.mentioned  
    is_reply_to_bot = False
    
    if event.is_reply:
        reply_msg = await event.get_reply_message()
        if reply_msg and reply_msg.sender_id == me.id:
            is_reply_to_bot = True  
            
    # Trigger Conditions (Mention/Reply = 100% | Normal Chat = 15%)
    should_reply = is_mentioned or is_reply_to_bot or (random.random() < 0.15)
    
    if not should_reply:
        return

    context_messages = []
    
    # 🧠 ADVANCED SYSTEM PROMPT (Intellectual, Human-like Admin Persona)
    system_instruction = {
        "role": "system",
        "content": (
            "You are a highly intelligent, sophisticated, and respected senior admin/member of the 'Brotherhood of Dexter' (BoD) community. "
            "Your personality is a perfect blend of a sharp-witted human leader, an educated intellectual, and an approachable community mentor. "
            "Guidelines:\n"
            "1. Language: Always reply in natural, modern, and highly fluent Burmese (မြန်မာဘာသာ). "
            "2. Tone: Speak like a real, well-educated human admin. Avoid robotic text, generic AI pleasantries, or clichés. "
            "3. Style: Be articulate, perceptive, and witty. Use logic, emotion, and proper community context. "
            "4. Conciseness: Keep responses direct, sharp, and concise. Do not type overly long explanations unless highly necessary. "
            "Match the vibe of an elite human leader managing a smart community. Never reveal you are an AI model."
        )
    }
    context_messages.append(system_instruction)
    
    try:
        async for msg in bot.iter_messages(chat_id, limit=6):
            if msg.text and not msg.text.startswith('/'):
                role = "assistant" if msg.sender_id == me.id else "user"
                name = msg.sender.first_name if msg.sender and hasattr(msg.sender, 'first_name') else "User"
                context_messages.append({"role": role, "content": f"{name}: {msg.text}"})
                
        system_part = context_messages[0]
        chat_part = context_messages[1:]
        chat_part.reverse()
        final_messages = [system_part] + chat_part
        
        async with bot.action(chat_id, 'typing'):
            response = ai_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=final_messages,
                max_tokens=200,
                temperature=0.75
            )
            
            ai_reply = response.choices[0].message.content.strip()
            
            # Direct Reply without borders
            await event.reply(ai_reply)
            
    except Exception as e:
        print(f"Groq AI Error: {e}")

# ==========================================
# 🚀 RUN BOT SYSTEM
# ==========================================
async def main():
    # Render Port Timeout မဖြစ်အောင် Background Thread ဖြင့် Flask အား အရင်မောင်းနှင်မည်
    threading.Thread(target=run_flask, daemon=True).start()
    
    print("🚀 Starting BoD Bot System...")
    await bot.start(bot_token=BOT_TOKEN)
    
    # Run 3-Hour Reminder in background
    bot.loop.create_task(reminder_loop())
    
    print("✅ BoD Bot is fully Active!")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
