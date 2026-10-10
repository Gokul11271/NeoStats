"""
RideWise Assist - Streamlit Conversational AI Interface
Multi-Persona (Customer / Support Agent) with Deterministic Guardrails & Verifiable Citations
"""
import streamlit as st
from ridewise import db
from ridewise.orchestrator import RideWiseOrchestrator

# Page Configuration
st.set_page_config(
    page_title="RideWise Assist | AI Mobility Assistant",
    page_icon="🛵",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------
# DARK THEME SESSION STATE
# -----------------------------------------------------------------------
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False

# Build dynamic CSS based on dark/light mode
_DARK = st.session_state.dark_mode

_bg_main    = "#1C1B1F" if _DARK else "#F8F9FA"
_bg_card    = "#2B2930" if _DARK else "#FFFFFF"
_bg_sidebar = "#1C1B1F" if _DARK else "#F8F9FA"
_border     = "#49454F" if _DARK else "#E3E3E3"
_title_col  = "#A8C7FA" if _DARK else "#0B57D0"
_text_col   = "#E6E1E5" if _DARK else "#1F1F1F"
_subtext    = "#CAC4D0" if _DARK else "#444746"
_chip_blue_bg = "#004A77" if _DARK else "#D3E3FD"
_chip_blue_fg = "#C2E7FF" if _DARK else "#041E49"
_chip_green_bg = "#005234" if _DARK else "#C4EDD6"
_chip_green_fg = "#6DD58C" if _DARK else "#07381A"
_chip_gold_bg  = "#5C4400" if _DARK else "#FFE08B"
_chip_gold_fg  = "#FFDF99" if _DARK else "#4E3700"
_chip_out_border = "#938F99" if _DARK else "#747775"
_chip_out_fg     = "#CAC4D0" if _DARK else "#444746"
_chip_out_bg     = "#2B2930" if _DARK else "#FFFFFF"
_citation_bg     = "#1E2B3C" if _DARK else "#F0F4F9"
_citation_border = "#A8C7FA" if _DARK else "#0B57D0"
_btn_bg          = "#2B2930" if _DARK else "#FFFFFF"
_btn_fg          = "#A8C7FA" if _DARK else "#0B57D0"
_btn_border      = "#938F99" if _DARK else "#747775"
_btn_hover_bg    = "#37343F" if _DARK else "#F0F4F9"
_input_border    = "#938F99" if _DARK else "#747775"
_input_focus     = "#A8C7FA" if _DARK else "#0B57D0"
_focus_ring      = "#004A77" if _DARK else "#D3E3FD"
_shadow          = "rgba(0,0,0,0.4)" if _DARK else "rgba(60,64,67,0.12)"

# Custom CSS for Google Material Design 3 (Material UI) — Dark/Light adaptive
st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Google+Sans:wght@400;500;700&family=Roboto:wght@300;400;500;700&family=Roboto+Mono:wght@400;500&display=swap');

    /* Global Material UI Typography & Surface */
    html, body, [class*="st-"], .stApp {{
        font-family: 'Google Sans', 'Roboto', -apple-system, BlinkMacSystemFont, sans-serif !important;
        background-color: {_bg_main} !important;
        color: {_text_col} !important;
    }}

    /* Google Material Top Navigation Header Card */
    .material-header-card {{
        background-color: {_bg_card};
        border: 1px solid {_border};
        border-radius: 20px;
        padding: 20px 28px;
        margin-bottom: 24px;
        box-shadow: 0 1px 3px {_shadow}, 0 4px 8px rgba(0,0,0,0.06);
    }}
    .material-title {{
        font-family: 'Google Sans', sans-serif;
        font-size: 2.1rem;
        font-weight: 700;
        color: {_title_col};
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 10px;
        letter-spacing: -0.5px;
    }}
    .material-subtitle {{
        font-size: 0.95rem;
        color: {_subtext};
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
    }}

    /* Material 3 Chips & Badges */
    .m3-chip {{
        display: inline-flex;
        align-items: center;
        padding: 5px 14px;
        border-radius: 50px;
        font-size: 0.85rem;
        font-weight: 500;
        letter-spacing: 0.2px;
    }}
    .m3-chip-blue  {{ background-color: {_chip_blue_bg};  color: {_chip_blue_fg};  }}
    .m3-chip-green {{ background-color: {_chip_green_bg}; color: {_chip_green_fg}; }}
    .m3-chip-gold  {{ background-color: {_chip_gold_bg};  color: {_chip_gold_fg};  }}
    .m3-chip-outline {{
        border: 1px solid {_chip_out_border};
        color: {_chip_out_fg};
        background-color: {_chip_out_bg};
    }}

    /* Material 3 Elevated Citation Cards */
    .citation-card {{
        background-color: {_citation_bg};
        border-left: 4px solid {_citation_border};
        border-radius: 12px;
        padding: 14px 18px;
        margin: 10px 0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.12);
        font-size: 0.92rem;
        color: {_text_col};
        line-height: 1.5;
    }}

    /* Material Design Button Overrides */
    .stButton > button {{
        border-radius: 20px !important;
        font-family: 'Google Sans', sans-serif !important;
        font-weight: 500 !important;
        border: 1px solid {_btn_border} !important;
        background-color: {_btn_bg} !important;
        color: {_btn_fg} !important;
        transition: all 0.2s cubic-bezier(0.2, 0, 0, 1) !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.12) !important;
    }}
    .stButton > button:hover {{
        background-color: {_btn_hover_bg} !important;
        border-color: {_input_focus} !important;
        color: {_btn_fg} !important;
        box-shadow: 0 2px 6px rgba(168,199,250,0.15) !important;
    }}

    /* Material Sidebar */
    [data-testid="stSidebar"] {{
        background-color: {_bg_sidebar} !important;
        border-right: 1px solid {_border} !important;
    }}
    [data-testid="stSidebar"] * {{
        color: {_text_col} !important;
    }}

    /* Markdown & headings */
    h1, h2, h3, h4, h5, h6, p, span, label, div {{
        color: {_text_col} !important;
    }}

    /* Chat message bubbles */
    [data-testid="stChatMessage"] {{
        background-color: {"#2B2930" if _DARK else "#FFFFFF"} !important;
        border: 1px solid {_border} !important;
        border-radius: 16px !important;
        margin-bottom: 8px !important;
    }}

    /* Input Field Material Focus */
    .stTextInput > div > div > input {{
        border-radius: 12px !important;
        border: 1px solid {_input_border} !important;
        font-family: 'Google Sans', sans-serif !important;
        background-color: {"#37343F" if _DARK else "#FFFFFF"} !important;
        color: {_text_col} !important;
    }}
    .stTextInput > div > div > input:focus {{
        border-color: {_input_focus} !important;
        box-shadow: 0 0 0 2px {_focus_ring} !important;
    }}

    /* Selectbox & radio */
    .stSelectbox > div > div,
    .stRadio > div {{
        background-color: {"#37343F" if _DARK else "transparent"} !important;
        border-radius: 12px !important;
    }}

    /* Expander */
    .streamlit-expanderHeader {{
        background-color: {"#37343F" if _DARK else "#F0F4F9"} !important;
        border-radius: 10px !important;
        color: {_text_col} !important;
    }}
    .streamlit-expanderContent {{
        background-color: {"#2B2930" if _DARK else "#FFFFFF"} !important;
    }}

    /* Code block */
    .stCodeBlock {{
        background-color: {"#121212" if _DARK else "#F6F8FA"} !important;
        border-radius: 10px !important;
    }}

    /* Divider */
    hr {{ border-color: {_border} !important; }}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_orchestrator():
    return RideWiseOrchestrator()


