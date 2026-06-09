import logging
import re
from telethon import TelegramClient, events, Button

# Logging Setup
logging.basicConfig(level=logging.INFO)

# --- CONFIGURATION ---
API_ID = 31920527
API_HASH = '32009b7d9db347c3dce25ace64f87399'
BOT_TOKEN = '8922005521:AAEV0Sdb72DuWUxH5kgfF3gBAxwSlsnFy7c'

bot = TelegramClient('calc_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Calculator Layout (for /calc command)
def calc_keyboard(user_id):
    return [
        [Button.inline("C", f"C_{user_id}"), Button.inline("⌫", f"back_{user_id}"), Button.inline("(", f"(_{user_id}"), Button.inline(")", f")_{user_id}")],
        [Button.inline("7", f"7_{user_id}"), Button.inline("8", f"8_{user_id}"), Button.inline("9", f"9_{user_id}"), Button.inline("÷", f"/_{user_id}")],
        [Button.inline("4", f"4_{user_id}"), Button.inline("5", f"5_{user_id}"), Button.inline("6", f"6_{user_id}"), Button.inline("×", f"*_{user_id}")],
        [Button.inline("1", f"1_{user_id}"), Button.inline("2", f"2_{user_id}"), Button.inline("3", f"3_{user_id}"), Button.inline("-", f"-_{user_id}")],
        [Button.inline("0", f"0_{user_id}"), Button.inline(".", f"._{user_id}"), Button.inline("=", f"=_{user_id}"), Button.inline("+", f"+_{user_id}")]
    ]

# ========================================================
# ⚡ SYSTEM 1: AUTO-TEXT CALCULATOR (စာသားပို့ရုံဖြင့် အလိုအလျောက်တွက်ပေးသည့်စနစ်)
# ========================================================
@bot.on(events.NewMessage)
async def auto_text_calculator(event):
    # Command တွေဆိုရင် ဒီစနစ်ထဲကနေ ကျော်သွားမယ်
    if event.text.startswith('/'):
        return
        
    text = event.text.strip()
    if not text:
        return

    # လူသားတွေအသုံးများတဲ့ သင်္ကေတတွေကို ကုဒ်သင်္ကေတအဖြစ် ပြောင်းလဲခြင်း
    # ^ ကို Python ရဲ့ Power (**) အဖြစ်ပြောင်းပေးထားလို့ ဘယ်လောက်ကြီးတဲ့ထပ်ညွှန်းမဆို တွက်လို့ရမယ်
    math_expr = text.replace("÷", "/").replace("×", "*").replace("^", "**")

    # စာသားထဲမှာ သင်္ချာတွက်ချက်မှုဆိုင်ရာ သင်္ကေတတွေပဲ ပါ၊ မပါ စစ်ဆေးခြင်း (လုံခြုံရေးအရ)
    # ကိန်းဂဏန်းသီးသန့် (ဥပမာ "111") ပို့ရင် Reply မပြန်အောင် Operator တစ်ခုခုပါဝင်မှ အလုပ်လုပ်စေမယ်
    if re.match(r'^[0-9.+\-*/()%\s]+$', math_expr) and any(op in math_expr for op in "+-*/%"):
        try:
            # လွန်စွာကြီးမားသော ထပ်ညွှန်းများကြောင့် Bot Crash မဖြစ်စေရန် ကာကွယ်ခြင်း (ဥပမာ 9^9^9^9)
            if "**" in math_expr and len(math_expr) > 20:
                return

            # စိတ်ချရသော ပတ်ဝန်းကျင်တွင် တွက်ချက်ခြင်း
            result = eval(math_expr, {"__builtins__": None}, {})

            # အကယ်၍ အဖြေက ဒသမကိန်းဖြစ်ပြီး .0 နဲ့ဆုံးရင် (ဥပမာ 5.0) ဆိုရင် ကိန်းပြည့် (5) အဖြစ်ပြောင်းမယ်
            if isinstance(result, float) and result.is_integer():
                result = int(result)

            # မင်းတောင်းဆိုထားတဲ့ ပုံစံအတိုင်း ပို့ပေးခြင်း
            reply_text = (
                f"`{text} = {result}`\n\n"
                f"📣 For support - @Rashxdl"
            )
            await event.reply(reply_text)
            
        except Exception:
            # သင်္ချာပုံစံမှားနေရင် (ဥပမာ 111++2) စကားပြောခန်းတွေထဲမှာ ရှုပ်မသွားအောင် ငြိမ်နေပေးမယ်
            pass

# ========================================================
# ⚡ SYSTEM 2: INTERACTIVE CALCULATOR (ခလုတ်နှိပ်တွက်လိုသူများအတွက်)
# ========================================================
@bot.on(events.NewMessage(pattern=r'(?i)^/(start|calc)'))
async def start_calc(event):
    user_id = event.sender_id
    user = await event.get_sender()
    first_name = user.first_name if user else "User"
    
    text = (
        f"📱 **INTERACTIVE CALCULATOR**\n"
        f"👤 **Owner:** [{first_name}](tg://user?id={user_id})\n"
    )
    
    if event.is_private:
        text += f"💼 For business - @Rashxdl\n💡 Use \" + - * / \"\n"
        
    text += (
        f"⚡ ━━━━━━━━━━━━━━━━━━━━ ⚡\n"
        f"🔢 **Expression:** `0`\n\n"
        f"📣 For support - @Rashxdl"
    )
    await event.respond(text, buttons=calc_keyboard(user_id))

@bot.on(events.CallbackQuery)
async def handle_calc(event):
    data = event.data.decode('utf-8')
    msg = await event.get_message()
    
    if "_" in data:
        action, allowed_user_id = data.split("_", 1)
        allowed_user_id = int(allowed_user_id)
    else:
        action = data
        allowed_user_id = None

    if allowed_user_id and event.sender_id != allowed_user_id:
        await event.answer("⚠️ ဒီ Calculator က တခြားသူ ဖွင့်ထားတာမို့လို့ မင်းနှိပ်လို့မရပါဘူးခင်ဗျာ။", alert=True)
        return
    
    match = re.search(r'`([^`]*)`', msg.text)
    if match:
        current_expr = match.group(1).strip()
    else:
        current_expr = "0"

    if current_expr == "0":
        current_expr = ""

    if action == "C":
        new_expr = "0"
    elif action == "back":
        new_expr = current_expr[:-1] if len(current_expr) > 0 else "0"
        if not new_expr:
            new_expr = "0"
    elif action == "=":
        if "=" in current_expr or "Error" in current_expr:
            await event.answer()
            return
        try:
            math_expr = current_expr.replace("÷", "/").replace("×", "*")
            if any(char not in "0123456789+-*/(). " for char in math_expr):
                raise ValueError()
            result = eval(math_expr, {"__builtins__": None}, {})
            new_expr = f"{current_expr} = {result}"
        except Exception:
            new_expr = "Error"
    else:
        if "Error" in current_expr or "=" in current_expr:
            if action in ["+", "-", "/", "*"]:
                try:
                    current_expr = current_expr.split("=")[1].strip()
                except:
                    current_expr = ""
            else:
                current_expr = ""
        new_expr = current_expr + action

    display_expr = new_expr.replace("/", "÷").replace("*", "×")
    if not display_expr:
        display_expr = "0"

    try:
        lines = msg.text.split("\n")
        owner_line = [l for l in lines if "Owner:" in l][0]
    except Exception:
        owner_line = "👤 **Owner:** User"

    new_text = (
        f"📱 **INTERACTIVE CALCULATOR**\n"
        f"{owner_line}\n"
    )
    
    if event.is_private:
        new_text += f"💼 For business - @Rashxdl\n💡 Use \" + - * / \"\n"
        
    new_text += (
        f"⚡ ━━━━━━━━━━━━━━━━━━━━ ⚡\n"
        f"🔢 **Expression:** `{display_expr}`\n\n"
        f"📣 For support - @Rashxdl"
    )

    if msg.text != new_text:
        try:
            await event.edit(new_text, buttons=calc_keyboard(allowed_user_id))
        except Exception:
            pass
    await event.answer()

print("⚡ Super Calculator Bot is running perfectly with Auto-Text Engine...")
bot.run_until_disconnected()
