"""Star-Fusion Long Reads module."""

from typing import Any, Dict, List, Tuple

from fusion_report.parsers.abstract_fusion import AbstractFusionTool


class Ctat_lr_fusion(AbstractFusionTool):
    """Star-Fusion Long Reads (Nanopore or PacBio) tool parser."""

    def set_header(self, header: str, delimiter: str | None = "\t") -> None:
        """Parse and store the TSV header line.

        Args:
            header: Raw header string read from the CTAT-LR-Fusion output file.
            delimiter: Column separator; default ``"\\t"``.
        """
        self.header: List[str] = header.strip().split(delimiter)

    def parse(self, line: str, delimiter: str | None = "\t") -> List[Tuple[str, Dict[str, Any]]]:
        """Parse one data line from a CTAT-LR-Fusion output file.

        Extracts the fusion name, breakpoint positions, long-read count, FFPM,
        and Ensembl gene IDs.  The ``LeftGene`` / ``RightGene`` columns carry
        the format ``SYMBOL^ENSGID``; the Ensembl ID is extracted and version
        suffix is stripped.

        Args:
            line: A single tab-separated data line (not the header).
            delimiter: Column separator; default ``"\\t"``.

        Returns:
            List containing one ``(fusion_name, details)`` tuple.
        """
        col: List[str] = [x.strip() for x in line.split(delimiter)]
        fusion: str = f"{col[self.header.index('#FusionName')]}"
        # LeftGene / RightGene fields are formatted as "SYMBOL^ENSGID"
        left_gene_field = col[self.header.index("LeftGene")]
        right_gene_field = col[self.header.index("RightGene")]
        ensembl_id1 = left_gene_field.split("^")[1].split(".")[0] if "^" in left_gene_field else ""
        ensembl_id2 = right_gene_field.split("^")[1].split(".")[0] if "^" in right_gene_field else ""
        details: Dict[str, Any] = {
            "position": "#".join(
                [
                    col[self.header.index("LeftBreakpoint")],
                    col[self.header.index("RightBreakpoint")],
                ]
            ),
            "num_LR": int(col[self.header.index("num_LR")]),
            "ffmp": float(col[self.header.index("LR_FFPM")]),
            "ensembl_id1": ensembl_id1,
            "ensembl_id2": ensembl_id2,
        }

        return [(fusion, details)]
