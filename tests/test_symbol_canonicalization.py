"""Test symbol canonicalization and HGNC resolution."""

import pytest
import sys

from fusion_report.common.symbol_resolver import SymbolResolver
from fusion_report.common.models import fusion as fusion_module
from fusion_report.common.models.fusion import Fusion

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 12), reason="fusion-report requires Python >= 3.12"
)


@pytest.fixture(autouse=True)
def mock_dynamic_hgnc_source(monkeypatch):
    """Keep unit tests deterministic while exercising dynamic HGNC loading."""
    sample_tsv = (
        "hgnc_id\tsymbol\talias_symbol\tprev_symbol\tlocation\tstatus\n"
        "HGNC:1097\tBRAF\t\t\t7q34\tApproved\n"
        "HGNC:3689\tFGFR3\tFGF3\t\t4p16.3\tApproved\n"
        "HGNC:427\tALK\t\t\t2p23.2\tApproved\n"
        "HGNC:10261\tROS1\tROS\t\t6q22.1\tApproved\n"
        "HGNC:3236\tEGFR\tERBB1|PIG61\tERBB\t7p11.2\tApproved\n"
        "HGNC:3430\tERBB2\tHER2|NEU\tERBB2A\t17q12\tApproved\n"
        "HGNC:8031A\tNTRK1\tTRKA|NTRK\t\t1q23.1\tApproved\n"
        "HGNC:8030\tNTRK2\tTRKB|NTRK\t\t9q21.33\tApproved\n"
        "HGNC:8031\tNTRK3\tTRKC|NTRK\t\t15q25.3\tApproved\n"
    )

    monkeypatch.setattr(SymbolResolver, "_download_hgnc_tsv", lambda self: sample_tsv)
    monkeypatch.setattr(SymbolResolver, "_read_cached_tsv", lambda self: None)
    monkeypatch.setattr(SymbolResolver, "_write_cached_tsv", lambda self, text: None)
    # Reset module-level singleton so each test gets a fresh resolver from mocked download.
    monkeypatch.setattr(fusion_module, "_SYMBOL_RESOLVER", None)


class TestSymbolResolver:
    """Test HGNC symbol resolution and alias mapping."""

    def test_symbol_resolver_initialization(self):
        """Test that symbol resolver initializes with HGNC mappings."""
        resolver = SymbolResolver()
        assert resolver.hgnc_records is not None
        assert len(resolver.hgnc_records) > 0
        assert SymbolResolver.HGNC_SNAPSHOT_VERSION

    def test_symbol_resolve_to_hgnc_id(self):
        """Test that symbols and aliases resolve to stable HGNC IDs."""
        resolver = SymbolResolver()
        assert resolver.resolve_to_hgnc_id("EGFR") == "HGNC:3236"
        assert resolver.resolve_to_hgnc_id("ERBB1") == "HGNC:3236"

    def test_ambiguous_symbol_requires_chromosome_context(self):
        """Test ambiguous symbols are disambiguated only with chromosome hint."""
        resolver = SymbolResolver()
        # NTRK maps to multiple genes in this curated table.
        assert resolver.resolve_to_hgnc_id("NTRK") is None
        assert resolver.resolve_to_hgnc_id("NTRK", chromosome_hint="chr1") == "HGNC:8031A"
        assert resolver.resolve_to_hgnc_id("NTRK", chromosome_hint="9") == "HGNC:8030"
        assert resolver.resolve_to_hgnc_id("NTRK", chromosome_hint="chr15") == "HGNC:8031"

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
        metadata = resolver.resolve_with_metadata("ERBB1")
        assert metadata["hgnc_id"] == "HGNC:3236"
        assert metadata["resolved_via_alias"] is True
        # ALK is used as-is
        assert resolver.resolve("ALK") == "ALK"

    def test_unknown_symbol_handling(self):
        """Test that unknown symbols are returned as-is with warning."""
        resolver = SymbolResolver()
        # Unknown symbols should be returned as-is
        result = resolver.resolve("UNKNOWNGENE")
        assert result == "UNKNOWNGENE"
        metadata = resolver.resolve_with_metadata("UNKNOWNGENE")
        assert metadata["hgnc_id"] is None
        assert metadata["known"] is False

    def test_ambiguous_symbol_metadata(self):
        """Test ambiguity metadata with and without chromosome context."""
        resolver = SymbolResolver()
        metadata_no_chr = resolver.resolve_with_metadata("NTRK")
        assert metadata_no_chr["known"] is True
        assert metadata_no_chr["ambiguous"] is True
        assert metadata_no_chr["hgnc_id"] is None

        metadata_with_chr = resolver.resolve_with_metadata("NTRK", chromosome_hint="chr15")
        assert metadata_with_chr["known"] is True
        assert metadata_with_chr["ambiguous"] is True
        assert metadata_with_chr["chromosome_matched"] is True
        assert metadata_with_chr["hgnc_id"] == "HGNC:8031"

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

    def test_parse_hgnc_tsv(self, monkeypatch):
        """Test HGNC complete_set TSV parser for dynamic source support."""
        resolver = SymbolResolver()
        sample_tsv = (
            "hgnc_id\tsymbol\talias_symbol\tprev_symbol\tlocation\tstatus\n"
            "HGNC:3236\tEGFR\tERBB1|PIG61\tERBB\t7p11.2\tApproved\n"
            "HGNC:3430\tERBB2\tHER2|NEU\tERBB2A\t17q12\tApproved\n"
        )

        parsed = resolver._parse_hgnc_tsv(sample_tsv)
        assert parsed["HGNC:3236"]["approved_symbol"] == "EGFR"
        assert "ERBB1" in parsed["HGNC:3236"]["aliases"]
        assert "ERBB" in parsed["HGNC:3236"]["aliases"]
        assert parsed["HGNC:3236"]["chromosome"] == "7"

    def test_loads_from_bundled_gzip_when_download_and_cache_missing(self, monkeypatch):
        """Test fallback order uses bundled gzip after download/cache miss."""
        sample_tsv = (
            "hgnc_id\tsymbol\talias_symbol\tprev_symbol\tlocation\tstatus\n"
            "HGNC:3236\tEGFR\tERBB1|PIG61\tERBB\t7p11.2\tApproved\n"
        )
        monkeypatch.setattr(SymbolResolver, "_download_hgnc_tsv", lambda self: None)
        monkeypatch.setattr(SymbolResolver, "_read_cached_tsv", lambda self: None)
        monkeypatch.setattr(SymbolResolver, "_read_bundled_tsv_gzip", lambda self: sample_tsv)
        monkeypatch.delenv(SymbolResolver.HGNC_STRICT_ENV, raising=False)

        resolver = SymbolResolver()
        assert resolver.resolve("ERBB1") == "EGFR"

    def test_non_strict_mode_degrades_to_empty_mapping(self, monkeypatch):
        """Test non-strict mode does not raise when all HGNC sources are unavailable."""
        monkeypatch.setattr(SymbolResolver, "_download_hgnc_tsv", lambda self: None)
        monkeypatch.setattr(SymbolResolver, "_read_cached_tsv", lambda self: None)
        monkeypatch.setattr(SymbolResolver, "_read_bundled_tsv_gzip", lambda self: None)
        monkeypatch.delenv(SymbolResolver.HGNC_STRICT_ENV, raising=False)

        resolver = SymbolResolver()
        assert resolver.hgnc_records == {}
        assert resolver.resolve("BRAF") == "BRAF"

    def test_strict_mode_raises_when_all_sources_missing(self, monkeypatch):
        """Test strict mode raises RuntimeError when HGNC cannot be loaded."""
        monkeypatch.setattr(SymbolResolver, "_download_hgnc_tsv", lambda self: None)
        monkeypatch.setattr(SymbolResolver, "_read_cached_tsv", lambda self: None)
        monkeypatch.setattr(SymbolResolver, "_read_bundled_tsv_gzip", lambda self: None)
        monkeypatch.setenv(SymbolResolver.HGNC_STRICT_ENV, "1")

        with pytest.raises(RuntimeError, match="download -> cache -> bundled gzip"):
            SymbolResolver()


