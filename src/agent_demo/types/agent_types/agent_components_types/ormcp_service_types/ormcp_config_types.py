import os
import re

from pydantic import BaseModel, Field
from typing import Optional
from typing_extensions import Literal
from agent_demo.common.json_loader import JSONLoader
from agent_demo.common.project_env import load_project_dotenv
from mcp import StdioServerParameters
from rich.table import Table
import logging

logger = logging.getLogger(__name__)
ENV_PLACEHOLDER_PATTERN = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


class ORMCPServiceConfig(BaseModel):
    connection_type: Literal["STDIO", "SSE"] = Field(default="STDIO")
    command: str
    need_activation: bool = False
    description: dict[str, str] = Field(default_factory=dict)
    args: list[str] = Field(default_factory=list)
    url: Optional[str] = Field(default=None)
    env: Optional[dict[str, str]] = Field(default=None)
    cwd: Optional[str] = Field(default=None)

    def rich_table(self) -> Table:
        table: Table = Table(title="service", show_lines=False, box=None, expand=False)
        table.add_column("Field", style="cyan", no_wrap=True)
        table.add_column("Value", style="magenta")
        table.add_row("Connection Type", str(self.connection_type))
        table.add_row("Command", self.command)
        table.add_row("Need Activation", str(self.need_activation))
        table.add_row("Description_cn", str(self.description_cn))
        table.add_row("Description_en", str(self.description_en))
        table.add_row("Arguments", str(self.args))
        table.add_row("URL", str(self.url) if self.url else "N/A")
        table.add_row("Environment", str(self.env) if self.env else "N/A")
        table.add_row("CWD", str(self.cwd) if self.cwd else "N/A")
        return table

    @property
    def description_cn(self) -> str:
        return self.description.get("simple_cn", "")

    @property
    def description_en(self) -> str:
        return self.description.get("simple_en", "")

    @classmethod
    def load_from_json(cls, file_abspath: str) -> dict[str, "ORMCPServiceConfig"]:
        # 使用 JSONLoader 加载 JSON 文件
        data: dict = JSONLoader.load(file_abspath)
        # 检查 JSON 结构是否符合预期
        if not data or "ORMCPServices" not in data:
            raise ValueError("The JSON file structure is invalid or missing 'mcpServers' key.")
        # 提取服务器配置
        services_data: Optional[dict[str, dict]] = data.get("ORMCPServices", None)
        if services_data is None:
            raise ValueError("The JSON file structure is invalid or missing'services' key.")
        # 创建字典，键是服务器名称，值是 ORMCPServiceConfig 对象
        config_dict: dict[str, "ORMCPServiceConfig"] = {}
        for service_name, service_config in services_data.items():
            desc: dict = service_config.get("description", {})
            if len(desc.get("simple_cn", "")) <= 10:
                raise ValueError(f"The Len({desc}) of description({service_name}) must > 10.")

            config_dict[service_name] = ORMCPServiceConfig(
                connection_type=service_config.get("connection_type", "STDIO"),
                command=service_config.get("command", ""),
                description=desc,
                need_activation=service_config.get("need_activation", False),
                args=service_config.get("args", []),
                url=service_config.get("url", None),
                env=service_config.get("env", None),
                cwd=service_config.get("cwd", None),
            )
            logger.debug(f"Loaded config for service: {service_name}")

        return config_dict

    def resolved_env(self) -> Optional[dict[str, str]]:
        if not self.env:
            return None

        load_project_dotenv()
        resolved_env: dict[str, str] = {}
        for key, value in self.env.items():
            match = ENV_PLACEHOLDER_PATTERN.fullmatch(value)
            if match is None:
                resolved_env[key] = value
                continue

            env_name = match.group(1)
            env_value = os.getenv(env_name, "")
            if env_value:
                resolved_env[key] = env_value
            else:
                logger.warning("Environment variable %s is not set; skipping %s.", env_name, key)

        return resolved_env or None

    def to_stdio_service_parameters(self) -> StdioServerParameters:
        return StdioServerParameters(command=self.command, args=self.args, env=self.resolved_env(), cwd=self.cwd)
