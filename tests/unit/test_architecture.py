import ast
import os
from pathlib import Path

import pytest


def test_application_does_not_import_infrastructure_or_ui():
    """
    Ensures that files in src/application/ do not import from infrastructure, ui, or specific external frameworks.
    """
    app_dir = Path("src/application")

    # Exceptions that are currently allowed for historical or pragmatic reasons.
    # Currently none for UI/Infrastructure.
    allowed_exceptions = []

    banned_modules = [
        "src.infrastructure",
        "src.ui",
        "src.composition",
        "PySide6",
        "fitz",
        "sqlite3",
    ]

    violations = []

    for root, _, files in os.walk(app_dir):
        for file in files:
            if not file.endswith(".py"):
                continue

            file_path = Path(root) / file

            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    tree = ast.parse(f.read(), filename=str(file_path))
                except SyntaxError:
                    continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        for banned in banned_modules:
                            if (alias.name == banned or alias.name.startswith(f"{banned}.")) and (
                                f"{file_path}:{alias.name}" not in allowed_exceptions
                            ):
                                violations.append(f"{file_path} imports {alias.name}")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    for banned in banned_modules:
                        if (node.module == banned or node.module.startswith(f"{banned}.")) and (
                            f"{file_path}:{node.module}" not in allowed_exceptions
                        ):
                            violations.append(f"{file_path} imports from {node.module}")

    if violations:
        pytest.fail("Architecture violations found in Application layer:\n" + "\n".join(violations))
