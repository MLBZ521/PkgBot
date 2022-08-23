import argparse
import os
import yaml

from functools import lru_cache

from pydantic import BaseSettings
from pydantic.env_settings import SettingsSourceCallable


def yml_config_setting(settings: BaseSettings):

	with open(settings.__config__.config_file) as file:
		return yaml.safe_load(file)


def instantiate_config():

	class PkgBot_Configuration(BaseSettings):

		class Config:

			arbitrary_types_allowed = True
			config_file = os.environ.get("PKGBOT_CONFIG")
			env_prefix = "PKGBOT_"
			# allow extra options so we can detect legacy configuration files
			extra = "allow"

			@classmethod
			def customise_sources(
				cls,
				init_settings: SettingsSourceCallable,
				env_settings: SettingsSourceCallable,
				file_secret_settings: SettingsSourceCallable,
			):
				# Add load from yml file, change priority and remove file secret option
				return init_settings, yml_config_setting, env_settings

	return PkgBot_Configuration


@lru_cache()
def load_config(cli_args=None):

	# print(f'PkgBot.Load_Config:\n\tAll calling args:  {cli_args}')

	parser = argparse.ArgumentParser(description="PkgBot Main.")
	parser.add_argument(
		'--pkgbot_config', '-pc', metavar='./pkgbot.config', default=None, 
		type=str, required=False, help='A defined pkgbot configuration file.'
	)
	args, _ = parser.parse_known_args(cli_args)

	# print(f'PkgBot.Load_Config:\n\tArgparse args:  {args}')

	pkg_dir = os.path.abspath(os.path.join(os.path.abspath(os.path.dirname(__file__)), os.pardir))
	config_file = (
		args.pkgbot_config or 
		os.environ.get(
			"PKGBOT_CONFIG", 
			os.path.join(pkg_dir, "Settings/pkgbot_config.yaml")
		)
	)

	if not os.path.exists(config_file):
		raise("The specified config file does not exist.")

	os.environ["PKGBOT_CONFIG"] = config_file

	PkgBot_Configuration = instantiate_config()

	return PkgBot_Configuration()
