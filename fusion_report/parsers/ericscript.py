"""EricScript module"""

from typing import Any, Dict, List, Tuple

from fusion_report.parsers.abstract_fusion import AbstractFusionTool


class Ericscript(AbstractFusionTool):
    """EricScript tool parser."""

    def set_header(self, header: str, delimiter: str | None = "\t") -> None:
        """Parse and store the TSV header line.

        Args:
            header: Raw header string read from the EricScript output file.
            delimiter: Column separator; default ``"\\t"``.
        """
        self.header: List[str] = header.strip().split(delimiter)

    def parse(self, line: str, delimiter: str | None = "\t") -> List[Tuple[str, Dict[str, Any]]]:
        """Parse one data line from an EricScript output file.

        Constructs the breakpoint position from the ``chr1``, ``Breakpoint1``,
        ``strand1`` / ``chr2``, ``Breakpoint2``, ``strand2`` columns.  Ensembl
        gene IDs are read from ``EnsemblGene1`` / ``EnsemblGene2`` with
        version suffixes stripped (e.g. ``ENSG00000068078.19`` →
        ``ENSG00000068078``).

        Args:
            line: A single tab-separated data line (not the header).
            delimiter: Column separator; default ``"\\t"``.

        Returns:
            List containing one ``(fusion_name, details)`` tuple.
        """
        col: List[str] = [x.strip() for x in line.split(delimiter)]
        fusion: str = "--".join(
            [col[self.header.index("GeneName1")], col[self.header.index("GeneName2")]]
        )
        details: Dict[str, Any] = {
            "position": (
                f"{col[self.header.index('chr1')]}:{col[self.header.index('Breakpoint1')]}:"
                f"{col[self.header.index('strand1')]}#{col[self.header.index('chr2')]}:"
                f"{col[self.header.index('Breakpoint2')]}:{col[self.header.index('strand2')]}"
            ),
            "discordant_reads": int(col[self.header.index("crossingreads")]),
            "junction_reads": int(col[self.header.index("spanningreads")]),
            "fusion_type": col[self.header.index("fusiontype")],
            "gene_expr1": float(col[self.header.index("GeneExpr1")]),
            "gene_expr2": float(col[self.header.index("GeneExpr2")]),
            "gene_expr_fusion": float(col[self.header.index("GeneExpr_Fused")]),
            "ensembl_id1": col[self.header.index("EnsemblGene1")].split(".")[0],
            "ensembl_id2": col[self.header.index("EnsemblGene2")].split(".")[0],
        }

        return [(fusion, details)]
