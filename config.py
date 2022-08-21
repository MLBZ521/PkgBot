import os
import sys
import yaml

from functools import lru_cache


class PkgBot_Configuration(dict):

	def __init__(self, **kwargs):

		cwd = os.path.abspath(os.path.dirname(__file__))

		config_file = (
			kwargs.get('pkgbot_config') or 
			os.environ.get('PKGBOT_CONFIG', os.path.join(cwd, "examples/settings/pkgbot_config.yaml"))
		)

		if os.path.exists(config_file):

			with open(os.path.abspath(config_file), "rb") as yaml_file:
				configuration = yaml.safe_load(yaml_file)

		else:

			print("\nError:  Unable to load configuration.\n")
			sys.exit(1)

		for section in configuration:

			for key in configuration.get(section):

				value = configuration[section].get(key)

				# Set defaults if not defined
				if key == "AutoPkg.binary" and value is None:
					value = "/usr/local/bin/autopkg"

				elif key == "Git.binary" and value is None:
					value = "/usr/bin/git"

				self[f"{section}.{key}"] = value


@lru_cache()
def load(**kwargs):
	return PkgBot_Configuration(**kwargs)
