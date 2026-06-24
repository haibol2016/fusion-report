"""Template wrapper"""

import os
from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

from fusion_report.common.page import Page
from fusion_report.config import Config
from fusion_report.settings import Settings


class Template:
    """The class implements core methods.

    Attributes:
        j2_env: Jinja2 Environment
        j2_variables: Extra variables from configuration
        output_dir: Output directory where the files will be generated
    """

    def __init__(self, config_path: str, output_dir: str) -> None:
        """Initialize Jinja2 template engine.

        Sets up Jinja2 environment with template loaders for fusion_report
        templates and modules directories, loads configuration from YAML file,
        and ensures output directory exists.

        Args:
            config_path: Path to YAML configuration file (or None for defaults).
            output_dir: Directory where rendered HTML files will be written.
        """
        self.j2_env = Environment(
            loader=FileSystemLoader(
                [
                    os.path.join(Settings.ROOT_DIR, "templates/"),
                    os.path.join(Settings.ROOT_DIR, "modules/"),
                ]
            ),
            trim_blocks=True,
            autoescape=True,
        )
        self.j2_variables: Config = Config().parse(config_path)
        self.output_dir: str = output_dir

        # helper functions which can be used inside partial templates
        self.j2_env.globals["include_raw"] = self.include_raw
        self.j2_env.globals["get_id"] = self.get_id

        # Making sure output directory exists
        if not os.path.exists(output_dir):
            os.mkdir(output_dir)

    def render(self, page: Page, extra_variables: Dict[str, Any]) -> None:
        """Render a page template to HTML file.

        Merges configuration variables with extra page variables and renders
        the page's view template, then writes the resulting HTML to file.

        Args:
            page: Page object containing title, view, and filename.
            extra_variables: Dict of variables to pass to the template.
        """
        merged_variables = {**self.j2_variables.json_serialize(), **extra_variables}
        view = self.j2_env.get_template(page.view).render(merged_variables)
        with open(os.path.join(self.output_dir, page.filename), "w", encoding="utf-8") as file_out:
            file_out.write(view)

    def include_raw(self, filename: str) -> Markup:
        """Include raw file content in Jinja2 template.

        Reads file content from the template loader and wraps it in appropriate
        HTML tags (style for CSS, script for JavaScript). Used to embed custom
        or vendor CSS and JavaScript directly in templates.

        Args:
            filename: Name of the CSS or JS file to include (relative to
                template directories).

        Returns:
            Markup-wrapped HTML content (style/script tags or raw content).
        """
        file_extension = Path(filename).suffix
        assert isinstance(self.j2_env.loader, FileSystemLoader)

        if file_extension == ".css":
            return Markup(
                '<style type="text/css">{css}</style>'.format(
                    css=self.j2_env.loader.get_source(self.j2_env, filename)[0]
                )
            )
        if file_extension == ".js":
            return Markup(
                "<script>{js}</script>".format(
                    js=self.j2_env.loader.get_source(self.j2_env, filename)[0]
                )
            )

        return Markup(self.j2_env.loader.get_source(self.j2_env, filename)[0])

    @staticmethod
    def get_id(title: str) -> str:
        """Generate HTML element ID from page title.

        Converts title to lowercase and replaces spaces with underscores for
        use as HTML id attributes.

        Args:
            title: Page title or text to convert.

        Returns:
            HTML-safe ID string (lowercase, underscores for spaces).
        """
        return title.lower().replace(" ", "_")
