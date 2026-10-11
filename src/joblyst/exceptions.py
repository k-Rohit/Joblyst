class CVReadError(ValueError):
    """Raised when a PDF cannot be read or yields no usable text."""

class LLMBudgetExceededError(RuntimeError):
    """Raised when a run would exceed ``MAX_LLM_CALLS_PER_RUN``."""
class PromptUnavailableError(RuntimeError):
    """Raised when a prompt can't be fetched from Opik, or is filled in with missing values."""
