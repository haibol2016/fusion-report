"""Pizzly module"""

from typing import Any, Dict, List, Tuple

from fusion_report.parsers.abstract_fusion import AbstractFusionTool


class Pizzly(AbstractFusionTool):
    """Pizzly tool parser."""

    def set_header(self, header: str, delimiter: str | None = "\t") -> None:
        """Parse and store the TSV header line.

        Args:
            header: Raw header string read from the Pizzly output file.
            delimiter: Column separator; default ``"\\t"``.
        """
        self.header: List[str] = header.strip().split(delimiter)

    def parse(self, line: str, delimiter: str | None = "\t") -> List[Tuple[str, Dict[str, Any]]]:
        """Parse one data line from a Pizzly output file.

        Pizzly does not report genomic breakpoint coordinates.  The Ensembl
        gene IDs (``geneA.id`` / ``geneB.id``) with their version suffixes
        stripped (e.g. ``ENSG00000068078.19`` → ``ENSG00000068078``) are stored
        in ``ensembl_id1`` / ``ensembl_id2`` so that HGNC canonicalization can
        use an unambiguous lookup.

        Args:
            line: A single tab-separated data line (not the header).
            delimiter: Column separator; default ``"\\t"``.

        Returns:
            List containing one ``(fusion_name, details)`` tuple.
        """
        col: List[str] = [x.strip() for x in line.split(delimiter)]
        fusion: str = "--".join(
            [col[self.header.index("geneA.name")], col[self.header.index("geneB.name")]]
        )
        details: Dict[str, Any] = {
            "pair_count": int(col[self.header.index("paircount")]),
            "split_count": int(col[self.header.index("splitcount")]),
            "ensembl_id1": col[self.header.index("geneA.id")].split(".")[0],
            "ensembl_id2": col[self.header.index("geneB.id")].split(".")[0],
        }

        return [(fusion, details)]
