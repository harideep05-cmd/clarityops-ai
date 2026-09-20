"""Local operator bootstrap/recovery. Credentials go only to an exclusive private file."""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings  # noqa: E402
from app.errors import AppError  # noqa: E402
from app.identity import IdentityRegistry  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-workspace")
    create.add_argument("--name", required=True)
    recover = commands.add_parser("recover-owner")
    recover.add_argument("--workspace", required=True)
    for command in (create, recover):
        command.add_argument("--owner", required=True)
        command.add_argument(
            "--credential-file",
            required=True,
            help="New filename inside the configured data directory; never stdout",
        )
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    destination = Path(args.credential_file).resolve()
    if not destination.is_relative_to(settings.data_dir) or destination == settings.data_dir:
        parser.error("Credential files must be inside CLARITYOPS_DATA_DIR (ignored by Git by default).")
    if destination.exists():
        parser.error("Credential file already exists; refusing to overwrite it.")
    # All relative paths in --credential-file are relative to this command's cwd.
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.parent.chmod(0o700)
    created = False

    def deliver(result):
        nonlocal created
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")

    try:
        registry = IdentityRegistry(settings)
        if args.command == "create-workspace":
            result = registry.create_workspace(args.name, args.owner, deliver)
        else:
            result = registry.issue_owner(args.workspace, args.owner, deliver)
    except (AppError, OSError, sqlite3.Error) as exc:
        if created:
            destination.unlink(missing_ok=True)
        message = (
            exc.message
            if isinstance(exc, AppError)
            else "Workspace setup failed. Check storage and file permissions."
        )
        parser.exit(1, message + " No credential was published.\n")
    print(f"Workspace ID: {result['workspace']['id']}")
    print(
        "Credential saved privately. Open the requested file locally; never paste its contents into logs or chat."
    )
    print("Set CLARITYOPS_AUTH_MODE=members and restart the backend to use member access.")


if __name__ == "__main__":
    main()
