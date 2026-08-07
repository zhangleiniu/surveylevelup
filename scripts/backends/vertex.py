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
import shutil
import subprocess
import sys
from pathlib import Path

from . import BackendError, GenerationResult, TransientError

# Gemini reasoning tokens share the output budget with the visible answer. Card
# extraction should not starve the answer merely to save a few tokens; the API
# bills actual usage, not this ceiling. Gemini 3.6 Flash accepts 65,536.
DEFAULT_MAX_TOKENS = 65_536

CLOUD_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
SKILL_ROOT = Path(__file__).resolve().parents[2]

# Vertex reports transient conditions as message text on a generic exception
# more often than as a typed error, so match on the text as well.
_TRANSIENT_MARKERS = ("429", "500", "502", "503", "504", "resource exhausted",
                      "deadline exceeded", "unavailable", "internal error",
                      "rate limit", "timeout", "overloaded")


def _load_sdk():
    from google import genai
    from google.genai import types
    return genai, types


def _load_adc():
    import google.auth
    return google.auth.default(scopes=[CLOUD_SCOPE])


def _gcloud_adc_available() -> bool:
    if not shutil.which("gcloud"):
        return False
    try:
        result = subprocess.run(
            ["gcloud", "auth", "application-default", "print-access-token"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _gcloud_default_project() -> str | None:
    if not shutil.which("gcloud"):
        return None
    try:
        result = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value and value != "(unset)" else None


def _gcloud_vertex_api_enabled(project: str) -> bool | None:
    """True/False when gcloud can answer; None when the check is unavailable."""
    if not project or not shutil.which("gcloud"):
        return None
    try:
        result = subprocess.run(
            ["gcloud", "services", "list", "--enabled", "--project", project,
             "--filter=config.name:aiplatform.googleapis.com",
             "--format=value(config.name)"],
            capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode:
        return None
    return "aiplatform.googleapis.com" in result.stdout.split()


def _resolve_project(explicit: str | None = None) -> tuple[str | None, str | None]:
    if explicit:
        return explicit, "argument_or_project_config"
    environmental = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if environmental:
        return environmental, "GOOGLE_CLOUD_PROJECT"
    try:
        _credentials, adc_project = _load_adc()
    except Exception:
        return None, None
    return (adc_project, "application_default_credentials") if adc_project else (None, None)


def preflight(model: str | None, project: str | None = None,
              location: str | None = None, project_source: str | None = None,
              location_source: str | None = None,
              check_service: bool = False, **opts) -> dict:
    """Verify local Vertex prerequisites without calling a model."""
    problems = []
    genai = None
    try:
        genai, _types = _load_sdk()
    except ImportError:
        problems.append({
            "code": "sdk_missing",
            "message": "the Vertex SDK is not installed",
            "fix": f"{sys.executable} -m pip install -r "
                   f"{SKILL_ROOT / 'requirements-vertex.txt'}",
        })

    credentials_available = False
    credential_source = None
    adc_project = None
    adc_error = None
    try:
        credentials, adc_project = _load_adc()
        credentials_available = credentials is not None
        credential_source = "google_auth_default"
    except Exception as exc:
        adc_error = exc
        credentials_available = _gcloud_adc_available()
        if credentials_available:
            credential_source = "gcloud_application_default_credentials"
    if not credentials_available:
        problems.append({
            "code": "credentials_missing",
            "message": "Application Default Credentials are unavailable"
                       + (f": {_brief(adc_error)}" if adc_error else ""),
            "fix": "gcloud auth application-default login",
        })

    gcloud_project = _gcloud_default_project()

    resolved_project = project or os.environ.get("GOOGLE_CLOUD_PROJECT") or adc_project
    if project:
        resolved_project_source = project_source or "argument_or_project_config"
    elif os.environ.get("GOOGLE_CLOUD_PROJECT"):
        resolved_project_source = "GOOGLE_CLOUD_PROJECT"
    elif adc_project:
        resolved_project_source = "application_default_credentials"
    else:
        resolved_project_source = None
    if not resolved_project:
        configure = (f"{sys.executable} {SKILL_ROOT / 'scripts' / 'configure_extraction.py'} "
                     f"--project SURVEY_PROJECT --backend vertex --model "
                     f"{model or 'EXACT_MODEL_ID'}")
        fix = (f"{configure} --backend-project {gcloud_project}, set "
               "GOOGLE_CLOUD_PROJECT, or set an ADC quota/default project"
               if gcloud_project else
               f"{configure} --backend-project GOOGLE_CLOUD_PROJECT_ID, set "
               "GOOGLE_CLOUD_PROJECT, or set an ADC quota/default project")
        problems.append({
            "code": "project_missing",
            "message": "no Google Cloud project was resolved",
            "detected_gcloud_default": gcloud_project,
            "fix": fix,
        })

    resolved_location = location or os.environ.get("GOOGLE_CLOUD_LOCATION") or "global"
    if location:
        resolved_location_source = location_source or "argument_or_project_config"
    elif os.environ.get("GOOGLE_CLOUD_LOCATION"):
        resolved_location_source = "GOOGLE_CLOUD_LOCATION"
    else:
        resolved_location_source = "default"
    if not model:
        problems.append({"code": "model_missing",
                         "message": "an exact Vertex model id is required"})

    service_enabled = (_gcloud_vertex_api_enabled(resolved_project)
                       if check_service and resolved_project else None)
    if service_enabled is False:
        problems.append({
            "code": "vertex_api_disabled",
            "message": "aiplatform.googleapis.com is not enabled for the resolved project",
            "fix": f"gcloud services enable aiplatform.googleapis.com "
                   f"--project {resolved_project}",
        })

    return {
        "backend": "vertex",
        "model": model,
        "ready": not problems,
        "sdk": {
            "package": "google-genai",
            "available": genai is not None,
            "version": getattr(genai, "__version__", None) if genai else None,
        },
        "authentication": {
            "method": "application_default_credentials",
            "available": credentials_available,
            "source": credential_source,
            "verified_with_model_call": False,
        },
        "service": {
            "name": "aiplatform.googleapis.com",
            "enabled": service_enabled,
            "checked": service_enabled is not None,
            "attempted": bool(check_service and resolved_project),
        },
        "resolved": {
            "project": resolved_project,
            "project_source": resolved_project_source,
            "location": resolved_location,
            "location_source": resolved_location_source,
            "gcloud_default_project_not_implicitly_used": gcloud_project,
        },
        "network_call": (credential_source == "gcloud_application_default_credentials"
                         or bool(check_service and resolved_project)),
        "paid_call": False,
        "problems": problems,
    }


def generate(prompt: str, model: str, max_tokens: int = DEFAULT_MAX_TOKENS,
             timeout: float = 600.0, project: str | None = None,
             location: str | None = None, **opts) -> GenerationResult:
    try:
        genai, types = _load_sdk()
    except ImportError:
        raise BackendError(
            "the Vertex SDK is not installed; "
            f"{sys.executable} -m pip install -r "
            f"{SKILL_ROOT / 'requirements-vertex.txt'}") from None

    project, _project_source = _resolve_project(project)
    if not project:
        raise BackendError(
            "no Google Cloud project was resolved; configure --backend-project, "
            "set GOOGLE_CLOUD_PROJECT, or set an ADC quota/default project")
    location = location or os.environ.get("GOOGLE_CLOUD_LOCATION", "global")

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