class TestFusionSymbolCanonical:
    """Test Fusion model symbol canonicalization."""

    def test_fusion_canonical_name_approved_symbols(self):
        """Test fusion with approved HGNC symbols stays unchanged."""
        fusion = Fusion("BRAF--FGFR3")
        assert fusion.name == "BRAF--FGFR3"
        assert fusion.original_name == "BRAF--FGFR3"
        assert fusion.gene1_hgnc_id == "HGNC:1097"
        assert fusion.gene2_hgnc_id == "HGNC:3689"

    def test_fusion_canonical_name_with_aliases(self):
        """Test fusion names with known aliases get canonicalized."""
        fusion = Fusion("ERBB1--HER2")
        # ERBB1 should resolve to EGFR, HER2 to ERBB2
        assert fusion.name == "EGFR--ERBB2"
        assert fusion.original_name == "ERBB1--HER2"
        assert fusion.gene1_hgnc_id == "HGNC:3236"
        assert fusion.gene2_hgnc_id == "HGNC:3430"

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
        assert json_data["HGNC IDs"]["5_prime"] == "HGNC:3236"
        assert json_data["HGNC IDs"]["3_prime"] == "HGNC:3430"
        assert json_data["HGNC Snapshot"] == SymbolResolver.HGNC_SNAPSHOT_VERSION
        assert "Symbol Resolution Details" in json_data

    def test_fusion_json_serialization_no_resolution(self):
        """Test json serialization when no resolution occurs."""
        fusion = Fusion("BRAF--FGFR3")
        json_data = fusion.json_serialize()
        assert json_data["Fusion"] == "BRAF--FGFR3"
        assert "Symbol Resolution" not in json_data
        assert json_data["HGNC IDs"]["5_prime"] == "HGNC:1097"
        assert json_data["HGNC IDs"]["3_prime"] == "HGNC:3689"

    def test_fusion_with_invalid_format(self):
        """Test fusion names not in gene1--gene2 format."""
        fusion = Fusion("BRAF")
        assert fusion.name == "BRAF"
        assert fusion.original_name == "BRAF"

    def test_fusion_uses_position_for_disambiguation(self):
        """Test fusion canonicalization uses breakpoint chromosomes to resolve ambiguity."""
        details = {"position": "chr15:1000:+#chr4:2000:-"}
        fusion = Fusion("NTRK--FGFR3", details)
        assert fusion.name == "NTRK3--FGFR3"
        assert fusion.gene1_hgnc_id == "HGNC:8031"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
