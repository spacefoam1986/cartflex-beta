import streamlit as st

from cartflex_core import (
    analyze_images,
    display_saved_image,
    get_guess_rank,
    get_guess_rank_message,
    load_engagement,
    make_record,
    money,
    new_post_id,
    safe_float,
    save_post_record,
    save_uploaded_image,
)

st.set_page_config(
    page_title="Top Cart",
    page_icon="🛒",
    layout="centered",
)

CATEGORY = "Top Cart"

st.title("🛒 Top Cart")
st.subheader("Best priced cart by pounds.")

st.success(
    "Free beta: upload a cart/haul photo and receipt. "
    "AI estimates pounds of food, price per pound, BulkScore, and lets people guess the damage."
)

st.caption(
    "Only upload images you have the right to share. Review receipts for private info before uploading."
)

st.divider()

# ============================================================
# Input form
# ============================================================

display_name = st.text_input("Display name", value="Anonymous")

col_a, col_b = st.columns(2)

with col_a:
    shopping_frequency = st.selectbox(
        "How often do you Costco/grocery shop?",
        [
            "Weekly",
            "Every 2 weeks",
            "Monthly",
            "Random chaos",
            "First time / not sure",
        ],
    )

with col_b:
    household_size = st.number_input(
        "Household size",
        min_value=1,
        max_value=25,
        value=2,
        step=1,
    )

cart_goal = st.text_input(
    "Optional cart goal",
    placeholder="Example: under $250, mostly staples, best $/lb possible",
)

cart_file = st.file_uploader(
    "Upload cart / haul photo",
    type=["jpg", "jpeg", "png"],
)

receipt_file = st.file_uploader(
    "Upload receipt photo",
    type=["jpg", "jpeg", "png"],
)

consent = st.checkbox(
    "I reviewed my images for private info and understand this beta processes uploaded images."
)

if cart_file:
    st.image(cart_file, caption="Cart / haul photo", width="stretch")

if receipt_file:
    st.image(receipt_file, caption="Receipt photo", width="stretch")

st.divider()

# ============================================================
# Analyze
# ============================================================

if st.button("Analyze Top Cart Post", type="primary"):
    if not cart_file or not receipt_file:
        st.error("Upload both a cart/haul photo and a receipt photo.")
        st.stop()

    if not consent:
        st.error("Please check the beta consent box before analyzing.")
        st.stop()

    post_id = new_post_id()

    metadata = {
        "display_name": display_name,
        "shopping_frequency": shopping_frequency,
        "household_size": int(household_size),
        "cart_goal": cart_goal,
        "lane": CATEGORY,
        "hook": "Best priced cart by pounds.",
    }

    with st.spinner("Analyzing pounds, price per pound, BulkScore, and receipt damage..."):
        try:
            analysis, raw = analyze_images(
                category=CATEGORY,
                metadata=metadata,
                uploaded_files=[cart_file, receipt_file],
            )

            image_paths = {
                "cart": save_uploaded_image(cart_file, post_id, "cart"),
                "receipt": save_uploaded_image(receipt_file, post_id, "receipt"),
            }

            actual_total = safe_float(analysis.get("receipt_total"), 0)
            estimated_lbs = safe_float(analysis.get("estimated_food_weight_lbs"), 0)

            if estimated_lbs > 0:
                analysis["price_per_lb"] = actual_total / estimated_lbs

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
                rank="",
            )

            saved_file = save_post_record(record)

            st.session_state["cart_record"] = record
            st.session_state["cart_saved_file"] = str(saved_file)
            st.session_state["cart_guess_locked"] = False
            st.session_state["cart_guess"] = 0.0
            st.session_state["cart_difference"] = 0.0
            st.session_state["cart_rank"] = ""

        except Exception as e:
            st.error("Could not analyze this Top Cart post.")
            st.caption(str(e))
            st.stop()


# ============================================================
# Render result
# ============================================================

