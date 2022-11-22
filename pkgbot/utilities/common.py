import asyncio
import hashlib
import hmac
import logging.config
import os
# import pickle
import plistlib
import re
import shlex
import subprocess
import yaml

from datetime import datetime, timezone
from distutils.util import strtobool

# from sqlalchemy import create_engine
# from sqlalchemy.orm import sessionmaker

from pkgbot import config


config = config.load_config()


def log_setup(name="PkgBot"):

	logger = logging.getLogger(name)

	if not logger.hasHandlers():
		logger.debug("LOGGER HAS NO HANDLERS!")

		# Get the log configuration
		log_config = yaml.safe_load(f"{config.PkgBot.get('log_config')}")

		# Load log configuration
		logging.config.dictConfig(log_config)

	else:
		logger.debug("Logger has handlers!")

	# Create logger
	return logger


log = log_setup()


async def execute_process(command, input=None):
	"""
	A helper function for asyncio's subprocess.

	Args:
		command (str):  The command line level syntax that would be
			written in shell or a terminal window.
	Returns:
		Results in a dictionary.
	"""

	# Validate that command is not a string
	if not isinstance(command, str):
		raise TypeError('Command must be a str type')

	# Format the command
	# command = shlex.quote(command)

	# Run the command
	process = await asyncio.create_subprocess_shell(
		command, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
		stderr=asyncio.subprocess.PIPE)

	if input:
		(stdout, stderr) = await process.communicate(input=bytes(input, "utf-8"))
	else:
		(stdout, stderr) = await process.communicate()

	return {
		"stdout": (stdout.decode()).strip(),
		"stderr": (stderr.decode()).strip() if stderr != None else None,
		"status": process.returncode,
		"success": True if process.returncode == 0 else False
	}


async def ask_yes_or_no(question):
	"""Ask a yes/no question via input() and determine the value of the answer.

	Args:
		question:  A string that is written to stdout

	Returns:
		True of false based on the users' answer.

	"""

	print(f"{question} [Yes/No] ", end="")

	while True:
		try:
			return strtobool(input().lower())
		except ValueError:
			print("Please respond with [yes|y] or [no|n]: ", end="")


async def plist_reader(plistFile):
	"""A helper function to get the contents of a Property List.
	Args:
		plistFile:  A .plist file to read in.
	Returns:
		stdout:  Returns the contents of the plist file.
	"""

	if os.path.exists(plistFile):
		with open(plistFile, "rb") as plist:
			plist_contents = plistlib.load(plist)
		return plist_contents


async def utc_to_local(utc_dt):

	return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)


async def string_to_datetime(datetime_string: str, format_string: str = "%Y-%m-%d %H:%M:%S.%f"):

	return datetime.strptime(datetime_string, format_string)


async def datetime_to_string(datetime_string: str, format_string: str = "%Y-%m-%d %I:%M:%S"):

	converted = datetime.fromisoformat(datetime_string)
	return converted.strftime(format_string)


async def compute_hex_digest(key: bytes,
	message: bytes, hash: hashlib._hashlib.HASH = hashlib.sha256):

	return hmac.new(key, message, hash).hexdigest()


async def load_yaml(config_file):

	# Load the recipe config
	with open(config_file, 'rb') as config_file_path:
		return yaml.safe_load(config_file_path)


async def save_yaml(contents, config_file):
	"""Writes the passed dict to the passed file.

	Args:
		contents (dict):  a updated dict object of recipes
		config_file (str):  path to the configuration file to update
	"""

	with open(config_file, 'w', encoding="utf8") as config_file_path:
		yaml.dump(contents, config_file_path)