def should_show_audit_expander(res_or_citations, calculations=None, evidence=None, role="Customer"):
    """
    Determines whether the policy citations and audit evidence expander should be shown.
    Accepts either a response dictionary `res` or positional arguments `(citations, calculations, evidence)`.
    """
    if isinstance(res_or_citations, dict):
        res = res_or_citations
        citations = res.get("citations", [])
        calculations = res.get("calculations", {})
        evidence = res.get("evidence", "")
        intent = res.get("intent", "")
        retrieval_performed = res.get("retrieval_performed", True)
    else:
        citations = res_or_citations or []
        calculations = calculations or {}
        evidence = evidence or ""
        intent = ""
        retrieval_performed = True

    # 1. Casual greetings & conversational messages: NEVER display audit expander
    if intent == "conversational" or not retrieval_performed:
        return False

    role_str = role.lower().strip()

    # 2. Customer mode:
    # Show only customer-friendly answers by default.
    # Expose policy citations expander when policy citations exist on policy/calculation questions.
    # For booking/payment database queries, present readable answer without exposing raw audit expander by default.
    if role_str == "customer":
        if intent in ("policy", "calculation") and (citations or calculations):
            return True
        return False

    # 3. Support Agent mode:
    # Expose audit expander for authorized operational queries when citations, calculations, or DB evidence exist.
    if role_str in ("support agent", "agent"):
        if citations or calculations:
            return True
        if evidence and evidence.strip():
            return True
        return False

    return False


