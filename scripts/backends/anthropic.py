"""Anthropic backend — the Claude API, for comparison runs.

    generate(prompt, model, max_tokens=..., timeout=...) -> str

The model id is passed through verbatim; this module never picks one. A card
is a model-identified artifact, so the caller must say which model produced it
and `extract_cards.py` records that id in the card's front matter.

Credentials come from the environment (`ANTHROPIC_API_KEY`, or an `ant auth
login` profile — the SDK's own resolution order). They are never read here and
never logged.

The SDK import is lazy so the rest of the skill runs without it installed.
"""

from . import BackendError, TransientError

# A card is short; the prompt is long. Streaming keeps a long request from
# hitting the SDK's HTTP timeout.
DEFAULT_MAX_TOKENS = 4096


def generate(prompt: str, model: str, max_tokens: int = DEFAULT_MAX_TOKENS,
             timeout: float = 600.0, **opts) -> str:
    try:
        import anthropic
    except ImportError:
        raise BackendError(
            "the anthropic SDK is not installed; pip install anthropic") from None

    client = anthropic.Anthropic(timeout=timeout)
    try:
        with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            message = stream.get_final_message()
    except anthropic.RateLimitError as exc:
        raise TransientError(f"rate limited: {_brief(exc)}") from None
    except anthropic.APITimeoutError:
        raise TransientError("request timed out") from None
    except anthropic.APIConnectionError:
        raise TransientError("connection error") from None
    except anthropic.APIStatusError as exc:
        if exc.status_code >= 500:
            raise TransientError(f"server error {exc.status_code}") from None
        raise BackendError(f"api error {exc.status_code}: {_brief(exc)}") from None

    if message.stop_reason == "refusal":
        raise BackendError("the model declined this request")
    if message.stop_reason == "max_tokens":
        raise BackendError(
            f"card truncated at max_tokens={max_tokens}; raise --max-output-tokens")
    return "".join(b.text for b in message.content if b.type == "text")


def _brief(exc) -> str:
    """One short line. Never the prompt, never a credential."""
    return str(getattr(exc, "message", exc)).splitlines()[0][:200]
