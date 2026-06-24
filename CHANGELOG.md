# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Fixed packaging metadata in `setup.py` by correcting `package_data` entries so `arguments.json`, SQL schemas, and templates are included reliably in package builds.
- Fixed package version metadata in `setup.py` by setting `version="4.1.2"` so built wheels no longer default to `0.0.0`.
- Fixed database enrichment mapping in `fusion_report/app.py` so `--no-fusiongdb2` and `--no-mitelman` control the correct databases.
- Fixed broken README links and badges by updating docs/demo URLs, CI badge URL, and Codacy badge image URL to currently reachable endpoints.
- Fixed version mismatch in `docs/download.md` COSMIC manual commands (aligned all examples to v101 to match `Settings.COSMIC["VERSION"]`).
- Fixed inverted SSL verify flag in `Net.get_large_file`: `no_ssl=True` now correctly disables certificate verification (`verify=not no_ssl`).
- Fixed containerized `run` resilience so HGNC loading now degrades gracefully when live download fails due to TLS/CA issues by falling back to cached or bundled HGNC resources.

### Changed

- Refactored database include checks in `fusion_report/app.py` to use explicit positive boolean flags (`include_*`) for clearer control flow.
- Updated `Dockerfile` to use Python 3.12 and a multi-stage build strategy with wheel-based installation and a smaller runtime image.
- Added `.dockerignore` to reduce Docker build context size and avoid sending non-runtime files to image builds.
- Updated source installation instructions in `README.md` from `python3 setup.py install` to `pip3 install .`.
- Harmonized manual database setup examples in `docs/download.md` with current schema paths under `fusion_report/data/schema/` and corrected the COSMIC base64 command example.
- Updated `docs/add_database.md` schema path guidance from `fusion_report/schema/...` to `fusion_report/data/schema/...`.
- Updated `.github/workflows/integration_tests.yml` to install the package using `pip install .` instead of `python setup.py install`.
- Updated the COSMIC manual download example in `docs/download.md` to use the current scripted API endpoint and v101 tarball flow.
- Updated documentation pages for consistency: fixed docs site repository/homepage links in `docs/index.html`, corrected YAML asset examples in `docs/customize_report.md`, refreshed wording and Jinja2 docs link in `docs/templating.md`, improved command help coverage in `docs/usage.md`, and fixed quick-start navigation in `docs/_sidebar.md`.
- Updated `.gitignore` and `.dockerignore` to better exclude local virtualenv, cache, coverage, and generated runtime artifacts from source control and Docker build context.
- Updated `docs/download.md` external reference links for Mitelman and COSMIC landing pages.
- Updated README attribution links for Slack invite and icon credits.
- Added Docker usage examples to `README.md`, `docs/usage.md`, `docs/download.md`, and `docs/createdb.md`.
- Added a direct documentation index in `README.md` with links to all main docs files for easier navigation in GitHub.
- Updated Docker examples to include `-u "$(id -u):$(id -g)"` so generated files are owned by the invoking host user.
- Verified Docker image execution with `tests/test_data` and `--no-cosmic`: report generation completes with FusionGDB2+Mitelman enrichment while COSMIC is excluded.

### Added

