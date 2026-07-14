"""Turns pasted listing text or a listing screenshot into a structured deal.

Two independent extraction paths feed one merge step:

1. Regex — fast, deterministic, and reliable for a handful of fields that
   follow predictable patterns in listing text (price, beds/baths, sqft,
   zip). Used as an override on top of the LLM output for exactly those
   fields, per the build spec.
2. Anthropic API (text or vision) — structured JSON extraction via forced
   tool use, for everything regex can't reliably catch (address, rent
   estimate, tax/insurance/HOA figures, property type, unit count,
   condition notes).

Neither path is trusted silently: callers (app.py) always return the merged
result to the user for correction before anything is saved to the database.

This module never fetches a listing site itself — it only ever processes
text or an image the user already copied/captured themselves.
"""

import base64
import os
import re

import anthropic

MODEL = os.environ.get("DEAL_SCREENER_MODEL", "claude-sonnet-4-6")

EXTRACTION_TOOL = {
    "name": "extract_listing_fields",
    "description": (
        "Extract structured real-estate listing fields from the given "
        "text or image. Use null for any field not present or not "
        "confidently inferable — never guess a number that isn't stated "
        "or clearly implied."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "address": {"type": ["string", "null"]},
            "zip": {"type": ["string", "null"]},
            "price": {"type": ["number", "null"]},
            "beds": {"type": ["number", "null"]},
            "baths": {"type": ["number", "null"]},
            "sqft": {"type": ["number", "null"]},
            "unit_count": {"type": ["integer", "null"]},
            "property_type": {
                "type": ["string", "null"],
                "enum": ["SFH", "duplex", "tri", "quad", None],
            },
            "rent_monthly_total": {
                "type": ["number", "null"],
                "description": (
                    "Current or estimated total monthly rent for the "
                    "property, if the listing states or implies one "
                    "(e.g. 'rented for $X', 'rental estimate', "
                    "'in-place rent')."
                ),
            },
            "tax_annual": {"type": ["number", "null"]},
            "insurance_annual": {"type": ["number", "null"]},
            "hoa_monthly": {"type": ["number", "null"]},
            "condition_notes": {
                "type": ["string", "null"],
                "description": (
                    "Short summary of condition/rehab-relevant remarks "
                    "from the listing description or agent remarks."
                ),
            },
        },
        "required": [],
    },
}

_FIELDS = tuple(EXTRACTION_TOOL["input_schema"]["properties"].keys())

_PRICE_RE = re.compile(r"\$\s?([\d,]{4,})(?:\.\d{2})?")
_SQFT_RE = re.compile(
    r"([\d,]{3,})\s*(?:sq\.?\s?ft\.?|sqft|square\s+feet)", re.IGNORECASE
)
_BEDS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:bed(?:room)?s?|bd|br)\b", re.IGNORECASE)
_BATHS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:bath(?:room)?s?|ba)\b", re.IGNORECASE)
_ZIP_NEAR_GA_RE = re.compile(r"\bGA\b\D{0,5}(\d{5})\b")
_ZIP_BARE_RE = re.compile(r"(?<!\d)(\d{5})(?!\d)")


def regex_parse(text: str) -> dict:
    """Extracts the handful of fields regex is reliable for.

    Only returns keys it found a confident match for — everything else is
    left to the LLM pass. The first dollar-amount match is treated as the
    list price on the (documented) assumption that listing text dumps show
    price first/most prominently; this can misfire on pages that lead with
    an HOA fee or tax figure, which is exactly why the parsed result is
    always shown for correction before saving.
    """
    result = {}

    price_match = _PRICE_RE.search(text)
    if price_match:
        result["price"] = float(price_match.group(1).replace(",", ""))

    sqft_match = _SQFT_RE.search(text)
    if sqft_match:
        result["sqft"] = float(sqft_match.group(1).replace(",", ""))

    beds_match = _BEDS_RE.search(text)
    if beds_match:
        result["beds"] = float(beds_match.group(1))

    baths_match = _BATHS_RE.search(text)
    if baths_match:
        result["baths"] = float(baths_match.group(1))

    zip_match = _ZIP_NEAR_GA_RE.search(text) or _ZIP_BARE_RE.search(text)
    if zip_match:
        result["zip"] = zip_match.group(1)

    return result


def _extract_tool_input(message) -> dict:
    for block in message.content:
        if block.type == "tool_use" and block.name == "extract_listing_fields":
            return block.input
    return {}


def llm_parse_text(text: str) -> dict:
    """Structured-field extraction from pasted listing text via the
    Anthropic API. Raises if ANTHROPIC_API_KEY isn't configured — callers
    should catch and fall back to regex-only results."""
    client = anthropic.Anthropic()
    message = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        tools=[EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "extract_listing_fields"},
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract listing fields from this pasted real estate "
                    "listing text:\n\n" + text
                ),
            }
        ],
    )
    return _extract_tool_input(message)


def llm_parse_image(image_bytes: bytes, media_type: str) -> dict:
    """Structured-field extraction from a listing screenshot via the
    Anthropic API's vision input."""
    client = anthropic.Anthropic()
    b64_image = base64.standard_b64encode(image_bytes).decode("utf-8")
    message = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        tools=[EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "extract_listing_fields"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64_image,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Extract listing fields from this screenshot "
                            "of a real estate listing."
                        ),
                    },
                ],
            }
        ],
    )
    return _extract_tool_input(message)


def merge_parsed_fields(llm_fields: dict, regex_fields: dict) -> dict:
    """Regex wins where it found something; LLM fills everything else."""
    merged = {k: v for k, v in (llm_fields or {}).items() if v is not None}
    merged.update(regex_fields)
    return {k: merged.get(k) for k in _FIELDS}


def parse_text(text: str) -> dict:
    regex_fields = regex_parse(text)
    try:
        llm_fields = llm_parse_text(text)
    except Exception:
        llm_fields = {}
    return merge_parsed_fields(llm_fields, regex_fields)


def parse_image(image_bytes: bytes, media_type: str, ocr_text: str = "") -> dict:
    regex_fields = regex_parse(ocr_text) if ocr_text else {}
    llm_fields = llm_parse_image(image_bytes, media_type)
    return merge_parsed_fields(llm_fields, regex_fields)