async def replace_sensitive_strings(message, sensitive_strings=None, sensitive_regex_strings=None):
	"""Redact sensitive strings, such as passwords, serial numbers, license keys, etc. before
	exporting to a non-secure location.

	Args:
		message (str, Any): A message that could contain sensitive strings.  If `message` is not a
			string, it will be "converted" to a string via `str(message)`.
		sensitive_strings (str, optional): A string of sensitive strings, separated by a `|` (pipe).
			These strings will be Regex escaped.  Defaults to None.
		sensitive_regex_strings (str, optional): A string of sensitive strings in Regex format,
			separated by a `|` (pipe).  Defaults to None.
	"""


	async def parse_for_sensitive_keys(a_dict: dict, sensitive_key_names: str):

		found_sensitive_strings = ""

		for key, value in a_dict.items():

			if re.search(rf".*({sensitive_key_names}).*", key, re.IGNORECASE) and value:

				if found_sensitive_strings:
					found_sensitive_strings = "|".join([found_sensitive_strings, re.escape(value)])
				else:
					found_sensitive_strings = re.escape(value)

		return found_sensitive_strings


	def parse_dict(message: dict, all_sensitive_strings: str):
		"""Parse a dict object and replace sensitive strings if required.

		Args:
			message (dict): Object that will be parsed.

		Returns:
			(any): The received object will be returned, modified if required.
		"""

		if isinstance(message, dict):

			for key, value in message.items():
				if value is not None:

					if isinstance(value, (bool, int)):
						return value

					elif isinstance(value, dict):
						message[key] = parse_dict(value, all_sensitive_strings)

					else:
						message[key] = re.sub(rf"{all_sensitive_strings}", '<redacted>', value)

		return message


	all_sensitive_strings = r"bearer\s[\w+.-]+|"
	sensitive_key_names = r"password|secret|license|serial|key"

	if config.Common.get("additional_sensitive_key_names"):
		sensitive_key_names += f"|{config.Common.get('additional_sensitive_key_names')}"

	for plist in [
		config.JamfPro_Prod.get("autopkg_prefs"),
		config.JamfPro_Dev.get("autopkg_prefs")
	]:
		plist_contents = await plist_reader(plist)
		all_sensitive_strings += await parse_for_sensitive_keys(plist_contents, sensitive_key_names)

	for string in [
		config.Common.get("redaction_strings"),
		sensitive_regex_strings
	]:
		if string:
			all_sensitive_strings = "|".join([all_sensitive_strings, string])

	for string in [
		config.JamfPro_Dev.get("api_user"),
		config.JamfPro_Dev.get("api_password"),
		config.JamfPro_Dev.get("dp1_user"),
		config.JamfPro_Dev.get("dp1_password"),
		config.JamfPro_Prod.get("api_user"),
		config.JamfPro_Prod.get("api_password"),
		config.JamfPro_Prod.get("dp1_user"),
		config.JamfPro_Prod.get("dp1_password"),
		sensitive_strings
	]:
		if string:
			all_sensitive_strings = "|".join([all_sensitive_strings, re.escape(string)])

	if isinstance(message, str):
		return re.sub(rf"{all_sensitive_strings}", '<redacted>', message)

	elif isinstance(message, dict):

		return parse_dict(message, all_sensitive_strings)

	else:
		log.warning(
			f"Unaccounted for type in sensitive string substitution!  Type is:  {type(message)}")
		return re.sub(rf"{all_sensitive_strings}", '<redacted>', str(message))


# async def get_task_results(task_id: str):

# 	# https://docs.sqlalchemy.org/en/14/core/engines.html#sqlite
# 	db_engine = create_engine(f"sqlite:///{config.Database.get('location')}")
# 	Session = sessionmaker(db_engine)

# 	with Session() as session:
# 		result = session.execute(f"SELECT result from celery_taskmeta where task_id = '{task_id}';").fetchone()

# 	return pickle.loads(result.result)


async def find_receipt_plist(content: str):

	run_receipt = re.search(r'Receipt written to (.*)', content)[1]
	return await plist_reader(run_receipt)


async def parse_recipe_receipt(content: dict, key: str):

	for step in reversed(content):
		if step.get(key):
			return step.get(key)
		elif re.search(key, step.get("Processor"), re.IGNORECASE):
			return step
