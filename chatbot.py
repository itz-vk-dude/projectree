import requests
from ml_engine import recommender

import os
from dotenv import load_dotenv

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


def get_chat_response(user_msg):
    msg = user_msg.lower()

    # 1. ALLOWED TOPIC FILTER (Strict Guard)
    ALLOWED_TOPICS = [
        "project",
        "code",
        "build",
        "resume",
        "job",
        "career",
        "engineer",
        "web",
        "ai",
        "iot",
        "data",
        "python",
        "javascript",
        "hardware",
        "software",
        "portfolio"]
    if not any(word in msg for word in ALLOWED_TOPICS) and len(msg) > 5:
        return "I am the Projectree Guide, specialized ONLY in Engineering Projects and Careers. Let's get back to your technical growth!"

    # 2. LOCAL CONTEXT (30,000 Projects)
    matches = recommender.get_recommendations(user_msg, top_n=1)
    context = f"(Context: Suggest the project '{matches[0]['title']}')" if matches else ""

    # 3. SECURE API CALL (Groq Llama-3)
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}",
               "Content-Type": "application/json"}

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "system",
                "content": """You are Projectree AI Career Assistant.
                RULES:
                1. ONLY discuss engineering projects, coding, resumes, and technical jobs.
                2. REJECT off-topic questions (food, sports, etc) with a professional refusal.
                3. Reply in Tamil if user uses Tamil, otherwise English.
                4. Be concise and use a senior developer tone."""
            },
            {"role": "user", "content": f"{user_msg} {context}"}
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        return response.json()['choices'][0]['message']['content']
    except BaseException:
        return "மன்னிக்கவும், AI உடன் இணைப்பதில் சிக்கல் உள்ளது. (Sorry, there is a connection error.)"
