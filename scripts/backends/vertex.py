"""Google Vertex AI backend — the cheap bulk pass.

    generate(prompt, model, max_tokens=..., timeout=...) -> str

Credentials and project come from the environment, the way gcloud sets them:

    GOOGLE_APPLICATION_CREDENTIALS   service-account key file
    GOOGLE_CLOUD_PROJECT             project id
    GOOGLE_CLOUD_LOCATION            region, e.g. us-central1 (default: global)

Nothing here reads the key file or prints any of it.

The SDK import is lazy so the rest of the skill runs without `google-genai`
installed; it is listed as optional in requirements.txt.
"""

import os

from . import BackendError, TransientError

DEFAULT_MAX_TOKENS = 4096

# Vertex reports transient conditions as message text on a generic exception
# more often than as a typed error, so match on the text as well.
_TRANSIENT_MARKERS = ("429", "500", "502", "503", "504", "resource exhausted",
                      "deadline exceeded", "unavailable", "internal error",
                      "rate limit", "timeout", "overloaded")


def generate(prompt: str, model: str, max_tokens: int = DEFAULT_MAX_TOKENS,
             timeout: float = 600.0, **opts) -> str:
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

    try:
        client = genai.Client(vertexai=True, project=project, location=location)
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                http_options=types.HttpOptions(timeout=int(timeout * 1000)),
            ),
        )
    except Exception as exc:
        message = _brief(exc)
        if any(m in message.lower() for m in _TRANSIENT_MARKERS):
            raise TransientError(message) from None
        raise BackendError(f"{type(exc).__name__}: {message}") from None

    text = getattr(response, "text", None)
    if not text:
        raise BackendError("Vertex returned no text (blocked, or empty candidate)")
    return text


def _brief(exc) -> str:
    """One short line. Never the prompt, never a credential."""
    return str(exc).splitlines()[0][:200]
