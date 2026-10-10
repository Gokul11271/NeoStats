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

# Custom CSS for styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .status-badge-verified {
        background-color: #DEF7EC;
        color: #03543F;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .status-badge-gold {
        background-color: #FEF3C7;
        color: #92400E;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .citation-card {
        background-color: #F8FAFC;
        border-left: 4px solid #3B82F6;
        padding: 10px 14px;
        margin: 6px 0;
        border-radius: 4px;
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_orchestrator():
    return RideWiseOrchestrator()


orchestrator = get_orchestrator()

# Initialize Session State
if "messages" not in st.session_state:
    st.session_state.messages = []
if "role" not in st.session_state:
    st.session_state.role = "Customer"
if "customer_id" not in st.session_state:
    st.session_state.customer_id = "CUST0001"


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

    # 3. New Conversation Button
    if st.button("🔄 Start New Conversation", use_container_width=True):
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
st.markdown('<div class="main-header">🛵 RideWise Assist</div>', unsafe_allow_html=True)
if st.session_state.role == "Customer":
    st.markdown(
        f'<div class="sub-header">Customer Session: <b>{st.session_state.customer_id}</b> | '
        f'Deterministic Pricing, Cancellations & Policy Assistance</div>',
        unsafe_allow_html=True
    )
else:
    st.markdown(
        '<div class="sub-header">Support Desk & Hub Operations Session | Cross-Fleet Analytics & Policy Verification</div>',
        unsafe_allow_html=True
    )

# Display Chat History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🧑‍💻" if msg["role"] == "user" else "🛵"):
        st.markdown(msg["content"])

        # Display expandable citations & calculations if available
        if msg["role"] == "assistant":
            citations = msg.get("citations", [])
            evidence = msg.get("evidence", "")
            calculations = msg.get("calculations", {})

            if citations or calculations or evidence:
                with st.expander("🔍 View Policy Citations & Audit Evidence"):
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

                    if evidence:
                        st.markdown("#### 🗄️ Untrusted Raw Evidence Payload")
                        st.code(evidence, language="text")


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
                conversation_history=history_tuples
            )

            st.markdown(res["answer"])

            # Render Citations & Audit expander
            if res.get("citations") or res.get("calculations") or res.get("evidence"):
                with st.expander("🔍 View Policy Citations & Audit Evidence"):
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

                    if res.get("evidence"):
                        st.markdown("#### 🗄️ Untrusted Raw Evidence Payload")
                        st.code(res["evidence"], language="text")

    # Save assistant message to state
    st.session_state.messages.append({
        "role": "assistant",
        "content": res["answer"],
        "citations": res.get("citations", []),
        "evidence": res.get("evidence", ""),
        "calculations": res.get("calculations", {})
    })
