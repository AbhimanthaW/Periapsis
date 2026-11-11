class PipelineError(ValueError):
    """A rejected input, failed validation, or unavailable source."""


class ConfigurationError(PipelineError):
    pass


class CoordinateError(PipelineError):
    pass


class IntegrityError(PipelineError):
    pass
