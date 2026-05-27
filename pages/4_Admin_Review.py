import json
from pathlib import Path

import streamlit as st

from cartflex_core import (
    HAULS_DIR,
    UPLOADS_DIR,
    display_saved_image,
    get_category_icon,
    load_engagement,
    load_saved_records,
    money,
    normalize_category,
    safe_float,
    safe_int,
    time_ago_text,
)

st.set_page_config(
    page_title="Admin Review",
    page_icon="🛠️",
    layout="centered",
)

st.title("🛠️ Admin Review")
st.subheader("Review saved beta posts, uploads, comments, and receipt data.")

st.warning(
    "Local admin page. Do not expose this publicly unless you are okay with people seeing saved post data."
)

st.caption(
    "Use this to inspect consensual beta uploads, check images, read comments, and see what categories are getting traction."
)

st.divider()


# ============================================================
# Helpers
# ============================================================

def get_record_summary(record):
    analysis = record.get("analysis", {})
    category = normalize_category(record.get("category", analysis.get("category", "Unknown")))
    icon = get_category_icon(category)
    name = record.get("display_name", "Anonymous")
    actual_total = safe_float(record.get("actual_total", analysis.get("receipt_total", 0)))
    post_id = record.get("post_id", "unknown")
    saved_at = record.get("saved_at", "")
    return icon, category, name, actual_total, post_id, saved_at


def count_upload_files():
    if not UPLOADS_DIR.exists():
        return 0

    return len(list(UPLOADS_DIR.glob("**/*.*")))


def count_engagement_files():
    if not HAULS_DIR.exists():
        return 0

    return len(list(HAULS_DIR.glob("engagement_*.json")))


def load_raw_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# Load data
# ============================================================

records = load_saved_records()

total_posts = len(records)
total_uploads = count_upload_files()
total_engagement = count_engagement_files()

categories = {}
total_comments = 0
total_likes = 0

for record in records:
    analysis = record.get("analysis", {})
    category = normalize_category(record.get("category", analysis.get("category", "Unknown")))
    categories[category] = categories.get(category, 0) + 1

    post_id = record.get("post_id")
    engagement = load_engagement(post_id)
    total_comments += len(engagement.get("comments", []))
    total_likes += safe_int(engagement.get("likes", 0))


# ============================================================
# Dashboard metrics
# ============================================================

metric_cols = st.columns(4)

with metric_cols[0]:
    st.metric("Saved posts", total_posts)

with metric_cols[1]:
    st.metric("Uploaded images", total_uploads)

with metric_cols[2]:
    st.metric("Likes", total_likes)

with metric_cols[3]:
    st.metric("Comments", total_comments)

if categories:
    st.subheader("Posts by lane")
    for category, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        st.write(f"**{get_category_icon(category)} {category}:** {count}")

st.divider()


# ============================================================
# Filters
# ============================================================

st.subheader("Filter posts")

lane_filter = st.selectbox(
    "Lane",
    ["All", "Stay Beautiful", "Feed an Army", "Top Cart", "Other"],
)

sort_mode = st.selectbox(
    "Sort by",
    [
        "Newest",
        "Most comments",
        "Most likes",
        "Highest receipt total",
        "Lowest receipt total",
    ],
)

filtered = []

for record in records:
    analysis = record.get("analysis", {})
    category = normalize_category(record.get("category", analysis.get("category", "Unknown")))

    if lane_filter != "All":
        if lane_filter == "Other":
            if category in ["Stay Beautiful", "Feed an Army", "Top Cart"]:
                continue
        elif category != lane_filter:
            continue

    filtered.append(record)


def sort_key(record):
    analysis = record.get("analysis", {})
    post_id = record.get("post_id")
    engagement = load_engagement(post_id)

    if sort_mode == "Most comments":
        return len(engagement.get("comments", []))

    if sort_mode == "Most likes":
        return safe_int(engagement.get("likes", 0))

    if sort_mode == "Highest receipt total":
        return safe_float(record.get("actual_total", analysis.get("receipt_total", 0)))

    if sort_mode == "Lowest receipt total":
        return -safe_float(record.get("actual_total", analysis.get("receipt_total", 0)))

    # Newest
    return record.get("saved_at", "")


reverse = True
filtered = sorted(filtered, key=sort_key, reverse=reverse)

st.caption(f"Showing {len(filtered)} posts.")

st.divider()


# ============================================================
# Export area
# ============================================================

st.subheader("Export beta data")

export_payload = {
    "total_posts": total_posts,
    "total_uploads": total_uploads,
    "total_likes": total_likes,
    "total_comments": total_comments,
    "categories": categories,
    "records": records,
}

