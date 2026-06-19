"""Gene symbol canonicalization and HGNC validation module."""

from typing import Dict, Optional, Set

from fusion_report.common.logger import Logger


class SymbolResolver:
    """Resolves and canonicalizes gene symbols using HGNC approved symbols and known aliases.
    
    Handles symbol normalization, alias resolution, and validation to reduce
    annotation mismatches due to HGNC symbol drift and version inconsistencies.
    """

    def __init__(self) -> None:
        """Initialize resolver with built-in HGNC mappings and aliases."""
        self.logger = Logger(__name__)
        # approved_symbol -> set of known aliases
        self.aliases: Dict[str, Set[str]] = self._load_aliases()
        # reverse lookup: alias -> approved symbol
        self.alias_to_approved: Dict[str, str] = {}
        for approved, aliases in self.aliases.items():
            for alias in aliases:
                self.alias_to_approved[alias.upper()] = approved

    def resolve(self, symbol: str) -> Optional[str]:
        """Resolve a gene symbol to its approved HGNC symbol.
        
        Args:
            symbol: Gene symbol to resolve
            
        Returns:
            Approved HGNC symbol if found, None if unresolved
        """
        if not symbol:
            return None
        
        symbol_upper = symbol.upper()
        
        # Direct match in approved symbols
        if symbol_upper in self.aliases:
            return symbol_upper
        
        # Check if it's a known alias
        if symbol_upper in self.alias_to_approved:
            approved = self.alias_to_approved[symbol_upper]
            if symbol_upper != approved:
                self.logger.debug(f"Resolved alias '{symbol}' to approved symbol '{approved}'")
            return approved
        
        # Unknown symbol
        self.logger.warning(f"Gene symbol '{symbol}' not found in HGNC mapping; using as-is")
        return symbol

    def is_known(self, symbol: str) -> bool:
        """Check if a symbol is in HGNC mapping (approved or alias).
        
        Args:
            symbol: Gene symbol to check
            
        Returns:
            True if symbol is known, False otherwise
        """
        if not symbol:
            return False
        symbol_upper = symbol.upper()
        return symbol_upper in self.aliases or symbol_upper in self.alias_to_approved

    def _load_aliases(self) -> Dict[str, Set[str]]:
        """Load HGNC approved symbols and known aliases.
        
        This uses a curated built-in mapping. In production, this could be:
        - Loaded from a database file
        - Fetched from HGNC API (https://www.genenames.org/api/)
        - Loaded from a JSON resource file
        
        Returns:
            Dictionary mapping approved symbols to sets of aliases
        """
        # Curated HGNC mappings (approved symbol -> aliases)
        # This is a subset for common cancer fusion genes and known historical aliases
        hgnc_map = {
            # Common fusion genes and their aliases
            "FGFR3": {"FGF3"},
            "TACC3": {"TACC", "TACC3"},
            "EGFR": {"ERBB1"},
            "ERBB2": {"HER2", "NEU"},
            "ERBB3": {"HER3"},
            "MET": {"HGFR"},
            "ALK": {"ALK"},
            "ROS1": {"ROS", "ROS1"},
            "RET": {"RET"},
            "BRAF": {"BRAF"},
            "KRAS": {"KRAS"},
            "NRAS": {"NRAS"},
            "HRAS": {"HRAS"},
            "TP53": {"P53", "LFS1"},
            "BRCA1": {"BRCA1"},
            "BRCA2": {"BRCA2"},
            "PTEN": {"PTEN"},
            "PIK3CA": {"PI3KCA"},
            "AKT1": {"AKT", "PKB", "PRKBA"},
            "CHEK2": {"CHK2"},
            "CDH1": {"CDHI"},
            "CDKN1A": {"P21", "CIP1", "WAF1"},
            "CDKN1B": {"P27", "KIP1"},
            "CDKN2A": {"P16", "INK4A"},
            "CDKN2B": {"P15", "INK4B"},
            "RB1": {"RB"},
            "NF1": {"NF1"},
            "NF2": {"NF2"},
            "VHL": {"VHL"},
            "BAP1": {"BAP1"},
            "ARID1A": {"BAF250A"},
            "PBRM1": {"BAF180"},
            "BRD4": {"BRD4"},
            "NUTM1": {"NUT"},
            "TMPRSS2": {"TMPRSS2"},
            "ETV1": {"ETV1", "ER81"},
            "ETV4": {"ETV4", "PEA3"},
            "ETV5": {"ETV5", "ERM"},
            "ERG": {"ERG"},
            "ETS1": {"ETS1"},
            "ETS2": {"ETS2"},
            "FEV": {"FEV", "ETV7"},
            "FLI1": {"FLI1"},
            "FLII": {"FLII"},
            "GABPA": {"GABPA", "NFXL1"},
            "SPDEF": {"SPDEF"},
            "EWSR1": {"EWSR1", "EWS"},
            "CD74": {"CD74"},
            "NPM1": {"NPM1"},
            "HOOK3": {"HOOK3"},
            "DUX4": {"DUX4"},
            "IGH": {"IGH", "IGHM"},
            "CRLF2": {"CRLF2"},
            "MALT1": {"MALT1"},
            "CIC": {"CIC"},
            "EML4": {"EML4"},
            "NTRK3": {"NTRK3", "TRKA"},
            "ETV6": {"ETV6", "TEL"},
            "FGFR1": {"FGFR1"},
            "FGFR2": {"FGFR2"},
            "FGFR4": {"FGFR4"},
            "PDGFRA": {"PDGFRA"},
            "PDGFRB": {"PDGFRB"},
            "FIP1L1": {"FIP1L1"},
            "SLC6A15": {"SLC6A15"},
            "MT-ATP8": {"ATP8"},
            "MT-ND2": {"ND2"},
            "AKAP9": {"AKAP9"},
            "IFT81": {"IFT81"},
            "NDRG4": {"NDRG4"},
            "GOPC": {"GOPC"},
        }
        
        # Ensure all symbols are uppercase
        return {sym.upper(): {alias.upper() for alias in aliases} for sym, aliases in hgnc_map.items()}
