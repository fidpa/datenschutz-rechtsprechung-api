"""System Collector Stub für MVP."""


class SystemCollector:
    """Basic system collector implementation."""

    def __init__(self, component_name: str = "system_collector"):
        self.component_name = component_name

    async def collect_system_metrics(self, context=None):
        """Collect system metrics."""
