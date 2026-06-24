"""Create databases from local files"""

import csv
import gzip
import os
import re
import shutil
import time
from argparse import Namespace
from typing import Any, Dict, List
from zipfile import ZipFile

import pandas as pd

from fusion_report.common.exceptions.db import DbException
from fusion_report.common.logger import Logger
from fusion_report.common.symbol_resolver import SymbolResolver
from fusion_report.data.cosmic import CosmicDB
from fusion_report.data.fusiongdb2 import FusionGDB2
from fusion_report.data.mitelman import MitelmanDB

LOG = Logger(__name__)


class CreateDB:
    """Build database files from local data files without downloading.

    Supports building any combination of COSMIC, Mitelman, and FusionGDB2
    databases from user-provided files.
    """

    def __init__(self, params: Namespace):
        """Initialize database creation from local files.

        Creates SQLite databases for any combination of COSMIC, Mitelman, and
        FusionGDB2 from user-provided local files. At least one database file
        must be provided. Creates output directory if needed, uses a temporary
        working directory for processing, and records creation timestamp.

        Args:
            params: Parsed arguments containing:
                - cosmic: Path to COSMIC TSV or gzipped file (optional)
                - mitelman: Path to Mitelman ZIP or data file (optional)
                - fusiongdb2: Path to FusionGDB2 TXT or CSV file (optional)
                - output: Output directory for .db files

        Raises:
            DbException: If no database files provided or if any database
                creation fails.
        """
        if not params.cosmic and not params.mitelman and not params.fusiongdb2:
            raise DbException(
                "At least one database file must be provided. "
                "Use --cosmic, --mitelman, and/or --fusiongdb2."
            )

        # Resolve paths to absolute before changing directory
        cosmic_path = os.path.abspath(params.cosmic) if params.cosmic else None
        mitelman_path = os.path.abspath(params.mitelman) if params.mitelman else None
        fusiongdb2_path = os.path.abspath(params.fusiongdb2) if params.fusiongdb2 else None
        output_path = os.path.abspath(params.output)

        if not os.path.exists(output_path):
            os.makedirs(output_path, 0o755)

        tmp_dir = os.path.join(output_path, "tmp_dir")
        if not os.path.exists(tmp_dir):
            os.mkdir(tmp_dir)
        os.chdir(tmp_dir)

        return_err: List[str] = []
        aggregate_stats: Dict[str, int] = {
            "total_pairs": 0,
            "mapped_pairs": 0,
            "total_symbols": 0,
            "mapped_symbols": 0,
            "strict_unambiguous_symbols": 0,
            "context_disambiguated_symbols": 0,
        }
        resolver = SymbolResolver()

        if cosmic_path:
            self.build_cosmic(cosmic_path, return_err, resolver, aggregate_stats)

        if mitelman_path:
            self.build_mitelman(
                mitelman_path,
                return_err,
                resolver,
                aggregate_stats,
                diagnostic_report_path=os.path.join(
                    output_path,
                    "mitelman_hgnc_diagnostic_report.txt",
                ),
            )

        if fusiongdb2_path:
            self.build_fusiongdb2(fusiongdb2_path, return_err, resolver, aggregate_stats)

        LOG.info(
            (
                "HGNC mapping summary [Combined]: "
                "symbols mapped=%s/%s (strict_unambiguous=%s, context_disambiguated=%s), "
                "pairs mapped=%s/%s"
            ),
            aggregate_stats["mapped_symbols"],
            aggregate_stats["total_symbols"],
            aggregate_stats["strict_unambiguous_symbols"],
            aggregate_stats["context_disambiguated_symbols"],
            aggregate_stats["mapped_pairs"],
            aggregate_stats["total_pairs"],
        )

        if return_err:
            for err in return_err:
                LOG.error(err)
            raise DbException(return_err)

        # Move db files and clean up
        self._clean()
        self._timestamp(output_path)
        LOG.info("Database creation finished")

    @staticmethod
    def build_cosmic(
        file_path: str,
        return_err: List[str],
        resolver: SymbolResolver,
        aggregate_stats: Dict[str, int] | None = None,
    ) -> None:
        """Build COSMIC database from a local TSV file (plain or gzipped).

        HGNC IDs are resolved from raw input rows before database setup.
        """
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"COSMIC file not found: {file_path}")

            data_file = file_path
            if file_path.endswith(".gz"):
                LOG.info(f"Decompressing {file_path}")
                decompressed = os.path.basename(file_path).rsplit(".gz", 1)[0]
                with gzip.open(file_path, "rb") as f_in, open(decompressed, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                data_file = decompressed

            # Rename to match expected table name
            target_file = "cosmic_fusion_v101_grch38.tsv"
            if os.path.basename(data_file) != target_file:
                shutil.copy(data_file, target_file)

            raw_pair_records = CreateDB._parse_cosmic_pair_records(target_file)
            resolved_pairs = CreateDB._resolve_hgnc_pairs(
                resolver,
                raw_pair_records,
                source_name="COSMIC",
                aggregate_stats=aggregate_stats,
            )

            db = CosmicDB(".")
            db.setup([target_file], delimiter="\t", skip_header=True)
            db.insert_hgnc_pairs(resolved_pairs)
            LOG.info("COSMIC database created successfully")
        except Exception as ex:
            return_err.append(f"COSMIC: {ex}")

    @staticmethod
    def build_mitelman(
        file_path: str,
        return_err: List[str],
        resolver: SymbolResolver,
        aggregate_stats: Dict[str, int] | None = None,
        diagnostic_report_path: str | None = None,
    ) -> None:
        """Build Mitelman database from a ZIP archive or extracted data file.

        HGNC IDs are resolved from raw input rows before database setup.
        """
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Mitelman file not found: {file_path}")

            if file_path.endswith(".zip"):
                LOG.info(f"Extracting {file_path}")
                with ZipFile(file_path, "r") as archive:
                    files = [
                        x for x in archive.namelist() if "MBCA.TXT.DATA" in x and "MACOSX" not in x
                    ]
                    archive.extractall()
            else:
                files = [file_path]

            raw_pair_records = CreateDB._parse_mitelman_pair_records(files)
            diagnostics: Dict[str, Any] = {
                "ambiguous_symbols": {},
                "non_unique_rows": [],
            }
            resolved_pairs = CreateDB._resolve_hgnc_pairs(
                resolver,
                raw_pair_records,
                source_name="Mitelman",
                aggregate_stats=aggregate_stats,
                diagnostics=diagnostics,
            )

            db = MitelmanDB(".")
            db.setup(files, delimiter="\t", skip_header=False, encoding="ISO-8859-1")
            db.insert_hgnc_pairs(resolved_pairs)
            if diagnostic_report_path:
                CreateDB._write_mitelman_diagnostic_report(
                    diagnostic_report_path,
                    diagnostics,
                )
            LOG.info("Mitelman database created successfully")
        except Exception as ex:
            return_err.append(f"Mitelman: {ex}")

    @staticmethod
    def build_fusiongdb2(
        file_path: str,
        return_err: List[str],
        resolver: SymbolResolver,
        aggregate_stats: Dict[str, int] | None = None,
    ) -> None:
        """Build FusionGDB2 database from a TSV or pre-processed CSV file.

        HGNC IDs are resolved from raw input rows before database setup.
        """
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"FusionGDB2 file not found: {file_path}")

            pair_records = []
            if file_path.endswith(".txt"):
                LOG.info(f"Processing FusionGDB2 file {file_path}")
                # Headerless 6-column TSV: col2 = 5'-gene, col4 = 3'-gene (0-indexed)
                df = pd.read_csv(file_path, sep="\t", header=None)
                df["fusion"] = df[2] + "--" + df[4]
                pair_records = [
                    {
                        "gene1_symbol": str(row[2]).strip(),
                        "gene2_symbol": str(row[4]).strip(),
                        "gene1_entrez": str(row[3]).strip(),
                        "gene2_entrez": str(row[5]).strip(),
                    }
                    for _, row in df.iterrows()
                ]
                csv_file = "fusionGDB2.csv"
                df["fusion"].to_csv(csv_file, header=False, index=False, sep=",", encoding="utf-8")
            elif file_path.endswith(".csv"):
                csv_file = file_path
                with open(csv_file, "r", encoding="utf-8") as resource:
                    for line in resource:
                        pair = [token.strip() for token in line.strip().split("--", maxsplit=1)]
                        if len(pair) == 2 and pair[0] and pair[1]:
                            pair_records.append(
                                {
                                    "gene1_symbol": pair[0],
                                    "gene2_symbol": pair[1],
                                    "gene1_entrez": None,
                                    "gene2_entrez": None,
                                }
                            )
            else:
                raise ValueError(
                    f"Unsupported FusionGDB2 file format: {file_path}. " "Expected .txt or .csv"
                )

            resolved_pairs = CreateDB._resolve_hgnc_pairs(
                resolver,
                pair_records,
                source_name="FusionGDB2",
                aggregate_stats=aggregate_stats,
            )

            db = FusionGDB2(".")
            db.setup([csv_file], delimiter=",", skip_header=False)
            db.insert_hgnc_pairs(resolved_pairs)
            LOG.info("FusionGDB2 database created successfully")
        except Exception as ex:
            return_err.append(f"FusionGDB2: {ex}")

    @staticmethod
    def _resolve_hgnc_pairs(
        resolver: SymbolResolver,
        pair_records: List[Dict[str, Any]],
        source_name: str | None = None,
        aggregate_stats: Dict[str, int] | None = None,
        diagnostics: Dict[str, Any] | None = None,
    ) -> List[tuple[str, str, str]]:
        """Resolve raw pair records into HGNC-ID tuples.

        Returns:
            List of (gene1_hgnc_id, gene2_hgnc_id, source_pair) tuples.
        """
        resolved: List[tuple[str, str, str]] = []
        total_pairs = 0
        mapped_pairs = 0
        total_symbols = 0
        mapped_symbols = 0
        strict_unambiguous_symbols = 0
        context_disambiguated_symbols = 0

        for record in pair_records:
            gene1 = str(record.get("gene1_symbol") or "").strip().upper()
            gene2 = str(record.get("gene2_symbol") or "").strip().upper()
            if not gene1 or not gene2:
                continue

            total_pairs += 1
            total_symbols += 2

            res1 = CreateDB._resolve_symbol_with_fallback_hints(
                resolver,
                gene1,
                chromosome_hint=record.get("gene1_chr"),
                chromosome_hints=record.get("gene1_chr_candidates"),
                ensembl_id=record.get("gene1_ensembl"),
                entrez_id=record.get("gene1_entrez"),
            )
            res2 = CreateDB._resolve_symbol_with_fallback_hints(
                resolver,
                gene2,
                chromosome_hint=record.get("gene2_chr"),
                chromosome_hints=record.get("gene2_chr_candidates"),
                ensembl_id=record.get("gene2_ensembl"),
                entrez_id=record.get("gene2_entrez"),
            )

            # Mitelman karyotype can encode chromosome translocation pairs;
            # use them jointly to disambiguate ambiguous symbols at pair level.
            res1, res2 = CreateDB._resolve_pair_with_karyotype_chr_pairs(
                resolver,
                gene1,
                gene2,
                res1,
                res2,
                chromosome_pairs=record.get("gene_chr_pairs"),
                gene1_ensembl=record.get("gene1_ensembl"),
                gene2_ensembl=record.get("gene2_ensembl"),
                gene1_entrez=record.get("gene1_entrez"),
                gene2_entrez=record.get("gene2_entrez"),
            )

            if diagnostics is not None:
                if not res1.get("hgnc_id") and res1.get("ambiguous"):
                    CreateDB._record_mitelman_ambiguous_symbol(diagnostics, resolver, gene1)
                if not res2.get("hgnc_id") and res2.get("ambiguous"):
                    CreateDB._record_mitelman_ambiguous_symbol(diagnostics, resolver, gene2)

                pair_debug = CreateDB._get_non_unique_pair_debug(
                    resolver,
                    gene1,
                    gene2,
                    chromosome_pairs=record.get("gene_chr_pairs"),
                    gene1_ensembl=record.get("gene1_ensembl"),
                    gene2_ensembl=record.get("gene2_ensembl"),
                    gene1_entrez=record.get("gene1_entrez"),
                    gene2_entrez=record.get("gene2_entrez"),
                )
                if pair_debug["non_unique_after_pair_hint"]:
                    diagnostics["non_unique_rows"].append(
                        {
                            "refno": record.get("refno", ""),
                            "invno": record.get("invno", ""),
                            "source_pair": f"{gene1}--{gene2}",
                            "chr_pairs": record.get("gene_chr_pairs", []),
                            "candidate_hgnc_pairs": pair_debug["candidate_hgnc_pairs"],
                            "karylong": record.get("karylong", ""),
                        }
                    )

            for res in (res1, res2):
                if not res["hgnc_id"]:
                    continue
                mapped_symbols += 1
                if res["ambiguous"]:
                    context_disambiguated_symbols += 1
                else:
                    strict_unambiguous_symbols += 1

            if not res1["hgnc_id"] or not res2["hgnc_id"]:
                continue

            mapped_pairs += 1
            resolved.append((res1["hgnc_id"], res2["hgnc_id"], f"{gene1}--{gene2}"))

        label = source_name or "Input"
        LOG.info(
            (
                "HGNC mapping summary [%s]: "
                "symbols mapped=%s/%s (strict_unambiguous=%s, context_disambiguated=%s), "
                "pairs mapped=%s/%s"
            ),
            label,
            mapped_symbols,
            total_symbols,
            strict_unambiguous_symbols,
            context_disambiguated_symbols,
            mapped_pairs,
            total_pairs,
        )

        if aggregate_stats is not None:
            aggregate_stats["total_pairs"] += total_pairs
            aggregate_stats["mapped_pairs"] += mapped_pairs
            aggregate_stats["total_symbols"] += total_symbols
            aggregate_stats["mapped_symbols"] += mapped_symbols
            aggregate_stats["strict_unambiguous_symbols"] += strict_unambiguous_symbols
            aggregate_stats["context_disambiguated_symbols"] += context_disambiguated_symbols

        return resolved

    @staticmethod
    def _resolve_symbol_with_fallback_hints(
        resolver: SymbolResolver,
        symbol: str,
        chromosome_hint: str | None = None,
        chromosome_hints: List[str] | None = None,
        ensembl_id: str | None = None,
        entrez_id: str | None = None,
    ) -> Dict[str, Any]:
        """Resolve one symbol and, if needed, retry with candidate chromosome hints.

        This is primarily used for Mitelman where karyotype information may
        provide a set of chromosomes but not a direct per-gene chromosome.
        """
        resolved = resolver.resolve_with_metadata(
            symbol,
            chromosome_hint=chromosome_hint,
            ensembl_id=ensembl_id,
            entrez_id=entrez_id,
        )
        if resolved["hgnc_id"]:
            return resolved

        hints = [str(h).strip() for h in (chromosome_hints or []) if str(h).strip()]
        if not hints:
            return resolved

        unique_matches: Dict[str, Dict[str, Any]] = {}
        for hint in hints:
            candidate = resolver.resolve_with_metadata(
                symbol,
                chromosome_hint=hint,
                ensembl_id=ensembl_id,
                entrez_id=entrez_id,
            )
            if candidate["hgnc_id"]:
                unique_matches[candidate["hgnc_id"]] = candidate

        if len(unique_matches) == 1:
            return next(iter(unique_matches.values()))

        return resolved

    @staticmethod
    def _resolve_pair_with_karyotype_chr_pairs(
        resolver: SymbolResolver,
        gene1: str,
        gene2: str,
        resolved1: Dict[str, Any],
        resolved2: Dict[str, Any],
        chromosome_pairs: List[tuple[str, str]] | None,
        gene1_ensembl: str | None = None,
        gene2_ensembl: str | None = None,
        gene1_entrez: str | None = None,
        gene2_entrez: str | None = None,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Resolve a gene pair using Mitelman karyotype chromosome pairs.

        Tries both orientations for each translocation chromosome pair, and
        accepts the result only when exactly one HGNC-ID pair is found.
        """
        if resolved1.get("hgnc_id") and resolved2.get("hgnc_id"):
            return resolved1, resolved2
        if not chromosome_pairs:
            return resolved1, resolved2

        unique_pair_matches: Dict[tuple[str, str], tuple[Dict[str, Any], Dict[str, Any]]] = {}
        for chr_a, chr_b in chromosome_pairs:
            for left_chr, right_chr in ((chr_a, chr_b), (chr_b, chr_a)):
                c1 = resolver.resolve_with_metadata(
                    gene1,
                    chromosome_hint=left_chr,
                    ensembl_id=gene1_ensembl,
                    entrez_id=gene1_entrez,
                )
                c2 = resolver.resolve_with_metadata(
                    gene2,
                    chromosome_hint=right_chr,
                    ensembl_id=gene2_ensembl,
                    entrez_id=gene2_entrez,
                )
                if c1.get("hgnc_id") and c2.get("hgnc_id"):
                    unique_pair_matches[(c1["hgnc_id"], c2["hgnc_id"])] = (c1, c2)

        if len(unique_pair_matches) == 1:
            return next(iter(unique_pair_matches.values()))
        return resolved1, resolved2

    @staticmethod
    def _get_non_unique_pair_debug(
        resolver: SymbolResolver,
        gene1: str,
        gene2: str,
        chromosome_pairs: List[tuple[str, str]] | None,
        gene1_ensembl: str | None = None,
        gene2_ensembl: str | None = None,
        gene1_entrez: str | None = None,
        gene2_entrez: str | None = None,
    ) -> Dict[str, Any]:
        """Return debugging info for pair-level chr-pair disambiguation."""
        if not chromosome_pairs:
            return {
                "non_unique_after_pair_hint": False,
                "candidate_hgnc_pairs": [],
            }

        unique_pair_matches: set[tuple[str, str]] = set()
        for chr_a, chr_b in chromosome_pairs:
            for left_chr, right_chr in ((chr_a, chr_b), (chr_b, chr_a)):
                c1 = resolver.resolve_with_metadata(
                    gene1,
                    chromosome_hint=left_chr,
                    ensembl_id=gene1_ensembl,
                    entrez_id=gene1_entrez,
                )
                c2 = resolver.resolve_with_metadata(
                    gene2,
                    chromosome_hint=right_chr,
                    ensembl_id=gene2_ensembl,
                    entrez_id=gene2_entrez,
                )
                if c1.get("hgnc_id") and c2.get("hgnc_id"):
                    unique_pair_matches.add((c1["hgnc_id"], c2["hgnc_id"]))

        return {
            "non_unique_after_pair_hint": len(unique_pair_matches) > 1,
            "candidate_hgnc_pairs": sorted(unique_pair_matches),
        }

    @staticmethod
    def _record_mitelman_ambiguous_symbol(
        diagnostics: Dict[str, Any], resolver: SymbolResolver, symbol: str
    ) -> None:
        """Record unresolved ambiguous symbol and its candidate HGNC records."""
        entries = diagnostics["ambiguous_symbols"]
        if symbol in entries:
            entries[symbol]["count"] += 1
            return

        candidate_ids = sorted(resolver.symbol_to_hgnc_ids.get(symbol, set()))
        candidates = []
        for hgnc_id in candidate_ids:
            record = resolver.hgnc_records.get(hgnc_id, {})
            candidates.append(
                {
                    "hgnc_id": hgnc_id,
                    "approved_symbol": record.get("approved_symbol", ""),
                    "chromosome": record.get("chromosome", ""),
                }
            )

        entries[symbol] = {
            "count": 1,
            "candidates": candidates,
        }

    @staticmethod
    def _write_mitelman_diagnostic_report(
        report_path: str, diagnostics: Dict[str, Any]
    ) -> None:
        """Write Mitelman ambiguity diagnostics to a text report."""
        ambiguous_symbols: Dict[str, Any] = diagnostics.get("ambiguous_symbols", {})
        non_unique_rows: List[Dict[str, Any]] = diagnostics.get("non_unique_rows", [])

        with open(report_path, "w", encoding="utf-8") as handle:
            handle.write(
                "# Mitelman HGNC Diagnostic Report\n\n"
                "## 1) Ambiguous symbols unresolved after karyotype hinting\n"
                "SYMBOL\tCOUNT\tCANDIDATES\n"
            )
            for symbol in sorted(ambiguous_symbols.keys()):
                entry = ambiguous_symbols[symbol]
                candidate_repr = ";".join(
                    [
                        f"{cand['hgnc_id']}|{cand['approved_symbol']}|chr:{cand['chromosome']}"
                        for cand in entry["candidates"]
                    ]
                )
                handle.write(f"{symbol}\t{entry['count']}\t{candidate_repr}\n")

            handle.write(
                "\n## 2) Rows with translocation chr-pairs available but still non-unique\n"
                "REFNO\tINVNO\tSOURCE_PAIR\tCHR_PAIRS\tCANDIDATE_HGNC_PAIRS\tKARYLONG\n"
            )
            for row in non_unique_rows:
                chr_pairs = ";".join([f"{a}-{b}" for a, b in row["chr_pairs"]])
                candidate_pairs = ";".join([f"{a}--{b}" for a, b in row["candidate_hgnc_pairs"]])
                karylong = str(row.get("karylong", "")).replace("\t", " ")
                handle.write(
                    f"{row['refno']}\t{row['invno']}\t{row['source_pair']}\t"
                    f"{chr_pairs}\t{candidate_pairs}\t{karylong}\n"
                )

        LOG.info("Mitelman diagnostic report written: %s", report_path)

    @staticmethod
    def _parse_cosmic_pair_records(file_path: str) -> List[Dict[str, Any]]:
        """Parse COSMIC TSV and extract pair records with chromosome hints."""
        records: List[Dict[str, Any]] = []
        with open(file_path, "r", encoding="utf-8") as resource:
            reader = csv.DictReader(resource, delimiter="\t")
            for row in reader:
                records.append(
                    {
                        "gene1_symbol": row.get("FIVE_PRIME_GENE_SYMBOL"),
                        "gene2_symbol": row.get("THREE_PRIME_GENE_SYMBOL"),
                        "gene1_chr": row.get("FIVE_PRIME_CHROMOSOME"),
                        "gene2_chr": row.get("THREE_PRIME_CHROMOSOME"),
                    }
                )
        return records

    @staticmethod
    def _parse_mitelman_pair_records(files: List[str]) -> List[Dict[str, Any]]:
        """Parse Mitelman MBCA files and extract fusion pair records.

        MBCA.TXT.DATA uses tab-delimited columns and stores fusion symbols in
        column 8 (0-based index 7) as token(s) separated by commas, with gene
        pairs represented as GENE1::GENE2.
        """
        records: List[Dict[str, Any]] = []
        for file_path in files:
            with open(file_path, "r", encoding="ISO-8859-1") as resource:
                for line in resource:
                    fields = line.rstrip("\n").split("\t")
                    if len(fields) < 8:
                        continue
                    raw = (fields[7] or "").strip()
                    if not raw or "::" not in raw:
                        continue
                    for token in [piece.strip() for piece in raw.split(",") if "::" in piece]:
                        pair = [part.strip() for part in token.split("::", maxsplit=1)]
                        if len(pair) != 2 or not pair[0] or not pair[1]:
                            continue

                        karylong = fields[11] if len(fields) > 11 else ""
                        chr_candidates = CreateDB._extract_karyotype_chromosome_hints(karylong)
                        chr_pairs = CreateDB._extract_karyotype_translocation_pairs(karylong)
                        records.append(
                            {
                                "gene1_symbol": pair[0],
                                "gene2_symbol": pair[1],
                                "gene1_chr_candidates": chr_candidates,
                                "gene2_chr_candidates": chr_candidates,
                                "gene_chr_pairs": chr_pairs,
                                "refno": fields[1] if len(fields) > 1 else "",
                                "invno": fields[2] if len(fields) > 2 else "",
                                "karylong": karylong,
                            }
                        )
        return records

    @staticmethod
    def _extract_karyotype_chromosome_hints(karylong: str | None) -> List[str]:
        """Extract chromosome tokens from Mitelman karyotype text.

        Example: ``t(4;14)(p16;q32),t(11;14)(q13;q32)`` -> ["4", "11", "14"]
        """
        if not karylong:
            return []

        chromosome_pattern = re.compile(r"^(?:\d+|X|Y|M|MT)$", re.IGNORECASE)
        chromosomes: set[str] = set()

        for chunk in re.findall(r"\(([^()]*)\)", karylong):
            for token in re.split(r"[;,/\s]+", chunk):
                if not token:
                    continue
                clean = token.strip().upper()
                if chromosome_pattern.match(clean):
                    chromosomes.add("MT" if clean == "M" else clean)

        return sorted(chromosomes, key=lambda c: (c not in {"X", "Y", "MT"}, c))

    @staticmethod
    def _extract_karyotype_translocation_pairs(karylong: str | None) -> List[tuple[str, str]]:
        """Extract translocation chromosome pairs from karyotype text.

        Example: ``t(4;14)(p16;q32),t(11;14)(q13;q32)`` ->
        ``[("4", "14"), ("11", "14")]``
        """
        if not karylong:
            return []

        chromosome_pattern = re.compile(r"^(?:\d+|X|Y|M|MT)$", re.IGNORECASE)
        pairs: List[tuple[str, str]] = []

        for chr_group in re.findall(r"t\(([^()]*)\)\([^()]*\)", karylong, flags=re.IGNORECASE):
            raw = [token.strip().upper() for token in chr_group.split(";") if token.strip()]
            if len(raw) != 2:
                continue
            if not chromosome_pattern.match(raw[0]) or not chromosome_pattern.match(raw[1]):
                continue
            left = "MT" if raw[0] == "M" else raw[0]
            right = "MT" if raw[1] == "M" else raw[1]
            pairs.append((left, right))

        # Preserve order while removing duplicates.
        seen: set[tuple[str, str]] = set()
        deduped: List[tuple[str, str]] = []
        for pair in pairs:
            if pair in seen:
                continue
            seen.add(pair)
            deduped.append(pair)
        return deduped

    @staticmethod
    def _clean() -> None:
        """Move generated .db files to output directory and clean up.

        Copies all .db files from the temporary working directory to the parent
        output directory, then removes the temporary directory tree.
        """
        import glob

        for temp in glob.glob("*.db"):
            shutil.copy(temp, "../")
        os.chdir("../")
        shutil.rmtree("tmp_dir")

    @staticmethod
    def _timestamp(output_dir: str) -> None:
        """Create a timestamp file recording database creation time.

        Writes the current date and time in \"YYYY-MM-DD/HH:MM\" format to
        DB-timestamp.txt in the output directory.

        Args:
            output_dir: Directory where DB-timestamp.txt will be written.
        """
        timestr = time.strftime("%Y-%m-%d/%H:%M")
        with open(os.path.join(output_dir, "DB-timestamp.txt"), "w") as text_file:
            text_file.write(timestr)
