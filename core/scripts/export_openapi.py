import json
import os
import sys


def main(output_path: str) -> None:
    # Export de documentation, aucun lien présigné n'est signé : la garde de démarrage
    # REV-315 (S3_PUBLIC_ENDPOINT_URL vide) ne doit pas bloquer la génération (CI
    # api-types-drift). Posé le temps de l'export seulement : un setdefault à l'import
    # fuirait dans toute la suite de tests qui importe ce module.
    added = "S3_PUBLIC_ENDPOINT_URL" not in os.environ
    if added:
        os.environ["S3_PUBLIC_ENDPOINT_URL"] = "http://localhost:9000"
    try:
        from app.main import create_app

        app = create_app()
        with open(output_path, "w") as f:
            json.dump(app.openapi(), f, indent=2, sort_keys=True)
    finally:
        if added:
            del os.environ["S3_PUBLIC_ENDPOINT_URL"]


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
