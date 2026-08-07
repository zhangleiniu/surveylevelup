"""Offline tests for extract_cards.py — no network, no real project.

    python3 tests/test_extract_cards.py

Each test stands up a throwaway project by hand: state/progress.json, one
prompt, and a couple of full-text files. The `fake` backend supplies canned
answers, so the whole runner path — provenance stamping, pre-validation, the
gate and model-mixing refusals, overwrite refusal, evidence verification — runs
without a backend.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import extract_cards  # noqa: E402
from common import parse_card  # noqa: E402

PROMPT = """# Method card

Fill one card per paper. `not reported` means the paper did not say so.

```fields
# name    | kind | values            | flags
approach  | enum | graph, sequence   | required
purpose   | text |                   | required, evidence
stages    | int  |                   |
```
"""

PAPER = """# A Paper About Routing

We route messages along the instance graph, then decode a solution.
The encoder runs for two stages.

Prior work by Bother and Kissig is discussed on page four.
"""


def run(project, *argv, env=None):
    """Run extract_cards.py in a subprocess; return (returncode, parsed JSON)."""
    environment = {**os.environ, **(env or {})}
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "extract_cards.py"), "--project", str(project),
         *argv],
        capture_output=True, text=True, env=environment)
    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        payload = {"_stdout": proc.stdout, "_stderr": proc.stderr}
    return proc.returncode, payload


def check(project):
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "cards.py"), "--project", str(project),
         "--check"], capture_output=True, text=True)
    return json.loads(proc.stdout)


class ProjectCase(unittest.TestCase):
    """A throwaway project with one prompt, two papers, and an open gate."""

    gate_open = True
    trial = ["goodpaper2024x", "otherpaper2024y"]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name) / "project"
        for sub in ("state", "inputs/prompts", "inputs/fulltext", "inputs/cards"):
            (self.project / sub).mkdir(parents=True)
        (self.project / "state" / "progress.json").write_text(json.dumps({
            "gate": {"open": self.gate_open, "signed_by": "Tester, 2026-01-01"},
            "trial_papers": self.trial,
            "counts": {}, "history": [],
        }))
        (self.project / "inputs" / "prompts" / "method_card.md").write_text(PROMPT)
        for key in ("goodpaper2024x", "otherpaper2024y"):
            (self.project / "inputs" / "fulltext" / f"{key}.md").write_text(PAPER)

    def tearDown(self):
        self.tmp.cleanup()

    def card(self, bibkey, card_type="method"):
        return (self.project / "inputs" / "cards" / card_type / f"{bibkey}.md")

    def write_assignments(self, table):
        (self.project / "state" / "card_assignments.json").write_text(
            json.dumps(table))


class TestProvenance(ProjectCase):

    def test_front_matter_records_model_and_prompt_digest(self):
        code, out = run(self.project, "--type", "method",
                        "--keys", "goodpaper2024x",
                        "--backend", "fake", "--model", "fake-model-1")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(out["written"]), 1, out)
        front = parse_card(self.card("goodpaper2024x").read_text())["front"]
        self.assertEqual(front["bibkey"], "goodpaper2024x")
        self.assertEqual(front["card_type"], "method")
        self.assertEqual(front["model"], "fake-model-1")
        self.assertEqual(front["backend"], "fake")
        self.assertEqual(front["prompt"], "method_card.md")
        self.assertEqual(len(front["prompt_sha256"]), 12)
        self.assertEqual(len(front["fulltext_sha256"]), 12)
        self.assertIn("generated", front)

    def test_written_card_passes_cards_py_check(self):
        run(self.project, "--type", "method", "--keys", "goodpaper2024x",
            "--backend", "fake", "--model", "fake-model-1")
        report = check(self.project)
        self.assertEqual(report["cards_clean"], 1, report)
        self.assertEqual(report["cards_with_problems"], [], report)

    def test_model_and_fenced_front_matter_are_stripped(self):
        code, out = run(self.project, "--type", "method", "--keys", "goodpaper2024x",
                        "--backend", "fake", "--model", "fake-model-1",
                        env={"SURVEYLEVELUP_FAKE_MODE": "wrapped"})
        self.assertEqual(code, 0, out)
        parsed = parse_card(self.card("goodpaper2024x").read_text())
        # ours wins: the model's own front matter must not shadow provenance
        self.assertEqual(parsed["front"]["model"], "fake-model-1")
        self.assertEqual(parsed["front"]["bibkey"], "goodpaper2024x")
        self.assertNotIn("```", self.card("goodpaper2024x").read_text())

    def test_dry_run_calls_no_backend_and_reports_the_estimate(self):
        code, out = run(self.project, "--type", "method", "--keys", "goodpaper2024x",
                        "--backend", "fake", "--model", "fake-model-1", "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertTrue(out["dry_run"])
        self.assertEqual(out["model"], "fake-model-1")
        self.assertGreater(out["input_tokens_estimate_total"], 0)
        self.assertEqual(len(out["would_write"]), 1)
        self.assertFalse(self.card("goodpaper2024x").exists())


class TestPreValidation(ProjectCase):
    """A card that fails is still written, and reported as invalid."""

    def extract(self, mode, key="goodpaper2024x"):
        return run(self.project, "--type", "method", "--keys", key,
                   "--backend", "fake", "--model", "fake-model-1",
                   env={"SURVEYLEVELUP_FAKE_MODE": mode})

    def assertFlags(self, mode, needle):
        code, out = self.extract(mode)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["written"], [], out)
        self.assertEqual(len(out["invalid"]), 1, out)
        problems = json.dumps(out["invalid"][0]["problems"])
        self.assertIn(needle, problems)
        # written anyway, and cards.py agrees it is broken
        self.assertTrue(self.card("goodpaper2024x").exists())
        report = check(self.project)
        self.assertEqual(report["cards_clean"], 0, report)

    def test_missing_required_field(self):
        self.assertFlags("missing_required", "required field absent")

    def test_enum_out_of_range(self):
        self.assertFlags("bad_enum", "outside the declared enum")

    def test_undeclared_field(self):
        self.assertFlags("undeclared", "not declared by the prompt")

    def test_missing_evidence_sibling(self):
        self.assertFlags("no_evidence", "without _evidence")

    def test_non_integer(self):
        self.assertFlags("bad_int", "not an integer")

    def test_free_text_escape_hatch_is_accepted(self):
        code, out = self.extract("free_text")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["invalid"], [], out)
        self.assertEqual(len(out["written"]), 1, out)
        self.assertEqual(check(self.project)["cards_clean"], 1)


class TestRefusals(ProjectCase):

    def test_overwrite_refused_without_force(self):
        run(self.project, "--type", "method", "--keys", "goodpaper2024x",
            "--backend", "fake", "--model", "fake-model-1")
        first = self.card("goodpaper2024x").read_text()
        code, out = run(self.project, "--type", "method", "--keys", "goodpaper2024x",
                        "--backend", "fake", "--model", "fake-model-1",
                        env={"SURVEYLEVELUP_FAKE_MODE": "bad_enum"})
        self.assertEqual(code, 0, out)
        self.assertEqual(len(out["skipped"]), 1, out)
        self.assertEqual(out["skipped"][0]["status"], "exists")
        self.assertEqual(self.card("goodpaper2024x").read_text(), first)

    def test_force_overwrites(self):
        run(self.project, "--type", "method", "--keys", "goodpaper2024x",
            "--backend", "fake", "--model", "fake-model-1")
        code, out = run(self.project, "--type", "method", "--keys", "goodpaper2024x",
                        "--backend", "fake", "--model", "fake-model-1", "--force",
                        env={"SURVEYLEVELUP_FAKE_MODE": "bad_enum"})
        self.assertEqual(code, 0, out)
        self.assertEqual(len(out["invalid"]), 1, out)

    def test_model_mixing_refused(self):
        run(self.project, "--type", "method", "--keys", "goodpaper2024x",
            "--backend", "fake", "--model", "fake-model-1")
        code, out = run(self.project, "--type", "method", "--keys", "otherpaper2024y",
                        "--backend", "fake", "--model", "fake-model-2")
        self.assertEqual(code, 1, out)
        self.assertEqual(out["refused"], "artifact_cohort_mixing")
        self.assertEqual(out["papers"], ["goodpaper2024x"])
        self.assertIn("model", out["conflicts"]["goodpaper2024x"])
        self.assertFalse(self.card("otherpaper2024y").exists())

    def test_force_does_not_bypass_model_mixing(self):
        run(self.project, "--type", "method", "--keys", "goodpaper2024x",
            "--backend", "fake", "--model", "fake-model-1")
        code, out = run(self.project, "--type", "method", "--keys", "otherpaper2024y",
                        "--backend", "fake", "--model", "fake-model-2", "--force")
        self.assertEqual(code, 1, out)
        self.assertEqual(out["refused"], "artifact_cohort_mixing")
        self.assertFalse(self.card("otherpaper2024y").exists())

    def test_prompt_mixing_is_refused(self):
        run(self.project, "--type", "method", "--keys", "goodpaper2024x",
            "--backend", "fake", "--model", "fake-model-1")
        prompt = self.project / "inputs" / "prompts" / "method_card.md"
        prompt.write_text(prompt.read_text() + "\nA clarified instruction.\n")
        code, out = run(self.project, "--type", "method", "--keys", "otherpaper2024y",
                        "--backend", "fake", "--model", "fake-model-1")
        self.assertEqual(code, 1, out)
        self.assertIn("prompt_sha256", out["conflicts"]["goodpaper2024x"])

    def test_backend_mixing_is_refused_before_backend_import(self):
        run(self.project, "--type", "method", "--keys", "goodpaper2024x",
            "--backend", "fake", "--model", "same-model")
        code, out = run(self.project, "--type", "method", "--keys", "otherpaper2024y",
                        "--backend", "anthropic", "--model", "same-model")
        self.assertEqual(code, 1, out)
        self.assertIn("backend", out["conflicts"]["goodpaper2024x"])

    def test_missing_fulltext_is_reported_not_fatal(self):
        code, out = run(self.project, "--type", "method",
                        "--keys", "goodpaper2024x,ghost2024z",
                        "--backend", "fake", "--model", "fake-model-1")
        self.assertEqual(code, 1, out)          # a failure did occur
        self.assertEqual(len(out["written"]), 1, out)   # and the other key ran
        self.assertEqual(out["failed"][0]["bibkey"], "ghost2024z")
        self.assertEqual(out["failed"][0]["status"], "no_fulltext")

    def test_unknown_backend_and_missing_model(self):
        code, out = run(self.project, "--type", "method", "--keys", "goodpaper2024x",
                        "--backend", "telepathy", "--model", "m")
        self.assertEqual(code, 1)
        self.assertIn("unknown backend", out["error"])
        code, out = run(self.project, "--type", "method", "--keys", "goodpaper2024x",
                        "--backend", "fake")
        self.assertEqual(code, 1)
        self.assertIn("--model is required", out["error"])

    def test_unknown_card_type(self):
        code, out = run(self.project, "--type", "theory", "--keys", "goodpaper2024x",
                        "--backend", "fake", "--model", "m")
        self.assertEqual(code, 1)
        self.assertIn("no prompt declares card type", out["error"])
        self.assertEqual(out["known_types"], ["method"])


class TestGateClosed(ProjectCase):
    gate_open = False
    trial = ["goodpaper2024x"]

    def test_trial_paper_is_allowed(self):
        code, out = run(self.project, "--type", "method", "--keys", "goodpaper2024x",
                        "--backend", "fake", "--model", "fake-model-1")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["gate"], "closed")
        self.assertEqual(len(out["written"]), 1, out)

    def test_paper_outside_the_trial_set_is_refused(self):
        code, out = run(self.project, "--type", "method", "--keys", "otherpaper2024y",
                        "--backend", "fake", "--model", "fake-model-1")
        self.assertEqual(code, 1, out)
        self.assertEqual(out["refused"], "gate_violation")
        self.assertEqual(out["papers"], ["otherpaper2024y"])
        self.assertFalse(self.card("otherpaper2024y").exists())

    def test_a_mixed_batch_writes_nothing(self):
        code, out = run(self.project, "--type", "method",
                        "--keys", "goodpaper2024x,otherpaper2024y",
                        "--backend", "fake", "--model", "fake-model-1")
        self.assertEqual(code, 1, out)
        self.assertEqual(out["refused"], "gate_violation")
        self.assertFalse(self.card("goodpaper2024x").exists())


class TestCardAssignments(ProjectCase):

    def test_all_requires_assignments(self):
        code, out = run(self.project, "--type", "method", "--all",
                        "--backend", "fake", "--model", "fake-model-1", "--dry-run")
        self.assertEqual(code, 1, out)
        self.assertIn("card_assignments.json is required", out["error"])

    def test_all_selects_explicit_assignments_and_allows_empty_list(self):
        self.write_assignments({
            "goodpaper2024x": ["method"],
            "otherpaper2024y": [],
        })
        code, out = run(self.project, "--type", "method", "--all",
                        "--backend", "fake", "--model", "fake-model-1", "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertEqual([x["bibkey"] for x in out["would_write"]],
                         ["goodpaper2024x"])
        self.assertEqual(out["selection"]["reviewed_papers"], 2)

    def test_one_paper_may_have_two_card_types(self):
        (self.project / "inputs" / "prompts" / "benchmark_card.md").write_text(PROMPT)
        self.write_assignments({
            "goodpaper2024x": ["method", "benchmark"],
            "otherpaper2024y": [],
        })
        code, out = run(self.project, "--type", "benchmark", "--all",
                        "--backend", "fake", "--model", "fake-model-1", "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertEqual([x["bibkey"] for x in out["would_write"]],
                         ["goodpaper2024x"])

    def test_incomplete_assignments_fail_closed(self):
        self.write_assignments({"goodpaper2024x": ["method"]})
        code, out = run(self.project, "--type", "method", "--all",
                        "--backend", "fake", "--model", "fake-model-1", "--dry-run")
        self.assertEqual(code, 1, out)
        self.assertEqual(out["papers_with_no_assignment"], ["otherpaper2024y"])

    def test_invalid_assignment_is_reported(self):
        self.write_assignments({
            "goodpaper2024x": "method",
            "otherpaper2024y": ["telepathy"],
        })
        code, out = run(self.project, "--type", "method", "--all",
                        "--backend", "fake", "--model", "fake-model-1", "--dry-run")
        self.assertEqual(code, 1, out)
        self.assertEqual(len(out["problems"]), 2, out)


class TestVerifyEvidence(ProjectCase):

    def write_card(self, bibkey, evidence):
        path = self.card(bibkey)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\n"
            f"bibkey: {bibkey}\ncard_type: method\nprompt: method_card.md\n"
            "prompt_sha256: 000000000000\nmodel: fake-model-1\nbackend: fake\n"
            "---\n\n"
            "approach: graph\n"
            "purpose: routes a message along the instance graph\n"
            f"  purpose_evidence: {evidence}\n"
            "stages: 2\n")

    def verify(self):
        code, out = run(self.project, "--verify-evidence")
        self.assertEqual(code, 0, out)
        return out

    def status_for(self, out, bibkey):
        for entry in out["flagged"]:
            if entry["card"].endswith(bibkey):
                return entry["fields"][0]
        return {"status": "verified"}

    def test_quote_that_is_present(self):
        self.write_card("goodpaper2024x",
                        '"we route messages along the instance graph" (p. 1)')
        out = self.verify()
        self.assertEqual(out["verify_evidence"]["fields"]["verified"], 1, out)
        self.assertEqual(out["flagged"], [], out)

    def test_quote_differing_only_in_whitespace_still_verifies(self):
        self.write_card("goodpaper2024x",
                        '"we   route\tmessages  along the instance graph" (pp. 1-2)')
        out = self.verify()
        self.assertEqual(self.status_for(out, "goodpaper2024x")["status"], "verified")

    def test_quote_differing_only_in_quote_marks_and_dashes_still_verifies(self):
        self.write_card("goodpaper2024x",
                        '“we route messages along the instance graph” (p. 1)')
        out = self.verify()
        self.assertEqual(self.status_for(out, "goodpaper2024x")["status"], "verified")

    def test_fabricated_quote_is_flagged(self):
        self.write_card("goodpaper2024x",
                        '"we solve the problem with a transformer" (p. 3)')
        out = self.verify()
        self.assertEqual(self.status_for(out, "goodpaper2024x")["status"], "not_found")
        self.assertEqual(out["verify_evidence"]["fields"]["not_found"], 1, out)

    def test_a_diacritic_the_extraction_dropped_is_a_near_match(self):
        # Extraction mangles accented names — this project has seen Böther come
        # out as BÃ˝uther. A quote copied from the PDF then differs from the
        # file by a character or two. Reporting that as not_found would repeat
        # the wrong result the corpus already produced once, so it is flagged
        # as a near match for a human to settle against the PDF.
        self.write_card("goodpaper2024x",
                        '"Prior work by Böther and Kißig is discussed" (p. 4)')
        out = self.verify()
        field = self.status_for(out, "goodpaper2024x")
        self.assertEqual(field["status"], "near_match", out)
        self.assertGreaterEqual(field["similarity"], 0.90)

    def test_missing_evidence_field_is_reported(self):
        path = self.card("goodpaper2024x")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("---\nbibkey: goodpaper2024x\nmodel: fake-model-1\n---\n\n"
                        "approach: graph\npurpose: routes a message\n")
        out = self.verify()
        self.assertEqual(self.status_for(out, "goodpaper2024x")["status"],
                         "no_evidence_field")

    def test_card_with_no_fulltext_is_reported(self):
        self.write_card("ghost2024z", '"anything at all" (p. 1)')
        out = self.verify()
        entry = next(e for e in out["flagged"] if e["card"].endswith("ghost2024z"))
        self.assertIn("no full text", entry["problem"])

    def test_nothing_is_edited(self):
        self.write_card("goodpaper2024x", '"a fabricated quote entirely" (p. 9)')
        before = self.card("goodpaper2024x").read_text()
        self.verify()
        self.assertEqual(self.card("goodpaper2024x").read_text(), before)


class TestNoShellOut(unittest.TestCase):
    """NUL bytes must not defeat the evidence check.

    BSD grep on macOS treats a file containing a NUL as binary and matches
    nothing in it, silently. That has already produced a wrong result in this
    project, so every read here is Python with errors='ignore'.
    """

    def test_nul_bytes_and_mojibake_do_not_hide_a_quote(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paper.md"
            path.write_bytes(
                b"intro\x00\x00 we route messages along the \xc3\x83\xc2\xa9 graph\n")
            text = extract_cards.read_text(path)
            self.assertIn("we route messages", text)
            self.assertIn("we route messages along the",
                          extract_cards.normalise(text))

    def test_source_never_invokes_grep(self):
        source = (SCRIPTS / "extract_cards.py").read_text()
        for forbidden in ("subprocess", "os.system", "os.popen"):
            self.assertNotIn(forbidden, source)


class TestBackendRetry(unittest.TestCase):

    def test_transient_failures_are_retried_then_succeed(self):
        os.environ["SURVEYLEVELUP_FAKE_MODE"] = "transient"
        try:
            slept = []
            result = backends_generate(slept)
            self.assertIn("approach: graph", result.text)
            self.assertEqual(len(slept), 2)     # two backoffs, third attempt won
        finally:
            os.environ.pop("SURVEYLEVELUP_FAKE_MODE", None)

    def test_a_hard_failure_raises_backend_error(self):
        import backends
        os.environ["SURVEYLEVELUP_FAKE_MODE"] = "nonexistent-mode"
        try:
            with self.assertRaises(backends.BackendError):
                backends.generate("fake", "prompt", "model", sleep=lambda _: None)
        finally:
            os.environ.pop("SURVEYLEVELUP_FAKE_MODE", None)

    def test_unknown_backend_raises_key_error(self):
        import backends
        with self.assertRaises(KeyError):
            backends.load("telepathy")


def backends_generate(slept):
    import backends
    from backends import fake
    fake._attempts.clear()
    return backends.generate("fake", "prompt", "model", sleep=slept.append)


if __name__ == "__main__":
    unittest.main(verbosity=2)
