import base64
import json
import os
import re
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

# ============================================================
# CartFlex Core
# Public ugly beta version
#
# - Local JSON storage
# - Upload image saving
# - OpenAI vision calls
# - App-side beta scan limit
# - Safer local/Streamlit secrets handling
# - Feed, comments, likes, reactions
# ============================================================

load_dotenv()

APP_NAME = "CartFlex"

BASE_DIR = Path(".")
DATA_DIR = BASE_DIR / "data"
HAULS_DIR = DATA_DIR / "hauls"
UPLOADS_DIR = DATA_DIR / "uploads"
BETA_STATE_FILE = DATA_DIR / "beta_state.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
HAULS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# Safe config / secrets
# ============================================================

def get_secret_or_env(name, default=""):
    """
    Reads from environment first, then Streamlit secrets if available.
    Does NOT crash locally if no .streamlit/secrets.toml exists.
    """
    value = os.getenv(name)
    if value not in [None, ""]:
        return value

    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


OPENAI_API_KEY = get_secret_or_env("OPENAI_API_KEY", "")
CARTFLEX_MODEL = get_secret_or_env("CARTFLEX_MODEL", "gpt-4.1-mini")
CARTFLEX_MAX_ANALYSES = int(get_secret_or_env("CARTFLEX_MAX_ANALYSES", "40"))
CARTFLEX_PUBLIC_BETA = str(
    get_secret_or_env("CARTFLEX_PUBLIC_BETA", "true")
).lower() in ["1", "true", "yes", "y"]

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


# ============================================================
# Basic helpers
# ============================================================

def money(value):
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "$0.00"


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def safe_int(value, default=0):
    try:
        if value is None:
            return default
        return int(float(value))
    except Exception:
        return default


def clamp(value, low, high):
    try:
        value = float(value)
    except Exception:
        value = low
    return max(low, min(high, value))


