"""Error Collector Stub für MVP."""


class ErrorCollector:
    """Basic error collector implementation."""

    def __init__(self, component_name: str = "error_collector"):
        self.component_name = component_name

    async def collect_error(self, error, context=None):
        """Collect error event."""
