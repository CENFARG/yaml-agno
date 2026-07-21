"""BUILTIN_REGISTRY — declarative catalog of built-in Agno toolkits.

Each ``ToolkitAdapter`` carries the Agno (module, class) pair, an alias map
(yfinance shorthand -> enable_* canonical), and the Agno pip package. The
adapter instantiates the toolkit, filtering ``init_args`` against
``inspect.signature(cls.__init__)`` (Toolkits are NOT dataclasses).

Slice D (SPEC_11) expands the catalog from the original 5 adapters
(calculator, yfinance, hackernews, duckduckgo, shell) to ~131 adapters
covering the full Agno 2.6.22 tool surface.

``resolve_class`` is lazy: ``ToolkitAdapter.build()`` resolves the class at
BUILD time, not at registry-definition time. Optional-dep modules can live in
the registry; they only fail if the user actually uses them without the dep
installed. The ``packages`` tuple lists the pip package(s) required (for
Dockerfile/pyproject generation), not for runtime import.
"""

from __future__ import annotations

import dataclasses
import inspect
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from yaml_agno.di.agno_resolver import AgnoResolver

__all__ = ["BUILTIN_REGISTRY", "ToolkitAdapter", "UnknownBuiltinError"]


class UnknownBuiltinError(Exception):
    """Raised when a ``builtin`` name is not in BUILTIN_REGISTRY."""