def compact_number(n):
    n = safe_float(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(int(n))


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def time_ago_text(saved_at):
    if not saved_at:
        return "just now"

    try:
        dt = datetime.fromisoformat(saved_at)
        now = datetime.now()
        diff = now - dt

        minutes = diff.total_seconds() / 60
        hours = minutes / 60
        days = hours / 24

        if minutes < 1:
            return "just now"
        if minutes < 60:
            return f"{int(minutes)}m ago"
        if hours < 24:
            return f"{int(hours)}h ago"
        return f"{int(days)}d ago"
    except Exception:
        return "recently"


def new_post_id():
    return str(uuid.uuid4())[:8]


# ============================================================
# Beta limits / public safety
# ============================================================

def load_beta_state():
    if not BETA_STATE_FILE.exists():
        return {
            "analysis_count": 0,
            "created_at": now_iso(),
            "last_analysis_at": "",
        }

    try:
        with open(BETA_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "analysis_count" not in data:
            data["analysis_count"] = 0
        if "created_at" not in data:
            data["created_at"] = now_iso()
        if "last_analysis_at" not in data:
            data["last_analysis_at"] = ""

        return data
    except Exception:
        return {
            "analysis_count": 0,
            "created_at": now_iso(),
            "last_analysis_at": "",
        }


def save_beta_state(state):
    with open(BETA_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def beta_analysis_count():
    return safe_int(load_beta_state().get("analysis_count", 0))


def beta_remaining_analyses():
    return max(0, CARTFLEX_MAX_ANALYSES - beta_analysis_count())


def beta_can_analyze():
    return beta_remaining_analyses() > 0


def increment_beta_analysis_count():
    state = load_beta_state()
    state["analysis_count"] = safe_int(state.get("analysis_count", 0)) + 1
    state["last_analysis_at"] = now_iso()
    save_beta_state(state)
    return state["analysis_count"]


def render_public_beta_notice():
    st.warning(
        "Ugly public beta: only upload images you are comfortable sharing with testers. "
        "Cover or crop receipt membership numbers, addresses, phone numbers, payment info, "
        "barcodes, QR codes, and anything private. Selfies are optional."
    )

    remaining = beta_remaining_analyses()
    st.caption(
        f"Beta AI scans remaining tonight: {remaining}/{CARTFLEX_MAX_ANALYSES}. "
        "Comments and reactions do not use AI."
    )


def render_upload_consent_checkbox(key):
    return st.checkbox(
        "I reviewed my images, covered private info, and understand this beta may show my upload/results to testers.",
        key=key,
    )


# ============================================================
# Category helpers
# ============================================================

def normalize_category(category):
    if category == "Skincare / Cosmetics Haul":
        return "Stay Beautiful"
    if category == "Meal Prep Haul":
        return "Feed an Army"
    if category == "Pantry / Fridge Haul":
        return "Feed an Army"
    if category == "Costco Grocery Haul":
        return "Top Cart"
    return category or "Top Cart"


def get_category_icon(category):
    category = normalize_category(category)

    if category == "Stay Beautiful":
        return "✨"
    if category == "Feed an Army":
        return "👨‍👩‍👧"
    if category == "Top Cart":
        return "🛒"
    return "🧾"


def category_prompt_rules(category):
    category = normalize_category(category)

    if category == "Stay Beautiful":
        return """
For Stay Beautiful:
- The user may upload product photo, shelfie, routine photo, receipt, and optional selfie.
- Selfies are optional.
- Do not judge attractiveness.
- Do not rate the person's face.
- Do not estimate age from face.
- The user may provide actual age voluntarily; use it only as context for routine/value.
- Do not diagnose skin conditions.
- Do not make medical claims.
- Keep skincare advice general and non-medical.
- Score routine/value, not the person's appearance.
- routine_score should be 1 to 10.
- glow_score should be 1 to 10.
- value_score should be 1 to 10.
- estimated_food_weight_lbs should be 0.
- estimated_meals should be 0.
- best_value_items should list useful/value products.
- wallet_villains should list expensive, redundant, luxury, or low-value products.
- routine_notes should comment generally on cleanser, moisturizer, sunscreen, actives, simplicity, redundancy, and value.
- Tone: beauty haul, shelfie, routine battle, "Can you stay beautiful for less?"
"""

    if category == "Feed an Army":
        return """
For Feed an Army:
- The user uploads a food haul/cart/pantry image and receipt.
- family_size, days_goal, shopping_frequency, and budget_goal may be provided.
- estimated_food_weight_lbs should estimate edible food weight only.
- estimated_meals should estimate practical individual meals/snacks.
- feed_score should be 1 to 10.
- cost_per_meal should estimate receipt_total / estimated_meals if possible.
- cost_per_person_meal should estimate receipt_total / estimated_meals if estimated_meals already counts individual meals.
- staples_ratio_percent should estimate useful staples vs snacks/luxury items.
- snack_tax should be low, medium, or high.
- best_value_items should favor proteins, rice, eggs, produce, frozen veg, grains, staples.
- wallet_villains should identify snacks, drinks, prepared meals, supplements, luxury items.
- Tone: practical but funny, "Can your haul feed an army?"
"""

    return """
For Top Cart:
- The user uploads a cart/haul image and receipt.
- estimated_food_weight_lbs should estimate edible food weight only.
- price_per_lb should be receipt_total / estimated_food_weight_lbs if possible.
- cart_fullness_percent should estimate how full the cart looks.
- bulk_score should be 1 to 10.
- estimated_meals should estimate practical meals/snacks.
- kirkland_ratio_percent should estimate Costco/Kirkland/private-label share when relevant.
- best_value_items should favor staples, bulk foods, high-utility household items.
- wallet_villains should identify expensive, luxury, snack, beverage, prepared-food, or sneaky-cost items.
- Tone: game show, Costco, bulk shopping, receipt reveal, "Best priced cart by pounds?"
"""


# ============================================================
# Rank helpers
# ============================================================

def get_guess_rank(diff):
    diff = safe_float(diff)

    if diff <= 5:
        return "Kirkland Psychic"
    if diff <= 20:
        return "Bulk Savant"
    if diff <= 50:
        return "Cart Competent"
    if diff <= 100:
        return "Sample Station Casual"
    if diff <= 250:
        return "Costco Got You"
    return "Cart Delusion Champion"


def get_guess_rank_message(diff):
    diff = safe_float(diff)

    if diff <= 5:
        return "Elite guess. You have forbidden receipt vision."
    if diff <= 20:
        return "Respectable. You understand bulk damage."
    if diff <= 50:
        return "Not bad, but the receipt hid a few expensive goblins."
    if diff <= 100:
        return "The cart tricked you, but you stayed in the parking lot."
    if diff <= 250:
        return "Costco got you. The cart was lying."
    return "Historic miss. The cart created a false reality."


def get_beauty_rank(value_score):
    score = safe_float(value_score)

    if score >= 9:
        return "Glow Arbitrage"
    if score >= 8:
        return "Budget Baddie"
    if score >= 7:
        return "Routine Investor"
    if score >= 5:
        return "Serum Casual"
    return "Wallet Took Damage"


def get_feed_rank(feed_score):
    score = safe_float(feed_score)

    if score >= 9:
        return "Army Quartermaster"
    if score >= 8:
        return "Family Fuel Genius"
    if score >= 7:
        return "Pantry Strategist"
    if score >= 5:
        return "Snack Tax Survivor"
    return "Receipt Casualty"


# ============================================================
# Image helpers
# ============================================================

def reset_uploaded_file(uploaded_file):
    try:
        uploaded_file.seek(0)
    except Exception:
        pass


def image_to_base64(uploaded_file):
    reset_uploaded_file(uploaded_file)

    image = Image.open(uploaded_file).convert("RGB")
    image.thumbnail((1000, 1000))

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=78)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def save_uploaded_image(uploaded_file, post_id, label):
    """
    Saves a resized JPEG copy of uploaded image.
    Returns relative path as string.
    """
    if uploaded_file is None:
        return ""

    reset_uploaded_file(uploaded_file)

    post_dir = UPLOADS_DIR / post_id
    post_dir.mkdir(parents=True, exist_ok=True)

    safe_label = re.sub(r"[^a-zA-Z0-9_-]+", "_", label).strip("_").lower()
    filename = f"{safe_label}.jpg"
    path = post_dir / filename

    image = Image.open(uploaded_file).convert("RGB")
    image.thumbnail((1200, 1200))
    image.save(path, format="JPEG", quality=82)

    return str(path)


def display_saved_image(path, caption=None):
    try:
        if path and Path(path).exists():
            st.image(path, caption=caption, use_container_width=True)
            return True
    except Exception:
        pass
    return False


# ============================================================
# JSON extraction / normalization
# ============================================================

def extract_json(raw_text):
    if not raw_text:
        raise ValueError("Empty model response.")

    raw_text = raw_text.strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model response.")

    return json.loads(match.group(0))


def default_analysis(category):
    category = normalize_category(category)

    return {
        "store": "Unknown",
        "category": category,
        "receipt_total": 0,
        "item_count": 0,
        "detected_items": [],
        "cart_fullness_percent": 0,
        "estimated_food_weight_lbs": 0,
        "estimated_meals": 0,
        "kirkland_ratio_percent": 0,
        "price_per_lb": 0,
        "bulk_score": 5,
        "feed_score": 0,
        "cost_per_meal": 0,
        "cost_per_person_meal": 0,
        "staples_ratio_percent": 0,
        "snack_tax": "medium",
        "routine_score": 0,
        "glow_score": 0,
        "value_score": 0,
        "impulse_score": "medium",
        "best_value_items": [],
        "wallet_villains": [],
        "routine_notes": [],
        "public_caption": "Guess the receipt total before the reveal.",
        "verdict": "The receipt has spoken.",
        "privacy_notes": [],
        "uncertainty_notes": [],
    }


def normalize_analysis(data, category):
    category = normalize_category(category)

    if not isinstance(data, dict):
        data = {}

    merged = {**default_analysis(category), **data}
    merged["category"] = category

    merged["receipt_total"] = safe_float(merged.get("receipt_total"), 0.0)
    merged["item_count"] = safe_int(merged.get("item_count"), 0)
    merged["cart_fullness_percent"] = safe_int(clamp(merged.get("cart_fullness_percent"), 0, 100), 0)
    merged["estimated_food_weight_lbs"] = safe_int(max(0, safe_float(merged.get("estimated_food_weight_lbs"), 0)), 0)
    merged["estimated_meals"] = safe_int(max(0, safe_float(merged.get("estimated_meals"), 0)), 0)
    merged["kirkland_ratio_percent"] = safe_int(clamp(merged.get("kirkland_ratio_percent"), 0, 100), 0)
    merged["staples_ratio_percent"] = safe_int(clamp(merged.get("staples_ratio_percent"), 0, 100), 0)

    merged["price_per_lb"] = safe_float(merged.get("price_per_lb"), 0)
    if merged["price_per_lb"] <= 0 and merged["estimated_food_weight_lbs"] > 0:
        merged["price_per_lb"] = merged["receipt_total"] / merged["estimated_food_weight_lbs"]

    merged["cost_per_meal"] = safe_float(merged.get("cost_per_meal"), 0)
    if merged["cost_per_meal"] <= 0 and merged["estimated_meals"] > 0:
        merged["cost_per_meal"] = merged["receipt_total"] / merged["estimated_meals"]

    merged["cost_per_person_meal"] = safe_float(merged.get("cost_per_person_meal"), 0)
    if merged["cost_per_person_meal"] <= 0 and merged["estimated_meals"] > 0:
        merged["cost_per_person_meal"] = merged["receipt_total"] / merged["estimated_meals"]

    for field in ["bulk_score", "feed_score", "routine_score", "glow_score", "value_score"]:
        merged[field] = round(clamp(merged.get(field), 0, 10), 1)

    if merged["bulk_score"] == 0:
        merged["bulk_score"] = 5

    for field in ["impulse_score", "snack_tax"]:
        value = str(merged.get(field, "medium")).lower().strip()
        if value not in ["low", "medium", "high"]:
            value = "medium"
        merged[field] = value

    for field in [
        "detected_items",
        "best_value_items",
        "wallet_villains",
        "routine_notes",
        "privacy_notes",
        "uncertainty_notes",
    ]:
        if not isinstance(merged.get(field), list):
            merged[field] = []

    return merged


# ============================================================
# Prompt + OpenAI vision
# ============================================================

def build_prompt(category, metadata):
    category = normalize_category(category)
    metadata_text = json.dumps(metadata or {}, indent=2, ensure_ascii=False)

    return f"""
You are CartFlex, a funny but useful AI judge for receipt-based posts.

CartFlex has three public beta lanes:
1. Top Cart: best priced cart by pounds.
2. Feed an Army: can this haul feed more people for less?
3. Stay Beautiful: can you stay beautiful for less?

Selected category: {category}

User-provided metadata:
{metadata_text}

You will receive one or more images:
- haul/cart/product image
- receipt image
- optional selfie/routine image depending on category

Analyze the images together.

Return ONLY valid JSON.
No markdown.
No commentary.
No code fences.
No extra text.

Use this exact schema:
{{
  "store": "string",
  "category": "string",
  "receipt_total": number,
  "item_count": number,
  "detected_items": ["string"],

  "cart_fullness_percent": number,
  "estimated_food_weight_lbs": number,
  "estimated_meals": number,
  "kirkland_ratio_percent": number,
  "price_per_lb": number,
  "bulk_score": number,

  "feed_score": number,
  "cost_per_meal": number,
  "cost_per_person_meal": number,
  "staples_ratio_percent": number,
  "snack_tax": "low | medium | high",

  "routine_score": number,
  "glow_score": number,
  "value_score": number,

  "impulse_score": "low | medium | high",
  "best_value_items": ["string"],
  "wallet_villains": ["string"],
  "routine_notes": ["string"],

  "public_caption": "string",
  "verdict": "string",
  "privacy_notes": ["string"],
  "uncertainty_notes": ["string"]
}}

General rules:
- receipt_total should come from the receipt if visible.
- item_count should come from the receipt if visible.
- detected_items should include recognizable receipt/cart/product items.
- store should be the retailer if visible.
- category should match the selected category.
- public_caption should make people want to react, comment, or try to beat the post.
- verdict should be funny, punchy, and not mean.
- Do not mention private payment info, membership numbers, barcodes, QR codes, full addresses, phone numbers, or card fragments.
- If the image is unclear, make a reasonable estimate and add uncertainty_notes.
- If receipt total is not visible, estimate it and say so in uncertainty_notes.
- Do not give medical, dermatological, financial, or legal claims.

{category_prompt_rules(category)}
"""


def call_openai_vision(category, metadata, image_payloads):
    """
    image_payloads = list of base64 strings
    """
    if client is None:
        raise RuntimeError("Missing OPENAI_API_KEY. Add it to your .env file or Streamlit secrets.")

    if not beta_can_analyze():
        raise RuntimeError(
            f"Beta AI scan limit reached: {CARTFLEX_MAX_ANALYSES}. "
            "Raise CARTFLEX_MAX_ANALYSES only if you want to spend more."
        )

    prompt = build_prompt(category, metadata)

    content = [{"type": "input_text", "text": prompt}]

    for image_b64 in image_payloads:
        if image_b64:
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{image_b64}",
                }
            )

    response = client.responses.create(
        model=CARTFLEX_MODEL,
        input=[
            {
                "role": "user",
                "content": content,
            }
        ],
        max_output_tokens=900,
    )

    increment_beta_analysis_count()
    return response.output_text


