from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from bot import compose, respond, is_optout


start_time = time.time()
lock = threading.RLock()

store = {
    "category": {},
    "merchant": {},
    "customer": {},
    "trigger": {},
}

versions = {
    "category": {},
    "merchant": {},
    "customer": {},
    "trigger": {},
}

conversations = {}
sent = set()
blocked_merchants = set()
blocked_customers = set()


metadata = {
    "team_name": "Vera Builder",
    "team_members": ["Candidate"],
    "model": "deterministic-rule-engine",
    "approach": "context-grounded rules with category-aware composition and reply handling",
    "contact_email": "",
    "version": "1.1.0",
    "submitted_at": "2026-09-26T00:00:00Z",
}


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def make_ack(scope, context_id, version):
    return f"ack_{scope}_{context_id}_v{version}"


def get_contexts(trigger):
    outer = trigger.get("payload", {}) or {}
    if not isinstance(outer, dict):
        outer = {}
    inner = outer.get("payload", {}) or {}
    if not isinstance(inner, dict):
        inner = {}

    merchant_id = (
        outer.get("merchant_id")
        or inner.get("merchant_id")
        or trigger.get("merchant_id")
    )

    customer_id = (
        outer.get("customer_id")
        or inner.get("customer_id")
        or trigger.get("customer_id")
    )

    category_slug = (
        outer.get("category")
        or outer.get("category_slug")
        or inner.get("category")
        or inner.get("category_slug")
        or trigger.get("category")
    )

    merchant = store["merchant"].get(merchant_id)

    if not category_slug and merchant:
        category_slug = merchant.get("category_slug")

    category = store["category"].get(category_slug)

    customer = None

    if customer_id:
        customer = store["customer"].get(customer_id)

    return category, merchant, customer


