from __future__ import annotations
import re
from typing import Optional

def name_of(m):
    i = m.get("identity", {}) or {}
    return i.get("owner_first_name") or i.get("name") or m.get("merchant_name") or m.get("name") or "there"

def business_of(m):
    return (m.get("identity", {}) or {}).get("name") or "your business"

def offers(m):
    return [x for x in m.get("offers", []) or [] if str(x.get("status", "")).lower() == "active"]

def offer_of(m, words=()):
    xs = offers(m)
    for x in xs:
        t = str(x.get("title", ""))
        if any(w.lower() in t.lower() for w in words):
            return t
    return str(xs[0].get("title")) if xs else None

def item_of(category, trigger):
    p = trigger.get("payload", {}) or {}
    if not isinstance(p, dict):
        p = {}
    wanted = p.get("top_item_id")
    items = category.get("digest", []) or []
    if wanted:
        for x in items:
            if x.get("id") == wanted:
                return x
    x = p.get("top_item")
    if isinstance(x, dict):
        return x
    return items[0] if items else {}

def clean(s):
    # Preserve any URLs; only collapse whitespace and strip surrounding spaces.
    return re.sub(r"\s+", " ", str(s or "")).strip()

def result(body, cta, send_as, key, why):
    return {
        "body": clean(body),
        "cta": cta,
        "send_as": send_as,
        "suppression_key": key,
        "rationale": clean(why)[:500]
    }

def context_text(x):
    if isinstance(x, dict):
        return " ".join(
            str(x.get(k, ""))
            for k in ("title", "summary", "description", "source", "text", "name")
            if x.get(k)
        )
    return str(x or "")

def compose(category: dict, merchant: dict, trigger: dict, customer: Optional[dict] = None) -> dict:
    if isinstance(category, str):
        category = {"slug": category, "display_name": category.replace("_", " ")}
    elif not isinstance(category, dict):
        category = {}
    merchant = merchant if isinstance(merchant, dict) else {}
    trigger = trigger if isinstance(trigger, dict) else {}
    kind = str(trigger.get("kind", "")).lower()
    customer_mode = customer is not None or trigger.get("scope") == "customer"
    send_as = "merchant_on_behalf" if customer_mode else "vera"
    key = trigger.get("suppression_key") or trigger.get("id") or kind
    if customer_mode:
        return customer_message(category, merchant, trigger, customer or {}, send_as, key)
    return merchant_message(category, merchant, trigger, send_as, key)

