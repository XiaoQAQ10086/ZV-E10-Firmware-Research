"""Typed confirmations.

Write-related confirmations have no default and no bypass. Callers must pass the
exact string they displayed to the user.
"""

from __future__ import annotations

import sys

from .errors import InstallerError


def confirm_exact(expected: str, prompt: str) -> None:
    print(prompt)
    print(f"Type exactly: {expected}")
    try:
        answer = input("> ").strip()
    except EOFError as exc:
        raise InstallerError("confirmation aborted: no input") from exc
    if answer != expected:
        raise InstallerError("confirmation did not match; nothing was changed")


def confirm_yes(prompt: str) -> None:
    print(prompt)
    try:
        answer = input("Type yes to continue: ").strip().lower()
    except EOFError as exc:
        raise InstallerError("confirmation aborted: no input") from exc
    if answer != "yes":
        raise InstallerError("not confirmed; nothing was changed")


def warn(message: str) -> None:
    print(message, file=sys.stderr)
