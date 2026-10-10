import json
import os
import sys

# Export de documentation, aucun lien présigné n'est signé : la garde de démarrage
# REV-315 (S3_PUBLIC_ENDPOINT_URL vide) ne doit pas bloquer la génération (CI api-types-drift).
os.environ.setdefault("S3_PUBLIC_ENDPOINT_URL", "http://localhost:9000")

from app.main import create_app  # noqa: E402


def main(output_path: str) -> None:
    app = create_app()
    with open(output_path, "w") as f:
        json.dump(app.openapi(), f, indent=2, sort_keys=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