def merchant_message(category, merchant, trigger, send_as, key):
    kind = str(trigger.get("kind", "")).lower()
    p = trigger.get("payload", {}) or {}
    if not isinstance(p, dict):
        p = {}
    n = name_of(merchant)
    slug = merchant.get("category_slug") or category.get("slug") or "your category"
    display = category.get("display_name") or slug.replace("_", " ")
    perf = merchant.get("performance", {}) or {}
    peers = category.get("peer_stats", {}) or {}
    active = offer_of(merchant)
    item = item_of(category, trigger)
    title = item.get("title") or item.get("name") or "a new update"
    source = item.get("source") or "the supplied update"
    summary = str(item.get("summary") or item.get("description") or "").strip()

    if kind in {"research_digest", "category_research_digest_release"}:
        body = f"{n}, {source} has a useful update for {display}: {title}."
        if summary:
            body += f" {summary[:260]}"
        body += " Want me to turn the key point into a merchant-ready action?"
        return result(
            body,
            "open_ended",
            send_as,
            key,
            "Research content is taken from the supplied category digest and connected to the merchant category."
        )

    if kind in {"regulation_change", "compliance_alert"}:
        deadline = p.get("deadline_iso") or p.get("deadline") or item.get("date")
        body = f"{n}, quick compliance update: {title}."
        if deadline:
            body += f" Deadline: {deadline}."
        if summary:
            body += f" {summary[:240]}"
        body += " Want a short checklist for the team?"
        return result(
            body,
            "open_ended",
            send_as,
            key,
            "Uses the supplied compliance requirement and deadline without inventing additional obligations."
        )

    if kind in {"supply_alert", "atorvastatin_recall"}:
        affected = p.get("affected_customer_count", p.get("affected_count"))
        batches = p.get("batches") or p.get("batch_numbers")
        extra = []
        if batches:
            extra.append("batches " + ", ".join(map(str, batches)))
        if affected is not None:
            extra.append(f"{affected} matching customer records")
        body = f"{n}, this needs attention: {title}."
        if extra:
            body += " " + ", ".join(extra) + "."
        if summary:
            body += f" {summary[:220]}"
        body += " Want me to draft the customer notice?"
        return result(
            body,
            "binary_yes_no",
            send_as,
            key,
            "Supply or recall alert uses only supplied affected records and source details."
        )

    if kind in {"perf_dip", "seasonal_perf_dip"}:
        metric = p.get("metric") or "performance"
        delta = p.get("delta_pct")
        if delta is None:
            d7 = perf.get("delta_7d", {}) or {}
            delta = d7.get(f"{metric}_pct")

        subject = "are" if metric in {"calls", "directions", "views"} else "is"
        body = f"{n}, your {metric} {subject} showing a dip"

        if isinstance(delta, (int, float)):
            pct = abs(delta) * 100 if abs(delta) <= 1 else abs(delta)
            body += f" ({pct:.0f}% lower in the trigger window)"

        body += "."

        peer_key = {
            "views": "avg_views_30d",
            "calls": "avg_calls_30d",
            "directions": "avg_directions_30d",
            "ctr": "avg_ctr"
        }.get(metric)

        peer = peers.get(peer_key) if peer_key else None

        if peer is not None:
            body += f" Category benchmark in the supplied data is {peer}."

        body += " Want me to identify one practical recovery action?"

        return result(
            body,
            "open_ended",
            send_as,
            key,
            "Performance trigger uses the supplied metric, change and available benchmark context."
        )

    if kind == "perf_spike":
        metric = p.get("metric") or "performance"
        delta = p.get("delta_pct")
        body = f"{n}, your {metric} is moving up"
        if isinstance(delta, (int, float)):
            pct = abs(delta) * 100 if abs(delta) <= 1 else abs(delta)
            body += f" ({pct:.0f}% in the trigger window)"
        body += ". Want me to suggest how to capitalize on the momentum?"
        return result(
            body,
            "open_ended",
            send_as,
            key,
            "Performance spike is acknowledged from the supplied trigger data and converted to an actionable next step."
        )

    if kind == "renewal_due":
        due = p.get("due_date") or p.get("renewal_date") or p.get("days_remaining")
        body = f"{n}, your {display} renewal is coming up"
        if p.get("due_date") or p.get("renewal_date"):
            body += f" on {due}"
        elif p.get("days_remaining") is not None:
            body += f" in {p.get('days_remaining')} days"
        body += ". Want me to prepare the next-step checklist?"
        return result(
            body,
            "open_ended",
            send_as,
            key,
            "Renewal message uses the supplied due information and asks for one concrete action."
        )

    if kind in {"festival_upcoming", "category_seasonal", "wedding_package_followup"}:
        event = (
            p.get("event")
            or p.get("name")
            or p.get("occasion")
            or p.get("festival")
            or kind.replace("_", " ")
        )
        days = p.get("days_until")
        body = f"{n}, {event}"
        if days is not None:
            body += f" is in {days} days"
        body += f" and is relevant to {display}."
        if active:
            body += f" You already have {active} active."
        body += " Want one focused message for it?"
        return result(
            body,
            "open_ended",
            send_as,
            key,
            "Seasonal trigger is tied to the merchant category and existing offer data."
        )

    if kind == "ipl_match_today":
        event = p.get("match") or p.get("event") or "today's match"
        body = f"{n}, {event} is a timely local-growth opportunity."
        if active:
            body += f" You already have {active} active."
        body += " Want a concise promotion angle?"
        return result(
            body,
            "open_ended",
            send_as,
            key,
            "Uses the supplied event and current merchant offer context."
        )

    if kind == "review_theme_emerged":
        theme = p.get("theme") or p.get("review_theme") or "a review theme"
        count = p.get("review_count") or p.get("count") or p.get("occurrences_30d")
        body = f"{n}, a recurring review theme has emerged: {theme}."
        if count is not None:
            body += f" It appears in {count} reviews."
        body += " Want me to turn it into one concrete improvement or response?"
        return result(
            body,
            "open_ended",
            send_as,
            key,
            "Review message reflects the supplied theme and count without inventing sentiment."
        )

    if kind == "milestone_reached":
        milestone = (
            p.get("milestone")
            or p.get("name")
            or p.get("metric")
            or "a milestone"
        )
        value = p.get("value")
        if value is None:
            value = p.get("value_now")
        target = p.get("milestone_value")
        body = f"{n}, you reached {milestone}"
        if value is not None:
            body += f" ({value}"
            if target is not None:
                body += f"/{target}"
            body += ")"
        body += ". Want to turn the milestone into a customer-facing message?"
        return result(
            body,
            "open_ended",
            send_as,
            key,
            "Milestone message uses the supplied milestone and value."
        )

    if kind == "competitor_opened":
        competitor = p.get("competitor_name") or p.get("name") or "a nearby competitor"
        distance = p.get("distance")
        if distance is None:
            distance = p.get("distance_km")
        body = f"{n}, {competitor} has opened"
        if distance is not None:
            body += f" {distance} km away"
        body += ". I can help identify one response based on your current offer and positioning. Want that?"
        return result(
            body,
            "open_ended",
            send_as,
            key,
            "Competitor alert is framed around the supplied event and merchant-controlled response."
        )

    if kind == "gbp_unverified":
        body = f"{n}, your Google Business profile is marked unverified in the supplied context."
        body += " Want a short checklist to address it?"
        return result(
            body,
            "open_ended",
            send_as,
            key,
            "Uses the supplied profile status and proposes a concrete operational next step."
        )

    if kind == "cde_opportunity":
        opportunity = (
            p.get("opportunity")
            or p.get("reason")
            or p.get("digest_item_id")
            or "a customer-growth opportunity"
        )
        body = f"{n}, I found {opportunity} in the current context."
        body += " Want me to turn it into one action?"
        return result(
            body,
            "open_ended",
            send_as,
            key,
            "Opportunity message stays grounded in supplied merchant context."
        )

    if kind == "dormant_with_vera":
        body = f"{n}, you have not used Vera recently."
        body += " Want to pick up from the merchant-growth opportunities already in context?"
        return result(
            body,
            "open_ended",
            send_as,
            key,
            "Dormancy trigger reopens the existing merchant-growth workflow without inventing a new offer."
        )

    if kind == "curious_ask_due":
        question = p.get("question") or p.get("ask") or "your pending question"
        body = f"{n}, following up on {question}."
        body += " Want me to work through the next step?"
        return result(
            body,
            "open_ended",
            send_as,
            key,
            "Follow-up uses the supplied pending question and asks for a concrete next step."
        )

    if kind == "active_planning_intent":
        intent = (
            p.get("intent")
            or p.get("plan")
            or p.get("intent_topic")
            or "your current plan"
        )
        body = f"{n}, I can help with {intent} using the current merchant context."
        body += " Want me to turn it into a simple action plan?"
        return result(
            body,
            "open_ended",
            send_as,
            key,
            "Planning intent is connected directly to the supplied merchant context."
        )

    return result(
        f"{n}, I found a timely {kind.replace('_', ' ') or 'merchant'} opportunity for {display}. Want me to turn the available context into one concrete next step?",
        "open_ended",
        send_as,
        key,
        "Fallback uses the trigger type and available category context without inventing missing facts."
    )

