"""Cosmic Database"""

from typing import List

from fusion_report.common.db import Db
from fusion_report.common.singleton import Singleton
from fusion_report.settings import Settings


class CosmicDB(Db, metaclass=Singleton):
    """Implementation of Cosmic Database. All core functionality is handled by parent class."""

    def __init__(self, path: str) -> None:
        super().__init__(path, Settings.COSMIC["NAME"], Settings.COSMIC["SCHEMA"])

    def _get_table_name(self) -> str:
        """Dynamically find the cosmic fusion table name regardless of version."""
        tables = self.select(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'cosmic_fusion%'"
        )
        if not tables:
            return ""
        return tables[0]["name"]

    def get_all_fusions(self) -> List[str]:
        """Returns all fusions from database."""
        table_name = self._get_table_name()
        if not table_name:
            return []

        query: str = f'''SELECT DISTINCT
                            FIVE_PRIME_GENE_SYMBOL || '--' || THREE_PRIME_GENE_SYMBOL AS fusion_pair
                        FROM [{table_name}]
                        WHERE FIVE_PRIME_GENE_SYMBOL != "" AND THREE_PRIME_GENE_SYMBOL != ""'''
        res = self.select(query)

        return [x["fusion_pair"] for x in res if x["fusion_pair"]]