if "cart_record" in st.session_state:
    record = st.session_state["cart_record"]
    analysis = record.get("analysis", {})
    metadata = record.get("metadata", {})
    image_paths = record.get("image_paths", {})
    post_id = record.get("post_id")

    actual_total = safe_float(analysis.get("receipt_total"), 0)
    estimated_lbs = safe_float(analysis.get("estimated_food_weight_lbs"), 0)
    price_per_lb = safe_float(analysis.get("price_per_lb"), 0)
    bulk_score = safe_float(analysis.get("bulk_score"), 0)

    st.divider()

    st.markdown("# 🛒 TOP CART RESULT")
    st.markdown("### Best priced cart by pounds.")

    img_col1, img_col2 = st.columns(2)

    with img_col1:
        display_saved_image(image_paths.get("cart"), "Cart / haul photo")

    with img_col2:
        display_saved_image(image_paths.get("receipt"), "Receipt")

    st.caption(f"Post ID: `{post_id}`")
    st.caption(f"Saved locally: {st.session_state.get('cart_saved_file', '')}")

    metric_cols = st.columns(4)

    with metric_cols[0]:
        st.metric("Receipt total", money(actual_total))

    with metric_cols[1]:
        st.metric("Estimated food", f"{int(estimated_lbs)} lbs" if estimated_lbs else "N/A")

    with metric_cols[2]:
        st.metric("Price / lb", money(price_per_lb))

    with metric_cols[3]:
        st.metric("BulkScore", f"{bulk_score}/10")

    st.info(
        f"Shopping frequency: **{metadata.get('shopping_frequency', 'N/A')}** · "
        f"Household size: **{metadata.get('household_size', 'N/A')}**"
    )

    if analysis.get("public_caption"):
        st.success(analysis.get("public_caption"))

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Best value vibes")
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

    extra_cols = st.columns(3)

    with extra_cols[0]:
        st.metric(
            "Cart fullness",
            f"{analysis.get('cart_fullness_percent', 'N/A')}%",
        )

    with extra_cols[1]:
        st.metric(
            "Estimated meals",
            analysis.get("estimated_meals", "N/A"),
        )

    with extra_cols[2]:
        st.metric(
            "Kirkland ratio",
            f"{analysis.get('kirkland_ratio_percent', 'N/A')}%",
        )

    with st.expander("AI verdict"):
        st.write(analysis.get("verdict", ""))

    if analysis.get("detected_items"):
        with st.expander("Detected items"):
            st.write(", ".join(analysis.get("detected_items", [])))

    if analysis.get("uncertainty_notes"):
        with st.expander("Uncertainty notes"):
            for note in analysis.get("uncertainty_notes", []):
                st.write(f"⚠️ {note}")

    st.divider()

    # ============================================================
    # Guess/reveal game
    # ============================================================

    st.subheader("🎯 Guess the damage")
    st.caption("Cart photos lie. Lock your guess before revealing the receipt damage.")

    q1, q2, q3 = st.columns(3)

    with q1:
        if st.button("$150-ish"):
            st.session_state["cart_quick_guess"] = 150.0

    with q2:
        if st.button("$250-ish"):
            st.session_state["cart_quick_guess"] = 250.0

    with q3:
        if st.button("$350-ish"):
            st.session_state["cart_quick_guess"] = 350.0

    default_guess = st.session_state.get("cart_quick_guess", 0.0)

    guess = st.number_input(
        "What do you think this receipt total was?",
        min_value=0.0,
        step=1.0,
        value=float(default_guess),
        format="%.2f",
    )

    if st.button("Lock Guess", type="primary"):
        difference = abs(guess - actual_total)
        rank = get_guess_rank(difference)

        st.session_state["cart_guess_locked"] = True
        st.session_state["cart_guess"] = guess
        st.session_state["cart_difference"] = difference
        st.session_state["cart_rank"] = rank

        # Update record and re-save a new record snapshot with guess included.
        record["guess_locked"] = True
        record["guess"] = guess
        record["difference"] = difference
        record["rank"] = rank

        saved_file = save_post_record(record)
        st.session_state["cart_saved_file"] = str(saved_file)

    if st.session_state.get("cart_guess_locked"):
        st.success(f"Guess locked: {money(st.session_state['cart_guess'])}")

    st.divider()

    st.subheader("🧾 Receipt Reveal")

    if not st.session_state.get("cart_guess_locked"):
        st.warning("Lock in your guess before revealing the receipt total.")
    else:
        user_guess = safe_float(st.session_state.get("cart_guess"), 0)
        diff = safe_float(st.session_state.get("cart_difference"), 0)
        rank = st.session_state.get("cart_rank", get_guess_rank(diff))

        with st.expander("Reveal the damage", expanded=True):
            score_cols = st.columns(3)

            with score_cols[0]:
                st.metric("Your guess", money(user_guess))

            with score_cols[1]:
                st.metric("Actual total", money(actual_total))

            with score_cols[2]:
                st.metric("Off by", money(diff))

            st.markdown(f"## Rank: {rank}")

            rank_message = get_guess_rank_message(diff)

            if diff <= 5:
                st.success(rank_message)
            elif diff <= 20:
                st.info(rank_message)
            elif diff <= 100:
                st.warning(rank_message)
            else:
                st.error(rank_message)

            st.write(analysis.get("verdict", ""))

    st.divider()

    st.subheader("Share text")

    if st.session_state.get("cart_guess_locked"):
        user_guess = safe_float(st.session_state.get("cart_guess"), 0)
        diff = safe_float(st.session_state.get("cart_difference"), 0)
        rank = st.session_state.get("cart_rank", get_guess_rank(diff))

        share_text = f"""
TOP CART 🛒

Best priced cart by pounds?

My guess: {money(user_guess)}
Actual total: {money(actual_total)}
Off by: {money(diff)}
Rank: {rank}

Estimated food: {int(estimated_lbs) if estimated_lbs else "N/A"} lbs
Price per lb: {money(price_per_lb)}
BulkScore: {bulk_score}/10

Best value vibes: {", ".join(analysis.get("best_value_items", []))}
Wallet villains: {", ".join(analysis.get("wallet_villains", []))}

Can your cart beat this?
"""
    else:
        share_text = f"""
TOP CART 🛒

Best priced cart by pounds?

Receipt hidden until guess.
Estimated food: {int(estimated_lbs) if estimated_lbs else "N/A"} lbs
Price per lb: {money(price_per_lb)}
BulkScore: {bulk_score}/10

Best value vibes: {", ".join(analysis.get("best_value_items", []))}
Wallet villains: {", ".join(analysis.get("wallet_villains", []))}

Guess the damage.
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