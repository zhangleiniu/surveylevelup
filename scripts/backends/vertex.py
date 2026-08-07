"""Google Vertex AI backend — the cheap bulk pass.

    generate(prompt, model, max_tokens=..., timeout=...) -> GenerationResult

Credentials and project come from the environment, the way gcloud sets them:

    GOOGLE_APPLICATION_CREDENTIALS   service-account key file
    GOOGLE_CLOUD_PROJECT             project id
    GOOGLE_CLOUD_LOCATION            region, e.g. us-central1 (default: global)

Nothing here reads the key file or prints any of it.

The SDK import is lazy so the rest of the skill runs without `google-genai`
installed; the optional dependency is in requirements-vertex.txt.
"""

import os

from . import BackendError, GenerationResult, TransientError

# Gemini reasoning tokens share the output budget with the visible answer. Card
# extraction should not starve the answer merely to save a few tokens; the API
# bills actual usage, not this ceiling. Gemini 3.6 Flash accepts 65,536.
DEFAULT_MAX_TOKENS = 65_536

# Vertex reports transient conditions as message text on a generic exception
# more often than as a typed error, so match on the text as well.
_TRANSIENT_MARKERS = ("429", "500", "502", "503", "504", "resource exhausted",
                      "deadline exceeded", "unavailable", "internal error",
                      "rate limit", "timeout", "overloaded")


def generate(prompt: str, model: str, max_tokens: int = DEFAULT_MAX_TOKENS,
             timeout: float = 600.0, **opts) -> GenerationResult:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise BackendError(
            "the Vertex SDK is not installed; pip install google-genai") from None

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise BackendError("GOOGLE_CLOUD_PROJECT is not set")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")

    client = None
    try:
        client = genai.Client(
            enterprise=True,
            project=project,
            location=location,
            http_options=types.HttpOptions(
                api_version="v1", timeout=int(timeout * 1000)),
        )
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=max_tokens,
            ),
        )
    except Exception as exc:
        message = _brief(exc)
        if any(m in message.lower() for m in _TRANSIENT_MARKERS):
            raise TransientError(message) from None
        raise BackendError(f"{type(exc).__name__}: {message}") from None
    finally:
        if client is not None:
            client.close()

    metadata = {
        "project": project,
        "location": location,
        "sdk_version": getattr(genai, "__version__", "unknown"),
    }
    for name in ("response_id", "model_version"):
        value = getattr(response, name, None)
        if value:
            metadata[name] = str(value)
    usage = getattr(response, "usage_metadata", None)
    if usage is not None:
        for output, source in (
            ("input_tokens", "prompt_token_count"),
            ("output_tokens", "candidates_token_count"),
            ("thought_tokens", "thoughts_token_count"),
            ("cached_input_tokens", "cached_content_token_count"),
            ("total_tokens", "total_token_count"),
        ):
            value = getattr(usage, source, None)
            if value is not None:
                metadata[output] = int(value)
    finish_reason = _finish_reason(response)
    if finish_reason:
        metadata["finish_reason"] = finish_reason
    _check_finish_reason(finish_reason, max_tokens, metadata)

    text = getattr(response, "text", None)
    if not text:
        raise BackendError("Vertex returned no text (blocked, or empty candidate)")
    return GenerationResult(text=text, metadata=metadata)


def _check_finish_reason(finish_reason: str | None, max_tokens: int,
                         metadata: dict) -> None:
    """Reject incomplete or blocked candidates before their text can be used."""
    if finish_reason == "MAX_TOKENS":
        detail = ", ".join(
            f"{name}={metadata[name]}" for name in
            ("thought_tokens", "output_tokens") if name in metadata)
        suffix = f", {detail}" if detail else ""
        raise BackendError(
            f"Vertex stopped at MAX_TOKENS (max_output_tokens={max_tokens}{suffix}); "
            "no card was written. Raise --max-output-tokens if the model allows it, "
            "or shorten the input.")
    if finish_reason not in (None, "STOP", "FINISH_REASON_UNSPECIFIED"):
        raise BackendError(
            f"Vertex stopped with finish_reason={finish_reason}; no card was written")


def _finish_reason(response) -> str | None:
    """Return the first candidate's finish reason without importing SDK types."""
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return None
    reason = getattr(candidates[0], "finish_reason", None)
    if reason is None:
        return None
    value = getattr(reason, "value", None) or getattr(reason, "name", None)
    return str(value or reason).rsplit(".", 1)[-1]


def _brief(exc) -> str:
    """One short line. Never the prompt, never a credential."""
    return str(exc).splitlines()[0][:200]
