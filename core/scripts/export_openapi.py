import json
import sys

from app.main import create_app


def main(output_path: str) -> None:
    app = create_app()
    with open(output_path, "w") as f:
        json.dump(app.openapi(), f, indent=2, sort_keys=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