def analyze_images(category, metadata, uploaded_files):
    """
    uploaded_files is a list of Streamlit UploadedFile objects.
    """
    b64_images = []

    for file in uploaded_files:
        if file is not None:
            b64_images.append(image_to_base64(file))

    raw = call_openai_vision(category, metadata, b64_images)
    parsed = extract_json(raw)
    return normalize_analysis(parsed, category), raw


# ============================================================
# Records / posts
# ============================================================

def save_post_record(record):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    post_id = record.get("post_id") or new_post_id()
    filename = HAULS_DIR / f"cartflex_{timestamp}_{post_id}.json"

    record["post_id"] = post_id
    record["saved_at"] = record.get("saved_at") or now_iso()
    record["app"] = APP_NAME

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)

    return filename


def load_saved_records():
    files = sorted(HAULS_DIR.glob("cartflex_*.json"), reverse=True)
    records = []

    for file in files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                record = json.load(f)
            record["_file"] = str(file)
            records.append(record)
        except Exception:
            pass

    return records


def make_record(
    category,
    display_name,
    analysis,
    metadata=None,
    image_paths=None,
    post_id=None,
    guess_locked=False,
    guess=0,
    difference=0,
    rank="",
):
    category = normalize_category(category)
    post_id = post_id or new_post_id()
    metadata = metadata or {}
    image_paths = image_paths or {}

    actual_total = safe_float(analysis.get("receipt_total"), 0.0)

    return {
        "id": str(uuid.uuid4()),
        "post_id": post_id,
        "saved_at": now_iso(),
        "app": APP_NAME,
        "display_name": display_name or "Anonymous",
        "category": category,
        "metadata": metadata,
        "image_paths": image_paths,
        "analysis": analysis,
        "actual_total": actual_total,
        "guess_locked": bool(guess_locked),
        "guess": safe_float(guess),
        "difference": safe_float(difference),
        "rank": rank,
    }


