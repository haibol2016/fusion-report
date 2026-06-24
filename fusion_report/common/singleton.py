"""Singleton"""

from typing import Any


class Singleton(type):
    """Implementation of Singleton design pattern"""

    _instances: Any = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        """Implement singleton pattern by caching class instances.

        Returns the cached instance of the class if it exists, otherwise creates
        a new instance, caches it, and returns it. Subsequent calls return the
        same instance regardless of arguments.

        Args:
            *args: Positional arguments passed to the class constructor.
            **kwargs: Keyword arguments passed to the class constructor.

        Returns:
            The singleton instance of the class.
        """
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]