- Added minimal CLI smoke tests in `tests/test_smoke_cli.py` covering `fusion_report --help`, `run --help`, `download --help`, and `createdb --help`.
- Added Python-version guard in smoke tests so they skip on interpreters older than 3.12 and run normally on supported versions.
- Added `SymbolResolver` class (`fusion_report/common/symbol_resolver.py`) that dynamically downloads the HGNC complete-set TSV at runtime with a four-level fallback chain: live download → local cache (`~/.cache/fusion-report/`) → bundled gzip snapshot (`fusion_report/data/hgnc/hgnc_complete_set.txt.gz`) → strict failure (opt-in via `FUSION_REPORT_HGNC_STRICT=1`). An alternative bundled path can be supplied via `FUSION_REPORT_HGNC_BUNDLED_PATH`.
- Added pre-SQL HGNC resolution in `createdb.py`: all three database build paths (COSMIC, FusionGDB2, Mitelman) now resolve gene-pair symbols to stable HGNC IDs before inserting into SQLite, using Ensembl ID, Entrez ID, and chromosome hints where available. Per-source and combined mapping quality summaries are logged.
- Added `hgnc_pairs` index table to all three SQLite databases, populated at build time with (gene1_hgnc_id, gene2_hgnc_id, source_pair) tuples for unambiguous runtime matching.
- Added HGNC-pair-first matching in `App.enrich()`: fusions are matched against the `hgnc_pairs` index before falling back to legacy symbol-pair lookup.
- Added Mitelman karyotype chromosome hint extraction and translocation-pair disambiguation in `createdb.py` to improve resolution of ambiguous gene symbols in Mitelman records.
- Added Mitelman diagnostic report (`mitelman_hgnc_diagnostic_report.txt`) listing unresolved ambiguous symbols and non-unique translocation rows.
- Added Ensembl gene ID extraction to parsers that support it (STAR-Fusion, CTAT-LR-Fusion, EricScript, FusionCatcher, Pizzly) for unambiguous HGNC resolution.
- Added breakpoint-position-aware fusion deduplication: fusions with the same gene pair but different breakpoints are stored as separate entries with unique page titles.
- Added `page_title` property to `Fusion` model for unique per-fusion HTML filenames that include breakpoint coordinates.
- Added HGNC IDs and snapshot version to `Fusion.json_serialize()` output.
- Integrated symbol canonicalization into the `Fusion` model to automatically resolve gene symbols during instantiation using chromosome and Ensembl hints from parser details.
- Added bundled HGNC gzip snapshot (`fusion_report/data/hgnc/hgnc_complete_set.txt.gz`, 3.9 MB compressed) as package data for fully offline operation.
- Added live-network integration tests (`tests/test_hgnc_download_integration.py`, `tests/test_fusiongdb2_download_integration.py`) gated behind `RUN_LIVE_NETWORK_TESTS=1`; tests skip gracefully when the network or TLS is unavailable.
- Added `choices` parameter support in `ArgsBuilder` for `arguments.json`-defined CLI arguments.
- Added comprehensive test suite (`tests/test_symbol_canonicalization.py`) with 28 tests covering HGNC fallback chain (bundled gzip, non-strict degraded mode, strict failure), symbol resolution, alias mapping, chromosome disambiguation, Ensembl-based resolution, case-insensitivity, and JSON serialization.


### Removed

- Removed generated `db/DB-timestamp.txt` from tracked content and added it to `.gitignore`.

## [4.1.2]

### Fixed