def make_title(record):
    analysis = record.get("analysis", {})
    category = normalize_category(record.get("category", analysis.get("category", "Top Cart")))

    if category == "Stay Beautiful":
        return "Can you stay beautiful for less?"

    if category == "Feed an Army":
        meals = analysis.get("estimated_meals", "N/A")
        return f"Can this haul feed an army? {meals} meals estimated"

    actual_total = safe_float(record.get("actual_total", analysis.get("receipt_total", 0)))
    estimated_weight = safe_float(analysis.get("estimated_food_weight_lbs", 0))
    price_per_lb = safe_float(analysis.get("price_per_lb"), 0)

    if price_per_lb <= 0 and estimated_weight > 0:
        price_per_lb = actual_total / estimated_weight

    if price_per_lb > 0:
        return f"Best priced cart by pounds? {money(price_per_lb)}/lb"

    return "Guess the receipt. Reveal the damage."


def relevance_score(post):
    likes = safe_float(post.get("likes", 0))
    comments = safe_float(post.get("comments_count", 0))
    bulk_score = safe_float(post.get("bulk_score", 0))
    feed_score = safe_float(post.get("feed_score", 0))
    routine_score = safe_float(post.get("routine_score", 0))
    value_score = safe_float(post.get("value_score", 0))
    price_per_lb = safe_float(post.get("price_per_lb", 0))

    score = 0
    score += likes * 2
    score += comments * 5
    score += bulk_score * 8
    score += feed_score * 10
    score += routine_score * 10
    score += value_score * 10

    if price_per_lb > 0:
        score += max(0, 60 - price_per_lb * 5)

    return score