class VeraHandler(BaseHTTPRequestHandler):

    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        return

    def send_json(self, status, data):
        raw = json.dumps(
            data,
            ensure_ascii=False
        ).encode("utf-8")

        self.send_response(status)

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )

        self.send_header(
            "Content-Length",
            str(len(raw))
        )

        self.end_headers()
        self.wfile.write(raw)

    def read_json(self):
        length = int(
            self.headers.get(
                "Content-Length",
                "0"
            )
        )

        raw = self.rfile.read(length)

        if not raw:
            return {}

        return json.loads(raw)

    def do_GET(self):

        path = urlparse(self.path).path

        if path == "/v1/healthz":

            with lock:
                counts = {
                    key: len(value)
                    for key, value in store.items()
                }

            return self.send_json(
                200,
                {
                    "status": "ok",
                    "uptime_seconds": round(
                        time.time() - start_time,
                        2
                    ),
                    "contexts_loaded": counts,
                },
            )

        if path == "/v1/metadata":
            return self.send_json(
                200,
                metadata
            )

        return self.send_json(
            404,
            {
                "error": "not_found"
            }
        )

    def do_POST(self):

        path = urlparse(self.path).path

        try:
            data = self.read_json()

        except Exception as exc:

            return self.send_json(
                400,
                {
                    "accepted": False,
                    "reason": "invalid_json",
                    "details": str(exc),
                },
            )

        if not isinstance(data, dict):
            return self.send_json(
                400,
                {
                    "accepted": False,
                    "reason": "malformed_request",
                    "details": "JSON request body must be an object.",
                },
            )

        if path == "/v1/context":
            return self.handle_context(data)

        if path == "/v1/tick":
            return self.handle_tick(data)

        if path == "/v1/reply":
            return self.handle_reply(data)

        return self.send_json(
            404,
            {
                "error": "not_found"
            }
        )

    def handle_context(self, data):

        scope = data.get("scope")
        context_id = data.get("context_id")
        version = data.get("version")
        payload = data.get("payload")

        if (
            scope in ("merchant", "customer")
            and "kind" in data
            and "id" in data
            and context_id is None
        ):
            scope = "trigger"
            context_id = data.get("id")
            version = data.get("version", 1)
            payload = data

        if scope is None:

            if "slug" in data:

                scope = "category"
                context_id = data.get("slug")

            elif "merchant_id" in data:

                scope = "merchant"
                context_id = data.get("merchant_id")

            elif "customer_id" in data:

                scope = "customer"
                context_id = data.get("customer_id")

            elif "kind" in data and "id" in data:

                scope = "trigger"
                context_id = data.get("id")

            version = data.get(
                "version",
                1
            )

            payload = data

        if scope not in store:

            return self.send_json(
                400,
                {
                    "accepted": False,
                    "reason": "invalid_scope",
                    "details": (
                        "scope must be category, merchant, "
                        "customer or trigger"
                    ),
                },
            )

        if (
            not context_id
            or not isinstance(version, int)
            or not isinstance(payload, dict)
        ):

            return self.send_json(
                400,
                {
                    "accepted": False,
                    "reason": "malformed_context",
                },
            )

        with lock:

            old_version = versions[
                scope
            ].get(context_id)

            if old_version is not None:
                if version == old_version:
                    return self.send_json(
                        200,
                        {
                            "accepted": True,
                            "ack_id": make_ack(
                                scope,
                                context_id,
                                version
                            ),
                            "stored_at": now_iso(),
                        },
                    )

                if version < old_version:
                    return self.send_json(
                        409,
                        {
                            "accepted": False,
                            "reason": "stale_version",
                            "current_version": old_version,
                        },
                    )

            store[
                scope
            ][context_id] = payload

            versions[
                scope
            ][context_id] = version

        return self.send_json(
            200,
            {
                "accepted": True,
                "ack_id": make_ack(
                    scope,
                    context_id,
                    version
                ),
                "stored_at": now_iso(),
            },
        )

    def handle_tick(self, data):

        available = data.get("available_triggers")
        if not isinstance(available, list):
            return self.send_json(
                400,
                {
                    "accepted": False,
                    "reason": "malformed_tick",
                    "details": "available_triggers must be a list",
                },
            )

        actions = []

        with lock:

            triggers = [
                store["trigger"].get(trigger_id)
                for trigger_id in available
            ]

        triggers = [
            trigger
            for trigger in triggers
            if isinstance(trigger, dict)
        ]

        def urgency(trigger):
            try:
                return int(trigger.get("urgency", 0))
            except (TypeError, ValueError):
                return 0

        triggers.sort(
            key=lambda trigger: (
                -urgency(trigger),
                0 if trigger.get(
                    "scope"
                ) == "customer" else 1,
                trigger.get("id") or "",
            )
        )

        for trigger in triggers:

            if len(actions) >= 20:
                break

            trigger_id = trigger.get("id")

            expires_at = trigger.get("expires_at")
            if expires_at:
                try:
                    from datetime import datetime, timezone
                    expiry = expires_at.replace("Z", "+00:00")
                    if datetime.fromisoformat(expiry) <= datetime.now(timezone.utc):
                        continue
                except (TypeError, ValueError):
                    continue

            category, merchant, customer = (
                get_contexts(trigger)
            )

            if trigger.get("scope") == "customer" and not customer:
                continue

            if not category or not merchant:
                continue

            merchant_id = merchant.get(
                "merchant_id"
            )

            trigger_payload = trigger.get("payload", {}) or {}
            if not isinstance(trigger_payload, dict):
                trigger_payload = {}
            nested_payload = trigger_payload.get("payload", {}) or {}
            if not isinstance(nested_payload, dict):
                nested_payload = {}
            customer_id = (
                trigger_payload.get("customer_id")
                or nested_payload.get("customer_id")
                or trigger.get("customer_id")
                or (customer or {}).get("customer_id")
            )

            if not merchant_id:
                continue

            if customer and customer.get("merchant_id") not in (None, merchant_id):
                continue

            with lock:

                if merchant_id in blocked_merchants:
                    continue

                if customer_id in blocked_customers:
                    continue

            suppression_key = (
                trigger.get(
                    "suppression_key"
                )
                or trigger_id
            )

            sent_key = (
                merchant_id,
                customer_id,
                suppression_key
            )

            with lock:

                if sent_key in sent:
                    continue

            output = compose(
                category,
                merchant,
                trigger,
                customer
            )

            if not output.get("body"):
                continue

            conversation_id = (
                f"conv_{merchant_id}_"
                f"{customer_id or 'merchant'}_"
                f"{trigger_id}"
            )

            conversation = {
                "merchant_id": merchant_id,
                "customer_id": customer_id,
                "trigger_id": trigger_id,
                "context": (
                    category,
                    merchant,
                    customer
                ),
                "history": [
                    {
                        "role": "vera",
                        "body": output["body"],
                    }
                ],
                "closed": False,
                "auto_replies": 0,
            }

            with lock:

                if sent_key in sent:
                    continue

                conversations[
                    conversation_id
                ] = conversation

                sent.add(sent_key)

            actions.append(
                {
                    "conversation_id": conversation_id,
                    "merchant_id": merchant_id,
                    "customer_id": customer_id,
                    "send_as": output["send_as"],
                    "trigger_id": trigger_id,
                    "template_name": (
                        f"vera_"
                        f"{trigger.get('kind', 'message')}"
                        f"_v1"
                    ),
                    "template_params": [output["body"]],
                    "body": output["body"],
                    "cta": output["cta"],
                    "suppression_key": (
                        output["suppression_key"]
                    ),
                    "rationale": output["rationale"],
                }
            )

        return self.send_json(
            200,
            {
                "actions": actions
            }
        )

    def handle_reply(self, data):

        conversation_id = data.get(
            "conversation_id"
        )

        message = data.get(
            "message",
            ""
        )

        with lock:

            state = conversations.get(
                conversation_id
            )

        if not state:

            return self.send_json(
                404,
                {
                    "action": "end",
                    "rationale": (
                        "Unknown conversation_id; "
                        "no state is available."
                    ),
                },
            )

        merchant_id = state.get(
            "merchant_id"
        )

        if is_optout(message):

            with lock:
                customer_id = state.get("customer_id")
                if customer_id:
                    blocked_customers.add(customer_id)
                else:
                    blocked_merchants.add(merchant_id)

        with lock:

            output = respond(
                state,
                message
            )

            if output.get("action") == "send":

                state["history"].append(
                    {
                        "role": "vera",
                        "body": output.get(
                            "body",
                            ""
                        ),
                    }
                )

            if output.get("action") == "end":

                state["closed"] = True

        return self.send_json(
            200,
            output
        )


def main():

    port = int(
        os.getenv(
            "PORT",
            "8080"
        )
    )

    server = ThreadingHTTPServer(
        ("0.0.0.0", port),
        VeraHandler
    )

    print(
        f"Vera bot running on http://localhost:{port}"
    )

    try:
        server.serve_forever()

    except KeyboardInterrupt:

        print(
            "\nVera bot stopped."
        )

    finally:

        server.server_close()


if __name__ == "__main__":
    main()
