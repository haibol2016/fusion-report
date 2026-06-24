"""Base module for CustomModules"""

from typing import Any, Dict

from fusion_report.common.fusion_manager import FusionManager


class BaseModule:
    """Parent class for CustomModule."""

    def __init__(self, manager: FusionManager, params: Dict[str, Any]) -> None:
        """Store shared module inputs.

        Args:
            manager: Fusion manager with parsed/annotated fusion events.
            params: Module-specific runtime parameters.
        """
        self.manager: FusionManager = manager
        self.params: Dict[str, Any] = params
