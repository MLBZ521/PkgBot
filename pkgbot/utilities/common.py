import asyncio
import hashlib
import hmac
import logging.config
import os
import pickle
import plistlib
import re
import shlex
import subprocess
import yaml

from datetime import datetime, timezone, tzinfo
from distutils.util import strtobool

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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


async def run_process_async(command, input=None):
	"""
	A helper function for asyncio's subprocess.

	Args:
		command:  The command line level syntax that would be
			written in shell or a terminal window.  (str)
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


def execute_process(command, input=None):
	"""
	A helper function for subprocess.

	Args:
		command:  The command line level syntax that would be
			written in shell or a terminal window.  (str)
	Returns:
		Results in a dictionary.
	"""

	# Validate that command is not a string
	if not isinstance(command, str):
		raise TypeError('Command must be a str type')

	# Format the command
	# command = shlex.quote(command)

	# Run the command
	process = subprocess.Popen(
		command, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
		stderr=subprocess.PIPE)

	if input:
		(stdout, stderr) = process.communicate(input=bytes(input, "utf-8"))

	else:
		(stdout, stderr) = process.communicate()

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

		return plist_Contents


async def utc_to_local(utc_dt):

	return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)


async def string_to_datetime(datetime_string: str, format_string: str = None):

	if not format_string:
		format_string = "%Y-%m-%d %H:%M:%S.%f"

	return datetime.strptime(datetime_string, format_string)


async def datetime_to_string(datetime_string: str, format_string: str = None):

	if not format_string:
		format_string = "%Y-%m-%d %I:%M:%S"

	converted = datetime.fromisoformat(datetime_string)

	return converted.strftime(format_string)


async def compute_hex_digest(key: bytes, message: bytes, hash: '_hashlib.HASH' = hashlib.sha256):

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


async def replace_sensitive_strings(message, sensitive_strings=None):

	default_sensitive_strings = r'{}|{}|{}|{}|{}|{}|{}|{}|{}|{}'.format(
		config.JamfPro_Dev.get("api_user"),
		config.JamfPro_Dev.get("api_password"),
		config.JamfPro_Dev.get("dp1_user"),
		config.JamfPro_Dev.get("dp1_password"),
		config.JamfPro_Prod.get("api_user"),
		config.JamfPro_Prod.get("api_password"),
		config.JamfPro_Prod.get("dp1_user"),
		config.JamfPro_Prod.get("dp1_password"),
		config.Common.get("RedactionStrings"),
		r"bearer\s[\w+.-]+"
	)

	if sensitive_strings:

		default_sensitive_strings = f"{default_sensitive_strings}|{sensitive_strings}"

	return re.sub(default_sensitive_strings, '<redacted>', message)


async def get_task_results(task_id: str):

	db_engine = create_engine(f"sqlite://{config.Database.get('location')}")
	Session = sessionmaker(db_engine)

	with Session() as session:
		result = session.execute(f"SELECT result from celery_taskmeta where id = {task_id};").fetchone()

	return pickle.loads(result)


async def find_receipt_plist(content):

	run_receipt = re.search(r'Receipt written to (.*)', content)[1]
	return await plist_reader(run_receipt)


async def parse_recipe_receipt(content, processor):

	for step in reversed(content):
		if re.search(processor, step.get("Processor"), re.IGNORECASE):
			return step
