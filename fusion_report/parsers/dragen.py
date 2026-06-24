"""Dragen module"""

from typing import Any, Dict, List, Tuple

from fusion_report.parsers.abstract_fusion import AbstractFusionTool


class Dragen(AbstractFusionTool):
    """Dragen tool parser."""

    def set_header(self, header: str, delimiter: str | None = "\t") -> None:
        """Parse and store the TSV header line.

        Args:
            header: Raw header string read from the DRAGEN output file.
            delimiter: Column separator; default ``"\\t"``.
        """
        self.header: List[str] = header.strip().split(delimiter)

    def parse(self, line: str, delimiter: str | None = "\t") -> List[Tuple[str, Dict[str, Any]]]:
        """Parse one data line from a DRAGEN output file.

        Args:
            line: A single tab-separated data line (not the header).
            delimiter: Column separator; default ``"\\t"``.

        Returns:
            List containing one ``(fusion_name, details)`` tuple.
        """
        col: List[str] = [x.strip() for x in line.split(delimiter)]
        fusion: str = col[self.header.index("#FusionGene")]
        details: Dict[str, Any] = {
            "position": "#".join(
                [
                    col[self.header.index("LeftBreakpoint")],
                    col[self.header.index("RightBreakpoint")],
                ]
            ).replace("chr", ""),
            "score": int(col[self.header.index("Score")]),
        }

        return [(fusion, details)]
