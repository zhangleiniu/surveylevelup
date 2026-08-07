#!/usr/bin/env python3
"""Record non-sensitive project defaults for card extraction.

Credentials remain in the provider's normal credential store or environment.
This command writes only backend, exact model id, project id and location.
"""

import argparse

from common import add_project_arg, die, find_project, print_json
from extraction_config import ExtractionConfigError, save_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_project_arg(parser)
    parser.add_argument("--backend", required=True)
    parser.add_argument("--model", required=True, help="exact provider model id")
    parser.add_argument("--backend-project", dest="backend_project",
                        help="Google Cloud project id; Vertex only")
    parser.add_argument("--backend-location", dest="backend_location",
                        help="provider location; Vertex defaults to global")
    args = parser.parse_args()

    project = find_project(args.project)
    values = {
        "backend": args.backend,
        "model": args.model,
        "project": args.backend_project,
        "location": args.backend_location,
    }
    try:
        path = save_config(project, values)
    except ExtractionConfigError as exc:
        die(str(exc))
    print_json({
        "configured": str(path),
        "extraction": {k: v for k, v in values.items() if v},
        "credentials_stored": False,
        "next": "doctor.py --project <survey-project>",
    })


if __name__ == "__main__":
    main()
