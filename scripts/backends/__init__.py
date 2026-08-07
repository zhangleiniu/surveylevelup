"""Backends for the card extraction runner.

A backend is one module exposing a single function:

    generate(prompt: str, model: str, **opts) -> str | GenerationResult

It returns model text and may attach non-sensitive response metadata. It never
logs credentials or echoes the paper text back out — the prompt it receives
carries a whole paper, and a traceback that prints it is a leak of the evidence
layer into the run log.

Backends import their SDK lazily, inside the call, so the rest of the skill
runs on a machine where neither SDK is installed.

Two error classes shape the retry policy:

    Transient  — rate limit, timeout, 5xx. Retried with backoff.
    Permanent  — bad credentials, unknown model, refusal. Reported at once.

Anything else raised by a backend is treated as permanent.
"""

import importlib
import random
import time
from dataclasses import dataclass, field

# `fake` is the offline backend the tests inject; it calls nothing.
KNOWN = ("vertex", "anthropic", "fake")


class BackendError(Exception):
    """A backend failure that is not worth retrying."""


class TransientError(BackendError):
    """A backend failure that another attempt might survive."""


@dataclass
class GenerationResult:
    """Model text plus non-sensitive response metadata.

    Simple backends may still return a string; ``generate`` wraps it. Cloud
    backends use metadata for token accounting and exact run provenance.
    """

    text: str
    metadata: dict = field(default_factory=dict)


def load(name: str):
    """Import a backend module by name. Raises KeyError if it is not known."""
    if name not in KNOWN:
        raise KeyError(name)
    return importlib.import_module(f"{__name__}.{name}")


def preflight(backend: str, model: str | None, **opts) -> dict:
    """Check a backend without generating content or incurring model usage.

    Preflights return structured diagnostics rather than raising, so both the
    doctor and the extraction runner can explain the exact missing prerequisite.
    """
    if backend not in KNOWN:
        return {
            "backend": backend,
            "model": model,
            "ready": False,
            "problems": [{
                "code": "unknown_backend",
                "message": f"unknown backend {backend!r}",
                "known_backends": list(KNOWN),
            }],
        }
    try:
        module = load(backend)
        check = getattr(module, "preflight")
        status = check(model, **opts)
    except Exception as exc:
        return {
            "backend": backend,
            "model": model,
            "ready": False,
            "problems": [{
                "code": "preflight_error",
                "message": f"{type(exc).__name__}: {str(exc).splitlines()[0][:200]}",
            }],
        }
    status.setdefault("backend", backend)
    status.setdefault("model", model)
    status.setdefault("problems", [])
    status["ready"] = bool(status.get("ready")) and not status["problems"]
    return status


def generate(backend: str, prompt: str, model: str, attempts: int = 4,
             base_delay: float = 2.0, sleep=time.sleep, **opts) -> GenerationResult:
    """Call a backend, retrying transient failures with exponential backoff.

    Raises BackendError with a message that never contains prompt text.
    """
    module = load(backend)
    last = None
    for attempt in range(1, attempts + 1):
        try:
            result = module.generate(prompt, model, **opts)
        except TransientError as exc:
            last = exc
            if attempt == attempts:
                break
            sleep(base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5))
            continue
        except BackendError:
            raise
        except Exception as exc:  # an SDK error we do not recognise
            raise BackendError(f"{type(exc).__name__}: {exc}") from None
        if isinstance(result, str):
            result = GenerationResult(result)
        if not isinstance(result, GenerationResult):
            raise BackendError(
                f"{backend} returned {type(result).__name__}, expected text or GenerationResult")
        if not (result.text or "").strip():
            last = TransientError("backend returned empty text")
            if attempt == attempts:
                break
            sleep(base_delay * (2 ** (attempt - 1)))
            continue
        return result
    raise BackendError(f"gave up after {attempts} attempts: {last}")
