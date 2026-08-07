"""Backends for the card extraction runner.

A backend is one module exposing a single function:

    generate(prompt: str, model: str, **opts) -> str

It returns the model's text and nothing else. It never logs credentials and
never echoes the paper text back out — the prompt it receives carries a whole
paper, and a traceback that prints it is a leak of the evidence layer into the
run log.

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

# `fake` is the offline backend the tests inject; it calls nothing.
KNOWN = ("vertex", "anthropic", "fake")


class BackendError(Exception):
    """A backend failure that is not worth retrying."""


class TransientError(BackendError):
    """A backend failure that another attempt might survive."""


def load(name: str):
    """Import a backend module by name. Raises KeyError if it is not known."""
    if name not in KNOWN:
        raise KeyError(name)
    return importlib.import_module(f"{__name__}.{name}")


def generate(backend: str, prompt: str, model: str, attempts: int = 4,
             base_delay: float = 2.0, sleep=time.sleep, **opts) -> str:
    """Call a backend, retrying transient failures with exponential backoff.

    Raises BackendError with a message that never contains prompt text.
    """
    module = load(backend)
    last = None
    for attempt in range(1, attempts + 1):
        try:
            text = module.generate(prompt, model, **opts)
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
        if not (text or "").strip():
            last = TransientError("backend returned empty text")
            if attempt == attempts:
                break
            sleep(base_delay * (2 ** (attempt - 1)))
            continue
        return text
    raise BackendError(f"gave up after {attempts} attempts: {last}")
