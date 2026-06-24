"""Gene symbol canonicalization and HGNC validation module."""

import csv
import gzip
import os
import re
import time
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Optional, Set

import requests

from fusion_report.common.logger import Logger


class SymbolResolver:
    """Resolves and canonicalizes gene symbols using HGNC approved symbols and known aliases.
    
    Handles symbol normalization, alias resolution, and validation to reduce
    annotation mismatches due to HGNC symbol drift and version inconsistencies.
    """

    HGNC_SNAPSHOT_VERSION = "dynamic:hgnc_complete_set"
    HGNC_COMPLETE_SET_URL = (
        "https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/"
        "hgnc_complete_set.txt"
    )
    CACHE_PATH = Path.home() / ".cache" / "fusion-report" / "hgnc_complete_set.txt"
    BUNDLED_HGNC_RESOURCE = "data/hgnc/hgnc_complete_set.txt.gz"
    HGNC_STRICT_ENV = "FUSION_REPORT_HGNC_STRICT"
    HGNC_BUNDLED_PATH_ENV = "FUSION_REPORT_HGNC_BUNDLED_PATH"
    HGNC_CONNECT_TIMEOUT_SEC = 15
    HGNC_READ_TIMEOUT_SEC = 90
    HGNC_RETRY_ATTEMPTS = 3
    HGNC_RETRY_DELAY_SEC = 2
    HGNC_READ_TIMEOUT_STEP_SEC = 60

    def __init__(self) -> None:
        """Initialize the resolver.

        Downloads the HGNC complete-set TSV, caches it locally, and builds
        three internal lookup indexes:

        * ``hgnc_records``        – HGNC ID → record dict
        * ``symbol_to_hgnc_ids`` – upper-cased symbol/alias → set of HGNC IDs
        * ``ensembl_to_hgnc_id`` – Ensembl gene ID (no version) → HGNC ID
        * ``entrez_to_hgnc_id``  – Entrez gene ID → HGNC ID
        """
        self.logger = Logger(__name__)
        # hgnc_id -> metadata {approved_symbol, aliases}
        self.hgnc_records: Dict[str, Dict[str, Any]] = self._load_hgnc_records()
        # symbol/alias -> possible hgnc_ids
        self.symbol_to_hgnc_ids: Dict[str, Set[str]] = {}
        for hgnc_id, record in self.hgnc_records.items():
            approved = str(record["approved_symbol"]).upper()
            aliases = {alias.upper() for alias in record["aliases"]}
            self.symbol_to_hgnc_ids.setdefault(approved, set()).add(hgnc_id)
            for alias in aliases:
                self.symbol_to_hgnc_ids.setdefault(alias, set()).add(hgnc_id)

        # ensembl_gene_id (no version) -> hgnc_id
        self.ensembl_to_hgnc_id: Dict[str, str] = {
            record["ensembl_gene_id"]: hgnc_id
            for hgnc_id, record in self.hgnc_records.items()
            if record.get("ensembl_gene_id")
        }
        # entrez_gene_id -> hgnc_id
        self.entrez_to_hgnc_id: Dict[str, str] = {
            record["entrez_id"]: hgnc_id
            for hgnc_id, record in self.hgnc_records.items()
            if record.get("entrez_id")
        }

    @property
    def aliases(self) -> Dict[str, Set[str]]:
        """Backward-compatible symbol-first view of the HGNC mapping.

        Returns a dict of ``{approved_symbol: set_of_aliases}`` built from
        ``hgnc_records``.  Used by legacy code and tests that pre-date the
        HGNC-ID-first redesign.

        Returns:
            Dict mapping each approved symbol to its full alias set.
        """
        return {
            str(record["approved_symbol"]).upper(): {
                alias.upper() for alias in record["aliases"]
            }
            for record in self.hgnc_records.values()
        }

    @staticmethod
    def strip_ensembl_version(ensembl_id: str | None) -> str | None:
        """Strip version suffix from an Ensembl gene ID.

        Ensembl gene IDs may be provided with a version suffix (e.g.
        ``ENSG00000068078.19``). This method removes everything after the
        first dot, returning the bare Ensembl ID.

        Args:
            ensembl_id: Ensembl gene ID, potentially with version suffix, or ``None``.

        Returns:
            The bare Ensembl ID (e.g. ``"ENSG00000068078"``), or ``None`` if
            input is ``None`` or empty. Returns the input unchanged if it does
            not contain a dot (defensive: most IDs should be bare already).
        """
        if not ensembl_id:
            return None
        bare_id = ensembl_id.split(".")[0].strip().upper()
        return bare_id if bare_id else None

    def resolve_by_ensembl_id(self, ensembl_id: str | None) -> Optional[str]:
        """Resolve a bare Ensembl gene ID (without version suffix) to an HGNC ID.

        The lookup is a direct O(1) dict lookup against the index built from
        the ``ensembl_gene_id`` column of the HGNC complete-set TSV.  Version
        suffixes (e.g. ``ENSG00000068078.18`` → ``ENSG00000068078``) are
        automatically stripped via :meth:`strip_ensembl_version`, making this
        method defensive against version numbers in the input.

        Args:
            ensembl_id: Ensembl gene ID, with or without version suffix,
                        e.g. ``"ENSG00000068078"`` or ``"ENSG00000068078.19"``.
                        ``None`` or empty string returns ``None``.

        Returns:
            The corresponding HGNC ID string (e.g. ``"HGNC:3689"``), or
            ``None`` if the Ensembl ID is not found in the mapping or is invalid.
        """
        if not ensembl_id:
            return None
        bare_id = self.strip_ensembl_version(ensembl_id)
        if not bare_id:
            return None
        return self.ensembl_to_hgnc_id.get(bare_id)

    def resolve_to_hgnc_id(
        self, symbol: str, chromosome_hint: str | None = None
    ) -> Optional[str]:
        """Resolve a gene symbol/alias to its stable HGNC ID."""
        if not symbol:
            return None

        symbol_upper = symbol.upper()
        candidates = self.symbol_to_hgnc_ids.get(symbol_upper, set())
        if not candidates:
            return None

        if len(candidates) == 1:
            return next(iter(candidates))

        normalized_chr = self._normalize_chromosome(chromosome_hint)
        if normalized_chr:
            chr_matched = {
                hgnc_id
                for hgnc_id in candidates
                if self._normalize_chromosome(self.hgnc_records[hgnc_id].get("chromosome"))
                == normalized_chr
            }
            if len(chr_matched) == 1:
                return next(iter(chr_matched))

        return None

    def resolve_with_metadata(
        self, symbol: str, chromosome_hint: str | None = None,
        ensembl_id: str | None = None,
        entrez_id: str | None = None,
    ) -> Dict[str, Any]:
        """Resolve a gene symbol and return a rich metadata dict.

        Resolution priority (highest to lowest):

        1. **Ensembl ID** – unambiguous direct lookup when *ensembl_id* is
           provided and present in the HGNC mapping.
          2. **Entrez ID** – unambiguous direct lookup when *entrez_id* is
              provided and present in the HGNC mapping.
          3. **Symbol + chromosome hint** – used to break ties when the same
           alias maps to multiple genes on different chromosomes.
          4. **Symbol alone** – returns the single matching HGNC record, or
           flags ambiguity when multiple records match.

        Args:
            symbol: Input gene symbol or alias (case-insensitive).
            chromosome_hint: Optional chromosome token from the breakpoint
                position, e.g. ``"chr7"`` or ``"7"``.
            ensembl_id: Optional bare Ensembl gene ID (version stripped),
                e.g. ``"ENSG00000068078"``.  When provided, tried first.
            entrez_id: Optional Entrez gene ID.  When provided and Ensembl
                lookup does not resolve, tried before symbol-only matching.

        Returns:
            A dict with the following keys:

            * ``input_symbol``       – original input string
            * ``resolved_symbol``    – approved HGNC symbol, or input uppercased
              if unresolvable
            * ``hgnc_id``            – HGNC ID if resolved, else ``None``
            * ``resolved_via_alias`` – ``True`` if the input was an alias
            * ``known``              – ``True`` if found in HGNC mapping
            * ``ambiguous``          – ``True`` if symbol maps to >1 HGNC IDs
            * ``chromosome_matched`` – ``True`` if chromosome hint resolved
              ambiguity
            * ``ensembl_matched``    – ``True`` if Ensembl ID resolved it
        """
        if not symbol:
            return {
                "input_symbol": symbol,
                "resolved_symbol": None,
                "hgnc_id": None,
                "resolved_via_alias": False,
                "known": False,
                "ambiguous": False,
                "chromosome_matched": False,
                "ensembl_matched": False,
            }

        symbol_upper = symbol.upper()
        candidates = self.symbol_to_hgnc_ids.get(symbol_upper, set())

        # Ensembl ID provides an unambiguous direct lookup — use it first.
        if ensembl_id:
            ensembl_resolved = self.resolve_by_ensembl_id(ensembl_id)
            if ensembl_resolved and ensembl_resolved in (candidates or {ensembl_resolved}):
                approved_symbol = str(
                    self.hgnc_records[ensembl_resolved]["approved_symbol"]
                ).upper()
                return {
                    "input_symbol": symbol,
                    "resolved_symbol": approved_symbol,
                    "hgnc_id": ensembl_resolved,
                    "resolved_via_alias": symbol_upper != approved_symbol,
                    "known": True,
                    "ambiguous": False,
                    "chromosome_matched": False,
                    "ensembl_matched": True,
                    "entrez_matched": False,
                }

        if entrez_id:
            entrez_resolved = self.resolve_by_entrez_id(entrez_id)
            if entrez_resolved and entrez_resolved in (candidates or {entrez_resolved}):
                approved_symbol = str(
                    self.hgnc_records[entrez_resolved]["approved_symbol"]
                ).upper()
                return {
                    "input_symbol": symbol,
                    "resolved_symbol": approved_symbol,
                    "hgnc_id": entrez_resolved,
                    "resolved_via_alias": symbol_upper != approved_symbol,
                    "known": True,
                    "ambiguous": False,
                    "chromosome_matched": False,
                    "ensembl_matched": False,
                    "entrez_matched": True,
                }

        hgnc_id = self.resolve_to_hgnc_id(symbol_upper, chromosome_hint)
        chromosome_matched = False
        ambiguous = len(candidates) > 1

        if ambiguous and chromosome_hint and hgnc_id:
            chromosome_matched = True

        if not candidates:
            self.logger.warning(
                "Gene symbol '%s' not found in HGNC mapping; using as-is", symbol
            )
            return {
                "input_symbol": symbol,
                "resolved_symbol": symbol_upper,
                "hgnc_id": None,
                "resolved_via_alias": False,
                "known": False,
                "ambiguous": False,
                "chromosome_matched": False,
                "ensembl_matched": False,
                "entrez_matched": False,
            }

        if not hgnc_id:
            self.logger.warning(
                "Gene symbol '%s' is ambiguous; add chromosome context to disambiguate",
                symbol,
            )
            return {
                "input_symbol": symbol,
                "resolved_symbol": symbol_upper,
                "hgnc_id": None,
                "resolved_via_alias": False,
                "known": True,
                "ambiguous": ambiguous,
                "chromosome_matched": False,
                "ensembl_matched": False,
                "entrez_matched": False,
            }

        approved_symbol = str(self.hgnc_records[hgnc_id]["approved_symbol"]).upper()
        resolved_via_alias = symbol_upper != approved_symbol

        if resolved_via_alias:
            self.logger.debug(
                "Resolved alias '%s' to '%s' (%s)",
                symbol,
                approved_symbol,
                hgnc_id,
            )

        return {
            "input_symbol": symbol,
            "resolved_symbol": approved_symbol,
            "hgnc_id": hgnc_id,
            "resolved_via_alias": resolved_via_alias,
            "known": True,
            "ambiguous": ambiguous,
            "chromosome_matched": chromosome_matched,
            "ensembl_matched": False,
            "entrez_matched": False,
        }

    def resolve_by_entrez_id(self, entrez_id: str | None) -> Optional[str]:
        """Resolve an Entrez gene ID to HGNC ID.

        Args:
            entrez_id: Entrez gene identifier as string, may be empty.

        Returns:
            HGNC ID if found, otherwise ``None``.
        """
        if not entrez_id:
            return None
        normalized = str(entrez_id).strip()
        if not normalized:
            return None
        return self.entrez_to_hgnc_id.get(normalized)

    def resolve(self, symbol: str) -> Optional[str]:
        """Resolve a gene symbol to its approved HGNC symbol.
        
        Args:
            symbol: Gene symbol to resolve
            
        Returns:
            Approved HGNC symbol if found, None if unresolved
        """
        metadata = self.resolve_with_metadata(symbol)
        return metadata["resolved_symbol"]

    def is_known(self, symbol: str) -> bool:
        """Check if a symbol is in HGNC mapping (approved or alias).
        
        Args:
            symbol: Gene symbol to check
            
        Returns:
            True if symbol is known, False otherwise
        """
        if not symbol:
            return False
        return symbol.upper() in self.symbol_to_hgnc_ids

    @staticmethod
    def _normalize_chromosome(value: str | None) -> str | None:
        """Normalize a raw chromosome token to the ``CHR*`` format.

        Accepts values like ``"7"``, ``"chr7"``, ``"CHR7"``, or a full
        breakpoint string ``"chr7:140787584:+"`` (leading token extracted
        via split on ``":"``).  Returns ``None`` for empty or un-parseable
        input.

        Args:
            value: Raw chromosome string from a breakpoint field or HGNC
                location column, e.g. ``"7"``, ``"chrX"``, ``"MT"``.

        Returns:
            Upper-cased ``CHR*`` token (e.g. ``"CHR7"``, ``"CHRX"``,
            ``"CHRMT"``), or ``None`` if input is empty.
        """
        if not value:
            return None

        head = value.split(":", maxsplit=1)[0].strip().upper()
        if not head:
            return None

        if head.startswith("CHR"):
            return head

        return f"CHR{head}"

    def _load_hgnc_records(self) -> Dict[str, Dict[str, Any]]:
        """Load and return HGNC records keyed by stable HGNC ID.

        Source priority is:

        1. Download from remote HGNC URL.
        2. Read local cache.
        3. Read bundled gzip snapshot from package resources.

        Strict failure is optional and controlled by ``FUSION_REPORT_HGNC_STRICT``.
        If strict mode is enabled and no source can be loaded, ``RuntimeError``
        is raised. Otherwise an empty mapping is returned and the resolver
        degrades gracefully (symbols are treated as unresolved/uppercased).

        Returns:
            Dict of ``{hgnc_id: record}`` where each record contains
            ``approved_symbol``, ``aliases``, ``chromosome``, and
            ``ensembl_gene_id``.

        Raises:
            RuntimeError: When strict mode is enabled and HGNC TSV cannot be
                loaded from any source.
        """
        tsv_text = self._download_hgnc_tsv()
        if tsv_text:
            self._write_cached_tsv(tsv_text)
            return self._parse_hgnc_records_or_empty(tsv_text, source_label="download")

        tsv_text = self._read_cached_tsv()
        if tsv_text:
            return self._parse_hgnc_records_or_empty(tsv_text, source_label="cache")

        tsv_text = self._read_bundled_tsv_gzip()
        if tsv_text:
            return self._parse_hgnc_records_or_empty(tsv_text, source_label="bundled-gzip")

        message = (
            "Failed to load HGNC complete set from all sources "
            "(download -> cache -> bundled gzip)"
        )
        if self._strict_hgnc_mode_enabled():
            raise RuntimeError(message)

        self.logger.warning(
            "%s; continuing in non-strict mode with empty HGNC mapping",
            message,
        )
        return {}

    def _parse_hgnc_records_or_empty(
        self, tsv_text: str, source_label: str
    ) -> Dict[str, Dict[str, Any]]:
        """Parse TSV text into records, returning empty mapping on parse failure."""

        try:
            records = self._parse_hgnc_tsv(tsv_text)
            if not records:
                self.logger.warning("Parsed HGNC TSV from %s had no usable records", source_label)
            else:
                self.logger.info("Loaded HGNC mapping from %s (%s records)", source_label, len(records))
            return records
        except Exception as ex:
            self.logger.warning("Failed to parse HGNC TSV from %s (%s)", source_label, ex)
            return {}

    @classmethod
    def _strict_hgnc_mode_enabled(cls) -> bool:
        """Return whether strict HGNC loading mode is enabled by environment."""
        value = os.environ.get(cls.HGNC_STRICT_ENV, "").strip().lower()
        return value in {"1", "true", "yes", "on"}

    def _download_hgnc_tsv(self) -> str | None:
        """Download the HGNC complete-set TSV with retry and progressive timeout.

        Makes up to :attr:`HGNC_RETRY_ATTEMPTS` attempts.  Each subsequent
        attempt adds :attr:`HGNC_READ_TIMEOUT_STEP_SEC` seconds to the read
        timeout to handle slow but eventually successful transfers.  A
        :attr:`HGNC_RETRY_DELAY_SEC` sleep is inserted between attempts.

        Returns:
            The raw TSV text on success, or ``None`` if all attempts fail.
        """
        for attempt in range(1, self.HGNC_RETRY_ATTEMPTS + 1):
            read_timeout = self.HGNC_READ_TIMEOUT_SEC + (
                attempt - 1
            ) * self.HGNC_READ_TIMEOUT_STEP_SEC
            timeout = (self.HGNC_CONNECT_TIMEOUT_SEC, read_timeout)
            try:
                response = requests.get(self.HGNC_COMPLETE_SET_URL, timeout=timeout)
                response.raise_for_status()
                return response.text
            except requests.RequestException as ex:
                self.logger.warning(
                    "HGNC download attempt %s/%s failed from %s (connect=%ss, read=%ss): %s",
                    attempt,
                    self.HGNC_RETRY_ATTEMPTS,
                    self.HGNC_COMPLETE_SET_URL,
                    self.HGNC_CONNECT_TIMEOUT_SEC,
                    read_timeout,
                    ex,
                )
                if attempt < self.HGNC_RETRY_ATTEMPTS:
                    time.sleep(self.HGNC_RETRY_DELAY_SEC)

        return None

    def _read_cached_tsv(self) -> str | None:
        """Read the locally cached HGNC TSV from :attr:`CACHE_PATH`.

        Returns:
            The cached TSV text if the file exists and is non-empty,
            otherwise ``None``.
        """
        try:
            if self.CACHE_PATH.exists() and self.CACHE_PATH.stat().st_size > 0:
                self.logger.info("Using cached HGNC TSV: %s", self.CACHE_PATH)
                return self.CACHE_PATH.read_text(encoding="utf-8")
        except OSError as ex:
            self.logger.debug("Unable to read HGNC cache: %s", ex)
        return None

    def _read_bundled_tsv_gzip(self) -> str | None:
        """Read bundled HGNC snapshot gzip from package resources.

        A custom bundled path can be provided via
        ``FUSION_REPORT_HGNC_BUNDLED_PATH`` for offline deployments.
        """
        override_path = os.environ.get(self.HGNC_BUNDLED_PATH_ENV)
        if override_path:
            try:
                path = Path(override_path).expanduser().resolve()
                if path.exists() and path.stat().st_size > 0:
                    self.logger.info("Using bundled HGNC override gzip: %s", path)
                    with gzip.open(path, "rt", encoding="utf-8") as handle:
                        return handle.read()
            except OSError as ex:
                self.logger.warning("Unable to read HGNC bundled override path (%s)", ex)

        try:
            resource = resources.files("fusion_report").joinpath(self.BUNDLED_HGNC_RESOURCE)
            if resource.is_file():
                self.logger.info(
                    "Using bundled HGNC gzip resource: %s", self.BUNDLED_HGNC_RESOURCE
                )
                with resource.open("rb") as raw, gzip.open(raw, "rt", encoding="utf-8") as handle:
                    return handle.read()
        except (FileNotFoundError, ModuleNotFoundError, OSError) as ex:
            self.logger.debug("Unable to read bundled HGNC gzip resource: %s", ex)

        return None

    def _write_cached_tsv(self, tsv_text: str) -> None:
        """Persist HGNC TSV content to :attr:`CACHE_PATH` for offline reuse.

        Creates parent directories if necessary.  Silently ignores filesystem
        errors (a missing cache is non-fatal; the next run will re-download).

        Args:
            tsv_text: Raw TSV content returned by :meth:`_download_hgnc_tsv`.
        """
        try:
            self.CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            self.CACHE_PATH.write_text(tsv_text, encoding="utf-8")
        except OSError as ex:
            self.logger.debug("Unable to write HGNC cache: %s", ex)

    def _parse_hgnc_tsv(self, tsv_text: str) -> Dict[str, Dict[str, Any]]:
        """Parse the HGNC complete-set TSV into the internal records format.

        Only rows with ``status == "Approved"`` are included.  Each record
        carries the approved symbol, its full alias set (``alias_symbol`` and
        ``prev_symbol`` fields, pipe-separated), the chromosome derived from
        the ``location`` column, and the bare Ensembl gene ID from
        ``ensembl_gene_id``.

        Args:
            tsv_text: Raw TSV text from the HGNC complete-set file.

        Returns:
            Dict of ``{hgnc_id: record}`` ready for use as
            :attr:`hgnc_records`.
        """
        records: Dict[str, Dict[str, Any]] = {}
        reader = csv.DictReader(tsv_text.splitlines(), delimiter="\t")

        for row in reader:
            status = (row.get("status") or "").strip()
            if status and status.lower() != "approved":
                continue

            hgnc_id = (row.get("hgnc_id") or "").strip().upper()
            symbol = (row.get("symbol") or "").strip().upper()
            if not hgnc_id or not symbol:
                continue

            aliases: Set[str] = {symbol}
            aliases.update(self._split_symbol_list(row.get("alias_symbol")))
            aliases.update(self._split_symbol_list(row.get("prev_symbol")))

            records[hgnc_id] = {
                "approved_symbol": symbol,
                "aliases": aliases,
                "chromosome": self._extract_chromosome_from_location(row.get("location")),
                "ensembl_gene_id": (row.get("ensembl_gene_id") or "").strip().upper() or None,
                "entrez_id": (row.get("entrez_id") or "").strip() or None,
            }

        return records

    @staticmethod
    def _split_symbol_list(raw: str | None) -> Set[str]:
        """Split a multi-value HGNC symbol field into a normalised set.

        HGNC stores ``alias_symbol`` and ``prev_symbol`` as pipe-separated
        lists (e.g. ``"ERBB1|PIG61"``).  Some older dump formats use commas.
        All tokens are stripped and upper-cased.

        Args:
            raw: Raw field value from the TSV row, or ``None``.

        Returns:
            Set of upper-cased symbol tokens.  Empty set for ``None`` or
            blank input.
        """
        if not raw:
            return set()

        # HGNC list fields are pipe-separated, some historical dumps include comma separators.
        chunks = re.split(r"\||,", raw)
        return {token.strip().upper() for token in chunks if token and token.strip()}

    @staticmethod
    def _extract_chromosome_from_location(location: str | None) -> str | None:
        """Extract a bare chromosome token from an HGNC ``location`` field.

        HGNC location strings follow the cytogenetic band format, e.g.
        ``"7q34"``, ``"Xp22.33"``, ``"mitochondria"``.  This method extracts
        only the chromosome identifier (digit(s), ``X``, ``Y``, or ``MT``).

        Args:
            location: Raw ``location`` column value from the HGNC TSV, or
                ``None``.

        Returns:
            Bare chromosome token (e.g. ``"7"``, ``"X"``, ``"MT"``), or
            ``None`` if the input is empty or un-parseable.
        """
        if not location:
            return None

        value = location.strip().upper()
        if value.startswith("MITOCHONDRIA"):
            return "MT"

        match = re.match(r"^(X|Y|MT|M|\d+)", value)
        if not match:
            return None

        token = match.group(1)
        return "MT" if token == "M" else token