def customer_message(category, merchant, trigger, customer, send_as, key):
    kind = str(trigger.get("kind", "")).lower()
    p = trigger.get("payload", {}) or {}
    if not isinstance(p, dict):
        p = {}
    n = name_of(merchant)
    b = business_of(merchant)
    identity = customer.get("identity", {}) or {}
    if not isinstance(identity, dict):
        identity = {}
    cn = (
        identity.get("first_name")
        or identity.get("name")
        or "there"
    )
    active = offer_of(merchant)
    prefs = customer.get("preferences", {}) or {}
    if not isinstance(prefs, dict):
        prefs = {}
    consent = customer.get("consent", {}) or {}
    if not isinstance(consent, dict):
        consent = {}
    scopes = consent.get("scope", []) or customer.get("consent_scopes", []) or customer.get("consents", [])
    if isinstance(scopes, str):
        scopes = [scopes]
    elif not isinstance(scopes, (list, tuple, set)):
        scopes = []
    scopes = {str(x).lower() for x in scopes}
    reminder_opt_in = bool(prefs.get("reminder_opt_in"))
    required_scopes = {
        "recall_due": {"recall_reminders"},
        "appointment_tomorrow": {"appointment_reminders"},
        "chronic_refill_due": {"refill_reminders"},
        "customer_lapsed_hard": {"promotional_offers", "marketing", "promotional", "promotions"},
        "customer_lapsed_soft": {"promotional_offers", "marketing", "promotional", "promotions"},
        "winback": {"promotional_offers", "marketing", "promotional", "promotions"},
        "winback_eligible": {"promotional_offers", "marketing", "promotional", "promotions"},
        "trial_followup": {"bridal_package_followup", "appointment_reminders"},
        "wedding_package_followup": {"bridal_package_followup", "appointment_reminders"},
    }
    required = required_scopes.get(kind)
    consented = bool(scopes.intersection(required or set()))
    if required and not (consented or reminder_opt_in):
        return result(
            "",
            "none",
            send_as,
            key,
            "Customer consent does not cover this outreach, so it is suppressed."
        )

    if kind in {"customer_lapsed_hard", "winback", "winback_eligible"}:
        days = p.get("days_since_last_visit")
        services = (
            (customer.get("relationship", {}) or {}).get("services_received", [])
            or []
        )
        last = services[-1] if services else None
        body = f"Hi {cn}, {b} here. "
        body += (
            f"It has been about {days} days since your last visit. "
            if days is not None
            else "We have not seen you in a while. "
        )
        if last:
            body += f"Your last recorded service was {str(last).replace('_', ' ')}. "
        if active:
            body += f"We currently have {active}. "
        body += "Would you like the details? Reply YES or STOP."
        return result(
            body,
            "yes_stop",
            send_as,
            key,
            "Win-back uses supplied customer history, current offer data and an explicit opt-out."
        )

    if kind in {"trial_followup", "wedding_package_followup"}:
        event = p.get("event") or p.get("occasion") or "your follow-up"
        body = f"Hi {cn}, {b} here. Quick follow-up on {event}. "
        if active:
            body += f"{active} is currently active. "
        body += "Want help with the next step? Reply YES or STOP."
        return result(
            body,
            "yes_stop",
            send_as,
            key,
            "Customer follow-up uses the supplied trigger and active offer with a clear opt-out."
        )

    if kind == "recall_due":
        due = p.get("due_date") or p.get("recall_date")
        service = p.get("service_due")
        body = f"Hi {cn}, {b} here. "
        if service:
            body += f"Your {str(service).replace('_', ' ')} follow-up is due"
        else:
            body += "Your follow-up is due"
        if due:
            body += f" on {due}"
        body += ". Would you like us to help arrange it? Reply YES or STOP."
        return result(
            body,
            "yes_stop",
            send_as,
            key,
            "Recall message uses the supplied due information and avoids adding medical claims."
        )

    if kind == "chronic_refill_due":
        medicine = p.get("medicine") or p.get("item") or ""
        if not medicine:
            molecules = p.get("molecule_list") or []
            if molecules:
                medicine = ", ".join(map(str, molecules))
        due = p.get("due_date")
        body = f"Hi {cn}, {b} here. Your refill reminder is due"
        if medicine:
            body += f" for {medicine}"
        if due:
            body += f" on {due}"
        body += ". We can confirm the existing order details with you. Reply CONFIRM or STOP."
        return result(
            body,
            "yes_stop",
            send_as,
            key,
            "Refill outreach stays within supplied order information and does not alter medication instructions."
        )

    return result(
        f"Hi {cn}, {b} here. We have a timely update for you. Reply YES for details or STOP to opt out.",
        "yes_stop",
        send_as,
        key,
        "Customer fallback remains consent-conscious and avoids unsupported claims."
    )