def record_to_feed_post(record):
    analysis = record.get("analysis", {})
    category = normalize_category(record.get("category", analysis.get("category", "Top Cart")))
    post_id = record.get("post_id") or record.get("id") or "unknown"
    engagement = load_engagement(post_id)

    actual_total = safe_float(record.get("actual_total", analysis.get("receipt_total", 0)))
    estimated_weight = safe_float(analysis.get("estimated_food_weight_lbs", 0))
    price_per_lb = safe_float(analysis.get("price_per_lb"), 0)

    if price_per_lb <= 0 and estimated_weight > 0:
        price_per_lb = actual_total / estimated_weight

    post = {
        "source": "saved",
        "post_id": post_id,
        "title": make_title(record),
        "category": category,
        "display_name": record.get("display_name", "Anonymous"),
        "saved_at": record.get("saved_at", ""),
        "time_ago": time_ago_text(record.get("saved_at", "")),
        "actual_total": actual_total,
        "estimated_food_weight_lbs": estimated_weight,
        "price_per_lb": price_per_lb,
        "bulk_score": analysis.get("bulk_score", "N/A"),
        "feed_score": analysis.get("feed_score", "N/A"),
        "routine_score": analysis.get("routine_score", "N/A"),
        "glow_score": analysis.get("glow_score", "N/A"),
        "value_score": analysis.get("value_score", "N/A"),
        "estimated_meals": analysis.get("estimated_meals", "N/A"),
        "caption": analysis.get("public_caption", "Guess the receipt total."),
        "verdict": analysis.get("verdict", ""),
        "best_values": analysis.get("best_value_items", []),
        "wallet_villains": analysis.get("wallet_villains", []),
        "rank": record.get("rank", ""),
        "difference": record.get("difference", None),
        "likes": engagement.get("likes", 0),
        "comments_count": len(engagement.get("comments", [])),
        "engagement": engagement,
        "image_paths": record.get("image_paths", {}),
        "metadata": record.get("metadata", {}),
        "file": record.get("_file", ""),
    }

    post["relevance"] = relevance_score(post)
    return post


