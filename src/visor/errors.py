"""Exceptions raised by visor's high-level actions."""


class VisorError(Exception):
    """Base class for visor errors."""


class TextNotFound(VisorError):
    """The text was not visible on screen (after waiting, scrolling and fallbacks)."""

    def __init__(self, label, visible=None, message=None):
        self.label = label
        self.visible = list(visible or [])
        if message is None:
            shown = ", ".join(repr(t) for t in self.visible[:30])
            more = f" … (+{len(self.visible) - 30} more)" if len(self.visible) > 30 else ""
            message = f"Could not find {label!r} on screen. Visible text: [{shown}{more}]"
        super().__init__(message)


class ElementDisabled(VisorError):
    """The text was found but its button stayed disabled."""


class NavigationError(VisorError):
    """A page failed to load."""


class Skip(VisorError):
    """Raise inside a flow to skip the current target; run_flow records 'skipped:<reason>'."""

    def __init__(self, reason: str = "skipped"):
        self.reason = reason
        super().__init__(reason)


class RestartFlow(VisorError):
    """Raise inside a flow to hot-reload the flow module and retry the target."""
