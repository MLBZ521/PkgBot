import os
import sys
import yaml


class PkgBot_Configuration():
	def __init__(self):
		self.config = {}

	def add(self, key, value):

		self.config[key] = value

	def get(self, key):

		return self.config.get(key, None)


def load(args=None, **kwargs):

	# print(f"args:  {args}")
	# print(f"kwargs:  {kwargs}")
	passed_config_file = kwargs.get('pkgbot_config', None)
	# env_config_file = os.environ.get('PKGBOT_CONFIG')
	env_config_file = "./settings/pkgbot_config.yaml"

	# print(f"passed_config_file:  {passed_config_file}")

	if passed_config_file != None and os.path.exists(passed_config_file):
		config_file = passed_config_file

	elif env_config_file != None and os.path.exists(env_config_file):
		config_file = env_config_file

	else:
		print("\nError:  Unable to load configuration.\n")
		sys.exit(1)

	# Read in the configuration file
	with open(config_file, "rb") as yaml_file:
		configuration = yaml.safe_load(yaml_file)

	##################################################
	# Define variables

	PkgBotConfig = PkgBot_Configuration()

	for section in configuration:
		for key in configuration.get(section):
			PkgBotConfig.add(f"{section}.{key}", configuration[section].get(key))

	if configuration.get("AutoPkg").get("binary") is None:
		PkgBotConfig.add("AutoPkg.binary", "/usr/local/bin/autopkg")

	if configuration.get("Git").get("binary") is None:
		PkgBotConfig.add("Git.binary", "/usr/bin/git")

	globals()["pkgbot_config"] = PkgBotConfig.config


if __name__ == "__main__":
	print("Initializing PkgBot Configuration...")
	load()