# ============================================================
# Engagement
# ============================================================

def engagement_file_for_post(post_id):
    return HAULS_DIR / f"engagement_{post_id}.json"


def default_engagement():
    return {
        "likes": 0,
        "reactions": {
            "🔥 I can beat this": 0,
            "💸 Wallet damage": 0,
            "😂 Receipt lied": 0,
            "✨ Stay beautiful": 0,
            "👨‍👩‍👧 Feeds an army": 0,
        },
        "comments": [],
    }


def load_engagement(post_id):
    default = default_engagement()

    if not post_id:
        return default

    path = engagement_file_for_post(post_id)

    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "likes" not in data:
            data["likes"] = 0

        if "reactions" not in data or not isinstance(data["reactions"], dict):
            data["reactions"] = default["reactions"]

        if "comments" not in data or not isinstance(data["comments"], list):
            data["comments"] = []

        for key in default["reactions"]:
            if key not in data["reactions"]:
                data["reactions"][key] = 0

        return data
    except Exception:
        return default


def save_engagement(post_id, engagement):
    if not post_id:
        return None

    path = engagement_file_for_post(post_id)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(engagement, f, indent=2, ensure_ascii=False)

    return path


def add_like(post_id):
    engagement = load_engagement(post_id)
    engagement["likes"] = safe_int(engagement.get("likes"), 0) + 1
    save_engagement(post_id, engagement)


def add_reaction(post_id, reaction):
    engagement = load_engagement(post_id)

    if reaction not in engagement["reactions"]:
        engagement["reactions"][reaction] = 0

    engagement["reactions"][reaction] += 1
    save_engagement(post_id, engagement)


