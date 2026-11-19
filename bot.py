import os, time, datetime, pathlib, subprocess, requests

PROVIDER = os.getenv("LLM_PROVIDER", "gemini")          # gemini | groq
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
GROQ_KEY = os.getenv("GROQ_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
TG = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED = os.getenv("ALLOWED_CHAT_ID")
REPO = pathlib.Path(os.getenv("REPO_DIR", os.getcwd()))

PROMPT = ("Turn this note into a short TIL markdown post: a title (## heading), "
          "3-5 sentence explanation, and one small code example only if relevant. "
          "Do not invent facts beyond the note.\n\nNOTE:\n")

def gemini(note):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    r = requests.post(url, params={"key": GEMINI_KEY}, timeout=60,
                      json={"contents": [{"parts": [{"text": PROMPT + note}]}]})
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]

def groq(note):
    r = requests.post("https://api.groq.com/openai/v1/chat/completions", timeout=60,
                      headers={"Authorization": f"Bearer {GROQ_KEY}"},
                      json={"model": GROQ_MODEL,
                            "messages": [{"role": "user", "content": PROMPT + note}]})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def ask_llm(note):
    order = [gemini, groq] if PROVIDER == "gemini" else [groq, gemini]
    keys = {gemini: GEMINI_KEY, groq: GROQ_KEY}
    last = None
    for fn in order:
        if not keys[fn]:
            continue
        try:
            return fn(note)
        except Exception as e:
            last = e
    raise RuntimeError(f"All providers failed: {last}")

def git(*args):
    subprocess.run(["git", *args], cwd=REPO, check=True)

def save_and_push(text):
    today = datetime.date.today().isoformat()
    path = REPO / "til" / f"{today}.md"
    stamp = datetime.datetime.now().strftime("%H:%M")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n<!-- {stamp} -->\n{text.strip()}\n")
    git("pull", "--rebase", "--autostash")
    git("add", "-A")
    git("commit", "-m", f"TIL {today} {stamp}")
    git("push")
    return path.name

def send(chat_id, text):
    requests.post(f"https://api.telegram.org/bot{TG}/sendMessage",
                  json={"chat_id": chat_id, "text": text}, timeout=30)

def main():
    offset = None
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{TG}/getUpdates",
                             params={"timeout": 50, "offset": offset}, timeout=70).json()
            for u in r.get("result", []):
                offset = u["update_id"] + 1
                m = u.get("message") or {}
                text, chat_id = m.get("text"), str(m.get("chat", {}).get("id"))
                if not text:
                    continue
                if not ALLOWED:
                    send(chat_id, f"Your chat id: {chat_id}\nSet ALLOWED_CHAT_ID to this and restart.")
                    continue
                if chat_id != ALLOWED:
                    continue
                if len(text.strip()) < 10:
                    send(chat_id, "Note too short. Write what you learned today.")
                    continue
                try:
                    name = save_and_push(ask_llm(text))
                    send(chat_id, f"Pushed til/{name}")
                except Exception as e:
                    send(chat_id, f"Failed: {e}")
        except Exception as e:
            print("loop error:", e)
            time.sleep(5)

main()
