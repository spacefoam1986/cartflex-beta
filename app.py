import streamlit as st

from cartflex_core import (
    add_comment,
    add_like,
    add_reaction,
    compact_number,
    display_saved_image,
    get_category_icon,
    load_engagement,
    load_feed_posts,
    money,
    normalize_category,
    safe_float,
    safe_int,
    time_ago_text,
)

try:
    from cartflex_core import beta_remaining_analyses, CARTFLEX_MAX_ANALYSES
except Exception:
    beta_remaining_analyses = None
    CARTFLEX_MAX_ANALYSES = None


st.set_page_config(
    page_title="CartFlex",
    page_icon="🛒",
    layout="centered",
    initial_sidebar_state="expanded",
)


# ============================================================
# Helpers
# ============================================================

def md_money(value):
    """
    Escape dollar signs so Streamlit markdown does not treat $...$ as math.
    """
    return money(value).replace("$", "\\$")


def scan_note_text():
    if beta_remaining_analyses is None or CARTFLEX_MAX_ANALYSES is None:
        return "Comments and reactions do not use AI."

    return (
        f"Beta AI scans remaining tonight: "
        f"{beta_remaining_analyses()}/{CARTFLEX_MAX_ANALYSES}. "
        "Comments and reactions do not use AI."
    )


def post_metric_line(post):
    category = normalize_category(post.get("category"))

    if category == "Stay Beautiful":
        return (
            f"RoutineScore **{post.get('routine_score', 'N/A')}/10** · "
            f"GlowScore **{post.get('glow_score', 'N/A')}/10** · "
            f"Receipt **{md_money(post.get('actual_total', 0))}**"
        )

    if category == "Feed an Army":
        meals = post.get("estimated_meals", "N/A")
        actual = safe_float(post.get("actual_total", 0))
        meals_float = safe_float(meals, 0)

        cost_per_meal = 0
        if meals_float > 0:
            cost_per_meal = actual / meals_float

        return (
            f"Estimated **{meals} meals** · "
            f"Receipt **{md_money(actual)}** · "
            f"About **{md_money(cost_per_meal)}/meal**"
        )

    weight = safe_float(post.get("estimated_food_weight_lbs", 0))
    pplb = safe_float(post.get("price_per_lb", 0))

    if weight > 0 and pplb > 0:
        return (
            f"**{int(weight)} lbs** estimated · "
            f"**{md_money(pplb)}/lb** · "
            f"Receipt **{md_money(post.get('actual_total', 0))}**"
        )

    return f"Receipt **{md_money(post.get('actual_total', 0))}**"


def render_images_for_post(post):
    image_paths = post.get("image_paths", {}) or {}

    primary_path = (
        image_paths.get("selfie")
        or image_paths.get("haul")
        or image_paths.get("products")
        or image_paths.get("cart")
    )

    receipt_path = image_paths.get("receipt")

    if not primary_path and not receipt_path:
        st.caption("No image preview yet. Seed/demo post.")
        return

    if primary_path and receipt_path:
        col1, col2 = st.columns(2)

        with col1:
            display_saved_image(primary_path, caption="Post image")

        with col2:
            display_saved_image(receipt_path, caption="Receipt")
    elif primary_path:
        display_saved_image(primary_path, caption="Post image")
    elif receipt_path:
        display_saved_image(receipt_path, caption="Receipt")


def render_reactions(post):
    post_id = post.get("post_id")
    engagement = load_engagement(post_id)

    reaction_cols = st.columns(5)

    with reaction_cols[0]:
        if st.button(
            f"👍 {compact_number(engagement.get('likes', 0))}",
            key=f"like_{post_id}",
        ):
            add_like(post_id)
            st.rerun()

    reaction_labels = list(engagement.get("reactions", {}).keys())

    for i, reaction in enumerate(reaction_labels[:4], start=1):
        with reaction_cols[i]:
            count = safe_int(engagement["reactions"].get(reaction, 0))
            if st.button(
                f"{reaction} {compact_number(count)}",
                key=f"react_{post_id}_{reaction}",
            ):
                add_reaction(post_id, reaction)
                st.rerun()


def render_comments(post):
    post_id = post.get("post_id")

    st.subheader("Comments")

    name = st.text_input(
        "Name",
        value="Anonymous",
        key=f"comment_name_{post_id}",
    )

    text = st.text_area(
        "Add a comment",
        placeholder="Talk trash. Ask for proof. Say you can beat it.",
        key=f"comment_text_{post_id}",
    )

    if st.button("Post comment", key=f"post_comment_{post_id}"):
        if not text.strip():
            st.warning("Write a comment first.")
        else:
            add_comment(post_id, name, text)
            st.success("Comment posted.")
            st.rerun()

    comments = load_engagement(post_id).get("comments", [])

    if not comments:
        st.info("No real beta comments yet. Be the first.")
        return

    for comment in reversed(comments[-10:]):
        st.markdown(f"**{comment.get('name', 'Anonymous')}**")
        st.write(comment.get("text", ""))
        st.caption(time_ago_text(comment.get("created_at", "")))
        st.divider()