def add_comment(post_id, name, text):
    engagement = load_engagement(post_id)

    clean_name = (name or "Anonymous").strip() or "Anonymous"
    clean_text = (text or "").strip()

    if not clean_text:
        return

    engagement["comments"].append(
        {
            "name": clean_name[:40],
            "text": clean_text[:1000],
            "created_at": now_iso(),
        }
    )

    save_engagement(post_id, engagement)


# ============================================================
# Seed posts for empty home feed
# ============================================================

def seeded_posts():
    posts = [
        {
            "source": "seed",
            "post_id": "seed_top_cart_001",
            "title": "Best priced shopping cart by pounds?",
            "category": "Top Cart",
            "display_name": "Beta Cart",
            "time_ago": "2d ago",
            "actual_total": 234.74,
            "estimated_food_weight_lbs": 50,
            "price_per_lb": 4.69,
            "bulk_score": 8.4,
            "feed_score": 0,
            "routine_score": 0,
            "glow_score": 0,
            "value_score": 0,
            "estimated_meals": 25,
            "caption": "This cart looks expensive, but the price per pound is weirdly strong.",
            "verdict": "Costco did not win this round. The cart came heavy and the receipt stayed reasonable.",
            "best_values": ["Potatoes", "Chicken", "Water", "Bananas"],
            "wallet_villains": ["Chocolate", "Almond milk"],
            "rank": "Bulk Savant",
            "difference": 12.50,
            "fake_likes": 11200,
            "fake_comments": 420,
            "image_paths": {},
            "metadata": {},
        },
        {
            "source": "seed",
            "post_id": "seed_beauty_001",
            "title": "Can you stay beautiful for less?",
            "category": "Stay Beautiful",
            "display_name": "Glow Budget",
            "time_ago": "1d ago",
            "actual_total": 84.12,
            "estimated_food_weight_lbs": 0,
            "price_per_lb": 0,
            "bulk_score": 8.1,
            "feed_score": 0,
            "routine_score": 8.7,
            "glow_score": 8.4,
            "value_score": 9.1,
            "estimated_meals": 0,
            "caption": "Age 39. Simple routine. No $300 serum. Can you beat the value?",
            "verdict": "This routine is doing more with less. Wallet survived, glow stayed alive.",
            "best_values": ["Cleanser", "Moisturizer", "Sunscreen"],
            "wallet_villains": ["Luxury serum temptation"],
            "rank": "Glow Arbitrage",
            "difference": 8.21,
            "fake_likes": 12400,
            "fake_comments": 690,
            "image_paths": {},
            "metadata": {"actual_age": 39},
        },
        {
            "source": "seed",
            "post_id": "seed_army_001",
            "title": "Realistic beats this: feeds an army?",
            "category": "Feed an Army",
            "display_name": "Family Stockup",
            "time_ago": "4h ago",
            "actual_total": 311.20,
            "estimated_food_weight_lbs": 82,
            "price_per_lb": 3.79,
            "bulk_score": 8.9,
            "feed_score": 9.0,
            "routine_score": 0,
            "glow_score": 0,
            "value_score": 0,
            "estimated_meals": 72,
            "caption": "Family of 5. One cart. Seventy-ish meals. Can your haul beat this?",
            "verdict": "Heavy on staples, light on nonsense. This cart came to feed people, not impress the snack aisle.",
            "best_values": ["Rice", "Eggs", "Chicken thighs", "Frozen vegetables"],
            "wallet_villains": ["Protein snacks", "Prepared meals"],
            "rank": "Army Quartermaster",
            "difference": 22.10,
            "fake_likes": 8700,
            "fake_comments": 310,
            "image_paths": {},
            "metadata": {"family_size": 5},
        },
    ]

    for post in posts:
        engagement = load_engagement(post["post_id"])
        post["likes"] = safe_int(post.get("fake_likes", 0)) + safe_int(engagement.get("likes", 0))
        post["comments_count"] = safe_int(post.get("fake_comments", 0)) + len(engagement.get("comments", []))
        post["engagement"] = engagement
        post["relevance"] = relevance_score(post)

    return posts


def load_feed_posts(include_seeds=True):
    records = load_saved_records()
    posts = [record_to_feed_post(record) for record in records]

    if include_seeds:
        posts.extend(seeded_posts())

    posts = sorted(posts, key=lambda p: p.get("relevance", 0), reverse=True)
    return posts