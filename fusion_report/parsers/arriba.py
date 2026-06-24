"""Arriba module"""

from typing import Any, Dict, List, Tuple

from fusion_report.parsers.abstract_fusion import AbstractFusionTool


class Arriba(AbstractFusionTool):
    """Arriba tool parser."""

    def set_header(self, header: str, delimiter: str | None = "\t") -> None:
        """Parse and store the TSV header line.

        Args:
            header: Raw header string read from the Arriba output file.
            delimiter: Column separator; default ``"\\t"``.
        """
        self.header: List[str] = header.strip().split(delimiter)

    def parse_multiple(self, left_fusion: str, right_fusion: str, delimiter: str) -> List[str]:
        """Expand multi-gene Arriba entries into individual fusion pairs.

        Args:
            left_fusion: Left gene field, possibly delimited list.
            right_fusion: Right gene field, possibly delimited list.
            delimiter: Multi-gene delimiter (typically comma).

        Returns:
            List of ``GENE1--GENE2`` fusion names.
        """
        if delimiter not in left_fusion and delimiter not in right_fusion:
            return [f"{left_fusion}--{right_fusion}"]

        left: List[str] = [x.split("(")[0] for x in left_fusion.split(delimiter)]
        right: List[str] = [x.split("(")[0] for x in right_fusion.split(delimiter)]
        fusions = [f"{a}--{b}" for a in left for b in right]

        return fusions

    def parse(self, line: str, delimiter: str | None = "\t") -> List[Tuple[str, Dict[str, Any]]]:
        """Parse one data line from an Arriba output file.

        Args:
            line: A single tab-separated data line (not the header).
            delimiter: Column separator; default ``"\\t"``.

        Returns:
            List of ``(fusion_name, details)`` tuples.
        """
        col: List[str] = [x.strip() for x in line.split(delimiter)]
        fusions = self.parse_multiple(
            col[self.header.index("#gene1")], col[self.header.index("gene2")], ","
        )
        details: Dict[str, Any] = {
            "position": "#".join(
                [
                    col[self.header.index("breakpoint1")],
                    col[self.header.index("breakpoint2")],
                ]
            ),
            "reading-frame": col[self.header.index("reading_frame")],
            "type": col[self.header.index("type")],
            "split_reads1": col[self.header.index("split_reads1")],
            "split_reads2": col[self.header.index("split_reads2")],
            "discordant_mates": col[self.header.index("discordant_mates")],
            "coverage1": col[self.header.index("coverage1")],
            "coverage2": col[self.header.index("coverage2")],
            "confidence": col[self.header.index("confidence")],
        }

        return [(fusion, details) for fusion in fusions]
