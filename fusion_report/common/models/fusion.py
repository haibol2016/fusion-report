"""Fusion Model"""

from typing import Any, Dict, List

from fusion_report.common.logger import Logger
from fusion_report.common.symbol_resolver import SymbolResolver

# Module-level singleton so HGNC TSV is downloaded exactly once per process.
_SYMBOL_RESOLVER: SymbolResolver | None = None


def _get_shared_resolver() -> SymbolResolver:
    """Return the process-level singleton SymbolResolver.

    Constructs the resolver on first call (triggering the HGNC download) and
    caches it in the module-level ``_SYMBOL_RESOLVER`` variable.  All
    ``Fusion`` instances share this resolver so the download occurs at most
    once per process.

    Returns:
        The shared :class:`~fusion_report.common.symbol_resolver.SymbolResolver`
        instance.
    """
    global _SYMBOL_RESOLVER
    if _SYMBOL_RESOLVER is None:
        _SYMBOL_RESOLVER = SymbolResolver()
    return _SYMBOL_RESOLVER


class Fusion:
    """Represents all required properties defining a fusion between two genes.

    Attributes:
        name: Fusion name (canonical HGNC symbols)
        original_name: Original fusion name as reported by detection tool
        score: Fusion Indication Index, attributes: `score` and `explained`
        dbs: List of databases where fusion was found
        tools: List of tools which detected fusion
        symbol_resolver: Shared symbol resolver for canonicalization
    """

    def __init__(self, name: str, details: Dict[str, Any] | None = None) -> None:
        """Create a Fusion instance and canonicalize the gene-pair name.

        Args:
            name: Raw fusion name as reported by the detection tool, in
                ``GENE1--GENE2`` format.
            details: Optional parser details dict.  Used to extract breakpoint
                position (for unique page title / deduplication) and Ensembl
                gene IDs (for unambiguous HGNC symbol canonicalization).
        """
        self.original_name: str = name.strip()
        self.gene1_hgnc_id: str | None = None
        self.gene2_hgnc_id: str | None = None
        self.symbol_resolution_notes: List[str] = []
        self.position: str | None = (details or {}).get("position") or None
        self.name: str = self._canonicalize_fusion_name(self.original_name, details)
        self._score: Dict[str, Any] = {"score": 0, "explained": ""}
        self.dbs: List[str] = []
        self.tools: Dict[str, Any] = {}

    def _canonicalize_fusion_name(
        self, name: str, details: Dict[str, Any] | None = None
    ) -> str:
        """Canonicalize gene symbols in fusion name using HGNC mapping.
        
        Converts fusion name like "GENE1--GENE2" to canonical approved symbols.
        Logs warnings if symbols are not found in HGNC mapping.
        
        Args:
            name: Fusion name, typically format "GENE1--GENE2"
            details: Optional parser details dict containing a 'position' key used
                     to extract chromosome hints for ambiguous symbol disambiguation.

        Returns:
            Canonicalized fusion name with approved HGNC symbols
        """
        if "--" not in name:
            return name
        
        resolver = _get_shared_resolver()
        parts = name.split("--")
        if len(parts) != 2:
            return name

        left_chr, right_chr = self._extract_chromosome_hints(details)
        ensembl_id1, ensembl_id2 = self._extract_ensembl_ids(details)
        
        gene1, gene2 = parts
        resolved_gene1 = resolver.resolve_with_metadata(
            gene1, chromosome_hint=left_chr, ensembl_id=ensembl_id1
        )
        resolved_gene2 = resolver.resolve_with_metadata(
            gene2, chromosome_hint=right_chr, ensembl_id=ensembl_id2
        )

        self.gene1_hgnc_id = resolved_gene1["hgnc_id"]
        self.gene2_hgnc_id = resolved_gene2["hgnc_id"]

        if resolved_gene1["resolved_via_alias"]:
            self.symbol_resolution_notes.append(
                f"{gene1} -> {resolved_gene1['resolved_symbol']} ({resolved_gene1['hgnc_id']})"
            )
        if resolved_gene2["resolved_via_alias"]:
            self.symbol_resolution_notes.append(
                f"{gene2} -> {resolved_gene2['resolved_symbol']} ({resolved_gene2['hgnc_id']})"
            )

        if not resolved_gene1["known"]:
            self.symbol_resolution_notes.append(f"Unresolved symbol: {gene1}")
        elif resolved_gene1["ambiguous"] and not (
            resolved_gene1["chromosome_matched"] or resolved_gene1.get("ensembl_matched")
        ):
            self.symbol_resolution_notes.append(
                f"Ambiguous symbol not disambiguated by chromosome: {gene1}"
            )
        if not resolved_gene2["known"]:
            self.symbol_resolution_notes.append(f"Unresolved symbol: {gene2}")
        elif resolved_gene2["ambiguous"] and not (
            resolved_gene2["chromosome_matched"] or resolved_gene2.get("ensembl_matched")
        ):
            self.symbol_resolution_notes.append(
                f"Ambiguous symbol not disambiguated by chromosome: {gene2}"
            )
        
        sym1 = resolved_gene1["resolved_symbol"] or gene1.upper()
        sym2 = resolved_gene2["resolved_symbol"] or gene2.upper()
        canonical_name = f"{sym1}--{sym2}"

        # Log if canonicalization changed the name
        if canonical_name != name:
            Logger(__name__).debug(
                "Canonicalized fusion name from '%s' to '%s'", name, canonical_name
            )

        return canonical_name

    @staticmethod
    def _extract_chromosome_hints(
        details: Dict[str, Any] | None,
    ) -> tuple[str | None, str | None]:
        """Extract left- and right-gene chromosome hints from the position field.

        The ``position`` value stored by most parsers uses the format
        ``"LEFT_CHR:pos:strand#RIGHT_CHR:pos:strand"``.  This method splits on
        ``"#"`` and extracts the leading token (chromosome) from each half.

        Args:
            details: Parser details dict.  ``None`` or a dict without a
                ``"position"`` key returns ``(None, None)``.

        Returns:
            ``(left_chromosome, right_chromosome)`` tuple.  Either element
            may be ``None`` when the position string is absent or malformed.
        """
        if not details:
            return (None, None)

        position = details.get("position")
        if not isinstance(position, str) or "#" not in position:
            return (None, None)

        left_raw, right_raw = position.split("#", maxsplit=1)
        left_chr = left_raw.split(":", maxsplit=1)[0].strip() if left_raw else None
        right_chr = right_raw.split(":", maxsplit=1)[0].strip() if right_raw else None
        return (left_chr, right_chr)

    @staticmethod
    def _extract_ensembl_ids(
        details: Dict[str, Any] | None,
    ) -> tuple[str | None, str | None]:
        """Extract version-stripped Ensembl gene IDs from parser details.

        Parsers that provide Ensembl IDs store them under the keys
        ``"ensembl_id1"`` (5′ gene) and ``"ensembl_id2"`` (3′ gene). This
        method retrieves them and ensures version suffixes are removed via
        :meth:`~fusion_report.common.symbol_resolver.SymbolResolver.strip_ensembl_version`,
        making this method defensive: if a parser forgets to strip versions,
        they will be removed here.

        Args:
            details: Parser details dict, or ``None``.

        Returns:
            ``(ensembl_id1, ensembl_id2)`` tuple.  Either element is ``None``
            when the key is absent or the value is empty after version stripping.
        """
        if not details:
            return (None, None)
        
        resolver = _get_shared_resolver()
        id1 = resolver.strip_ensembl_version(details.get("ensembl_id1"))
        id2 = resolver.strip_ensembl_version(details.get("ensembl_id2"))
        return (id1, id2)

    @property
    def page_title(self) -> str:
        """Unique display title for report pages.

        When a position is known, it is appended so that two events with the
        same gene pair but different breakpoints produce distinct page titles
        and therefore distinct HTML filenames.
        """
        if self.position:
            # Sanitize for display: keep it readable but unambiguous
            return f"{self.name} [{self.position}]"
        return self.name

    @property
    def score(self) -> float:
        """Return the computed Fusion Indication Index (FII) score."""
        return self._score["score"]

    @score.setter
    def score(self, value: float) -> None:
        """Set the computed Fusion Indication Index score."""
        self._score["score"] = float(value)

    @property
    def score_explained(self) -> str:
        """Returns explanation of how the FII was calculated."""
        return self._score["explained"]

    @score_explained.setter
    def score_explained(self, value: str) -> None:
        """Set the textual explanation of the FII score formula."""
        self._score["explained"] = value

    def add_tool(self, tool: str, details: Dict[str, Any]) -> None:
        """Add new fusion tool to the list."""
        if tool and tool not in self.tools.keys():
            self.tools[tool] = details
        else:
            Logger(__name__).debug("Tool %s already in list or empty", tool)

    def add_db(self, database: str) -> None:
        """Add new database to the list."""
        if database and database not in self.dbs:
            self.dbs.append(database)
        else:
            Logger(__name__).debug("Database %s already in list or empty", database)

    def json_serialize(self) -> Dict[str, Any]:
        """Helper serialization method for templating engine.
        
        Includes canonicalization metadata if the fusion name was resolved
        from an alias or deprecated symbol.
        """
        json: Dict[str, Any] = {
            "Fusion": self.name,
            "Databases": self.dbs,
            "Fusion Indication Index (FII)": self.score,
            "Explained FII": self.score_explained,
            "HGNC Snapshot": SymbolResolver.HGNC_SNAPSHOT_VERSION,
        }

        if self.gene1_hgnc_id or self.gene2_hgnc_id:
            json["HGNC IDs"] = {
                "5_prime": self.gene1_hgnc_id,
                "3_prime": self.gene2_hgnc_id,
            }
        
        # Add canonicalization note if name was resolved
        if self.original_name != self.name:
            json["Symbol Resolution"] = f"Resolved from '{self.original_name}'"
        if self.symbol_resolution_notes:
            json["Symbol Resolution Details"] = self.symbol_resolution_notes

        return {**json, **self.tools}
