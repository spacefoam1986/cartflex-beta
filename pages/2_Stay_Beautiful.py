import streamlit as st

from cartflex_core import (
    analyze_images,
    display_saved_image,
    get_beauty_rank,
    load_engagement,
    make_record,
    money,
    new_post_id,
    safe_float,
    save_post_record,
    save_uploaded_image,
)

st.set_page_config(
    page_title="Stay Beautiful",
    page_icon="✨",
    layout="centered",
)

CATEGORY = "Stay Beautiful"

st.title("✨ Stay Beautiful")
st.subheader("Can you stay beautiful for less?")

st.success(
    "Free beta: upload a selfie/product/routine photo and receipt. "
    "AI scores the routine value, glow economics, wallet damage, and product balance."
)

st.caption(
    "Important: this is not medical or dermatology advice. "
    "CartFlex scores the routine/value, not your attractiveness. "
    "Only upload images you have the right to share."
)

st.divider()

# ============================================================
# Input form
# ============================================================

display_name = st.text_input("Display name", value="Anonymous")

col_a, col_b = st.columns(2)

with col_a:
    actual_age = st.number_input(
        "Actual age",
        min_value=13,
        max_value=100,
        value=39,
        step=1,
    )

with col_b:
    beauty_goal = st.selectbox(
        "Beauty goal",
        [
            "Stay beautiful for less",
            "Simple glow",
            "Anti-aging routine",
            "Drugstore value",
            "Costco beauty haul",
            "Minimal routine",
            "Luxury routine check",
            "Not sure",
        ],
    )

routine_frequency = st.selectbox(
    "How consistent is the routine?",
    [
        "Daily",
        "Most days",
        "A few times a week",
        "Random chaos",
        "Just bought it / not sure yet",
    ],
)

routine_text = st.text_area(
    "Describe the routine",
    placeholder=(
        "Example: Morning: cleanser, vitamin C, moisturizer, sunscreen. "
        "Night: cleanser, retinol twice a week, moisturizer."
    ),
)

st.markdown("### Uploads")

selfie_file = st.file_uploader(
    "Optional selfie / face photo",
    type=["jpg", "jpeg", "png"],
)

products_file = st.file_uploader(
    "Upload skincare/product/shelfie photo",
    type=["jpg", "jpeg", "png"],
)

receipt_file = st.file_uploader(
    "Upload receipt photo",
    type=["jpg", "jpeg", "png"],
)

consent = st.checkbox(
    "I reviewed my images for private info and understand this beta processes uploaded images."
)

if selfie_file:
    st.image(selfie_file, caption="Optional selfie", width="stretch")

if products_file:
    st.image(products_file, caption="Products / routine photo", width="stretch")

if receipt_file:
    st.image(receipt_file, caption="Receipt photo", width="stretch")

st.divider()

# ============================================================
# Analyze
# ============================================================

if st.button("Analyze Stay Beautiful Post", type="primary"):
    if not products_file or not receipt_file:
        st.error("Upload at least a products/routine photo and a receipt photo.")
        st.stop()

    if not consent:
        st.error("Please check the beta consent box before analyzing.")
        st.stop()

    post_id = new_post_id()

    metadata = {
        "display_name": display_name,
        "actual_age": int(actual_age),
        "beauty_goal": beauty_goal,
        "routine_frequency": routine_frequency,
        "routine_text": routine_text,
        "lane": CATEGORY,
        "hook": "Can you stay beautiful for less?",
        "selfie_uploaded": bool(selfie_file),
        "safety_note": (
            "Do not judge attractiveness. Do not diagnose skin. "
            "Score routine/value only."
        ),
    }

    uploaded_files = []

    if selfie_file:
        uploaded_files.append(selfie_file)

    uploaded_files.extend([products_file, receipt_file])

    with st.spinner("Analyzing routine value, glow economics, and wallet damage..."):
        try:
            analysis, raw = analyze_images(
                category=CATEGORY,
                metadata=metadata,
                uploaded_files=uploaded_files,
            )

            image_paths = {
                "selfie": save_uploaded_image(selfie_file, post_id, "selfie") if selfie_file else "",
                "products": save_uploaded_image(products_file, post_id, "products"),
                "receipt": save_uploaded_image(receipt_file, post_id, "receipt"),
            }

            value_score = safe_float(analysis.get("value_score"), 0)
            if value_score <= 0:
                value_score = safe_float(analysis.get("bulk_score"), 0)

            beauty_rank = get_beauty_rank(value_score)

            record = make_record(
                category=CATEGORY,
                display_name=display_name,
                analysis=analysis,
                metadata=metadata,
                image_paths=image_paths,
                post_id=post_id,
                guess_locked=False,
                guess=0,
                difference=0,
                rank=beauty_rank,
            )

            # Add top-level metadata for easier future filtering
            record["actual_age"] = int(actual_age)
            record["beauty_goal"] = beauty_goal
            record["routine_frequency"] = routine_frequency

            saved_file = save_post_record(record)

            st.session_state["beauty_record"] = record
            st.session_state["beauty_saved_file"] = str(saved_file)

        except Exception as e:
            st.error("Could not analyze this Stay Beautiful post.")
            st.caption(str(e))
            st.stop()


