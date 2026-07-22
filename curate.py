import json
import os
import time
import logging
import datetime
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Setup logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename=f"logs/curate_{datetime.datetime.now(datetime.timezone.utc).date().isoformat()}.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger("").addHandler(console)

RAW_ITEMS_FILE = "data/raw_items.json"
CURATED_ITEMS_FILE = "data/curated_items.json"

SYSTEM_PROMPT = """You are a senior AI architect curating a newsletter for AI builders and developers.
You will receive a list of recent items from arXiv, Hacker News, GitHub, and Reddit.
Your task is to select the TOP 6 to 8 most impactful items from the list and group them into three categories: 'Tools', 'Research', and 'Agents'.

For each selected item, you MUST provide:
1. "title": The title of the item.
2. "url": The exact URL provided in the input.
3. "category": One of "Tools", "Research", or "Agents".
4. "summary": A 2-3 sentence technical summary.
5. "why_it_matters": A single sentence explaining "why it matters for builders".

You must output ONLY valid JSON in the following format, with no markdown formatting outside the JSON block:
{
  "curated_items": [
    {
      "title": "...",
      "url": "...",
      "category": "...",
      "summary": "...",
      "why_it_matters": "..."
    }
  ]
}
"""

def call_groq_with_backoff(client, prompt, max_retries=5):
    delay = 2
    for attempt in range(max_retries):
        try:
            logging.info(f"Calling Groq API (Attempt {attempt+1}/{max_retries})...")
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            return completion.choices[0].message.content
        except Exception as e:
            logging.warning(f"Groq API error: {e}")
            if attempt < max_retries - 1:
                logging.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2
            else:
                logging.error("Max retries reached for Groq API.")
                raise e

def main():
    if not os.path.exists(RAW_ITEMS_FILE):
        logging.warning(f"{RAW_ITEMS_FILE} not found. Nothing to curate.")
        return
        
    with open(RAW_ITEMS_FILE, "r", encoding="utf-8") as f:
        raw_items = json.load(f)
        
    if not raw_items:
        logging.info("No new items to curate.")
        with open(CURATED_ITEMS_FILE, "w", encoding="utf-8") as f:
            json.dump({"curated_items": []}, f, indent=2)
        return
        
    # We may want to truncate raw_items if there are too many to fit in context.
    # Llama-3.3-70b has 128k context, so 200 items is well within limits.
    max_items = 150
    if len(raw_items) > max_items:
        logging.info(f"Truncating {len(raw_items)} items to {max_items} for the prompt.")
        raw_items = raw_items[:max_items]
        
    # Format the user prompt
    items_text = json.dumps(raw_items, indent=2)
    user_prompt = f"Here are the recent items to evaluate:\n\n{items_text}"
    
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logging.error("GROQ_API_KEY environment variable is not set.")
        return
        
    client = Groq(api_key=api_key)
    
    try:
        response_text = call_groq_with_backoff(client, user_prompt)
        curated_data = json.loads(response_text)
        
        logging.info(f"Successfully curated {len(curated_data.get('curated_items', []))} items.")
        
        with open(CURATED_ITEMS_FILE, "w", encoding="utf-8") as f:
            json.dump(curated_data, f, indent=2)
            
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse Groq response as JSON: {e}\nResponse: {response_text}")
    except Exception as e:
        logging.error(f"Curation failed: {e}")

if __name__ == "__main__":
    main()
