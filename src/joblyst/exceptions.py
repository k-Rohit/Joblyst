class CVReadError(ValueError):
    """Raised when a PDF cannot be read or yields no usable text."""

class LLMBudgetExceededError(RuntimeError):
    """Raised when a run would exceed ``MAX_LLM_CALLS_PER_RUN``."""