def is_auto_reply(message):
    t = str(message or "").lower()
    return any(
        x in t
        for x in (
            "thank you for contacting",
            "thanks for contacting",
            "our team will respond",
            "we will get back",
            "automated response",
            "auto reply",
            "business hours"
        )
    )

def is_optout(message):
    return bool(
        re.search(
            r"\b(stop|unsubscribe|do not message|don't message|dont message|not interested|remove me)\b",
            str(message or "").lower()
        )
    )

def is_commitment(message):
    return bool(
        re.search(
            r"\b(let'?s do it|lets do it|go ahead|yes|confirm|do it|start it|i want to join|sign me up|what'?s next)\b",
            str(message or "").lower()
        )
    )

def respond(state, merchant_message):
    state = state if isinstance(state, dict) else {}
    if state.get("closed"):
        return {
            "action": "end",
            "rationale": "Conversation is already closed."
        }
    msg = str(merchant_message or "")
    state.setdefault("history", []).append({
        "role": "merchant",
        "body": msg
    })

    if is_optout(msg):
        state["closed"] = True
        return {
            "action": "end",
            "rationale": "Explicit opt-out detected; conversation is closed and future sends should be suppressed."
        }

    if state.get("committed"):
        confirmation = msg.strip().upper()
        if confirmation == "CONFIRM":
            state["closed"] = True
            return {
                "action": "end",
                "rationale": "The user confirmed the proposed next step; the conversation is closed."
            }
        if confirmation in {"CANCEL", "NO"}:
            state["closed"] = True
            return {
                "action": "end",
                "rationale": "The user cancelled the proposed next step; no action was taken."
            }
        return {
            "action": "send",
            "body": "Please reply CONFIRM to proceed or CANCEL to stop.",
            "cta": "binary_confirm_cancel",
            "rationale": "The conversation is awaiting confirmation; requesting CONFIRM or CANCEL."
        }

    if is_auto_reply(msg):
        count = int(state.get("auto_replies", 0)) + 1
        state["auto_replies"] = count
        if count >= 3:
            state["closed"] = True
            return {
                "action": "end",
                "rationale": "Repeated automated replies detected; backing off instead of repeatedly messaging."
            }
        return {
            "action": "wait",
            "wait_seconds": 14400 if count == 1 else 86400,
            "rationale": "Automated reply detected; backing off before another attempt."
        }

    state["auto_replies"] = 0

    if is_commitment(msg):
        state["committed"] = True
        return {
            "action": "send",
            "body": "Great! I'll move to the next step using the context already provided. Reply CONFIRM to proceed or CANCEL to stop.",
            "cta": "binary_confirm_cancel",
            "rationale": "Clear commitment detected; moving toward execution."
        }

    t = msg.lower()

    if any(
        x in t
        for x in (
            "gst filing",
            "tax filing",
            "legal case",
            "lawyer"
        )
    ):
        return {
            "action": "send",
            "body": "That's outside the merchant-growth task I can handle here. Want me to continue with the current task?",
            "cta": "open_ended",
            "rationale": "Out-of-scope request is redirected to the active merchant-growth task."
        }

    if any(
        x in t
        for x in (
            "how much",
            "price",
            "cost",
            "how many",
            "when",
            "which"
        )
    ):
        return {
            "action": "send",
            "body": "I can work from the facts already supplied in the current context. Tell me which part you want to act on first and I'll keep the next step concrete.",
            "cta": "open_ended",
            "rationale": "Avoids inventing missing facts and asks the merchant to select the next action."
        }

    return {
        "action": "send",
        "body": "Got it. I'll keep this focused on one useful next step from the current context. Want me to draft it now?",
        "cta": "open_ended",
        "rationale": "Acknowledges the reply and moves toward one concrete action."
    }