orchestrator = get_orchestrator()

# Initialize Session State
if "messages" not in st.session_state:
    st.session_state.messages = []
if "role" not in st.session_state:
    st.session_state.role = "Customer"
if "customer_id" not in st.session_state:
    st.session_state.customer_id = "CUST0001"
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False


# -------------------------------------------------------------
# SIDEBAR CONTROLS
# -------------------------------------------------------------
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/scooter.png", width=64)
    st.title("RideWise Assist")
    st.caption("Intelligent Two-Wheeler & EV Operations")
    st.divider()

    # 1. Role Selector
    st.subheader("👤 Active Session Role")
    selected_role = st.radio(
        "Select your role for evaluation:",
        options=["Customer", "Support Agent"],
        index=0 if st.session_state.role == "Customer" else 1,
        help="Evaluator role selection as specified in challenge section 7."
    )

    if selected_role != st.session_state.role:
        st.session_state.role = selected_role
        st.session_state.messages = []
        st.rerun()

    # 2. Customer ID (if Customer role)
    if st.session_state.role == "Customer":
        st.subheader("🔑 Customer Identity")
        cust_id_input = st.text_input(
            "Enter Customer ID:",
            value=st.session_state.customer_id,
            help="E.g., CUST0001, CUST0002, CUST0003"
        ).strip().upper()

        if cust_id_input != st.session_state.customer_id:
            st.session_state.customer_id = cust_id_input
            st.session_state.messages = []
            st.rerun()

        # Validate customer against DB
        profile = db.get_customer_profile(st.session_state.customer_id) if st.session_state.customer_id else None
        if profile:
            st.success(f"✓ Verified: **{profile['full_name']}**")
            st.markdown(f"**City:** {profile['city']} | **KYC:** `{profile['kyc_status']}`")
            st.markdown(f"**Tier:** `{profile['customer_tier']}`")
        else:
            st.error(f"❌ Customer ID '{st.session_state.customer_id}' not found in database.")

        st.caption("Quick Select Demo Customers:")
        col_c1, col_c2, col_c3 = st.columns(3)
        if col_c1.button("CUST0001"):
            st.session_state.customer_id = "CUST0001"
            st.session_state.messages = []
            st.rerun()
        if col_c2.button("CUST0002"):
            st.session_state.customer_id = "CUST0002"
            st.session_state.messages = []
            st.rerun()
        if col_c3.button("CUST0003"):
            st.session_state.customer_id = "CUST0003"
            st.session_state.messages = []
            st.rerun()

    else:
        st.subheader("🛡️ Support Agent Mode")
        st.info("Full operational access across all hubs, fleet inventory, bookings, and damage claims.")

    st.divider()

    # 3. Language Selector (Multilingual Chatbot Support)
    st.subheader("🌐 Language / भाषा")
    selected_language = st.selectbox(
        "Choose Chatbot Language:",
        options=["English", "Hindi (हिंदी)", "Kannada (ಕನ್ನಡ)", "Tamil (தமிழ்)", "Telugu (తెలుగు)"],
        index=0,
        help="Select language for conversational response."
    )

    st.divider()

    # 4. Dark Mode Toggle
    dark_label = "☀️ Light Mode" if st.session_state.dark_mode else "🌙 Dark Mode"
    if st.button(dark_label, use_container_width=True):
        st.session_state.dark_mode = not st.session_state.dark_mode
        st.rerun()

    # 5. New Conversation Button
    if st.button("🔄 New Conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.caption("System Status:")
    st.markdown("🟢 **Database:** SQLite (Read-Only URI)")
    st.markdown("🟢 **Policies:** 5 Indexed PDFs + Verified OCR")
    st.markdown("🟢 **LLM Model:** gpt-oss-120b (NeoStats)")


# -------------------------------------------------------------
# MAIN CHAT INTERFACE
# -------------------------------------------------------------
if st.session_state.role == "Customer":
    profile = db.get_customer_profile(st.session_state.customer_id) if st.session_state.customer_id else None
    tier_label = profile['customer_tier'] if profile else "STANDARD"
    kyc_label = profile['kyc_status'] if profile else "VERIFIED"
    city_label = profile['city'] if profile else "Bangalore"
    name_label = profile['full_name'] if profile else st.session_state.customer_id

    st.markdown(
        f'''
        <div class="material-header-card">
            <div class="material-title">🛵 RideWise Assist</div>
            <div class="material-subtitle">
                <span>Active Customer Session:</span>
                <span class="m3-chip m3-chip-blue"><b>{st.session_state.customer_id}</b> ({name_label})</span>
                <span class="m3-chip m3-chip-green">✓ KYC {kyc_label}</span>
                <span class="m3-chip m3-chip-gold">Tier: {tier_label}</span>
                <span class="m3-chip m3-chip-outline">📍 {city_label}</span>
            </div>
        </div>
        ''',
        unsafe_allow_html=True
    )
else:
    st.markdown(
        '''
        <div class="material-header-card">
            <div class="material-title">🛵 RideWise Assist</div>
            <div class="material-subtitle">
                <span class="m3-chip m3-chip-blue">🛡️ Support Desk & Hub Operations Mode</span>
                <span class="m3-chip m3-chip-outline">Cross-Fleet Analytics & Operational Diagnostics</span>
            </div>
        </div>
        ''',
        unsafe_allow_html=True
    )

# Display Chat History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🧑‍💻" if msg["role"] == "user" else "🛵"):
        st.markdown(msg["content"])

        # Display expandable citations & calculations if available
        if msg["role"] == "assistant" and st.session_state.role == "Customer":
            if should_show_audit_expander(msg, role=st.session_state.role):
                with st.expander("🔍 View Policy Citations"):
                    citations = msg.get("citations", [])
                    calculations = msg.get("calculations", {})

                    if citations:
                        st.markdown("#### 📄 Document Sources & Citations")
                        for idx, c in enumerate(citations, 1):
                            st.markdown(
                                f"<div class='citation-card'>"
                                f"<b>[{idx}] {c['title']} ({c['doc_id']})</b> — Version: <code>{c['version']}</code> | Page {c['page']}<br>"
                                f"<b>Section:</b> {c['section']}<br>"
                                f"<i>{c['content'][:250]}...</i>"
                                f"</div>",
                                unsafe_allow_html=True
                            )

                    if calculations:
                        st.markdown("#### 🧮 Deterministic Calculations Breakdown")
                        for calc_key, calc_val in calculations.items():
                            st.markdown(f"- **{calc_key}:** `{calc_val.get('reason', calc_val.get('formula', str(calc_val)))}`")


# Chat Input Box
user_prompt = st.chat_input("Ask a question about bookings, refunds, late return penalties, EV guidelines, or fleet...")

if user_prompt:
    # Display user message
    st.session_state.messages.append({"role": "user", "content": user_prompt})
    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(user_prompt)

    # Process query through Orchestrator
    with st.chat_message("assistant", avatar="🛵"):
        with st.spinner("Analyzing operational database and policy documents..."):
            history_tuples = [
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.messages[:-1]
            ]
            res = orchestrator.process_query(
                role=st.session_state.role.lower(),
                user_query=user_prompt,
                session_customer_id=st.session_state.customer_id if st.session_state.role == "Customer" else None,
                conversation_history=history_tuples,
                language=selected_language
            )

            st.markdown(res["answer"])

            # Render Citations expander — Customer mode only
            if st.session_state.role == "Customer" and should_show_audit_expander(res, role="Customer"):
                with st.expander("🔍 View Policy Citations"):
                    if res.get("citations"):
                        st.markdown("#### 📄 Document Sources & Citations")
                        for idx, c in enumerate(res["citations"], 1):
                            st.markdown(
                                f"<div class='citation-card'>"
                                f"<b>[{idx}] {c['title']} ({c['doc_id']})</b> — Version: <code>{c['version']}</code> | Page {c['page']}<br>"
                                f"<b>Section:</b> {c['section']}<br>"
                                f"<i>{c['content'][:250]}...</i>"
                                f"</div>",
                                unsafe_allow_html=True
                            )

                    if res.get("calculations"):
                        st.markdown("#### 🧮 Deterministic Calculations Breakdown")
                        for calc_key, calc_val in res["calculations"].items():
                            st.markdown(f"- **{calc_key}:** `{calc_val.get('reason', calc_val.get('formula', str(calc_val)))}`")

    # Save assistant message to state
    st.session_state.messages.append({
        "role": "assistant",
        "content": res["answer"],
        "citations": res.get("citations", []),
        "evidence": res.get("evidence", ""),
        "calculations": res.get("calculations", {}),
        "intent": res.get("intent"),
        "retrieval_performed": res.get("retrieval_performed", True)
    })
