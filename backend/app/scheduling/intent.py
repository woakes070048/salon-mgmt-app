"""Inbound email intent extractor.

Converts raw email text into a structured ParsedIntent using claude-haiku-4-5-20251001
with tool-use. The model resolves service and provider IDs directly from the catalogue
passed in the system prompt; IDs are left null when nothing matches.

Confidence scoring (computed here, not by the model):
  1.0  date + at least one service_id resolved
  0.7  date only
  0.5  service_id only (no date)
  0.3  neither resolved
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from uuid import UUID

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

# ── Output dataclasses ────────────────────────────────────────────────────────


@dataclass
class ParsedService:
    service_id: UUID | None
    service_name: str
    preferred_provider_id: UUID | None
    preferred_provider_name: str | None


@dataclass
class ParsedIntent:
    desired_date: date | None
    desired_time_note: str | None
    services: list[ParsedService]
    special_note: str | None
    confidence: float
    raw_text: str


# ── Tool schema ───────────────────────────────────────────────────────────────

_PARSE_TOOL: dict = {
    "name": "parse_booking_request",
    "description": (
        "Parse a salon booking request email and return structured intent. "
        "Resolve service and provider names to their catalogue IDs whenever a match is found. "
        "Never fabricate IDs — if unsure, leave the field null."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "desired_date": {
                "type": "string",
                "description": "Requested appointment date in YYYY-MM-DD format, or null if not specified.",
                "nullable": True,
            },
            "desired_time_note": {
                "type": "string",
                "description": (
                    "Free-text time preference exactly as described by the client "
                    "(e.g. 'Friday afternoon', 'after 2pm', 'morning'). "
                    "Null if no preference stated."
                ),
                "nullable": True,
            },
            "services": {
                "type": "array",
                "description": "List of services the client wants, in the order mentioned.",
                "items": {
                    "type": "object",
                    "properties": {
                        "service_id": {
                            "type": "string",
                            "description": (
                                "UUID of the matched service from the catalogue, or null "
                                "if no match found."
                            ),
                            "nullable": True,
                        },
                        "service_name": {
                            "type": "string",
                            "description": "Raw service name exactly as the client wrote it.",
                        },
                        "preferred_provider_id": {
                            "type": "string",
                            "description": (
                                "UUID of the matched provider from the list, or null "
                                "if no provider preference or no match."
                            ),
                            "nullable": True,
                        },
                        "preferred_provider_name": {
                            "type": "string",
                            "description": (
                                "Raw provider name exactly as the client wrote it, or null "
                                "if no provider preference stated."
                            ),
                            "nullable": True,
                        },
                    },
                    "required": ["service_name"],
                },
            },
            "special_note": {
                "type": "string",
                "description": (
                    "Any special instructions, constraints, or notes from the client "
                    "not captured by the other fields. Null if none."
                ),
                "nullable": True,
            },
        },
        "required": ["services"],
    },
}


# ── System prompt builder ─────────────────────────────────────────────────────


def _build_system_prompt(
    service_catalogue: list[dict],
    provider_list: list[dict],
) -> str:
    svc_lines = "\n".join(
        f"  - id={s['id']}  name={s['name']!r}"
        + (f"  aliases={s.get('aliases', [])}" if s.get("aliases") else "")
        for s in service_catalogue
    )
    prov_lines = "\n".join(
        f"  - id={p['id']}  display_name={p['display_name']!r}"
        for p in provider_list
    )

    return f"""\
You are a booking assistant at a hair salon. A client has sent an email requesting an appointment.
Your job is to parse their request and call the parse_booking_request tool with the structured data.

## Service catalogue
{svc_lines if svc_lines else '  (no services configured)'}

## Providers
{prov_lines if prov_lines else '  (no providers configured)'}

## Rules
- Match service names and aliases case-insensitively. Include common abbreviations \
(e.g. "colour" = "color", "blow-dry" = "blowout", "cut" = "haircut" = "trim").
- Match provider names case-insensitively on display_name (partial match acceptable).
- Use the EXACT UUIDs from the catalogue above — never invent IDs.
- If a service or provider cannot be confidently matched, set the ID to null.
- desired_date must be ISO format (YYYY-MM-DD) if parseable; null otherwise.
- Do not combine multiple services into one — list each separately.
- Always call parse_booking_request. Never refuse to parse.
"""


# ── Confidence scoring ────────────────────────────────────────────────────────


def _compute_confidence(intent: ParsedIntent) -> float:
    has_date = intent.desired_date is not None
    has_service = any(s.service_id is not None for s in intent.services)

    if has_date and has_service:
        return 1.0
    if has_date:
        return 0.7
    if has_service:
        return 0.5
    return 0.3


# ── Main extractor ────────────────────────────────────────────────────────────


async def extract_intent(
    from_address: str,
    subject: str,
    body: str,
    service_catalogue: list[dict],
    provider_list: list[dict],
) -> ParsedIntent:
    """Call Haiku with tool-use to extract booking intent from an email.

    Never raises — returns a low-confidence ParsedIntent on any failure so the
    caller can still persist a reviewable request record.
    """
    raw_text = body.strip()

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        system = _build_system_prompt(service_catalogue, provider_list)
        user_message = (
            f"From: {from_address}\n"
            f"Subject: {subject}\n\n"
            f"{raw_text}"
        )

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=system,
            tools=[_PARSE_TOOL],
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": user_message}],
        )

        # Extract tool-use block
        tool_block = next(
            (b for b in response.content if b.type == "tool_use" and b.name == "parse_booking_request"),
            None,
        )
        if tool_block is None:
            logger.warning("Intent extractor: model did not call parse_booking_request for email from %s", from_address)
            return _empty_intent(raw_text)

        data = tool_block.input
        return _build_intent(data, raw_text)

    except Exception:
        logger.warning("Intent extractor failed for email from %s", from_address, exc_info=True)
        return _empty_intent(raw_text)


def _build_intent(data: dict, raw_text: str) -> ParsedIntent:
    """Convert the tool call input dict into a ParsedIntent dataclass."""
    # Parse date
    desired_date: date | None = None
    raw_date = data.get("desired_date")
    if raw_date:
        try:
            desired_date = date.fromisoformat(raw_date)
        except (ValueError, TypeError):
            logger.warning("Intent extractor: could not parse date %r", raw_date)

    # Parse services
    services: list[ParsedService] = []
    for svc in data.get("services", []):
        service_id: UUID | None = None
        raw_sid = svc.get("service_id")
        if raw_sid:
            try:
                service_id = UUID(str(raw_sid))
            except (ValueError, AttributeError):
                pass

        provider_id: UUID | None = None
        raw_pid = svc.get("preferred_provider_id")
        if raw_pid:
            try:
                provider_id = UUID(str(raw_pid))
            except (ValueError, AttributeError):
                pass

        services.append(
            ParsedService(
                service_id=service_id,
                service_name=svc.get("service_name", ""),
                preferred_provider_id=provider_id,
                preferred_provider_name=svc.get("preferred_provider_name") or None,
            )
        )

    intent = ParsedIntent(
        desired_date=desired_date,
        desired_time_note=data.get("desired_time_note") or None,
        services=services,
        special_note=data.get("special_note") or None,
        confidence=0.0,  # placeholder — set below
        raw_text=raw_text,
    )
    intent.confidence = _compute_confidence(intent)
    return intent


def _empty_intent(raw_text: str) -> ParsedIntent:
    """Return a zero-confidence intent when parsing fails entirely."""
    return ParsedIntent(
        desired_date=None,
        desired_time_note=None,
        services=[],
        special_note=None,
        confidence=0.0,
        raw_text=raw_text,
    )
