"""FusionCatcher module"""

from typing import Any, Dict, List, Tuple

from fusion_report.parsers.abstract_fusion import AbstractFusionTool


class Fusioncatcher(AbstractFusionTool):
    """FusionCatcher tool parser."""

    def set_header(self, header: str, delimiter: str | None = "\t") -> None:
        """Parse and store the TSV header line.

        Args:
            header: Raw header string read from the FusionCatcher output file.
            delimiter: Column separator; default ``"\\t"``.
        """
        self.header: List[str] = header.strip().split(delimiter)

    def parse(self, line: str, delimiter: str | None = "\t") -> List[Tuple[str, Dict[str, Any]]]:
        """Parse one data line from a FusionCatcher output file.

        Constructs the fusion name from the 5′ and 3′ gene symbol columns.
        Ensembl gene IDs are read from ``Gene_1_id(...)`` / ``Gene_2_id(...)``
        with version suffixes stripped (e.g. ``ENSG00000068078.19`` →
        ``ENSG00000068078``).

        Args:
            line: A single tab-separated data line (not the header).
            delimiter: Column separator; default ``"\\t"``.

        Returns:
            List containing one ``(fusion_name, details)`` tuple.
        """
        col: List[str] = [x.strip() for x in line.split(delimiter)]
        fusion: str = "--".join(
            [
                col[self.header.index("Gene_1_symbol(5end_fusion_partner)")],
                col[self.header.index("Gene_2_symbol(3end_fusion_partner)")],
            ]
        )
        details: Dict[str, Any] = {
            "position": "#".join(
                [
                    col[self.header.index("Fusion_point_for_gene_1(5end_fusion_partner)")],
                    col[self.header.index("Fusion_point_for_gene_2(3end_fusion_partner)")],
                ]
            ),
            "common_mapping_reads": int(col[self.header.index("Counts_of_common_mapping_reads")]),
            "spanning_pairs": int(col[self.header.index("Spanning_pairs")]),
            "spanning_unique_reads": int(col[self.header.index("Spanning_unique_reads")]),
            "longest_anchor": int(col[self.header.index("Longest_anchor_found")]),
            "fusion_type": col[self.header.index("Predicted_effect")].strip(),
            "ensembl_id1": col[self.header.index("Gene_1_id(5end_fusion_partner)")].split(".")[0],
            "ensembl_id2": col[self.header.index("Gene_2_id(3end_fusion_partner)")].split(".")[0],
        }

        return [(fusion, details)]
