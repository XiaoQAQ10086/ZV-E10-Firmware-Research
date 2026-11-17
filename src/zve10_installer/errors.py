"""Installer error types.

The categories mirror docs/safety.md: preflight problems are fixable; gate
failures and uncertain writes require stopping and preserving evidence.
"""


class InstallerError(Exception):
    """Base class for all installer errors."""


class PreflightError(InstallerError):
    """Environment or upstream checkout is not usable."""


class GateError(InstallerError):
    """A safety gate refused to advance the run."""

    def __init__(self, gate: str, detail: str) -> None:
        self.gate = gate
        self.detail = detail
        super().__init__(f"{gate}: {detail}")


class ActionError(InstallerError):
    """The upstream service returned an error or refused an action."""


class UnknownResponse(ActionError):
    """The upstream response did not match the expected schema."""


class SessionError(InstallerError):
    """A service session could not be started, used, or closed safely."""
