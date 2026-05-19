"""Business Collector Stub für MVP."""


class BusinessCollector:
    """Basic business collector implementation."""

    def __init__(self, component_name: str = "business_collector"):
        self.component_name = component_name

    async def collect_business_event(self, action, feature, context=None):
        """Collect business event."""