# ============================================================
# Render result
# ============================================================

if "beauty_record" in st.session_state:
    record = st.session_state["beauty_record"]
    analysis = record.get("analysis", {})
    metadata = record.get("metadata", {})
    image_paths = record.get("image_paths", {})
    post_id = record.get("post_id")

    actual_total = safe_float(analysis.get("receipt_total"), 0)
    routine_score = safe_float(analysis.get("routine_score"), 0)
    glow_score = safe_float(analysis.get("glow_score"), 0)
    value_score = safe_float(analysis.get("value_score"), 0)
    bulk_score = safe_float(analysis.get("bulk_score"), 0)

    if value_score <= 0:
        value_score = bulk_score

    beauty_rank = record.get("rank", get_beauty_rank(value_score))

    st.divider()

    st.markdown("# ✨ STAY BEAUTIFUL RESULT")
    st.markdown("### Can you stay beautiful for less?")

    if image_paths.get("selfie") and image_paths.get("products"):
        img_col1, img_col2 = st.columns(2)

        with img_col1:
            display_saved_image(image_paths.get("selfie"), "Selfie / face photo")

        with img_col2:
            display_saved_image(image_paths.get("products"), "Products / routine")
    else:
        display_saved_image(image_paths.get("products"), "Products / routine")

    with st.expander("Receipt image"):
        display_saved_image(image_paths.get("receipt"), "Receipt")

    st.caption(f"Post ID: `{post_id}`")
    st.caption(f"Saved locally: {st.session_state.get('beauty_saved_file', '')}")

    metric_cols = st.columns(4)

    with metric_cols[0]:
        st.metric("Receipt total", money(actual_total))

    with metric_cols[1]:
        st.metric("RoutineScore", f"{routine_score}/10")

    with metric_cols[2]:
        st.metric("GlowScore", f"{glow_score}/10")

    with metric_cols[3]:
        st.metric("ValueScore", f"{value_score}/10")

    st.markdown(f"## Rank: {beauty_rank}")

    st.info(
        f"Actual age: **{metadata.get('actual_age', 'N/A')}** · "
        f"Goal: **{metadata.get('beauty_goal', 'N/A')}** · "
        f"Consistency: **{metadata.get('routine_frequency', 'N/A')}**"
    )

    if analysis.get("public_caption"):
        st.success(analysis.get("public_caption"))

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Best value products")
        best_values = analysis.get("best_value_items", [])
        if best_values:
            for item in best_values:
                st.write(f"✅ {item}")
        else:
            st.write("No best values detected.")

    with col2:
        st.subheader("Wallet villains")
        villains = analysis.get("wallet_villains", [])
        if villains:
            for item in villains:
                st.write(f"💸 {item}")
        else:
            st.write("No wallet villains detected.")

    st.subheader("Routine notes")
    notes = analysis.get("routine_notes", [])
    if notes:
        for note in notes:
            st.write(f"✨ {note}")
    else:
        st.write("No routine notes detected.")

    with st.expander("AI verdict"):
        st.write(analysis.get("verdict", ""))

    if routine_text:
        with st.expander("Your routine text"):
            st.write(routine_text)

    if analysis.get("detected_items"):
        with st.expander("Detected products/items"):
            st.write(", ".join(analysis.get("detected_items", [])))

    if analysis.get("uncertainty_notes"):
        with st.expander("Uncertainty notes"):
            for note in analysis.get("uncertainty_notes", []):
                st.write(f"⚠️ {note}")

    st.divider()

    st.subheader("Share text")

    share_text = f"""
STAY BEAUTIFUL ✨

Can you stay beautiful for less?

Receipt: {money(actual_total)}
Actual age: {metadata.get("actual_age", "N/A")}
Goal: {metadata.get("beauty_goal", "N/A")}

RoutineScore: {routine_score}/10
GlowScore: {glow_score}/10
ValueScore: {value_score}/10
Rank: {beauty_rank}

Best value products: {", ".join(analysis.get("best_value_items", []))}
Wallet villains: {", ".join(analysis.get("wallet_villains", []))}

Can your routine beat this for less?
"""
    st.code(share_text)

    st.divider()

    st.subheader("Next step")

    st.write(
        "Go back to the **Home** page from the sidebar. "
        "This post should now appear in the feed with images, scores, comments, and reactions."
    )

    engagement = load_engagement(post_id)
    st.caption(
        f"Current engagement: 👍 {engagement.get('likes', 0)} · "
        f"💬 {len(engagement.get('comments', []))}"
    )