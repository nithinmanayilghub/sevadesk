# Writes the API's OpenAPI description to a file so the frontend can generate types from it.
import json
import sys

from app.main import app


def main() -> None:
    out_path = sys.argv[1]
    with open(out_path, "w", encoding="utf-8") as out_file:
        out_file.write(json.dumps(app.openapi(), indent=2))


if __name__ == "__main__":
    main()
