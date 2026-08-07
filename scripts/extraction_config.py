"""Non-sensitive, project-local defaults for card extraction.

``state/extraction.json`` records which backend/model a survey intends to use.
It never stores credentials.  Command-line values override the file; backend
adapters may then fill provider-specific values from their normal environment
or Application Default Credentials.
"""

import json
from pathlib import Path

import backends


CONFIG_RELATIVE_PATH = Path("state/extraction.json")
FIELDS = ("backend", "model", "project", "location")


class ExtractionConfigError(ValueError):
    """A project extraction config is malformed or internally inconsistent."""


def config_path(project: Path) -> Path:
    return project / CONFIG_RELATIVE_PATH


def load_config(project: Path) -> dict:
    path = config_path(project)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ExtractionConfigError(
            f"{CONFIG_RELATIVE_PATH} does not parse: {exc}") from None
    if not isinstance(data, dict):
        raise ExtractionConfigError(
            f"{CONFIG_RELATIVE_PATH} must be a JSON object")
    unknown = sorted(set(data) - set(FIELDS))
    if unknown:
        raise ExtractionConfigError(
            f"{CONFIG_RELATIVE_PATH} has unknown fields: {', '.join(unknown)}")
    for name, value in data.items():
        if not isinstance(value, str) or not value.strip():
            raise ExtractionConfigError(
                f"{CONFIG_RELATIVE_PATH} field {name!r} must be a non-empty string")
    validate_config(data, require_pair=bool(data))
    return data


def save_config(project: Path, values: dict) -> Path:
    data = {name: values[name].strip() for name in FIELDS
            if isinstance(values.get(name), str) and values[name].strip()}
    validate_config(data, require_pair=True)
    path = config_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return path


def resolve(project: Path, overrides: dict | None = None) -> dict:
    """Resolve CLI overrides over project defaults and record each source."""
    stored = load_config(project)
    overrides = overrides or {}
    values, sources = {}, {}
    for name in FIELDS:
        value = overrides.get(name)
        if isinstance(value, str) and value.strip():
            values[name] = value.strip()
            sources[name] = "command_line"
        elif name in stored:
            values[name] = stored[name]
            sources[name] = "project_config"
    # Provider-specific defaults do not leak when the CLI deliberately switches
    # from a stored Vertex backend to another provider.
    if values.get("backend") != "vertex":
        for name in ("project", "location"):
            if sources.get(name) == "project_config" and not overrides.get(name):
                values.pop(name, None)
                sources.pop(name, None)
    validate_config(values)
    return {
        "path": str(config_path(project)),
        "exists": config_path(project).is_file(),
        "values": values,
        "sources": sources,
    }


def validate_config(data: dict, require_pair: bool = False) -> None:
    backend = data.get("backend")
    model = data.get("model")
    if backend and backend not in backends.KNOWN:
        raise ExtractionConfigError(
            f"unknown backend {backend!r}; expected one of: {', '.join(backends.KNOWN)}")
    if require_pair and (not backend or not model):
        raise ExtractionConfigError("backend and model must be configured together")
    if (data.get("project") or data.get("location")) and backend not in (None, "vertex"):
        raise ExtractionConfigError(
            "project and location are only valid for the vertex backend")
