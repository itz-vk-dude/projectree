import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY")


def generate_project_ideas(domain, level, technologies):
    """
    Generate AI-based project ideas safely using OpenRouter API
    """

    # Check API key first
    if not API_KEY:
        return """
⚠️ API Key Missing

Please check your .env file:
OPENROUTER_API_KEY=your_key_here
"""

    # Prompt
    prompt = f"""
Generate 5 unique project ideas.

Domain: {domain}
Level: {level}
Technologies: {technologies}

Return strictly in this format:

1. Project Title:
   Description:
   Technologies:

2. Project Title:
   Description:
   Technologies:
"""

    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "openrouter/auto",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=data,
            timeout=30
        )

        if response.status_code != 200:
            return f"""
⚠️ API Error

Status Code: {response.status_code}
Response: {response.text}
"""

        result = response.json()

        if "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["message"]["content"]

        else:
            return """
⚠️ Unexpected API Response

No project ideas returned.
"""

    except requests.exceptions.Timeout:
        return """
⚠️ Request Timed Out

The server took too long to respond.
Try again later.
"""

    except requests.exceptions.ConnectionError:
        return """
⚠️ Connection Error

Check your internet connection.
"""

    except Exception as e:
        print("AI Error:", e)

        return f"""
⚠️ AI Generation Failed

Error:
{str(e)}

Check:
• Internet connection
• API Key
• OpenRouter credits
"""
