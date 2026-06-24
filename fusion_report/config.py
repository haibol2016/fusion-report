"""Configuration module"""

import base64
import os
from datetime import datetime
from typing import Any, Dict, List

from yaml import YAMLError, safe_load

from fusion_report.common.exceptions.config import ConfigException
from fusion_report.settings import Settings


class Config:
    """Class for adjusting report defined in configuration file.

    Attributes:
        report_title: Title of the report
        logos: Dictionary of logos: fusion-report and nf-core/rnafusion
        institution: Institution name
        date: Date in format '%d/%m/%Y'
        assets: Additional CSS and JS files
    """

    def __init__(self) -> None:
        """Initialize configuration with defaults.

        Sets default report title, loads embedded logos (base64-encoded),
        initializes institution and assets to empty, and sets date to today
        in the configured format (default: "%d/%m/%Y").
        """
        self._report_title: str = "nfcore/rnafusion summary report"
        self.logos: Dict[str, str] = self._load_logos()
        self._institution: Dict[str, Any] = {}
        self._date: str = datetime.now().strftime(Settings.DATE_FORMAT)
        self._assets: Dict[str, List[str]] = {}

    @staticmethod
    def _load_logos() -> Dict[str, str]:
        """Load and base64-encode logo images.

        Reads two logo images from the templates/assets/img directory
        (fusion-report.png and rnafusion_logo.png) and returns them as
        base64-encoded strings for embedding in HTML.

        Returns:
            Dict with 'main' and 'rnafusion' keys mapping to base64-encoded
            image data.
        """
        logos = {}
        paths = {
            "main": "templates/assets/img/fusion-report.png",
            "rnafusion": "templates/assets/img/rnafusion_logo.png",
        }
        for key, path in paths.items():
            full_path = os.path.join(Settings.ROOT_DIR, path)
            with open(full_path, "rb") as image_file:
                logos[key] = base64.b64encode(image_file.read()).decode("utf-8")
        return logos

    @property
    def report_title(self) -> str:
        """Return title."""
        return self._report_title

    @report_title.setter
    def report_title(self, title: str) -> None:
        """Set the report title.

        Args:
            title: New report title. Must be non-empty after stripping
                whitespace. Ignored if empty.
        """
        if title.strip():
            self._report_title = title.strip()

    @property
    def institution(self) -> Dict[str, Any]:
        """Return institution name, img and url."""
        return self._institution

    @institution.setter
    def institution(self, institution: Dict[str, str]) -> None:
        """Set institution metadata including name, logo, and URL.

        Loads the institution logo image (if path exists) and base64-encodes it.
        Missing or invalid paths are silently ignored.

        Args:
            institution: Dict with optional keys:
                - "name": Institution name (string)
                - "img": Path to institution logo image file (path checked)
                - "url": Institution website URL (string)
        """
        if "name" in institution.keys():
            self._institution["name"] = institution["name"]

        if "img" in institution.keys() and os.path.exists(institution["img"]):
            image = os.path.join(Settings.ROOT_DIR, institution["img"])
            self._institution["img"] = base64.b64encode(open(image, "rb").read()).decode("utf-8")

        if "url" in institution.keys():
            self._institution["url"] = institution["url"]

    @property
    def date(self) -> str:
        """Return date in format."""
        return self._date

    @date.setter
    def date(self, date_format: str) -> None:
        """Set the report date using a format string.

        Args:
            date_format: strftime format string (e.g., "%d/%m/%Y").
                Non-empty strings are applied to today's date; empty strings
                are ignored.
        """
        if date_format.strip():
            self._date = datetime.now().strftime(date_format)

    @property
    def assets(self) -> Dict[str, List[str]]:
        """Return HTML assets, custom CSS or Javascript."""
        return self._assets

    @assets.setter
    def assets(self, assets) -> None:
        """Set custom HTML assets (CSS and JavaScript files).

        Only files that exist on the filesystem are retained; non-existent
        paths are filtered out.

        Args:
            assets: Dict with optional "css" and "js" keys, each mapping to
                a list of file paths (string).
        """
        for key, value in assets.items():
            if key in ("css", "js") and value is not None:
                self.assets[key] = [x for x in value if os.path.exists(x)]

    def parse(self, path) -> "Config":
        """
        Method for parsing the configuration file.

        Args:
            path (string): path to configuration file
        """
        if path:
            try:
                with open(path, "r", encoding="utf-8") as in_file:
                    try:
                        data: Dict[str, Any] = safe_load(in_file)
                        self.report_title = data["report_title"]
                        self.institution = data["institution"]
                        self.date = data["date_format"]
                        self.assets = data["assets"]
                        return self
                    except YAMLError as ex:
                        raise ConfigException(f"YAML parsing error: {ex}") from ex
            except IOError as ex:
                raise ConfigException(f"Failed to read config file: {ex}") from ex

        return self

    def json_serialize(self) -> Dict[str, Any]:
        """Helper serialization method for templating engine."""
        return {
            "report_title": self.report_title,
            "logos": self.logos,
            "institution": self.institution,
            "date": self.date,
            "assets": self.assets,
        }
