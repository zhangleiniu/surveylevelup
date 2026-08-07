"""Offline tests for extraction configuration, doctor and backend preflight."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from backends import vertex  # noqa: E402
from extraction_config import (ExtractionConfigError, load_config, resolve,
                               save_config)  # noqa: E402


PROMPT = """# Method card

```fields
approach | enum | graph, sequence | required
purpose  | text |                 | required, evidence
stages   | int  |                 |
```
"""

PAPER = """# Routing

We route messages along the instance graph. The encoder runs for two stages.
"""


class ProjectCase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name) / "project"
        for sub in ("state", "inputs/prompts", "inputs/fulltext", "inputs/cards"):
            (self.project / sub).mkdir(parents=True)
        (self.project / "state/progress.json").write_text(json.dumps({
            "gate": {"open": False, "opened": None, "signed_by": None},
            "trial_papers": ["trial2026routing"],
            "counts": {},
            "history": [],
        }))
        (self.project / "inputs/prompts/method_card.md").write_text(PROMPT)
        (self.project / "inputs/fulltext/trial2026routing.md").write_text(PAPER)

    def tearDown(self):
        self.tmp.cleanup()

    def invoke(self, script, *args, env=None):
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / script), "--project", str(self.project),
             *args], capture_output=True, text=True,
            env={**os.environ, **(env or {})})
        try:
            payload = json.loads(proc.stdout)
        except ValueError:
            payload = {"stdout": proc.stdout, "stderr": proc.stderr}
        return proc.returncode, payload


class TestExtractionConfig(ProjectCase):

    def test_project_defaults_and_command_line_precedence(self):
        save_config(self.project, {
            "backend": "vertex", "model": "stored-model",
            "project": "stored-project", "location": "global",
        })
        selected = resolve(self.project, {"model": "cli-model"})
        self.assertEqual(selected["values"]["backend"], "vertex")
        self.assertEqual(selected["values"]["model"], "cli-model")
        self.assertEqual(selected["sources"]["backend"], "project_config")
        self.assertEqual(selected["sources"]["model"], "command_line")

    def test_config_rejects_credentials_and_unknown_fields(self):
        path = self.project / "state/extraction.json"
        path.write_text(json.dumps({
            "backend": "vertex", "model": "m", "api_key": "secret",
        }))
        with self.assertRaisesRegex(ExtractionConfigError, "unknown fields"):
            load_config(self.project)

    def test_cli_backend_switch_drops_stored_vertex_specific_values(self):
        save_config(self.project, {
            "backend": "vertex", "model": "gemini-test",
            "project": "stored-project", "location": "global",
        })
        selected = resolve(self.project, {
            "backend": "anthropic", "model": "claude-test",
        })
        self.assertEqual(selected["values"], {
            "backend": "anthropic", "model": "claude-test",
        })

    def test_runner_uses_project_backend_and_model(self):
        save_config(self.project, {"backend": "fake", "model": "configured-model"})
        code, out = self.invoke(
            "extract_cards.py", "--type", "method", "--keys", "trial2026routing")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["backend"], "fake")
        self.assertEqual(out["model"], "configured-model")
        self.assertEqual(out["gate"], "closed")
        card = self.project / "inputs/cards/method/trial2026routing.md"
        self.assertTrue(card.is_file())
        self.assertIn("model: configured-model", card.read_text())


class TestDoctor(ProjectCase):

    def test_doctor_separates_backend_readiness_from_gate(self):
        save_config(self.project, {"backend": "fake", "model": "doctor-model"})
        code, out = self.invoke("doctor.py")
        self.assertEqual(code, 0, out)
        self.assertTrue(out["backend"]["ready"])
        self.assertEqual(out["survey"]["extraction_gate"], "closed")
        self.assertEqual(out["survey"]["trial_extraction"],
                         "allowed_for_nominated_papers")
        self.assertEqual(out["survey"]["corpus_wide_extraction"],
                         "blocked_by_gate")
        self.assertTrue(out["ready_for_trial_extraction"])
        self.assertTrue(out["read_only"])
        self.assertFalse(out["paid_call"])

    def test_failed_preflight_writes_no_card(self):
        save_config(self.project, {"backend": "fake", "model": "doctor-model"})
        code, out = self.invoke(
            "extract_cards.py", "--type", "method", "--keys", "trial2026routing",
            env={"SURVEYLEVELUP_FAKE_PREFLIGHT": "fail"})
        self.assertEqual(code, 1, out)
        self.assertEqual(out["refused"], "backend_not_ready")
        self.assertEqual(out["gate"], "closed")
        self.assertEqual(out["trial_extraction"], "allowed_for_nominated_papers")
        self.assertFalse((self.project / "inputs/cards/method/trial2026routing.md").exists())


class TestVertexPreflight(unittest.TestCase):

    def test_adc_project_is_used_when_environment_is_unset(self):
        fake_genai = SimpleNamespace(__version__="2.17.0")
        clean = {"GOOGLE_CLOUD_PROJECT": "", "GOOGLE_CLOUD_LOCATION": ""}
        with patch.dict(os.environ, clean, clear=False), \
                patch.object(vertex, "_load_sdk",
                             return_value=(fake_genai, SimpleNamespace())), \
                patch.object(vertex, "_load_adc",
                             return_value=(object(), "adc-project")), \
                patch.object(vertex, "_gcloud_default_project", return_value=None):
            status = vertex.preflight("gemini-test")
        self.assertTrue(status["ready"], status)
        self.assertEqual(status["resolved"]["project"], "adc-project")
        self.assertEqual(status["resolved"]["project_source"],
                         "application_default_credentials")
        self.assertEqual(status["resolved"]["location"], "global")
        self.assertTrue(status["authentication"]["available"])
        self.assertFalse(status["paid_call"])

    def test_explicit_project_wins_over_environment_and_adc(self):
        fake_genai = SimpleNamespace(__version__="2.17.0")
        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "environment-project"}), \
                patch.object(vertex, "_load_sdk",
                             return_value=(fake_genai, SimpleNamespace())), \
                patch.object(vertex, "_load_adc",
                             return_value=(object(), "adc-project")), \
                patch.object(vertex, "_gcloud_default_project", return_value=None):
            status = vertex.preflight(
                "gemini-test", project="configured-project",
                project_source="project_config")
        self.assertTrue(status["ready"], status)
        self.assertEqual(status["resolved"]["project"], "configured-project")
        self.assertEqual(status["resolved"]["project_source"], "project_config")

    def test_gcloud_adc_is_still_detected_when_sdk_is_missing(self):
        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": ""}), \
                patch.object(vertex, "_load_sdk", side_effect=ImportError()), \
                patch.object(vertex, "_load_adc", side_effect=ImportError()), \
                patch.object(vertex, "_gcloud_adc_available", return_value=True), \
                patch.object(vertex, "_gcloud_default_project",
                             return_value="gcloud-project"):
            status = vertex.preflight("gemini-test")
        self.assertFalse(status["ready"])
        self.assertFalse(status["sdk"]["available"])
        self.assertTrue(status["authentication"]["available"])
        self.assertEqual(status["authentication"]["source"],
                         "gcloud_application_default_credentials")
        project_problem = next(
            p for p in status["problems"] if p["code"] == "project_missing")
        self.assertEqual(project_problem["detected_gcloud_default"], "gcloud-project")

    def test_doctor_service_check_can_block_a_disabled_api(self):
        fake_genai = SimpleNamespace(__version__="2.17.0")
        with patch.object(vertex, "_load_sdk",
                          return_value=(fake_genai, SimpleNamespace())), \
                patch.object(vertex, "_load_adc",
                             return_value=(object(), "adc-project")), \
                patch.object(vertex, "_gcloud_default_project", return_value=None), \
                patch.object(vertex, "_gcloud_vertex_api_enabled", return_value=False):
            status = vertex.preflight(
                "gemini-test", project="configured-project", check_service=True)
        self.assertFalse(status["ready"])
        self.assertFalse(status["service"]["enabled"])
        self.assertIn("vertex_api_disabled",
                      {problem["code"] for problem in status["problems"]})


class TestInitConfiguration(unittest.TestCase):

    def test_init_can_record_non_sensitive_extraction_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus, project = root / "corpus", root / "survey"
            subprocess.run(
                [sys.executable, str(ROOT / "tests/make_fixture_corpus.py"),
                 str(corpus)], check=True, capture_output=True, text=True)
            proc = subprocess.run([
                sys.executable, str(SCRIPTS / "init.py"),
                "--corpus", str(corpus), "--project", str(project),
                "--backend", "vertex", "--model", "gemini-test",
                "--backend-project", "cloud-project",
                "--backend-location", "global",
            ], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            configured = json.loads((project / "state/extraction.json").read_text())
            self.assertEqual(configured, {
                "backend": "vertex", "model": "gemini-test",
                "project": "cloud-project", "location": "global",
            })
            self.assertNotIn("credential", json.dumps(configured).lower())

    def test_invalid_init_config_writes_no_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus, project = root / "corpus", root / "survey"
            subprocess.run(
                [sys.executable, str(ROOT / "tests/make_fixture_corpus.py"),
                 str(corpus)], check=True, capture_output=True, text=True)
            proc = subprocess.run([
                sys.executable, str(SCRIPTS / "init.py"),
                "--corpus", str(corpus), "--project", str(project),
                "--backend", "vertex",
            ], capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertFalse(project.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
