import os
import yaml
import sys

from abc import abstractmethod
from functools import lru_cache
from typing import Any, Dict, Tuple, Type

from pydantic import BaseModel
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic_settings.sources import EnvSettingsSource
from pydantic.fields import FieldInfo

from .settings.config_models import (
	AutoPkg,
	Celery,
	Database,
	JamfPro_Dev,
	JamfPro_Prod,
	Git,
	Services,
	Slack,
	PkgBot,
	Common
)


class BaseFileConfigSettingsSource(PydanticBaseSettingsSource):
	def __init__(self, settings_cls: Type[BaseSettings], path: str):
		super().__init__(settings_cls)
		self._data = self.load_file(path)

	@abstractmethod
	def load_file(self, path: str) -> Dict[str, Any]:
		pass

	def get_field_value(
		self, field: FieldInfo, field_name: str
	) -> Tuple[Any, str, bool]:
		if field_name in self._data:
			return self._data[field_name], field_name, True
		else:
			return field.default, field_name, False

	def __call__(self) -> Dict[str, Any]:
		settings = {}
		for field_name, field in self.settings_cls.model_fields.items():
			value, _, _ = self.get_field_value(field, field_name)
			settings[field_name] = value
		return settings


class YamlConfigSettingsSource(BaseFileConfigSettingsSource):
	def load_file(self, path: str) -> Dict[str, Any]:
		with open(path, "r") as f:
			return yaml.safe_load(f)


class CliArgsSource(EnvSettingsSource):
	def __init__(self, settings_cls: Type[BaseSettings], prefix: str = "config_"):
		super().__init__(settings_cls, env_prefix=prefix)
		self._prefix = prefix
		self.env_vars = self._load_args()

	def _load_args(self):
		args = sys.argv[1:]
		env_vars = {}
		for i in range(len(args)):
			if args[i].startswith(f"--{self._prefix}"):
				if "=" in args[i]:
					key, value = args[i].split("=")
					key = key[2:].strip()
					env_vars[key] = value.strip()
				elif i + 1 < len(args) and not args[i + 1].startswith("--"):
					key = args[i][2:].strip()
					env_vars[key] = args[i + 1].strip()
		return env_vars


class Settings(BaseSettings):
	AutoPkg: AutoPkg
	Celery: Celery
	Database: Database
	JamfPro_Dev: JamfPro_Dev
	JamfPro_Prod: JamfPro_Prod
	Git: Git
	Services: Services
	Slack: Slack
	PkgBot: PkgBot
	Common: Common
	model_config = SettingsConfigDict(env_prefix="PKGBOT_", env_nested_delimiter="__")


	@classmethod
	def settings_customise_sources(
		cls,
		settings_cls: Type[BaseSettings],
		init_settings: PydanticBaseSettingsSource,
		env_settings: PydanticBaseSettingsSource,
		dotenv_settings: PydanticBaseSettingsSource,
		file_secret_settings: PydanticBaseSettingsSource,
	) -> Tuple[PydanticBaseSettingsSource, ...]:
		return (
			env_settings,
			CliArgsSource(settings_cls, "PKGBOT_"),
			YamlConfigSettingsSource(settings_cls, os.environ.get("PKGBOT_CONFIG")),
			init_settings,
		)


@lru_cache()
def load_config(cli_args=None):

	pkg_dir = os.path.abspath(os.path.join(os.path.abspath(os.path.dirname(__file__)), os.pardir))
	os.environ["PKGBOT_CONFIG"] = os.environ.get(
			"PKGBOT_CONFIG",
			os.path.join(pkg_dir, "Settings/pkgbot_config.yaml")
		)

	return Settings()
