"""Test symbol canonicalization and HGNC resolution."""

import pytest
import sys

from fusion_report.common.symbol_resolver import SymbolResolver
from fusion_report.common.models.fusion import Fusion

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 12), reason="fusion-report requires Python >= 3.12"
)


class TestSymbolResolver:
    """Test HGNC symbol resolution and alias mapping."""

    def test_symbol_resolver_initialization(self):
        """Test that symbol resolver initializes with HGNC mappings."""
        resolver = SymbolResolver()
        assert resolver.aliases is not None
        assert len(resolver.aliases) > 0

    def test_approved_symbol_resolution(self):
        """Test that approved symbols resolve to themselves."""
        resolver = SymbolResolver()
        assert resolver.resolve("BRAF") == "BRAF"
        assert resolver.resolve("ALK") == "ALK"
        assert resolver.resolve("ROS1") == "ROS1"

    def test_case_insensitive_resolution(self):
        """Test that symbol resolution is case-insensitive."""
        resolver = SymbolResolver()
        assert resolver.resolve("braf") == "BRAF"
        assert resolver.resolve("Braf") == "BRAF"
        assert resolver.resolve("ERBB2") == "ERBB2"

    def test_alias_resolution(self):
        """Test that known aliases resolve to approved symbols."""
        resolver = SymbolResolver()
        # ERBB2 has alias "HER2"
        assert resolver.resolve("HER2") == "ERBB2"
        # ERBB1 is an alias for EGFR
        assert resolver.resolve("ERBB1") == "EGFR"
        # ALK is used as-is
        assert resolver.resolve("ALK") == "ALK"

    def test_unknown_symbol_handling(self):
        """Test that unknown symbols are returned as-is with warning."""
        resolver = SymbolResolver()
        # Unknown symbols should be returned as-is
        result = resolver.resolve("UNKNOWNGENE")
        assert result == "UNKNOWNGENE"

    def test_symbol_is_known(self):
        """Test checking if a symbol is known in HGNC mapping."""
        resolver = SymbolResolver()
        assert resolver.is_known("BRAF") is True
        assert resolver.is_known("HER2") is True  # alias
        assert resolver.is_known("UNKNOWNGENE") is False
        assert resolver.is_known("") is False

    def test_empty_symbol_handling(self):
        """Test handling of empty symbols."""
        resolver = SymbolResolver()
        assert resolver.resolve("") is None
        assert resolver.resolve(None) is None


class TestFusionSymbolCanonical:
    """Test Fusion model symbol canonicalization."""

    def test_fusion_canonical_name_approved_symbols(self):
        """Test fusion with approved HGNC symbols stays unchanged."""
        fusion = Fusion("BRAF--FGFR3")
        assert fusion.name == "BRAF--FGFR3"
        assert fusion.original_name == "BRAF--FGFR3"

    def test_fusion_canonical_name_with_aliases(self):
        """Test fusion names with known aliases get canonicalized."""
        fusion = Fusion("ERBB1--HER2")
        # ERBB1 should resolve to EGFR, HER2 to ERBB2
        assert fusion.name == "EGFR--ERBB2"
        assert fusion.original_name == "ERBB1--HER2"

    def test_fusion_canonical_name_mixed_case(self):
        """Test fusion names with mixed case get canonicalized."""
        fusion = Fusion("braf--FgfR3")
        assert fusion.name == "BRAF--FGFR3"

    def test_fusion_json_serialization_with_resolution(self):
        """Test that json serialization includes resolution metadata."""
        fusion = Fusion("ERBB1--HER2")
        json_data = fusion.json_serialize()
        assert json_data["Fusion"] == "EGFR--ERBB2"
        assert "Symbol Resolution" in json_data
        assert json_data["Symbol Resolution"] == "Resolved from 'ERBB1--HER2'"

    def test_fusion_json_serialization_no_resolution(self):
        """Test json serialization when no resolution occurs."""
        fusion = Fusion("BRAF--FGFR3")
        json_data = fusion.json_serialize()
        assert json_data["Fusion"] == "BRAF--FGFR3"
        assert "Symbol Resolution" not in json_data

    def test_fusion_with_invalid_format(self):
        """Test fusion names not in gene1--gene2 format."""
        fusion = Fusion("BRAF")
        assert fusion.name == "BRAF"
        assert fusion.original_name == "BRAF"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
