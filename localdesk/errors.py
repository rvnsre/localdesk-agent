"""User-facing exception types."""


class LocalDeskError(Exception):
    """Base exception that can be shown to the user."""


class ConfigurationError(LocalDeskError):
    """Invalid or incomplete configuration."""


class ModelError(LocalDeskError):
    """Local model API error."""


class PlanError(LocalDeskError):
    """The model-generated plan could not be parsed or validated."""


class SafetyError(LocalDeskError):
    """The plan violates a safety rule."""


class AutomationError(LocalDeskError):
    """A desktop operation could not be completed."""