st.download_button(
    label="Download all saved post JSON",
    data=json.dumps(export_payload, indent=2, ensure_ascii=False),
    file_name="cartflex_beta_export.json",
    mime="application/json",
)

st.divider()


# ============================================================
# Post review cards
# ============================================================

st.subheader("Review posts")

if not filtered:
    st.info("No posts match this filter.")
    st.stop()

for record in filtered:
    analysis = record.get("analysis", {})
    metadata = record.get("metadata", {})
    image_paths = record.get("image_paths", {})

    icon, category, name, actual_total, post_id, saved_at = get_record_summary(record)
    engagement = load_engagement(post_id)

    comment_count = len(engagement.get("comments", []))
    like_count = safe_int(engagement.get("likes", 0))

    title = f"{icon} {name} · {category} · {money(actual_total)} · 👍 {like_count} · 💬 {comment_count}"

    with st.expander(title):
        st.caption(f"Post ID: `{post_id}`")
        st.caption(f"Saved: {saved_at} · {time_ago_text(saved_at)}")

        img_col1, img_col2 = st.columns(2)

        with img_col1:
            primary = (
                image_paths.get("selfie")
                or image_paths.get("products")
                or image_paths.get("haul")
                or image_paths.get("cart")
            )

            if primary:
                display_saved_image(primary, "Primary image")
            else:
                st.info("No primary image saved.")

        with img_col2:
            receipt = image_paths.get("receipt")
            if receipt:
                display_saved_image(receipt, "Receipt")
            else:
                st.info("No receipt image saved.")

        st.markdown("### Scores")

        score_cols = st.columns(4)

        with score_cols[0]:
            st.metric("BulkScore", f"{analysis.get('bulk_score', 'N/A')}/10")

        with score_cols[1]:
            st.metric("FeedScore", f"{analysis.get('feed_score', 'N/A')}/10")

        with score_cols[2]:
            st.metric("GlowScore", f"{analysis.get('glow_score', 'N/A')}/10")

        with score_cols[3]:
            st.metric("ValueScore", f"{analysis.get('value_score', 'N/A')}/10")

        st.markdown("### Main data")

        data_cols = st.columns(3)

        with data_cols[0]:
            st.metric("Receipt total", money(actual_total))

        with data_cols[1]:
            st.metric("Estimated meals", analysis.get("estimated_meals", "N/A"))

        with data_cols[2]:
            lbs = safe_float(analysis.get("estimated_food_weight_lbs", 0))
            st.metric("Food lbs", f"{int(lbs)} lbs" if lbs else "N/A")

        if analysis.get("price_per_lb"):
            st.metric("Price / lb", money(analysis.get("price_per_lb")))

        if analysis.get("cost_per_meal"):
            st.metric("Cost / meal", money(analysis.get("cost_per_meal")))

        if record.get("rank"):
            st.markdown(f"### Rank: {record.get('rank')}")

        if analysis.get("public_caption"):
            st.info(analysis.get("public_caption"))

        if analysis.get("verdict"):
            st.write("**Verdict:**")
            st.write(analysis.get("verdict"))

        col1, col2 = st.columns(2)

        with col1:
            st.write("**Best value vibes:**")
            best_values = analysis.get("best_value_items", [])
            if best_values:
                for item in best_values:
                    st.write(f"✅ {item}")
            else:
                st.write("None")

        with col2:
            st.write("**Wallet villains:**")
            villains = analysis.get("wallet_villains", [])
            if villains:
                for item in villains:
                    st.write(f"💸 {item}")
            else:
                st.write("None")

        if analysis.get("routine_notes"):
            st.write("**Routine notes:**")
            for note in analysis.get("routine_notes", []):
                st.write(f"✨ {note}")

        if analysis.get("detected_items"):
            with st.expander("Detected items"):
                st.write(", ".join(analysis.get("detected_items", [])))

        if analysis.get("uncertainty_notes"):
            with st.expander("Uncertainty notes"):
                for note in analysis.get("uncertainty_notes", []):
                    st.write(f"⚠️ {note}")

        if metadata:
            with st.expander("Metadata"):
                st.json(metadata)

        st.markdown("### Engagement")

        st.write(f"**Likes:** {like_count}")

        reactions = engagement.get("reactions", {})
        if reactions:
            st.write("**Reactions:**")
            for reaction, count in reactions.items():
                st.write(f"{reaction}: {count}")

        comments = engagement.get("comments", [])
        if comments:
            st.write("**Comments:**")
            for comment in reversed(comments):
                st.markdown(f"**{comment.get('name', 'Anonymous')}**")
                st.write(comment.get("text", ""))
                st.caption(comment.get("created_at", ""))
                st.divider()
        else:
            st.write("No comments yet.")

        with st.expander("Raw record JSON"):
            st.json(record)