- Fixed the broken FusionGDB2 download ([#91](https://github.com/Clinical-Genomics/fusion-report/issues/91)). The previous file `https://compbio.uth.edu/FusionGDB2/tables/FusionGDB2_id.xlsx` returns a 404 and is no longer published. The tool now downloads `https://compbio.uth.edu/FusionGDB/combined_tables/combinedFGDB2genes_genes_ID_04302024.txt`.

### Changed

- FusionGDB2 parsing now reads the new headerless 6-column TSV (using the 5'- and 3'-gene columns) instead of the old `.xlsx` export. Updated in both the `download` and `createdb` code paths.
- `createdb --fusiongdb2` now accepts a `.txt` (or pre-processed `.csv`) file instead of `.xlsx`.
- Updated the `createdb` integration test in CI to download and use the new FusionGDB2 `.txt` file.
- Updated documentation (`docs/createdb.md`, `docs/download.md`) to reference the new FusionGDB2 file and URL.
- Switched the pre-commit tooling from `pre-commit` to [`prek`](https://github.com/j178/prek): the lint CI workflow now runs `prek run --all-files`, `prek` was added to `requirements-dev.txt`, and the generated example reports under `docs/example/` are excluded from hook formatting.

### Removed

- Removed the now-unused `openpyxl` and `xlrd` dependencies (only used for the removed `.xlsx` parsing).

## [4.1.0]

### Added

- Added `createdb` command for building databases from local files, bypassing download URLs entirely
- Added integration tests: minimal tests on every PR, COSMIC tests when credentials are available (skipped on forks)
- Added more documentation

### Changed

- Updated COSMIC database API access to use the current endpoint
- Fixed file parsing to handle input formats correctly
- 4.1.1 is simply 4.1.0 but with the correct version string

### Removed

- Removed unused `sync` command ([#69](https://github.com/Clinical-Genomics/fusion-report/issues/69))

## [4.0.0]

### Added

- Added support to run the tool without SSL chain verification for users behind proxy servers who act as MITM [#79](https://github.com/Clinical-Genomics/fusion-report/pull/79)
- Added support for [CTAT-LR-Fusion](https://github.com/TrinityCTAT/CTAT-LR-fusion), which supports the fusion calling in PacBio or Nanopore long reads data [#82](https://github.com/Clinical-Genomics/fusion-report/pull/82),[#83](https://github.com/Clinical-Genomics/fusion-report/pull/83) .

### Changed

- Updated COSMIC database to be compatible with the new SANGER website[#83](https://github.com/Clinical-Genomics/fusion-report/pull/83)
- Updated project to be compatible with Python 3.12 [#83](https://github.com/Clinical-Genomics/fusion-report/pull/83)
- Updated GitHub Actions workflow to use latest actions versions [#83](https://github.com/Clinical-Genomics/fusion-report/pull/83)
- The score is now called Fusion Indication Index (FII) [#83](https://github.com/Clinical-Genomics/fusion-report/pull/83)
- FII formula changed [#83](https://github.com/Clinical-Genomics/fusion-report/pull/83):
    $$
    FII = 0.5 * \sum_{tool}^{tools provided} f(fusion, tool) + 0.5 * \sum_{db}^{dbs provided} g(fusion, db)*w(db)
    $$

    Weights for databases are as follows:

    * COSMIC (50)
    * MITELMAN (50)
    * FusionGDB2 (0)

## [3.0.0]

### Added

- Options --no-cosmic/--no-fusiongdb2/--no-mitelman to download and run without those specified databases

## [2.1.8]

### Removed

- Removed FusionGDB

## [2.1.5](https://github.com/matq007/fusion-report/releases/tag/2.1.5)

### Added

- Implemented Jaffa by [@mikewlloyd](https://github.com/mikewlloyd)

## [2.1.4](https://github.com/matq007/fusion-report/releases/tag/2.1.4)

### Fixed

- Using header columns to extract values from the fusion outputs

## [2.1.3](https://github.com/matq007/fusion-report/releases/tag/2.1.3)

### Fixed

- Missing escaping when saving a fusion page ([#34](https://github.com/matq007/fusion-report/issues/34))

## [2.1.2](https://github.com/matq007/fusion-report/releases/tag/2.1.2)

### Added

- New parameter `--allow-multiple-gene-symbols`, by default `False`

### Fixed

- Case when fusion gene symbol can't be uniquely determined and multiple fusion options are provided ([#30](https://github.com/matq007/fusion-report/issues/30))

### Changed

- renamed `tool_cutoff` to `tool-cutoff`

## [2.1.1](https://github.com/matq007/fusion-report/releases/tag/2.1.1)

### Changed

- moved databases from GitHub to Sourceforge

## [2.1.0](https://github.com/matq007/fusion-report/releases/tag/2.1.0)

### Added

- `sync` option for downloading all databases

### Changed

- all databases except `COSMIC` are now versioned in [fusion-report-db](https://github.com/matq007/fusion-report-db)

### Fixed

- Issues with downloading too many stuff ([#28](https://github.com/matq007/fusion-report/issues/28))

## [2.0.2](https://github.com/matq007/fusion-report/releases/tag/2.0.2)

### Changed

- moved from Travis to Github Actions

### Fixed

- `tool_cutoff` was not casted to `int` ([#25](https://github.com/matq007/fusion-report/issues/25))
- csv export missing data ([#26](https://github.com/matq007/fusion-report/issues/26))
- better exception handling for downloading databases

## [2.0.1](https://github.com/matq007/fusion-report/releases/tag/2.0.1)

### Fixed

- Fixed missing Mitelman database file

## [2.0.0](https://github.com/matq007/fusion-report/releases/tag/2.0.0)

This version of fusion-report has been completely rebuild from scratch following
best `python` practices as well as `typing`.

### Added

- Implemented Illumina Dragon by [@chadisaad](https://github.com/chadisaad)
- Implemented `Arriba` ([#4](https://github.com/matq007/fusion-report/issues/4))
- Export fusion list into multiple formats ([#16](https://github.com/matq007/fusion-report/issues/16))
- Version parameter ([#10](https://github.com/matq007/fusion-report/issues/10))

### Changed

- Switched `docs` to `docsify`
- Slack invite link ([#20](https://github.com/matq007/fusion-report/issues/20))
- Renamed `fusion_genes_mqc.json` to `fusions_mqc.json` ([#9](https://github.com/matq007/fusion-report/issues/9))

### Fixed

- Check if input file exists and is not empty ([#13](https://github.com/matq007/fusion-report/issues/13))

## [1.0.0](https://github.com/matq007/fusion-report/releases/tag/1.0.0) - 2019-03-26
