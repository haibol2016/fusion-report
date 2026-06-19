"""Fusion Model"""

from typing import Any, Dict, List

from fusion_report.common.logger import Logger
from fusion_report.common.symbol_resolver import SymbolResolver


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

    _symbol_resolver: SymbolResolver | None = None

    def __init__(self, name: str) -> None:
        self.original_name: str = name.strip()
        self.name: str = self._canonicalize_fusion_name(self.original_name)
        self._score: Dict[str, Any] = {"score": 0, "explained": ""}
        self.dbs: List[str] = []
        self.tools: Dict[str, Any] = {}

    @classmethod
    def _get_symbol_resolver(cls) -> SymbolResolver:
        """Get or create shared symbol resolver instance."""
        if cls._symbol_resolver is None:
            cls._symbol_resolver = SymbolResolver()
        return cls._symbol_resolver

    def _canonicalize_fusion_name(self, name: str) -> str:
        """Canonicalize gene symbols in fusion name using HGNC mapping.
        
        Converts fusion name like "GENE1--GENE2" to canonical approved symbols.
        Logs warnings if symbols are not found in HGNC mapping.
        
        Args:
            name: Fusion name, typically format "GENE1--GENE2"
            
        Returns:
            Canonicalized fusion name with approved HGNC symbols
        """
        if "--" not in name:
            return name
        
        resolver = self._get_symbol_resolver()
        parts = name.split("--")
        if len(parts) != 2:
            return name
        
        gene1, gene2 = parts
        resolved_gene1 = resolver.resolve(gene1)
        resolved_gene2 = resolver.resolve(gene2)
        
        canonical_name = f"{resolved_gene1}--{resolved_gene2}"
        
        # Log if canonicalization changed the name
        if canonical_name != name:
            Logger(__name__).debug(f"Canonicalized fusion name from '{name}' to '{canonical_name}'")
        
        return canonical_name

    @property
    def score(self) -> float:
        return self._score["score"]

    @score.setter
    def score(self, value: float) -> None:
        self._score["score"] = float(value)

    @property
    def score_explained(self) -> str:
        """Returns explanation of how the FII was calculated."""
        return self._score["explained"]

    @score_explained.setter
    def score_explained(self, value: str) -> None:
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
        }
        
        # Add canonicalization note if name was resolved
        if self.original_name != self.name:
            json["Symbol Resolution"] = f"Resolved from '{self.original_name}'"

        return {**json, **self.tools}
