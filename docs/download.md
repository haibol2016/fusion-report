# Download resources

> If you already have the database files locally, you can use [`fusion_report createdb`](createdb.md) to build databases without downloading.

Currently the tool supports three different databases:

* [FusionGDB2](https://compbio.uth.edu/FusionGDB/combined_tables/combinedFGDB2genes_genes_ID_04302024.txt)
* [Mitelman](https://mitelmandatabase.isb-cgc.org/)
* [COSMIC](https://cancer.sanger.ac.uk/cosmic/download/cosmic/v101/fusion)

You can download the databases running:

```bash
fusion_report download
    --cosmic_usr '<username>'
    --cosmic_passwd '<password>'
    /path/to/db
```

With a non-academic/research login -> using QIAGEN with a commercial license:

```bash
fusion_report download
    --cosmic_usr '<QIAGEN username>'
    --cosmic_passwd 'QIAGEN <password>'
    --qiagen
    /path/to/db
```

You can exclude a specific database with --no-cosmic/--no-mitelman/--no-fusiongdb2. Example for no COSMIC:

```bash
fusion_report download
    --no-cosmic
    /path/to/db
```

## Download with Docker

```bash
# Build image locally
docker build -t fusion-report:latest .

# Download databases into host directory
docker run --rm \
    -u "$(id -u):$(id -g)" \
    -w /db \
    -v /path/to/db:/db \
    fusion-report:latest download \
    --cosmic_usr "<username>" \
    --cosmic_passwd "<password>" \
    /db
```


## Manual download

### Mitelman

Website: [https://mitelmandatabase.isb-cgc.org/](https://mitelmandatabase.isb-cgc.org/)

**ZIP Archive:** `mitelman_db.zip`  
**Data File:** `MBCA.TXT.DATA` (extracted from archive)

```bash
wget -O mitelman_db.zip "https://storage.googleapis.com/mitelman-data-files/prod/mitelman_db.zip"
fusion_report createdb /path/to/db --mitelman mitelman_db.zip
```

Alternatively, if you have extracted the data file directly:

```bash
fusion_report createdb /path/to/db --mitelman MBCA.TXT.DATA
```

### COSMIC

Website: [https://cancer.sanger.ac.uk/cosmic/download/cosmic/v101/fusion](https://cancer.sanger.ac.uk/cosmic/download/cosmic/v101/fusion)

Note: Different COSMIC fusion versions are also supported for local `createdb` input.
The file is internally normalized and renamed to the expected v101 filename
(`cosmic_fusion_v101_grch38.tsv`) before import.

```bash
PASSWD=$(echo -n "<username>:<password>" | base64)
URL=$(curl -s -H "Authorization: Basic ${PASSWD}" \
    "https://cancer.sanger.ac.uk/api/mono/products/v1/downloads/scripted?bucket=downloads&path=grch38/cosmic/v101/Cosmic_Fusion_Tsv_v101_GRCh38.tar" \
  | jq -r .url)
curl -L "$URL" -o Cosmic_Fusion_Tsv_v101_GRCh38.tar
tar -xf Cosmic_Fusion_Tsv_v101_GRCh38.tar Cosmic_Fusion_v101_GRCh38.tsv.gz
gunzip Cosmic_Fusion_v101_GRCh38.tsv.gz
fusion_report createdb /path/to/db --cosmic Cosmic_Fusion_v101_GRCh38.tsv
```

## Data Format

### COSMIC

**File Format:** Tab-separated values (TSV)  
**Encoding:** UTF-8  
**Header:** First line is skipped (treated as header)

**Expected Columns (25 total, in order):**

1. `COSMIC_SAMPLE_ID`
2. `SAMPLE_NAME`
3. `COSMIC_PHENOTYPE_ID`
4. `COSMIC_FUSION_ID`
5. `FUSION_SYNTAX`
6. `FIVE_PRIME_CHROMOSOME`
7. `FIVE_PRIME_STRAND`
8. `FIVE_PRIME_TRANSCRIPT_ID`
9. `FIVE_PRIME_GENE_SYMBOL`
10. `FIVE_PRIME_LAST_OBSERVE_EXON`
11. `FIVE_PRIME_GENOME_START_FROM`
12. `FIVE_PRIME_GENOME_START_TO`
13. `FIVE_PRIME_GENOME_STOP_FROM`
14. `FIVE_PRIME_GENOME_STOP_TO`
15. `THREE_PRIME_CHROMOSOME`
16. `THREE_PRIME_STRAND`
17. `THREE_PRIME_TRANSCRIPT_ID`
18. `THREE_PRIME_GENE_SYMBOL`
19. `THREE_PRIME_FIRST_OBSERVE_EXON`
20. `THREE_PRIME_GENOME_START_FROM`
21. `THREE_PRIME_GENOME_START_TO`
22. `THREE_PRIME_GENOME_STOP_FROM`
23. `THREE_PRIME_GENOME_STOP_TO`
24. `FUSION_TYPE`
25. `PUBMED_PMID`

**Notes:**
- Column order is critical: values are inserted positionally into the database schema.
- Fusion pairs are extracted using `FIVE_PRIME_GENE_SYMBOL` and `THREE_PRIME_GENE_SYMBOL`.
- The tool accepts both plain TSV and gzip-compressed (`*.tsv.gz`) files.
- COSMIC version in the input filename does not need to be `v101`; `createdb`
    renames compatible COSMIC TSV input internally to `cosmic_fusion_v101_grch38.tsv`.

## HGNC Resolver Environment Variables

The HGNC resolver loads mappings in this order:

1. Download from HGNC
2. Local cache
3. Bundled gzip snapshot
4. Strict failure (optional)

Environment variables:

- `FUSION_REPORT_HGNC_STRICT`: If set to `1`/`true`/`yes`/`on`, fail when HGNC data cannot be loaded from any source.
- `FUSION_REPORT_HGNC_BUNDLED_PATH`: Optional path to a local HGNC gzip snapshot (`.txt.gz`) used as bundled fallback.