@dataclasses.dataclass
class ToolkitAdapter:
    """Declarative metadata + instantiation logic for a built-in toolkit.

    Attributes:
        module_path: Agno module (e.g. 'agno.tools.calculator').
        class_name: Agno class (e.g. 'CalculatorTools').
        packages: Pip packages required (for Dockerfile/pyproject generation).
        alias_map: Shorthand -> canonical kwarg name (e.g. {'stock_price': 'enable_stock_price'}).
    """

    module_path: str
    class_name: str
    packages: tuple[str, ...]
    alias_map: dict[str, str] = dataclasses.field(default_factory=dict)

    def build(self, resolver: AgnoResolver, init_args: dict[str, Any]) -> Any:
        """Resolve the class, normalize aliases, filter kwargs, instantiate.

        Args:
            resolver: The AgnoResolver for allowlisted class resolution.
            init_args: Raw kwargs from the YAML (may use shorthand aliases).

        Returns:
            The instantiated Agno Toolkit.

        Raises:
            TypeError: If the toolkit constructor rejects a filtered kwarg
                (should not happen post-filtering, but defensive).
        """
        cls = resolver.resolve_class(self.module_path, self.class_name)
        normalized = self._normalize_aliases(init_args)
        filtered = self._filter_kwargs(cls, normalized)
        return cls(**filtered)

    def _normalize_aliases(self, init_args: dict[str, Any]) -> dict[str, Any]:
        """Apply the alias_map to rename shorthand keys to canonical."""
        return {self.alias_map.get(k, k): v for k, v in init_args.items()}

    def _filter_kwargs(self, cls: type, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Keep only kwargs the class __init__ accepts (Toolkits aren't dataclasses).

        Uses ``inspect.signature``. ``**kwargs`` in the signature (e.g.
        CalculatorTools) accepts everything, so nothing is dropped there.
        """
        try:
            # inspect.signature(cls) resolves to cls.__init__ without the
            # mypy "accessing __init__ on instance is unsound" warning.
            sig_params = inspect.signature(cls).parameters
        except (TypeError, ValueError):
            return kwargs
        allowed = set(sig_params) - {"self"}
        accepts_var_kw = any(
            p.kind is inspect.Parameter.VAR_KEYWORD for p in sig_params.values()
        )
        if accepts_var_kw:
            return kwargs
        return {k: v for k, v in kwargs.items() if k in allowed}


BUILTIN_REGISTRY: dict[str, ToolkitAdapter] = {
    # ------------------------------------------------------------------
    # ORIGINAL 5 ADAPTERS (kept verbatim — correct baseline)
    # ------------------------------------------------------------------
    "calculator": ToolkitAdapter(
        module_path="agno.tools.calculator",
        class_name="CalculatorTools",
        packages=("agno",),
    ),
    "yfinance": ToolkitAdapter(
        module_path="agno.tools.yfinance",
        class_name="YFinanceTools",
        packages=("yfinance",),
        alias_map={
            "stock_price": "enable_stock_price",
            "company_info": "enable_company_info",
            "news": "enable_company_news",
            "analyst": "enable_analyst_recommendations",
        },
    ),
    "hackernews": ToolkitAdapter(
        module_path="agno.tools.hackernews",
        class_name="HackerNewsTools",
        packages=("agno",),
        alias_map={
            "top_stories": "enable_get_top_stories",
            "user_details": "enable_get_user_details",
        },
    ),
    "duckduckgo": ToolkitAdapter(
        module_path="agno.tools.duckduckgo",
        class_name="DuckDuckGoTools",
        packages=("ddgs",),
    ),
    "shell": ToolkitAdapter(
        module_path="agno.tools.shell",
        class_name="ShellTools",
        packages=("agno",),
    ),
    # ------------------------------------------------------------------
    # IMPORTABLE NOW (stdlib / agno-core deps only)
    # ------------------------------------------------------------------
    "airflow": ToolkitAdapter(
        module_path="agno.tools.airflow",
        class_name="AirflowTools",
        packages=("agno",),
    ),
    "coding": ToolkitAdapter(
        module_path="agno.tools.coding",
        class_name="CodingTools",
        packages=("agno",),
    ),
    "csv_toolkit": ToolkitAdapter(
        module_path="agno.tools.csv_toolkit",
        class_name="CsvTools",
        packages=("agno",),
    ),
    "email": ToolkitAdapter(
        module_path="agno.tools.email",
        class_name="EmailTools",
        packages=("agno",),
    ),
    "file": ToolkitAdapter(
        module_path="agno.tools.file",
        class_name="FileTools",
        packages=("agno",),
    ),
    "file_generation": ToolkitAdapter(
        module_path="agno.tools.file_generation",
        class_name="FileGenerationTools",
        packages=("agno",),
    ),
    "knowledge": ToolkitAdapter(
        module_path="agno.tools.knowledge",
        class_name="KnowledgeTools",
        packages=("agno",),
    ),
    "local_file_system": ToolkitAdapter(
        module_path="agno.tools.local_file_system",
        class_name="LocalFileSystemTools",
        packages=("agno",),
    ),
    "memory": ToolkitAdapter(
        module_path="agno.tools.memory",
        class_name="MemoryTools",
        packages=("agno",),
    ),
    "python": ToolkitAdapter(
        module_path="agno.tools.python",
        class_name="PythonTools",
        packages=("agno",),
    ),
    "reasoning": ToolkitAdapter(
        module_path="agno.tools.reasoning",
        class_name="ReasoningTools",
        packages=("agno",),
    ),
    "sleep": ToolkitAdapter(
        module_path="agno.tools.sleep",
        class_name="SleepTools",
        packages=("agno",),
    ),
    "user_control_flow": ToolkitAdapter(
        module_path="agno.tools.user_control_flow",
        class_name="UserControlFlowTools",
        packages=("agno",),
    ),
    "user_feedback": ToolkitAdapter(
        module_path="agno.tools.user_feedback",
        class_name="UserFeedbackTools",
        packages=("agno",),
    ),
    "webbrowser": ToolkitAdapter(
        module_path="agno.tools.webbrowser",
        class_name="WebBrowserTools",
        packages=("agno",),
    ),
    "website": ToolkitAdapter(
        module_path="agno.tools.website",
        class_name="WebsiteTools",
        packages=("agno",),
    ),
    "visualization": ToolkitAdapter(
        module_path="agno.tools.visualization",
        class_name="VisualizationTools",
        packages=("agno",),
    ),
    "workspace": ToolkitAdapter(
        module_path="agno.tools.workspace",
        class_name="Workspace",
        packages=("agno",),
    ),
    "websearch": ToolkitAdapter(
        module_path="agno.tools.websearch",
        class_name="WebSearchTools",
        packages=("ddgs",),
    ),
    "unsplash": ToolkitAdapter(
        module_path="agno.tools.unsplash",
        class_name="UnsplashTools",
        packages=("agno",),
    ),
    "llms_txt": ToolkitAdapter(
        module_path="agno.tools.llms_txt",
        class_name="LLMsTxtTools",
        packages=("agno",),
    ),
    "models_labs": ToolkitAdapter(
        module_path="agno.tools.models_labs",
        class_name="ModelsLabTools",
        packages=("agno",),
    ),
    # httpx-based (httpx is an agno core dep — importable)
    "pubmed": ToolkitAdapter(
        module_path="agno.tools.pubmed",
        class_name="PubmedTools",
        packages=("agno",),
    ),
    "searxng": ToolkitAdapter(
        module_path="agno.tools.searxng",
        class_name="Searxng",
        packages=("agno",),
    ),
    "spotify": ToolkitAdapter(
        module_path="agno.tools.spotify",
        class_name="SpotifyTools",
        packages=("agno",),
    ),
    "webtools": ToolkitAdapter(
        module_path="agno.tools.webtools",
        class_name="WebTools",
        packages=("agno",),
    ),
    "youcom": ToolkitAdapter(
        module_path="agno.tools.youcom",
        class_name="YouTools",
        packages=("agno",),
    ),
    "brandfetch": ToolkitAdapter(
        module_path="agno.tools.brandfetch",
        class_name="BrandfetchTools",
        packages=("agno",),
    ),
    "jina": ToolkitAdapter(
        module_path="agno.tools.jina",
        class_name="JinaReaderTools",
        packages=("agno",),
    ),
    "whatsapp": ToolkitAdapter(
        module_path="agno.tools.whatsapp",
        class_name="WhatsAppTools",
        packages=("agno",),
    ),
    "shopify": ToolkitAdapter(
        module_path="agno.tools.shopify",
        class_name="ShopifyTools",
        packages=("agno",),
    ),
    "desi_vocal": ToolkitAdapter(
        module_path="agno.tools.desi_vocal",
        class_name="DesiVocalTools",
        packages=("agno",),
    ),
    "giphy": ToolkitAdapter(
        module_path="agno.tools.giphy",
        class_name="GiphyTools",
        packages=("agno",),
    ),
    "antigravity": ToolkitAdapter(
        module_path="agno.tools.antigravity",
        class_name="AntigravityTools",
        packages=("agno",),
    ),
    "perplexity": ToolkitAdapter(
        module_path="agno.tools.perplexity",
        class_name="PerplexitySearch",
        packages=("httpx",),
    ),
    "studio": ToolkitAdapter(
        module_path="agno.tools.studio",
        class_name="StudioTools",
        packages=("agno",),
    ),
    # requests-based (top-level `import requests` — requests in packages)
    "bitbucket": ToolkitAdapter(
        module_path="agno.tools.bitbucket",
        class_name="BitbucketTools",
        packages=("requests",),
    ),
    "discord": ToolkitAdapter(
        module_path="agno.tools.discord",
        class_name="DiscordTools",
        packages=("requests",),
    ),
    "linear": ToolkitAdapter(
        module_path="agno.tools.linear",
        class_name="LinearTools",
        packages=("requests",),
    ),
    "searchapi": ToolkitAdapter(
        module_path="agno.tools.searchapi",
        class_name="SearchApiTools",
        packages=("requests",),
    ),
    "serper": ToolkitAdapter(
        module_path="agno.tools.serper",
        class_name="SerperTools",
        packages=("requests",),
    ),
    "sofya": ToolkitAdapter(
        module_path="agno.tools.sofya",
        class_name="SofyaTools",
        packages=("requests",),
    ),
    "zoom": ToolkitAdapter(
        module_path="agno.tools.zoom",
        class_name="ZoomTools",
        packages=("requests",),
    ),
    "financial_datasets": ToolkitAdapter(
        module_path="agno.tools.financial_datasets",
        class_name="FinancialDatasetsTools",
        packages=("requests",),
    ),
    "azure_openai": ToolkitAdapter(
        module_path="agno.tools.models.azure_openai",
        class_name="AzureOpenAITools",
        packages=("requests",),
    ),
    "nebius": ToolkitAdapter(
        module_path="agno.tools.models.nebius",
        class_name="NebiusTools",
        packages=("agno",),
    ),
    # ------------------------------------------------------------------
    # OPTIONAL DEP (class known from source; import fails without the dep)
    # ------------------------------------------------------------------
    "agentql": ToolkitAdapter(
        module_path="agno.tools.agentql",
        class_name="AgentQLTools",
        packages=("agentql",),
    ),
    "apify": ToolkitAdapter(
        module_path="agno.tools.apify",
        class_name="ApifyTools",
        packages=("apify-client",),
    ),
    "arxiv": ToolkitAdapter(
        module_path="agno.tools.arxiv",
        class_name="ArxivTools",
        packages=("arxiv", "pypdf"),
    ),
    "aws_lambda": ToolkitAdapter(
        module_path="agno.tools.aws_lambda",
        class_name="AWSLambdaTools",
        packages=("boto3",),
    ),
    "aws_ses": ToolkitAdapter(
        module_path="agno.tools.aws_ses",
        class_name="AWSSESTool",
        packages=("boto3",),
    ),
    "baidusearch": ToolkitAdapter(
        module_path="agno.tools.baidusearch",
        class_name="BaiduSearchTools",
        packages=("baidusearch", "pycountry"),
    ),
    "bravesearch": ToolkitAdapter(
        module_path="agno.tools.bravesearch",
        class_name="BraveSearchTools",
        packages=("brave-search",),
    ),
    "browserbase": ToolkitAdapter(
        module_path="agno.tools.browserbase",
        class_name="BrowserbaseTools",
        packages=("browserbase", "playwright"),
    ),
    "calcom": ToolkitAdapter(
        module_path="agno.tools.calcom",
        class_name="CalComTools",
        packages=("requests", "pytz"),
    ),
    "cartesia": ToolkitAdapter(
        module_path="agno.tools.cartesia",
        class_name="CartesiaTools",
        packages=("cartesia",),
    ),
    "clickup": ToolkitAdapter(
        module_path="agno.tools.clickup",
        class_name="ClickUpTools",
        packages=("requests",),
    ),
    "confluence": ToolkitAdapter(
        module_path="agno.tools.confluence",
        class_name="ConfluenceTools",
        packages=("atlassian-python-api",),
    ),
    "crawl4ai": ToolkitAdapter(
        module_path="agno.tools.crawl4ai",
        class_name="Crawl4aiTools",
        packages=("crawl4ai",),
    ),
    "dalle": ToolkitAdapter(
        module_path="agno.tools.dalle",
        class_name="DalleTools",
        packages=("openai",),
    ),
    "daytona": ToolkitAdapter(
        module_path="agno.tools.daytona",
        class_name="DaytonaTools",
        packages=("daytona",),
    ),
    "docker": ToolkitAdapter(
        module_path="agno.tools.docker",
        class_name="DockerTools",
        packages=("docker",),
    ),
    "docling": ToolkitAdapter(
        module_path="agno.tools.docling",
        class_name="DoclingTools",
        packages=("docling",),
    ),
    "duckdb": ToolkitAdapter(
        module_path="agno.tools.duckdb",
        class_name="DuckDbTools",
        packages=("duckdb",),
    ),
    "e2b": ToolkitAdapter(
        module_path="agno.tools.e2b",
        class_name="E2BTools",
        packages=("e2b-code-interpreter",),
    ),
    "eleven_labs": ToolkitAdapter(
        module_path="agno.tools.eleven_labs",
        class_name="ElevenLabsTools",
        packages=("elevenlabs",),
    ),
    "evm": ToolkitAdapter(
        module_path="agno.tools.evm",
        class_name="EvmTools",
        packages=("web3",),
    ),
    "exa": ToolkitAdapter(
        module_path="agno.tools.exa",
        class_name="ExaTools",
        packages=("exa-py",),
    ),
    "fal": ToolkitAdapter(
        module_path="agno.tools.fal",
        class_name="FalTools",
        packages=("fal-client",),
    ),
    "firecrawl": ToolkitAdapter(
        module_path="agno.tools.firecrawl",
        class_name="FirecrawlTools",
        packages=("firecrawl-py",),
    ),
    "github": ToolkitAdapter(
        module_path="agno.tools.github",
        class_name="GithubTools",
        packages=("PyGithub",),
    ),
    "gitlab": ToolkitAdapter(
        module_path="agno.tools.gitlab",
        class_name="GitlabTools",
        packages=("python-gitlab", "httpx"),
    ),
    "jira": ToolkitAdapter(
        module_path="agno.tools.jira",
        class_name="JiraTools",
        packages=("jira",),
    ),
    "linkup": ToolkitAdapter(
        module_path="agno.tools.linkup",
        class_name="LinkupTools",
        packages=("linkup-sdk",),
    ),
    "lumalab": ToolkitAdapter(
        module_path="agno.tools.lumalab",
        class_name="LumaLabTools",
        packages=("lumaai",),
    ),
    "mem0": ToolkitAdapter(
        module_path="agno.tools.mem0",
        class_name="Mem0Tools",
        packages=("mem0ai",),
    ),
    "mlx_transcribe": ToolkitAdapter(
        module_path="agno.tools.mlx_transcribe",
        class_name="MLXTranscribeTools",
        packages=("mlx-whisper",),
    ),
    "moviepy_video": ToolkitAdapter(
        module_path="agno.tools.moviepy_video",
        class_name="MoviePyVideoTools",
        packages=("moviepy", "ffmpeg"),
    ),
    "nano_banana": ToolkitAdapter(
        module_path="agno.tools.nano_banana",
        class_name="NanoBananaTools",
        packages=("google-genai", "Pillow"),
    ),
    "neo4j": ToolkitAdapter(
        module_path="agno.tools.neo4j",
        class_name="Neo4jTools",
        packages=("neo4j",),
    ),
    "newspaper": ToolkitAdapter(
        module_path="agno.tools.newspaper",
        class_name="NewspaperTools",
        packages=("newspaper3k", "lxml-html-clean"),
    ),
    "newspaper4k": ToolkitAdapter(
        module_path="agno.tools.newspaper4k",
        class_name="Newspaper4kTools",
        packages=("newspaper4k", "lxml-html-clean"),
    ),
    "notion": ToolkitAdapter(
        module_path="agno.tools.notion",
        class_name="NotionTools",
        packages=("notion-client",),
    ),
    "openai": ToolkitAdapter(
        module_path="agno.tools.openai",
        class_name="OpenAITools",
        packages=("openai",),
    ),
    "openbb": ToolkitAdapter(
        module_path="agno.tools.openbb",
        class_name="OpenBBTools",
        packages=("openbb",),
    ),
    "opencv": ToolkitAdapter(
        module_path="agno.tools.opencv",
        class_name="OpenCVTools",
        packages=("opencv-python",),
    ),
    "openweather": ToolkitAdapter(
        module_path="agno.tools.openweather",
        class_name="OpenWeatherTools",
        packages=("requests",),
    ),
    "oxylabs": ToolkitAdapter(
        module_path="agno.tools.oxylabs",
        class_name="OxylabsTools",
        packages=("oxylabs",),
    ),
    "pandas": ToolkitAdapter(
        module_path="agno.tools.pandas",
        class_name="PandasTools",
        packages=("pandas",),
    ),
    "parallel": ToolkitAdapter(
        module_path="agno.tools.parallel",
        class_name="ParallelTools",
        packages=("parallel-web",),
    ),
    "postgres": ToolkitAdapter(
        module_path="agno.tools.postgres",
        class_name="PostgresTools",
        packages=("psycopg-binary",),
    ),
    "reddit": ToolkitAdapter(
        module_path="agno.tools.reddit",
        class_name="RedditTools",
        packages=("praw",),
    ),
    "redshift": ToolkitAdapter(
        module_path="agno.tools.redshift",
        class_name="RedshiftTools",
        packages=("redshift-connector",),
    ),
    "replicate": ToolkitAdapter(
        module_path="agno.tools.replicate",
        class_name="ReplicateTools",
        packages=("replicate",),
    ),
    "resend": ToolkitAdapter(
        module_path="agno.tools.resend",
        class_name="ResendTools",
        packages=("resend",),
    ),
    "salesforce": ToolkitAdapter(
        module_path="agno.tools.salesforce",
        class_name="SalesforceTools",
        packages=("simple-salesforce",),
    ),
    "scavio": ToolkitAdapter(
        module_path="agno.tools.scavio",
        class_name="ScavioTools",
        packages=("scavio",),
    ),
    "scrapegraph": ToolkitAdapter(
        module_path="agno.tools.scrapegraph",
        class_name="ScrapeGraphTools",
        packages=("scrapegraph-py",),
    ),
    "seltz": ToolkitAdapter(
        module_path="agno.tools.seltz",
        class_name="SeltzTools",
        packages=("seltz",),
    ),
    "serpapi": ToolkitAdapter(
        module_path="agno.tools.serpapi",
        class_name="SerpApiTools",
        packages=("google-search-results",),
    ),
    "slack": ToolkitAdapter(
        module_path="agno.tools.slack",
        class_name="SlackTools",
        packages=("slack-sdk",),
    ),
    "spider": ToolkitAdapter(
        module_path="agno.tools.spider",
        class_name="SpiderTools",
        packages=("spider-client",),
    ),
    "sql": ToolkitAdapter(
        module_path="agno.tools.sql",
        class_name="SQLTools",
        packages=("sqlalchemy",),
    ),
    "tavily": ToolkitAdapter(
        module_path="agno.tools.tavily",
        class_name="TavilyTools",
        packages=("tavily-python",),
    ),
    "telegram": ToolkitAdapter(
        module_path="agno.tools.telegram",
        class_name="TelegramTools",
        packages=("pyTelegramBotAPI",),
    ),
    "todoist": ToolkitAdapter(
        module_path="agno.tools.todoist",
        class_name="TodoistTools",
        packages=("todoist-api-python",),
    ),
    "trafilatura": ToolkitAdapter(
        module_path="agno.tools.trafilatura",
        class_name="TrafilaturaTools",
        packages=("trafilatura",),
    ),
    "trello": ToolkitAdapter(
        module_path="agno.tools.trello",
        class_name="TrelloTools",
        packages=("py-trello",),
    ),
    "twelvelabs": ToolkitAdapter(
        module_path="agno.tools.twelvelabs",
        class_name="TwelveLabsTools",
        packages=("twelvelabs",),
    ),
    "twilio": ToolkitAdapter(
        module_path="agno.tools.twilio",
        class_name="TwilioTools",
        packages=("twilio",),
    ),
    "valyu": ToolkitAdapter(
        module_path="agno.tools.valyu",
        class_name="ValyuTools",
        packages=("valyu",),
    ),
    "webex": ToolkitAdapter(
        module_path="agno.tools.webex",
        class_name="WebexTools",
        packages=("webexpythonsdk",),
    ),
    "wikipedia": ToolkitAdapter(
        module_path="agno.tools.wikipedia",
        class_name="WikipediaTools",
        packages=("wikipedia",),
    ),
    "x": ToolkitAdapter(
        module_path="agno.tools.x",
        class_name="XTools",
        packages=("tweepy",),
    ),
    "zendesk": ToolkitAdapter(
        module_path="agno.tools.zendesk",
        class_name="ZendeskTools",
        packages=("requests",),
    ),
    "zep": ToolkitAdapter(
        module_path="agno.tools.zep",
        class_name="ZepTools",
        packages=("zep-cloud",),
    ),
    "zep_async": ToolkitAdapter(
        module_path="agno.tools.zep",
        class_name="ZepAsyncTools",
        packages=("zep-cloud",),
    ),
    "youtube": ToolkitAdapter(
        module_path="agno.tools.youtube",
        class_name="YouTubeTools",
        packages=("youtube-transcript-api",),
    ),
    "gemini": ToolkitAdapter(
        module_path="agno.tools.models.gemini",
        class_name="GeminiTools",
        packages=("google-genai",),
    ),
    "groq": ToolkitAdapter(
        module_path="agno.tools.models.groq",
        class_name="GroqTools",
        packages=("groq",),
    ),
    "morph": ToolkitAdapter(
        module_path="agno.tools.models.morph",
        class_name="MorphTools",
        packages=("openai",),
    ),
    "google_bigquery": ToolkitAdapter(
        module_path="agno.tools.google.bigquery",
        class_name="GoogleBigQueryTools",
        packages=("google-cloud-bigquery",),
    ),
    "google_calendar": ToolkitAdapter(
        module_path="agno.tools.google.calendar",
        class_name="GoogleCalendarTools",
        packages=(
            "google-api-python-client",
            "google-auth-httplib2",
            "google-auth-oauthlib",
        ),
    ),
    "google_drive": ToolkitAdapter(
        module_path="agno.tools.google.drive",
        class_name="GoogleDriveTools",
        packages=(
            "google-api-python-client",
            "google-auth-httplib2",
            "google-auth-oauthlib",
        ),
    ),
    "google_sheets": ToolkitAdapter(
        module_path="agno.tools.google.sheets",
        class_name="GoogleSheetsTools",
        packages=(
            "google-api-python-client",
            "google-auth-httplib2",
            "google-auth-oauthlib",
        ),
    ),
    "google_slides": ToolkitAdapter(
        module_path="agno.tools.google.slides",
        class_name="GoogleSlidesTools",
        packages=(
            "google-api-python-client",
            "google-auth-httplib2",
            "google-auth-oauthlib",
        ),
    ),
    "google_maps": ToolkitAdapter(
        module_path="agno.tools.google.maps",
        class_name="GoogleMapTools",
        packages=("googlemaps", "google-maps-places"),
    ),
    "gmail": ToolkitAdapter(
        module_path="agno.tools.google.gmail",
        class_name="GmailTools",
        packages=(
            "google-api-python-client",
            "google-auth-httplib2",
            "google-auth-oauthlib",
        ),
    ),
    "brightdata": ToolkitAdapter(
        module_path="agno.tools.brightdata",
        class_name="BrightDataTools",
        packages=("requests",),
    ),
}
