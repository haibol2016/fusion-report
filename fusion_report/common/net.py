"""Network utilities for downloading and extracting databases."""
import base64
import glob
import gzip
import json
import os
import shutil
import subprocess
import tarfile
import time
from argparse import Namespace
from typing import List
from zipfile import ZipFile

import pandas as pd
import requests

from fusion_report.common.exceptions.download import DownloadException
from fusion_report.common.logger import Logger
from fusion_report.data.cosmic import CosmicDB
from fusion_report.data.fusiongdb2 import FusionGDB2
from fusion_report.data.mitelman import MitelmanDB
from fusion_report.settings import Settings

LOG = Logger(__name__)


class Net:
    """Network utilities for downloading and managing fusion databases.

    Provides static methods for downloading COSMIC, FusionGDB2, and Mitelman
    databases from their respective sources (Sanger, QIAGEN, remote hosts),
    extracting archives, and decompressing files.
    """
    @staticmethod
    def get_cosmic_token(params: Namespace) -> str:
        """Retrieve COSMIC authentication token.

        Either uses a provided token directly, or generates a base64-encoded
        token from username/password credentials.

        Args:
            params: Parsed arguments containing cosmic_token, cosmic_usr,
                and cosmic_passwd.

        Returns:
            Base64-encoded COSMIC authentication token.

        Raises:
            DownloadException: If credentials are not provided correctly.
        """
        if params.cosmic_token is not None:
            return params.cosmic_token

        if params.cosmic_usr is not None and params.cosmic_passwd is not None:
            return base64.b64encode(f"{params.cosmic_usr}:{params.cosmic_passwd}".encode()).decode(
                "utf-8"
            )
        else:
            raise DownloadException("COSMIC credentials have not been provided correctly")

    @staticmethod
    def run_qiagen_cmd(cmd: str, return_output: bool = False, silent: bool = False):
        """Execute a shell command via QIAGEN API.

        Runs command via /bin/bash, optionally capturing and returning output,
        and optionally suppressing command echo.

        Args:
            cmd: Shell command to execute.
            return_output: If True, capture and return command output.
            silent: If True, suppress printing the command.

        Returns:
            Command output if return_output=True, otherwise None.
        """
        if not silent:
            print(cmd)
        if return_output:
            output = subprocess.check_output(cmd, shell=True, executable="/bin/bash").strip()
            return output
        else:
            subprocess.check_call(cmd, shell=True, executable="/bin/bash")

    @staticmethod
    def get_qiagen_files(token: str, output_path: str) -> bytes:
        """Fetch list of available COSMIC files from QIAGEN.

        Retrieves file metadata (file_id, file_name, genome_draft) from QIAGEN
        and saves to qiagen_files.tsv.

        Args:
            token: QIAGEN authentication token.
            output_path: Directory where qiagen_files.tsv will be written.

        Returns:
            Command output from curl request.
        """
        files_request = (
            "curl --stderr -s -X GET "
            '-H "Content-Type: application/octet-stream" '
            '-H "Authorization: Bearer {token}" '
            '"https://my.qiagendigitalinsights.com/bbp/data/files/cosmic"'
            " -o {output_path}qiagen_files.tsv"
        )
        cmd = files_request.format(token=token, output_path=output_path)
        return Net.run_qiagen_cmd(cmd, True, True)

    @staticmethod
    def download_qiagen_file(token: str, file_id: str, output_path: str) -> None:
        """Download a specific COSMIC file from QIAGEN by file ID.

        Downloads the file and saves it to the output path as the configured
        COSMIC file name.

        Args:
            token: QIAGEN authentication token.
            file_id: QIAGEN file ID for the COSMIC release.
            output_path: Directory where the file will be downloaded.
        """
        file_request = (
            "curl -s -X GET "
            '-H "Content-Type: application/octet-stream" '
            '-H "Authorization: Bearer {token}" '
            '"https://my.qiagendigitalinsights.com/bbp/data/download/cosmic-download?name={file_id}"'
            " -o {output_path}{cosmic_file}"
        )
        cmd = file_request.format(
            token=token,
            file_id=file_id,
            output_path=output_path,
            cosmic_file=Settings.COSMIC["FILE"],
        )
        Net.run_qiagen_cmd(cmd, True, True)

    @staticmethod
    def fetch_fusion_file_id(output_path: str) -> str:
        """Extract COSMIC fusion file ID from QIAGEN files list.

        Parses qiagen_files.tsv to find the COSMIC GRCh38 fusion file ID.

        Args:
            output_path: Directory containing qiagen_files.tsv.

        Returns:
            File ID for the COSMIC fusion file.
        """
        df = pd.read_csv(
            output_path + "/qiagen_files.tsv",
            names=["file_id", "file_name", "genome_draft"],
            sep="\t",
        )
        file_id = df.loc[
            (df["file_name"] == Settings.COSMIC["FILE"]) & (df["genome_draft"] == "cosmic/GRCh38"),
            "file_id",
        ].values[0]
        return file_id

    @staticmethod
    def get_cosmic_qiagen_token(params: Namespace) -> str:
        """Retrieve COSMIC access token from QIAGEN using credentials.

        Authenticates with QIAGEN OAuth endpoint using provided username
        and password.

        Args:
            params: Parsed arguments containing cosmic_usr and cosmic_passwd.

        Returns:
            QIAGEN access token for downloading COSMIC files.
        """
        token_request = (
            "curl -s -X POST "
            '-H "Content-Type: application/x-www-form-urlencoded" '
            '-d "grant_type=password&client_id=603912630-14192122372034111918-SmRwso&username={uid}&password={pwd}" '  # noqa: E501
            '"https://apps.ingenuity.com/qiaoauth/oauth/token"'
        )
        cmd = token_request.format(uid=params.cosmic_usr, pwd=params.cosmic_passwd)
        token_response = Net.run_qiagen_cmd(cmd, True, True).decode("UTF-8")
        return json.loads(token_response)["access_token"]

    @staticmethod
    def get_large_file(url: str, no_ssl: bool) -> None:
        """Download a large file from a URL with resumption support.

        Downloads file in 8KB chunks. Resumes download if file already exists
        and size differs from Content-Length header.

        Args:
            url: Full URL of the file to download.
            no_ssl: If False, verify SSL certificates; if True, skip verification.

        Raises:
            DownloadException: If download fails.
        """
        LOG.info(f"Downloading {url}")
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            # no_ssl=True means disable SSL verification for this request.
            response = requests.get(url, headers=headers, stream=True, verify=not no_ssl)
            file = url.split("/")[-1].split("?")[0]

            if (
                not os.path.exists(file)
                or (response.headers.get("Content-Length") or 0) != os.stat(file).st_size
            ):
                with open(file, "wb") as out_file:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            out_file.write(chunk)
        except Exception as ex:
            LOG.error(f"Error downloading {url}, {ex}")
            raise DownloadException(ex) from ex

    @staticmethod
    def get_cosmic_from_sanger_url(token: str, file_path: str) -> str:
        """Get download URL for COSMIC database from Sanger website.

        Queries Sanger API to retrieve the direct download URL for COSMIC
        using the provided authentication token.

        Args:
            token: Base64-encoded COSMIC authentication token.
            file_path: Path to file on Sanger server (e.g.,
                "grch38/cosmic/v101/filename").

        Returns:
            Direct download URL for the file.
        """
        params = {"path": file_path, "bucket": "downloads"}
        url = Settings.COSMIC["HOSTNAME"]
        headers = {"Authorization": f"Basic {token}"}
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json().get("url")

    @staticmethod
    def extract_gz(file_path: str) -> str | None:
        """Decompress a gzipped file.

        Extracts .gz file to the same directory with the .gz extension removed.

        Args:
            file_path: Path to .gz file.

        Returns:
            Path to extracted file, or None if extraction fails.
        """
        try:
            output_file = file_path.rsplit(".", 1)[0]  # Remove .gz extension
            with gzip.open(file_path, "rb") as f_in, open(output_file, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            LOG.info(f"Decompressed {file_path} to {output_file}")
            return output_file
        except Exception as e:
            LOG.error(f"Error extracting gzip file: {e}")
            return None

    @staticmethod
    def extract_tar(file_path: str, extract_to: str) -> str | None:
        """Extract COSMIC file from tar archive.

        Searches tar archive for Settings.COSMIC["FILE"] and extracts it to
        the specified directory.

        Args:
            file_path: Path to tar archive.
            extract_to: Directory where file will be extracted.

        Returns:
            Path to extracted file, or None if file not found or extraction fails.
        """
        try:
            with tarfile.open(file_path, "r:") as tar:
                target_file = Settings.COSMIC["FILE"]
                if target_file in tar.getnames():
                    tar.extract(target_file, path=extract_to)
                    extracted_path = os.path.join(extract_to, target_file)
                    LOG.info(f"Extracted {target_file} to {extracted_path}")
                    return extracted_path
                else:
                    LOG.error(f"{target_file} not found in the tar archive.")
                    return None
        except Exception as e:
            LOG.error(f"Error extracting tar file: {e}")
            return None

    @staticmethod
    def get_cosmic_from_sanger(token: str, return_err: List[str], no_ssl: bool,
                               outputpath: str) -> None:
        """Download COSMIC database from Sanger website.

        Retrieves download URL, downloads tar archive, extracts and decompresses
        COSMIC TSV, renames it appropriately, and builds the SQLite database.

        Args:
            token: COSMIC authentication token.
            return_err: List to append error messages to.
            no_ssl: If True, skip SSL certificate verification.
            outputpath: Output directory for database file.
        """
        file_path = f"grch38/cosmic/{Settings.COSMIC['VERSION']}/{Settings.COSMIC['TARFILE']}"
        try:
            download_url = Net.get_cosmic_from_sanger_url(token, file_path=file_path)

            if not download_url:
                raise ValueError("Failed to retrieve the download URL.")

            LOG.info(f"Download URL: {download_url}")
            Net.get_large_file(download_url, no_ssl)
            Net.extract_tar(Settings.COSMIC["TARFILE"], ".")
            extracted_file = Net.extract_gz("." + "/" + Settings.COSMIC["FILE"])
            renamed_file = os.path.join(
                os.path.dirname(extracted_file), "cosmic_fusion_v101_grch38.tsv"
            )
            os.rename(extracted_file, renamed_file)
            db = CosmicDB(".")
            db.setup([os.path.basename(renamed_file)], delimiter="\t", skip_header=True)

        except requests.exceptions.RequestException as req_err:
            return_err.append(f'{Settings.COSMIC["NAME"]}: {req_err}')
        except (ValueError, KeyError) as json_err:
            return_err.append(f"Error processing request: {json_err}")

    @staticmethod
    def get_cosmic_from_qiagen(token: str, return_err: List[str], outputpath: str,
                               no_ssl: bool = True) -> None:
        """Download COSMIC database from QIAGEN.

        Retrieves file list from QIAGEN, finds the GRCh38 fusion file, downloads it,
        decompresses, and builds the SQLite database.

        Args:
            token: QIAGEN access token.
            return_err: List to append error messages to.
            outputpath: Output directory for database file.
            no_ssl: If True, skip SSL certificate verification.
        """
        try:
            Net.get_qiagen_files(token, outputpath)
        except Exception as ex:
            LOG.info(ex)

        file_id = Net.fetch_fusion_file_id(outputpath)
        Net.download_qiagen_file(token, file_id, outputpath)
        file: str = Settings.COSMIC["FILE"]
        files = []

        try:
            files.append(".".join(file.split(".")[:-1]))

            with gzip.open(file, "rb") as archive, open(files[0], "wb") as out_file:
                shutil.copyfileobj(archive, out_file)

            renamed_file = "cosmic_fusion_v101_grch38.tsv"
            os.rename(files[0], renamed_file)
            db = CosmicDB(".")
            db.setup([renamed_file], delimiter="\t", skip_header=True)
        except Exception as ex:
            return_err.append(f'{Settings.COSMIC["NAME"]}: {ex}')

    @staticmethod
    def get_fusiongdb2(self, return_err: List[str], no_ssl: bool) -> None:
        """Download and process FusionGDB2 database.

        Downloads the TSV file from FusionGDB2 remote host, extracts gene pairs,
        creates a CSV, and builds the SQLite database.

        Args:
            self: Unused (method signature for consistency with get_mitelman).
            return_err: List to append error messages to.
            no_ssl: If True, skip SSL certificate verification.
        """
        try:
            url: str = f'{Settings.FUSIONGDB2["HOSTNAME"]}/{Settings.FUSIONGDB2["FILE"]}'
            Net.get_large_file(url, no_ssl)
            file: str = f'{Settings.FUSIONGDB2["FILE"]}'
            # Headerless 6-column TSV: col2 = 5'-gene, col4 = 3'-gene (0-indexed)
            df = pd.read_csv(file, sep="\t", header=None)
            df["fusion"] = df[2] + "--" + df[4]
            file_csv = "fusionGDB2.csv"
            df["fusion"].to_csv(file_csv, header=False, index=False, sep=",", encoding="utf-8")

            db = FusionGDB2(".")
            db.setup([file_csv], delimiter=",", skip_header=False)

        except DownloadException as ex:
            return_err.append(f"FusionGDB2: {ex}")

    @staticmethod
    def get_mitelman(self, return_err: List[str], no_ssl: bool) -> None:
        """Download and process Mitelman database.

        Downloads ZIP archive from Mitelman remote host, extracts data files,
        and builds the SQLite database.

        Args:
            self: Unused (method signature for consistency with get_fusiongdb2).
            return_err: List to append error messages to.
            no_ssl: If True, skip SSL certificate verification.
        """
        try:
            url: str = f'{Settings.MITELMAN["HOSTNAME"]}/{Settings.MITELMAN["FILE"]}'
            Net.get_large_file(url, no_ssl)
            with ZipFile(Settings.MITELMAN["FILE"], "r") as archive:
                files = [
                    x for x in archive.namelist() if "MBCA.TXT.DATA" in x and "MACOSX" not in x
                ]
                archive.extractall()

            db = MitelmanDB(".")
            db.setup(files, delimiter="\t", skip_header=False, encoding="ISO-8859-1")
        except DownloadException as ex:
            return_err.append(f"Mitelman: {ex}")

    @staticmethod
    def clean() -> None:
        """Move generated .db files to output directory and clean up.

        Copies all .db files from the temporary working directory to the parent
        output directory, then removes the temporary directory tree.
        """
        for temp in glob.glob("*.db"):
            shutil.copy(temp, "../")
        os.chdir("../")
        shutil.rmtree("tmp_dir")

    @staticmethod
    def timestamp() -> None:
        """Create a timestamp file recording database creation time.

        Writes the current date and time in "YYYY-MM-DD/HH:MM" format to
        DB-timestamp.txt in the current working directory.
        """
        timestr = time.strftime("%Y-%m-%d/%H:%M")
        text_file = open("DB-timestamp.txt", "w")
        text_file.write(timestr)
        text_file.close()