def render_post_card(post):
    category = normalize_category(post.get("category"))
    icon = get_category_icon(category)
    post_id = post.get("post_id")

    engagement = load_engagement(post_id)

    base_likes = safe_int(post.get("likes", 0))
    live_likes = safe_int(engagement.get("likes", 0))

    if post.get("source") == "seed":
        total_likes = base_likes
    else:
        total_likes = live_likes

    base_comments = safe_int(post.get("comments_count", 0))
    live_comments = len(engagement.get("comments", []))

    if post.get("source") == "seed":
        total_comments = base_comments
    else:
        total_comments = live_comments

    with st.container(border=True):
        st.markdown(f"### {icon} {post.get('title', 'CartFlex Post')}")

        st.caption(
            f"{post.get('display_name', 'Anonymous')} · "
            f"{category} · "
            f"{post.get('time_ago', 'recently')} · "
            f"👍 {compact_number(total_likes)} · "
            f"💬 {compact_number(total_comments)}"
        )

        render_images_for_post(post)

        st.markdown(post_metric_line(post))

        if post.get("caption"):
            st.info(post.get("caption"))

        metric_cols = st.columns(3)

        with metric_cols[0]:
            st.metric("BulkScore", f"{post.get('bulk_score', 'N/A')}/10")

        with metric_cols[1]:
            if category == "Stay Beautiful":
                st.metric("GlowScore", f"{post.get('glow_score', 'N/A')}/10")
            elif category == "Feed an Army":
                st.metric("FeedScore", f"{post.get('feed_score', 'N/A')}/10")
            else:
                st.metric("Meals", post.get("estimated_meals", "N/A"))

        with metric_cols[2]:
            if category == "Stay Beautiful":
                st.metric("ValueScore", f"{post.get('value_score', 'N/A')}/10")
            elif safe_float(post.get("price_per_lb", 0)) > 0:
                st.metric("$/lb", money(post.get("price_per_lb")))
            else:
                st.metric("Receipt", money(post.get("actual_total", 0)))

        if post.get("best_values"):
            st.write("**Best value vibes:** " + ", ".join(post.get("best_values", [])))

        if post.get("wallet_villains"):
            st.write("**Wallet villains:** " + ", ".join(post.get("wallet_villains", [])))

        if post.get("rank"):
            st.write(f"**Rank:** {post.get('rank')}")

        if post.get("verdict"):
            with st.expander("Verdict"):
                st.write(post.get("verdict"))

        render_reactions(post)

        with st.expander("Open comments"):
            render_comments(post)

        st.caption(f"Post ID: `{post_id}`")


def filter_posts(posts, lane):
    if lane == "Most Relevant":
        return posts

    if lane == "Stay Beautiful":
        return [p for p in posts if normalize_category(p.get("category")) == "Stay Beautiful"]

    if lane == "Feed an Army":
        return [p for p in posts if normalize_category(p.get("category")) == "Feed an Army"]

    if lane == "Top Cart":
        return [p for p in posts if normalize_category(p.get("category")) == "Top Cart"]

    return posts


# ============================================================
# Sidebar
# ============================================================

with st.sidebar:
    st.header("CartFlex")

    lane = st.radio(
        "Home feed",
        [
            "Most Relevant",
            "Stay Beautiful",
            "Feed an Army",
            "Top Cart",
        ],
        index=0,
    )

    st.divider()

    st.markdown("""
**Upload pages**  
Use the page list in the sidebar.

- Feed an Army
- Stay Beautiful
- Top Cart
""")

    st.divider()

    st.caption("Receipts and selfies need trust. Only consensual uploads.")


# ============================================================
# Tiny top-left brand
# ============================================================

st.markdown(
    """
    <div style="font-size: 0.85rem; font-weight: 700; line-height: 1.1; margin-bottom: 0.05rem;">
        CartFlex
    </div>
    <div style="font-size: 0.72rem; color: #888; line-height: 1.1; margin-bottom: 0.75rem;">
        Real receipts. Real hauls. Guess the damage.
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# Feed
# ============================================================

posts = load_feed_posts(include_seeds=True)
visible_posts = filter_posts(posts, lane)

if lane == "Most Relevant":
    st.header("Most Relevant Right Now")
else:
    st.header(lane)

if not visible_posts:
    st.info("No posts in this lane yet. Upload one from the sidebar.")
else:
    for post in visible_posts[:25]:
        render_post_card(post)


# ============================================================
# Tiny footer
# ============================================================

st.divider()

st.caption(
    "CartFlex · Real receipts. Real hauls. Guess the damage. "
    "Best priced cart by pounds · Can you stay beautiful for less? · Can your haul feed an army?"
)

st.caption(
    "Free beta: upload your own receipts and images, let AI score the haul, "
    "then let people react, comment, and try to beat it."
)

st.caption(
    "Ugly public beta: only upload images you are comfortable sharing with testers. "
    "Cover or crop receipt membership numbers, addresses, phone numbers, payment info, "
    "barcodes, QR codes, and anything private. Selfies are optional."
)

st.caption(scan_note_text())