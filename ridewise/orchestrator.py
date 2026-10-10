"""
RideWise Assist Orchestrator
Coordinates Role-Based Authorization, Database Retrieval, Deterministic Calculations,
Policy Matching, Prompt-Injection Protection, and LLM Synthesis with Graceful Fallbacks.
"""
import re
from typing import Any, Dict, List, Optional, Tuple
from ridewise import db
from ridewise.calculations import (
    calculate_rental_charge,
    calculate_security_deposit,
    calculate_cancellation_refund,
    calculate_late_return_penalty,
    calculate_ev_battery_penalty,
    assess_damage_charge,
    get_cancellation_policy_version
)
from ridewise.policies import get_policy_store
from ridewise.llm_client import (
    RideWiseLLMClient,
    SYSTEM_PROMPT_CUSTOMER,
    SYSTEM_PROMPT_AGENT
)


class RideWiseOrchestrator:
    def __init__(self, llm_client: Optional[RideWiseLLMClient] = None):
        self.llm_client = llm_client or RideWiseLLMClient()
        self.policy_store = get_policy_store()

    def process_query(
        self,
        role: str,
        user_query: str,
        session_customer_id: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        language: str = "English"
    ) -> Dict[str, Any]:
        """
        Main processing pipeline.
        Returns a dict with 'answer', 'citations', 'evidence', 'calculations', 'is_fallback'.
        """
        role = role.lower().strip()
        user_query_clean = user_query.strip()
        conversation_history = conversation_history or []

        # -------------------------------------------------------------
        # 1. SECURITY & RBAC ENFORCEMENT (Python Layer)
        # -------------------------------------------------------------
        ALLOWED_ROLES = {"customer", "agent", "support agent"}
        if role not in ALLOWED_ROLES:
            return {
                "answer": f"Error: Invalid role '{role}'. Allowed roles are 'Customer' and 'Support Agent'.",
                "citations": [],
                "evidence": "",
                "calculations": {},
                "is_fallback": False
            }

        q_lower = user_query_clean.lower()

        # -------------------------------------------------------------
        # Conversational / Greeting Intent Detection
        # -------------------------------------------------------------
        GREETING_PATTERNS = [
            "hi", "hii", "hiii", "hello", "hey", "heyy", "greetings",
            "good morning", "good afternoon", "good evening", "good night",
            "thanks", "thank you", "thanks a lot", "thanks so much", "thank you so much",
            "thx", "ty", "bye", "goodbye", "how are you", "who are you",
            "what can you do", "help me", "ok", "okay", "cool", "great", "welcome"
        ]

        GREETING_WORDS = {
            "hi", "hii", "hiii", "hello", "hey", "heyy", "greetings",
            "good", "morning", "afternoon", "evening", "night",
            "thanks", "thank", "you", "thx", "ty", "bye", "goodbye",
            "there", "awesome", "great", "ok", "okay", "cool", "help",
            "assistant", "bot", "ridewise", "team", "support",
            "so", "much", "very", "lot", "a", "for", "your", "kind", "many"
        }

        DOMAIN_KEYWORDS = [
            "booking", "bookings", "payment", "payments", "vehicle", "vehicles",
            "scooter", "scooters", "bike", "bikes", "rental", "rentals", "rent",
            "cancel", "cancellation", "refund", "refunds", "late", "penalty", "penalties",
            "battery", "ev", "damage", "damages", "claim", "claims", "deposit", "deposits",
            "policy", "policies", "terms", "rule", "rules", "fee", "fees", "cost", "costs",
            "price", "prices", "rate", "rates", "charge", "charges", "hub", "hubs",
            "fleet", "customer", "customers", "distinct", "summary", "failed", "pending",
            "missing", "upcoming", "how many", "count", "total", "list", "show", "summarize",
            "breakdown", "calculate", "hours", "hrs", "rupees", "inr"
        ]

        clean_q = re.sub(r"[^\w\s]", "", q_lower).strip()
        has_domain_keyword = any(kw in q_lower for kw in DOMAIN_KEYWORDS)
        has_id_pattern = bool(re.search(r"\b(CUST\d+|B-\d+|VEH\d+|V-\d+|KA\d+)\b", user_query_clean, re.IGNORECASE))
        q_tokens = set(clean_q.split())

        is_conversational = False
        if not has_domain_keyword and not has_id_pattern:
            if clean_q in GREETING_PATTERNS or (q_tokens and q_tokens.issubset(GREETING_WORDS)):
                is_conversational = True

        # Intent detection flags
        is_distinct_cust_query = any(k in q_lower for k in [
            "distinct customer", "unique customer", "list customer", "all customer",
            "show customer", "how many customer", "count of customer", "total customer",
            "customers in my database", "customers in the database", "customer table"
        ]) and not any(k in q_lower for k in ["never booked", "no booking", "without booking", "zero booking"])

        is_no_booking_cust_query = any(k in q_lower for k in [
            "never booked", "no booking", "without booking", "zero booking", "has not booked", "have not booked"
        ]) and "customer" in q_lower

        is_financial_summary_query = ("summarize" in q_lower or "summary" in q_lower or "breakdown" in q_lower) and any(
            k in q_lower for k in ["payment", "financial", "revenue", "penalty", "penalties", "refund", "double-counting", "double counting"]
        )

        is_failed_or_pending_payment_query = any(k in q_lower for k in [
            "failed and pending", "pending and failed", "failed or pending", "pending payment", "pending payments"
        ])

        is_failed_payment_query = is_failed_or_pending_payment_query or any(k in q_lower for k in [
            "failed payment", "failed transaction", "unsuccessful payment", "payment failed", "declined payment"
        ])

        is_top_damaged_query = any(k in q_lower for k in [
            "most damage", "ten vehicle", "10 vehicle", "top damage", "vehicles with the most"
        ])

        is_open_disputed_damage_query = any(k in q_lower for k in [
            "open and disputed", "disputed and open", "open damage", "disputed damage", "open claim", "disputed claim"
        ])

        is_missing_return_query = any(k in q_lower for k in [
            "missing return", "missing timestamp", "without return timestamp", "missing actual return"
        ])

        is_upcoming_booking_query = any(k in q_lower for k in [
            "upcoming booking", "future booking", "next booking"
        ])

        is_damage_query = is_top_damaged_query or is_open_disputed_damage_query or any(k in q_lower for k in ["damage", "accident", "scratch", "claim"])

        if role == "customer":
            if not session_customer_id:
                return {
                    "answer": "Error: A valid Customer ID is required to start a customer session.",
                    "citations": [],
                    "evidence": "",
                    "calculations": {},
                    "is_fallback": False
                }

            # Verify customer exists in database
            profile = db.get_customer_profile(session_customer_id)
            if not profile:
                return {
                    "answer": f"Error: Customer ID '{session_customer_id}' was not found in RideWise records.",
                    "citations": [],
                    "evidence": "",
                    "calculations": {},
                    "is_fallback": False
                }

            # Check for cross-customer probing attempts in user query
            other_cust_match = re.findall(r"\b(CUST\d{4})\b", user_query_clean, re.IGNORECASE)
            for cid in other_cust_match:
                if cid.upper() != session_customer_id.upper():
                    return {
                        "answer": (
                            f"Access Denied: You are logged in as customer {session_customer_id}. "
                            f"You are not authorized to view or query records for {cid.upper()}."
                        ),
                        "citations": [],
                        "evidence": "Cross-customer access attempt blocked by application authorization.",
                        "calculations": {},
                        "is_fallback": False
                    }

            # Check if customer is attempting administrative cross-customer queries
            if is_distinct_cust_query or is_no_booking_cust_query or is_financial_summary_query:
                return {
                    "answer": (
                        f"Access Denied: You are logged in as customer {session_customer_id}. "
                        f"You are only authorized to view your own profile, bookings, payments, and damage claims. "
                        f"Global administrative queries regarding all customers or company-wide finances are restricted to Support Agents."
                    ),
                    "citations": [],
                    "evidence": "Cross-customer administrative query blocked by application authorization.",
                    "calculations": {},
                    "is_fallback": False
                }

        # Handle Conversational / Greeting intent directly without retrieval
        if is_conversational:
            system_prompt = (
                SYSTEM_PROMPT_CUSTOMER.format(customer_id=session_customer_id or "UNKNOWN")
                if role == "customer"
                else SYSTEM_PROMPT_AGENT
            )
            messages = [{"role": "system", "content": system_prompt}]
            for h in conversation_history[-4:]:
                messages.append({"role": h["role"], "content": h["content"]})

            lang_instruction = ""
            if language and language.lower() != "english":
                lang_instruction = f" Please reply in {language}."

            messages.append({
                "role": "user",
                "content": (
                    f"User Message: {user_query_clean}\n\n"
                    f"Instructions:\n"
                    f"1. Respond politely and helpfully to the user's greeting or pleasantry.\n"
                    f"2. Do not state or fabricate operational data, bookings, or policy details.\n"
                    f"3. Briefly ask how you can assist with RideWise two-wheeler & EV rentals."
                    f"{lang_instruction}"
                )
            })

            try:
                llm_response = self.llm_client.generate_response(messages)
            except Exception:
                llm_response = "Hello! How can I assist you with your RideWise rental today?"

            return {
                "answer": llm_response,
                "citations": [],
                "evidence": "",
                "calculations": {},
                "is_fallback": False,
                "intent": "conversational",
                "retrieval_performed": False
            }

        # -------------------------------------------------------------
        # 2. DATA GATHERING & DETERMINISTIC CALCULATIONS
        # -------------------------------------------------------------
        evidence_blocks: List[str] = []
        calculations: Dict[str, Any] = {}
        citations: List[Dict[str, Any]] = []

        if role == "customer":
            assert session_customer_id is not None
            profile = db.get_customer_profile(session_customer_id)
            evidence_blocks.append(
                f"[Database Evidence - Customer Profile]\n"
                f"Customer ID: {profile['customer_id']}\n"
                f"Name: {profile['full_name']}\n"
                f"Phone: {profile['phone']}\n"
                f"Email: {profile['email']}\n"
                f"City: {profile['city']}\n"
                f"KYC Status: {profile['kyc_status']}\n"
                f"Customer Tier: {profile['customer_tier']}\n"
            )

            # 1. Customer Upcoming Bookings
            if is_upcoming_booking_query:
                upc_list = db.get_customer_upcoming_bookings(session_customer_id)
                evidence_blocks.append(f"[Database Evidence - Customer Upcoming Bookings ({len(upc_list)} records)]")
                if upc_list:
                    for b in upc_list:
                        evidence_blocks.append(
                            f"  - Booking {b['booking_id']}: {b['model']} ({b['vehicle_type']}, Reg: {b['registration_no']}) | "
                            f"Hub: {b['hub_name']} | Scheduled: {b['scheduled_start']} to {b['scheduled_end']} | Status: {b['booking_status']}"
                        )
                else:
                    evidence_blocks.append("  You currently have no upcoming bookings scheduled.")

            # 2. Customer Failed Payments Query
            if is_failed_payment_query:
                cust_failed_p = db.get_customer_failed_payments(session_customer_id)
                evidence_blocks.append(f"[Database Evidence - Customer Failed Payments ({len(cust_failed_p)} records)]")
                if cust_failed_p:
                    for p in cust_failed_p:
                        evidence_blocks.append(
                            f"  - Payment ID: {p['payment_id']} | Booking ID: {p['booking_id']} | Type: {p['payment_type']} | "
                            f"Amount: ₹{p['amount']} (+ ₹{p['gst_amount']} GST) | Method: {p['payment_method']} | "
                            f"Status: {p['payment_status']} | Paid At: {p['paid_at']} | Remarks: {p['remarks']}"
                        )
                else:
                    evidence_blocks.append("  No failed payments found for your account.")

            # 3. Customer Vehicle Damage Query
            veh_match = re.search(r"\b(VEH\d{3}|VEH\d{1,4}|V-\d{1,4}|KA\d{2}[A-Z0-9]+)\b", user_query_clean, re.IGNORECASE)
            if is_damage_query and veh_match:
                v_term = veh_match.group(1).upper()
                cust_dmg = db.get_customer_damages_for_vehicle(session_customer_id, v_term)
                evidence_blocks.append(f"[Database Evidence - Customer Damage Reports for Vehicle '{v_term}' ({len(cust_dmg)} records)]")
                if cust_dmg:
                    for d in cust_dmg:
                        evidence_blocks.append(
                            f"  - Report ID: {d['report_id']} | Booking: {d['booking_id']} | Category: {d['damage_category']} | "
                            f"Severity: {d['severity']} | Assessed Cost: ₹{d['assessed_cost']} | Status: {d['claim_status']} | "
                            f"Notes: {d['description']}"
                        )
                else:
                    evidence_blocks.append(f"  No damage reports found for vehicle '{v_term}' under your bookings.")

            # Check if specific booking ID was referenced
            booking_match = re.search(r"\b(B-\d{4})\b", user_query_clean, re.IGNORECASE)
            specific_b_id = booking_match.group(1).upper() if booking_match else None

            # Fetch customer bookings
            bookings = db.get_customer_bookings(session_customer_id, booking_id=specific_b_id)
            if bookings:
                evidence_blocks.append(f"[Database Evidence - Customer Bookings ({len(bookings)} found)]")
                for b in bookings[:5]:  # Limit to 5 most relevant bookings
                    b_id = b["booking_id"]
                    evidence_blocks.append(
                        f"Booking ID: {b_id} | Status: {b['booking_status']} | Vehicle: {b['model']} ({b['vehicle_type']}, Reg: {b['registration_no']})\n"
                        f"  Hub: {b['hub_name']} | Hourly Rate: ₹{b['hourly_rate']} | Daily Rate: ₹{b['daily_rate']}\n"
                        f"  Booked At (UTC): {b['booked_at']}\n"
                        f"  Scheduled: {b['scheduled_start']} to {b['scheduled_end']}\n"
                        f"  Actual Return (UTC): {b['actual_return_at'] or 'None'}\n"
                        f"  Cancelled At (UTC): {b['cancelled_at'] or 'None'}\n"
                        f"  Return Battery %: {b['return_battery_pct'] if b['return_battery_pct'] is not None else 'N/A'}"
                    )

                    # Payments for this booking
                    payments = db.get_booking_payments_for_customer(session_customer_id, b_id)
                    if payments:
                        evidence_blocks.append(f"  Payments for {b_id}:")
                        for p in payments:
                            evidence_blocks.append(
                                f"    - Payment ID: {p['payment_id']} | Type: {p['payment_type']} | Status: {p['payment_status']} | "
                                f"Amount (ex GST): ₹{p['amount']} | GST: ₹{p['gst_amount']} | Method: {p['payment_method']} | "
                                f"Paid At: {p['paid_at']} | Remarks: {p['remarks']}"
                            )

                    # Damages for this booking
                    damages = db.get_booking_damages_for_customer(session_customer_id, b_id)
                    if damages:
                        evidence_blocks.append(f"  Damage Reports for {b_id}:")
                        for d in damages:
                            evidence_blocks.append(
                                f"    - Report: {d['report_id']} | Category: {d['damage_category']} | Severity: {d['severity']} | "
                                f"Assessed Cost: ₹{d['assessed_cost']} | Claim Status: {d['claim_status']} | Notes: {d['description']}"
                            )

                    # -----------------------------------------
                    # Run deterministic calculations for booking
                    # -----------------------------------------
                    # 1. Cancellation calculation if cancelled or asked
                    if b["booking_status"] in ("CNL_U", "CNL_S", "NSH") or b["cancelled_at"] or any(k in q_lower for k in ["cancel", "refund"]):
                        paid_rental = sum(
                            p["amount"] for p in payments
                            if p["payment_type"] == "BOOKING" and p["payment_status"] == "SUCCESS"
                        )
                        paid_gst = sum(
                            p["gst_amount"] for p in payments
                            if p["payment_type"] == "BOOKING" and p["payment_status"] == "SUCCESS"
                        )
                        refund_calc = calculate_cancellation_refund(
                            booked_at_str=b["booked_at"],
                            scheduled_start_str=b["scheduled_start"],
                            cancelled_at_str=b["cancelled_at"] or b["booked_at"],
                            paid_rental_amount=paid_rental,
                            paid_gst_amount=paid_gst,
                            is_ridewise_cancelled=(b["booking_status"] == "CNL_S"),
                            is_no_show=(b["booking_status"] == "NSH")
                        )
                        calculations[f"{b_id}_cancellation_refund"] = refund_calc
                        evidence_blocks.append(f"  [Deterministic Refund Calculation for {b_id}]: {refund_calc['reason']}")

                    # 2. Late Return & Battery penalty calculation if completed
                    if b["actual_return_at"]:
                        late_calc = calculate_late_return_penalty(
                            customer_tier=profile["customer_tier"],
                            hourly_rate=b["hourly_rate"],
                            scheduled_end_str=b["scheduled_end"],
                            actual_return_str=b["actual_return_at"]
                        )
                        calculations[f"{b_id}_late_return"] = late_calc
                        evidence_blocks.append(f"  [Deterministic Late Fee Calculation for {b_id}]: {late_calc['reason']}")

                        if "EV" in b["vehicle_type"]:
                            ev_calc = calculate_ev_battery_penalty(
                                vehicle_type=b["vehicle_type"],
                                return_battery_pct=b["return_battery_pct"]
                            )
                            calculations[f"{b_id}_ev_battery"] = ev_calc
                            evidence_blocks.append(f"  [Deterministic EV Battery Penalty for {b_id}]: {ev_calc['reason']}")
                    elif any(k in q_lower for k in ["late", "penalty"]):
                        evidence_blocks.append(f"  [Note for {b_id}]: Booking is not completed yet; actual return timestamp is unknown so late fees cannot be calculated.")

                    # 3. Damage assessment
                    if damages:
                        for dmg in damages:
                            dmg_calc = assess_damage_charge(dmg["claim_status"], dmg["assessed_cost"])
                            calculations[f"{dmg['report_id']}_damage"] = dmg_calc
                            evidence_blocks.append(f"  [Deterministic Damage Liability for {dmg['report_id']}]: {dmg_calc['reason']}")
            elif specific_b_id:
                evidence_blocks.append(f"[Database Evidence - Booking Details for {specific_b_id}]\nBooking ID '{specific_b_id}' does not exist or does not belong to your account.")

        else:
            # SUPPORT AGENT ROLE
            evidence_blocks.append("[Database Evidence - Support Agent Operational Session Active]")

            # Regex matches
            cust_match = re.search(r"\b(CUST\d{4})\b", user_query_clean, re.IGNORECASE)
            booking_match = re.search(r"\b(B-\d{4})\b", user_query_clean, re.IGNORECASE)
            vehicle_match = re.search(r"\b(VEH\d{3}|VEH\d{1,4}|V-\d{1,4}|KA\d{2}[A-Z0-9]+)\b", user_query_clean, re.IGNORECASE)

            # 1. Financial / Payment Summary
            if is_financial_summary_query:
                fin_summary = db.agent_get_payment_financial_summary()
                evidence_blocks.append("[Database Evidence - Financial & Payment Summary (No Double-Counting)]")
                evidence_blocks.append("Summary of successful payments, refunds, and penalties strictly grouped by payment type:")
                for ptype, pinfo in fin_summary.items():
                    evidence_blocks.append(
                        f"- Type: {ptype} | Transactions: {pinfo['count']} | Base Amount: ₹{pinfo['total_amount']} | "
                        f"18% GST: ₹{pinfo['total_gst']} | Net Total: ₹{pinfo['net_total']}"
                    )

            # 2. Failed and Pending Payments Query
            elif is_failed_or_pending_payment_query:
                failed_pending = db.agent_get_failed_and_pending_payments(limit=50)
                evidence_blocks.append(f"[Database Evidence - Failed and Pending Payments ({len(failed_pending)} records)]")
                if failed_pending:
                    for p in failed_pending:
                        evidence_blocks.append(
                            f"- Payment ID: {p['payment_id']} | Booking: {p['booking_id']} | Customer: {p['customer_id']} | "
                            f"Type: {p['payment_type']} | Amount: ₹{p['amount']} (+ ₹{p['gst_amount']} GST) | "
                            f"Method: {p['payment_method']} | Status: {p['payment_status']} | Paid At: {p['paid_at']} | Remarks: {p['remarks']}"
                        )
                else:
                    evidence_blocks.append("No failed or pending payment transactions found in database.")

            # 3. Top Damaged Vehicles Query
            elif is_top_damaged_query:
                top_vehicles = db.agent_get_top_damaged_vehicles(limit=10)
                evidence_blocks.append(f"[Database Evidence - Top {len(top_vehicles)} Vehicles with Most Damage Reports]")
                for v in top_vehicles:
                    evidence_blocks.append(
                        f"- Vehicle ID: {v['vehicle_id']} | Model: {v['model']} (Reg: {v['registration_no']}) | "
                        f"Hub: {v['hub_name']} | Damage Incidents: {v['damage_count']} | Total Assessed Cost: ₹{v['total_assessed_cost']}"
                    )

            # 4. Open and Disputed Damage Claims Query
            elif is_open_disputed_damage_query:
                open_disputed = db.agent_get_open_and_disputed_damages(limit=50)
                evidence_blocks.append(f"[Database Evidence - Open and Disputed Damage Claims ({len(open_disputed)} records)]")
                if open_disputed:
                    for d in open_disputed:
                        evidence_blocks.append(
                            f"- Report: {d['report_id']} | Booking: {d['booking_id']} | Vehicle: {d['vehicle_model']} ({d['vehicle_id']}) | "
                            f"Status: {d['claim_status']} | Assessed Cost: ₹{d['assessed_cost']} | Category: {d['damage_category']} | Notes: {d['description']}"
                        )
                else:
                    evidence_blocks.append("No open or disputed damage claims found in database.")

            # 5. Completed Bookings Missing Return Timestamps
            elif is_missing_return_query:
                missing_returns = db.agent_get_completed_bookings_missing_return()
                evidence_blocks.append(f"[Database Evidence - Completed Bookings Missing Return Timestamps ({len(missing_returns)} records)]")
                if missing_returns:
                    for b in missing_returns:
                        evidence_blocks.append(f"- Booking {b['booking_id']} (Customer: {b['customer_id']}, Vehicle: {b['vehicle_id']}) has missing actual return timestamp.")
                else:
                    evidence_blocks.append("Audit result: 0 completed bookings are missing return timestamps. All completed trips have valid return timestamps.")

            # 6. Distinct Customers / Customer Count Query
            elif is_distinct_cust_query:
                is_count_q = any(k in q_lower for k in ["how many", "count", "number of", "total count"])
                if is_count_q:
                    count_res = db.agent_get_distinct_customers(count_only=True)
                    evidence_blocks.append(
                        f"[Database Evidence - Distinct Customer Count]\n"
                        f"Total Distinct Customers in Database: {count_res['total_distinct_customers']}"
                    )
                else:
                    cust_list = db.agent_get_distinct_customers(count_only=False, limit=100)
                    evidence_blocks.append(f"[Database Evidence - Distinct Customers List ({len(cust_list)} records)]")
                    evidence_blocks.append("Privacy Notice: Sensitive PII (phone, email, driving license) excluded.")
                    for c in cust_list:
                        evidence_blocks.append(
                            f"- {c['customer_id']}: {c['full_name']} | City: {c['city']} | KYC: {c['kyc_status']} | Tier: {c['customer_tier']} | Joined: {c['created_at']}"
                        )

            # 7. Customers Who Have Never Booked Query
            elif is_no_booking_cust_query:
                no_booking_list = db.agent_get_customers_without_bookings(limit=100)
                evidence_blocks.append(f"[Database Evidence - Customers Who Have Never Booked ({len(no_booking_list)} records)]")
                if no_booking_list:
                    for c in no_booking_list:
                        evidence_blocks.append(
                            f"- {c['customer_id']}: {c['full_name']} | City: {c['city']} | KYC: {c['kyc_status']} | Tier: {c['customer_tier']}"
                        )
                else:
                    evidence_blocks.append("All registered customers have placed at least one booking.")

            # 8. Failed Payments Query
            elif is_failed_payment_query:
                failed_payments = db.agent_get_failed_payments(limit=50)
                evidence_blocks.append(f"[Database Evidence - System Failed Payments ({len(failed_payments)} records)]")
                if failed_payments:
                    for p in failed_payments:
                        evidence_blocks.append(
                            f"- Payment ID: {p['payment_id']} | Booking: {p['booking_id']} | Customer: {p['customer_id']} | "
                            f"Type: {p['payment_type']} | Amount: ₹{p['amount']} (+ ₹{p['gst_amount']} GST) | "
                            f"Method: {p['payment_method']} | Status: {p['payment_status']} | Paid At: {p['paid_at']} | Remarks: {p['remarks']}"
                        )
                else:
                    evidence_blocks.append("No failed payment transactions found in database.")

            # 9. Vehicle Damage Reports Query
            elif is_damage_query or vehicle_match:
                v_term = vehicle_match.group(1).upper() if vehicle_match else None
                if v_term:
                    dmgs = db.agent_get_damage_reports_for_vehicle(v_term, limit=50)
                    evidence_blocks.append(f"[Database Evidence - Damage Reports for Vehicle '{v_term}' ({len(dmgs)} records)]")
                else:
                    dmgs = db.agent_get_damage_reports(limit=50)
                    evidence_blocks.append(f"[Database Evidence - All Damage Reports ({len(dmgs)} records)]")

                if dmgs:
                    for d in dmgs:
                        evidence_blocks.append(
                            f"- Report: {d['report_id']} | Booking: {d['booking_id']} | Vehicle: {d.get('vehicle_model', d['vehicle_id'])} ({d['vehicle_id']}) | "
                            f"Category: {d['damage_category']} | Severity: {d['severity']} | Assessed Cost: ₹{d['assessed_cost']} | "
                            f"Status: {d['claim_status']} | Reported By: {d['reported_by']} | Notes: {d['description']}"
                        )
                else:
                    evidence_blocks.append("No damage reports found matching query criteria.")

            elif cust_match:
                cid = cust_match.group(1).upper()
                c_profile = db.agent_get_customer_profile(cid)
                if c_profile:
                    evidence_blocks.append(
                        f"[Database Evidence - Customer Profile for {cid}]\n"
                        f"Name: {c_profile['full_name']} | Phone: {c_profile['phone']} | KYC: {c_profile['kyc_status']} | Tier: {c_profile['customer_tier']}"
                    )
                else:
                    evidence_blocks.append(f"[Database Evidence - Customer Profile for {cid}]\nCustomer '{cid}' not found in database.")
                c_bookings = db.agent_search_bookings(customer_id=cid, limit=5)
                evidence_blocks.append(f"[Database Evidence - Recent Bookings for {cid}: {len(c_bookings)} records]")
                for b in c_bookings:
                    evidence_blocks.append(f"- Booking {b['booking_id']} ({b['model']}, Hub: {b['hub_name']}, Status: {b['booking_status']})")

            elif booking_match:
                bid = booking_match.group(1).upper()
                b_detail = db.agent_get_booking_details(bid)
                if b_detail:
                    evidence_blocks.append(
                        f"[Database Evidence - Booking Details for {bid}]\n"
                        f"Customer: {b_detail['customer_name']} ({b_detail['customer_id']}) | Tier: {b_detail['customer_tier']}\n"
                        f"Vehicle: {b_detail['model']} ({b_detail['vehicle_type']}, Reg: {b_detail['registration_no']}) | Hub: {b_detail['hub_name']}\n"
                        f"Status: {b_detail['booking_status']} | Booked: {b_detail['booked_at']}\n"
                        f"Scheduled: {b_detail['scheduled_start']} to {b_detail['scheduled_end']}\n"
                        f"Actual Return: {b_detail['actual_return_at'] or 'None'} | Cancelled: {b_detail['cancelled_at'] or 'None'}\n"
                        f"Return Battery %: {b_detail['return_battery_pct']}"
                    )
                    payments = b_detail.get("payments", [])
                    evidence_blocks.append(f"Payments: {len(payments)} transaction(s)")
                    for p in payments:
                        evidence_blocks.append(f"  - {p['payment_id']}: {p['payment_type']} ₹{p['amount']} (+ ₹{p['gst_amount']} GST) Status: {p['payment_status']} Notes: {p['remarks']}")

                    damages = b_detail.get("damage_reports", [])
                    evidence_blocks.append(f"Damage Reports: {len(damages)}")
                    for d in damages:
                        evidence_blocks.append(f"  - {d['report_id']}: {d['damage_category']} ₹{d['assessed_cost']} Status: {d['claim_status']} Notes: {d['description']}")
                else:
                    evidence_blocks.append(f"[Database Evidence - Booking Details for {bid}]\nNo booking found matching ID '{bid}'.")

            else:
                # Operational summary / Fleet lookup
                summary = db.agent_get_operational_summary()
                evidence_blocks.append(
                    f"[Database Evidence - Operational Fleet & Hub Summary]\n"
                    f"Fleet Status Breakdown: {summary['fleet_summary']}\n"
                    f"Hub Distribution: {summary['hub_distribution']}\n"
                    f"Booking Status Breakdown: {summary['booking_summary']}\n"
                    f"KYC Breakdown: {summary['kyc_summary']}\n"
                    f"Damage Claims Overview: {summary['damage_summary']}"
                )

        # -------------------------------------------------------------
        # 3. DYNAMIC VEHICLE RATE CALCULATION (From SQLite DB rates)
        # -------------------------------------------------------------
        hour_match = re.search(r"(\d+)\s*(?:hours|hrs|hr)", user_query_clean, re.IGNORECASE)
        is_calc_query = any(w in q_lower for w in ["cost", "charge", "price", "rate", "rent", "how much", "calculate"])
        if hour_match and is_calc_query:
            hrs = int(hour_match.group(1))
            resolved_vehicle = None
            # Check model keywords in query
            for candidate in [
                "Ather 450X", "Ola S1 Pro", "TVS iQube", "Bajaj Chetak", "Revolt RV400",
                "Oben Rorr", "Ultraviolette F77", "Activa", "Jupiter", "Classic 350", "Pulsar"
            ]:
                if candidate.lower() in q_lower:
                    resolved_vehicle = db.lookup_vehicle_rates(candidate)
                    break

            # If vehicle ID is referenced
            veh_code = re.search(r"\b(VEH\d{3}|VEH\d{1,4})\b", user_query_clean, re.IGNORECASE)
            if not resolved_vehicle and veh_code:
                v_res = db.agent_get_fleet_status()
                for v in v_res:
                    if v["vehicle_id"].upper() == veh_code.group(1).upper():
                        resolved_vehicle = v
                        break

            # Default to first fleet model in database if none specified
            if not resolved_vehicle:
                resolved_vehicle = db.lookup_vehicle_rates("Ather 450X")

            if resolved_vehicle:
                h_rate = float(resolved_vehicle["hourly_rate"])
                d_rate = float(resolved_vehicle["daily_rate"])
                v_model = resolved_vehicle.get("model", "Vehicle")
                calc_res = calculate_rental_charge(hrs, h_rate, d_rate)
                calculations[f"rental_calc_{v_model}"] = calc_res
                evidence_blocks.append(
                    f"[Database Evidence - Actual Vehicle Rate Calculation for {v_model} ({hrs} hours)]\n"
                    f"Model: {v_model} | DB Hourly Rate: ₹{h_rate} | DB Daily Rate: ₹{d_rate}\n"
                    f"Calculation Breakdown: {calc_res['formula']}\n"
                    f"Base Rental Amount: ₹{calc_res['base_rental_charge']} | 18% GST: ₹{calc_res['gst_amount']} | Total: ₹{calc_res['total_amount']}"
                )

        # -------------------------------------------------------------
        # 4. POLICY RETRIEVAL & CITATIONS
        # -------------------------------------------------------------
        policy_matches = self.policy_store.search_policy(user_query_clean, top_k=4)
        citations = policy_matches
        if policy_matches:
            evidence_blocks.append("\n[Policy Evidence - Document Rules]")
            evidence_blocks.append(self.policy_store.format_citations_for_evidence(policy_matches))

        # -------------------------------------------------------------
        # 5. PROMPT INJECTION DEFENSE & EVIDENCE ENCAPSULATION
        # -------------------------------------------------------------
        full_evidence_text = "\n\n".join(evidence_blocks)
        sandboxed_evidence = (
            "<untrusted_evidence>\n"
            f"{full_evidence_text}\n"
            "</untrusted_evidence>"
        )

        # Build prompt
        system_prompt = (
            SYSTEM_PROMPT_CUSTOMER.format(customer_id=session_customer_id or "UNKNOWN")
            if role == "customer"
            else SYSTEM_PROMPT_AGENT
        )

        messages = [
            {"role": "system", "content": system_prompt}
        ]

        # Add recent conversation history for conversational context (up to 4 turns)
        for h in conversation_history[-4:]:
            messages.append({"role": h["role"], "content": h["content"]})

        # Multilanguage instruction
        lang_instruction = ""
        if language and language.lower() != "english":
            lang_instruction = f"\nUser Preferred Language: {language}. Please reply in {language} while keeping technical IDs (e.g. CUST0001, B-0001, VEH001) and currency formats exact."

        # Add current user prompt with untrusted evidence payload
        current_user_content = (
            f"Here is the verified operational data and policy evidence:\n"
            f"{sandboxed_evidence}\n\n"
            f"User Question: {user_query_clean}\n\n"
            f"Instructions:\n"
            f"1. Answer the question accurately using only the verified evidence above.\n"
            f"2. Clearly distinguish verified database facts, policy guidance, and calculations.\n"
            f"3. When referencing policy rules, cite Document Title, Doc ID, Version, and Page.\n"
            f"4. Present financial figures and breakdowns clearly with ₹ (INR), showing base charge, 18% GST, and total.\n"
            f"5. If a requested Customer ID, Booking ID, or Vehicle ID does not exist in the evidence, state clearly that no such record was found.\n"
            f"6. If the user asks an irrelevant question outside RideWise mobility/rentals, politely explain that you assist with RideWise rentals and decline to fabricate unrelated facts."
            f"{lang_instruction}"
        )
        messages.append({"role": "user", "content": current_user_content})

        # Determine query intent for non-conversational queries
        intent = "policy" if any(k in q_lower for k in ["policy", "cancel", "refund", "late", "penalty", "battery", "deposit", "rule", "terms", "grace"]) else "database_query"

        # -------------------------------------------------------------
        # 5. LLM SYNTHESIS & GRACEFUL FALLBACK
        # -------------------------------------------------------------
        try:
            llm_response = self.llm_client.generate_response(messages)
            return {
                "answer": llm_response,
                "citations": citations,
                "evidence": full_evidence_text,
                "calculations": calculations,
                "is_fallback": False,
                "intent": intent,
                "retrieval_performed": True
            }
        except Exception as e:
            # Fallback response generated deterministically if LLM times out or rate limits
            fallback_text = (
                f"*(Note: LLM synthesis temporarily unavailable due to: {type(e).__name__}. "
                f"Displaying verified deterministic evidence directly:)*\n\n"
                f"{full_evidence_text}"
            )
            return {
                "answer": fallback_text,
                "citations": citations,
                "evidence": full_evidence_text,
                "calculations": calculations,
                "is_fallback": True,
                "intent": intent,
                "retrieval_performed": True,
                "error": str(e)
            }
