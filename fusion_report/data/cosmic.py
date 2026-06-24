"""Cosmic Database"""

from typing import List

from fusion_report.common.db import Db
from fusion_report.common.singleton import Singleton
from fusion_report.settings import Settings


class CosmicDB(Db, metaclass=Singleton):
    """Implementation of Cosmic Database. All core functionality is handled by parent class."""

    def __init__(self, path: str) -> None:
        """Initialize COSMIC database connection.

        Args:
            path: Directory containing or receiving the SQLite database file.
        """
        super().__init__(path, Settings.COSMIC["NAME"], Settings.COSMIC["SCHEMA"])

    def get_all_fusions(self) -> List[str]:
        """Returns all fusions from database."""
        query: str = '''SELECT DISTINCT
                            FIVE_PRIME_GENE_SYMBOL || '--' || THREE_PRIME_GENE_SYMBOL AS fusion_pair
                        FROM cosmic_fusion_v101_grch38
                        WHERE FIVE_PRIME_GENE_SYMBOL != "" AND THREE_PRIME_GENE_SYMBOL != ""'''
        res = self.select(query)

        return [x["fusion_pair"] for x in res if x["fusion_pair"]]

    def insert_hgnc_pairs(self, pairs: List[tuple[str, str, str]]) -> None:
        """Insert pre-resolved HGNC pair tuples into the index table."""
        self.execute(
            """CREATE TABLE IF NOT EXISTS hgnc_pairs (
                   gene1_hgnc_id VARCHAR(32) NOT NULL,
                   gene2_hgnc_id VARCHAR(32) NOT NULL,
                   source_pair VARCHAR(255) NOT NULL,
                   UNIQUE(gene1_hgnc_id, gene2_hgnc_id, source_pair)
               )"""
        )

        if pairs:
            self.connection.executemany(
                """INSERT OR IGNORE INTO hgnc_pairs
                   (gene1_hgnc_id, gene2_hgnc_id, source_pair)
                   VALUES (?, ?, ?)""",
                pairs,
            )
            self.connection.commit()

    def get_all_hgnc_pairs(self) -> List[str]:
        """Return distinct HGNC ID fusion pairs if index exists."""
        exists = self.select(
            """SELECT name FROM sqlite_master
               WHERE type='table' AND name='hgnc_pairs'"""
        )
        if not exists:
            return []

        rows = self.select(
            """SELECT DISTINCT gene1_hgnc_id || '--' || gene2_hgnc_id AS hgnc_pair
               FROM hgnc_pairs"""
        )
        return [row["hgnc_pair"] for row in rows if row.get("hgnc_pair")]
