"""Offline backend. Returns a canned card so the whole runner path is testable.

Selected with `--backend fake`. It reads nothing from the network and ignores
the model id beyond recording it, which is the point: the runner's own
behaviour — provenance stamping, pre-validation, the gate and model-mixing
refusals, overwrite refusal — is what the tests are about.

What it returns is set by the environment, so a test can drive it without the
runner growing test-only flags:

    SURVEYLEVELUP_FAKE_CARD=<path>   return this file's text verbatim
    SURVEYLEVELUP_FAKE_MODE=<name>   return one of the canned bodies below

Modes match the failure classes the pre-validation has to catch. `transient`
raises TransientError on every call but the last, to exercise the backoff.
"""

import os

from . import TransientError

CANNED = {
    # honours the smoke-test prompt's contract
    "good": 'approach: graph\n'
            'purpose: routes a message along the instance graph\n'
            '  purpose_evidence: "we route messages along the instance graph" (p. 4)\n'
            'stages: 2\n',
    "missing_required": 'purpose: routes a message\n'
                        '  purpose_evidence: "we route messages" (p. 4)\n'
                        'stages: 2\n',
    "bad_enum": 'approach: telepathy\n'
                'purpose: routes a message\n'
                '  purpose_evidence: "we route messages" (p. 4)\n'
                'stages: 2\n',
    "undeclared": 'approach: graph\n'
                  'purpose: routes a message\n'
                  '  purpose_evidence: "we route messages" (p. 4)\n'
                  'smuggled_field: not in the prompt\n',
    "no_evidence": 'approach: graph\n'
                   'purpose: routes a message\n'
                   'stages: 2\n',
    "bad_int": 'approach: graph\n'
               'purpose: routes a message\n'
               '  purpose_evidence: "we route messages" (p. 4)\n'
               'stages: many\n',
    "free_text": 'approach: FREE TEXT — solves a relaxation, then rounds. '
                 'Suggested label: relaxation\n'
                 'purpose: routes a message\n'
                 '  purpose_evidence: "we route messages" (p. 4)\n'
                 'stages: 2\n',
    # a model that wraps its answer in a fence and its own front matter
    "wrapped": '```\n---\nbibkey: whatever\nmodel: some-other-model\n---\n'
               'approach: graph\n'
               'purpose: routes a message\n'
               '  purpose_evidence: "we route messages" (p. 4)\n'
               '```\n',
}

_attempts = {}


def generate(prompt: str, model: str, **opts) -> str:
    path = os.environ.get("SURVEYLEVELUP_FAKE_CARD")
    if path:
        with open(path, encoding="utf-8", errors="ignore") as handle:
            return handle.read()
    mode = os.environ.get("SURVEYLEVELUP_FAKE_MODE", "good")
    if mode == "transient":
        n = _attempts.get("transient", 0) + 1
        _attempts["transient"] = n
        if n < 3:
            raise TransientError("simulated rate limit")
        return CANNED["good"]
    if mode not in CANNED:
        raise KeyError(f"unknown SURVEYLEVELUP_FAKE_MODE {mode!r}")
    return CANNED[mode]
