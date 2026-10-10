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
        conversation_history: Optional[List[Dict[str, str]]] = None
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
                f"[Customer Profile]\n"
                f"Customer ID: {profile['customer_id']}\n"
                f"Name: {profile['full_name']}\n"
                f"Phone: {profile['phone']}\n"
                f"Email: {profile['email']}\n"
                f"City: {profile['city']}\n"
                f"KYC Status: {profile['kyc_status']}\n"
                f"Customer Tier: {profile['customer_tier']}\n"
            )

            # Check if specific booking ID was referenced
            booking_match = re.search(r"\b(B-\d{4})\b", user_query_clean, re.IGNORECASE)
            specific_b_id = booking_match.group(1).upper() if booking_match else None

            # Fetch customer bookings
            bookings = db.get_customer_bookings(session_customer_id, booking_id=specific_b_id)
            if bookings:
                evidence_blocks.append(f"[Customer Bookings ({len(bookings)} found)]")
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
                    # 1. Cancellation calculation if cancelled
                    if b["booking_status"] in ("CNL_U", "CNL_S", "NSH") or b["cancelled_at"]:
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
                            cancelled_at_str=b["cancelled_at"],
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

                    # 3. Damage assessment
                    if damages:
                        for dmg in damages:
                            dmg_calc = assess_damage_charge(dmg["claim_status"], dmg["assessed_cost"])
                            calculations[f"{dmg['report_id']}_damage"] = dmg_calc
                            evidence_blocks.append(f"  [Deterministic Damage Liability for {dmg['report_id']}]: {dmg_calc['reason']}")

        else:
            # SUPPORT AGENT ROLE
            evidence_blocks.append("[Support Agent Operational Session Active]")

            # Check if query references a specific customer or booking
            cust_match = re.search(r"\b(CUST\d{4})\b", user_query_clean, re.IGNORECASE)
            booking_match = re.search(r"\b(B-\d{4})\b", user_query_clean, re.IGNORECASE)

            if cust_match:
                cid = cust_match.group(1).upper()
                c_profile = db.agent_get_customer_profile(cid)
                if c_profile:
                    evidence_blocks.append(
                        f"[Customer Profile for {cid}]\n"
                        f"Name: {c_profile['full_name']} | Phone: {c_profile['phone']} | KYC: {c_profile['kyc_status']} | Tier: {c_profile['customer_tier']}"
                    )
                c_bookings = db.agent_search_bookings(customer_id=cid, limit=5)
                evidence_blocks.append(f"[Recent Bookings for {cid}: {len(c_bookings)} records]")
                for b in c_bookings:
                    evidence_blocks.append(f"- Booking {b['booking_id']} ({b['model']}, Hub: {b['hub_name']}, Status: {b['booking_status']})")

            elif booking_match:
                bid = booking_match.group(1).upper()
                b_detail = db.agent_get_booking_details(bid)
                if b_detail:
                    evidence_blocks.append(
                        f"[Booking Details for {bid}]\n"
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
                # Operational summary / Fleet lookup
                summary = db.agent_get_operational_summary()
                evidence_blocks.append(
                    f"[Operational Fleet & Hub Summary]\n"
                    f"Fleet Status Breakdown: {summary['fleet_summary']}\n"
                    f"Hub Distribution: {summary['hub_distribution']}\n"
                    f"Booking Status Breakdown: {summary['booking_summary']}\n"
                    f"KYC Breakdown: {summary['kyc_summary']}\n"
                    f"Damage Claims Overview: {summary['damage_summary']}"
                )

        # -------------------------------------------------------------
        # 3. POLICY RETRIEVAL & CITATIONS
        # -------------------------------------------------------------
        policy_matches = self.policy_store.search_policy(user_query_clean, top_k=4)
        citations = policy_matches
        if policy_matches:
            evidence_blocks.append("\n[Relevant Policy Rules & Clauses]")
            evidence_blocks.append(self.policy_store.format_citations_for_evidence(policy_matches))

        # Check if query asks for standalone rate calculation (e.g. "How much for 10 hours on Ather 450X?")
        hour_match = re.search(r"(\d+)\s*(?:hours|hrs|hr)", user_query_clean, re.IGNORECASE)
        if hour_match and any(w in user_query_clean.lower() for w in ["cost", "charge", "price", "rate", "rent", "how much"]):
            hrs = int(hour_match.group(1))
            # Ather 450X default or matched rates
            calc_sample = calculate_rental_charge(hrs, 80.0, 700.0)
            calculations["general_rental_pricing_sample"] = calc_sample
            evidence_blocks.append(
                f"[Rental Pricing Example for {hrs} hours @ ₹80/hr, ₹700/day]: {calc_sample['formula']}"
            )

        # -------------------------------------------------------------
        # 4. PROMPT INJECTION DEFENSE & EVIDENCE ENCAPSULATION
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

        # Add current user prompt with untrusted evidence payload
        current_user_content = (
            f"Here is the verified operational data and policy evidence:\n"
            f"{sandboxed_evidence}\n\n"
            f"User Question: {user_query_clean}\n\n"
            f"Answer the user question accurately using only the evidence above. "
            f"Always cite policy documents (Doc ID, version, page) when referencing rules, "
            f"and present financial calculations clearly with ₹ (INR)."
        )
        messages.append({"role": "user", "content": current_user_content})

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
                "is_fallback": False
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
                "error": str(e)
            }
