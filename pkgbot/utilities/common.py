import asyncio
import csv
import hashlib
import hmac
import logging.config
import os
# import pickle
import plistlib
import re
# import shlex
import shutil
import yaml

from datetime import datetime, timezone
from distutils.util import strtobool
from io import StringIO
from typing import List, Union
from xml.etree import ElementTree
from xml.sax.saxutils import escape

from celery.result import AsyncResult

from fastapi import UploadFile

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


async def get_timestamp(format_string: str = None):

	if format_string:
		return await datetime_to_string(str(datetime.now()), format_string)
	return await datetime_to_string(str(datetime.now()))


async def compute_hex_digest(key: bytes,

	message: bytes, hash: hashlib._hashlib.HASH = hashlib.sha256):
	return hmac.new(key, message, hash).hexdigest()


async def load_yaml_file(config_file):

	# Open a yaml file
	with open(config_file, 'rb') as config_file_path:
		return load_yaml(config_file_path)


async def load_yaml(config_file):

	# Load yaml file
	return yaml.safe_load(config_file)


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


	async def parse_dict(message: dict, all_sensitive_strings: str):
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
						message[key] = value

					elif isinstance(value, (list, set, tuple)):

						if isinstance(value, list):
							new_obj = []
						elif isinstance(value, set):
							new_obj = set()
						elif isinstance(value, tuple):
							new_obj = ()

						for item in value:
							new_obj.append(re.sub(rf"{all_sensitive_strings}", '<redacted>', item))

						message[key] = new_obj

					elif isinstance(value, dict):
						message[key] = await parse_dict(value, all_sensitive_strings)

					else:
						message[key] = re.sub(rf"{all_sensitive_strings}", '<redacted>', str(value))

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

		return await parse_dict(message, all_sensitive_strings)

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


async def split_string(string: str, split_on: str = " ", split_index: int = 1):

	return string.split(split_on, split_index)


async def parse_slash_cmd_options(cmd_text: str, verb: str):

	final_options = {}

	if verb in { "run", "verify-trust-info" }:

		if v_count := re.search(r"-vv+", cmd_text, flags=re.IGNORECASE):
			v_count = re.subn("v", '', v_count[0])[1]
			final_options["verbose"] = f"{'v' * v_count}"

		elif v_count := re.subn(r"\s--verbose|\s-v", '', cmd_text)[1]:
			final_options["verbose"] = f"{'v' * v_count}"

	options_to_parse = await split_string(cmd_text, split_index = -1)
	indexes_to_ignore = []
	overrides = ""

	for index, option in enumerate(options_to_parse):

		if index not in indexes_to_ignore and option in { "-k", "--key" }:

			indexes_to_ignore.append(index + 1)
			override_pair = options_to_parse[index + 1]

			(key, sep, value) = override_pair.partition("=")
			key = re.sub(r'[“”"]', "", key)
			value = re.sub(r'[“”"]', "", value)

			if sep != "=":
				raise Exception(f"Error processing override --key `{override_pair}`")

			overrides = f"{overrides} --key '{key}={value}'"

		if option == "--ignore-parent-trust-verification-errors":
			final_options["ignore_parent_trust"] = True

	if overrides:
		final_options["overrides"] = overrides.lstrip()

	return final_options


class HumanBytes:
	"""
	HumanBytes returns a string of the supplied file size in human friendly format.
	Credit:  Mitch McMabers
	Source:  https://stackoverflow.com/a/63839503
	Notes:  Slightly modified from source
	Returns:
		str: Formatted string
	"""

	METRIC_LABELS: List[str] = ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"]
	BINARY_LABELS: List[str] = ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"]
	PRECISION_OFFSETS: List[float] = [0.5, 0.05, 0.005, 0.0005] # PREDEFINED FOR SPEED.
	PRECISION_FORMATS: List[str] = ["{}{:.0f} {}", "{}{:.1f} {}", "{}{:.2f} {}", "{}{:.3f} {}"] # PREDEFINED FOR SPEED.

	@staticmethod
	def format(num: Union[int, float], metric: bool=False, precision: int=1) -> str:
		"""
		Human-readable formatting of bytes, using binary (powers of 1024)
		or metric (powers of 1000) representation.
		"""

		assert isinstance(num, (int, float)), "num must be an int or float"
		assert isinstance(metric, bool), "metric must be a bool"
		assert isinstance(precision, int) and precision >= 0 and precision <= 3, "precision must be an int (range 0-3)"

		unit_labels = HumanBytes.METRIC_LABELS if metric else HumanBytes.BINARY_LABELS
		last_label = unit_labels[-1]
		unit_step = 1000 if metric else 1024
		unit_step_thresh = unit_step - HumanBytes.PRECISION_OFFSETS[precision]

		is_negative = num < 0
		if is_negative: # Faster than ternary assignment or always running abs().
			num = abs(num)

		for unit in unit_labels:
			if num < unit_step_thresh:
				# VERY IMPORTANT:
				# Only accepts the CURRENT unit if we're BELOW the threshold where
				# float rounding behavior would place us into the NEXT unit: F.ex.
				# when rounding a float to 1 decimal, any number ">= 1023.95" will
				# be rounded to "1024.0". Obviously we don't want ugly output such
				# as "1024.0 KiB", since the proper term for that is "1.0 MiB".
				break
			if unit != last_label:
				# We only shrink the number if we HAVEN'T reached the last unit.
				# NOTE: These looped divisions accumulate floating point rounding
				# errors, but each new division pushes the rounding errors further
				# and further down in the decimals, so it doesn't matter at all.
				num /= unit_step

		return HumanBytes.PRECISION_FORMATS[precision].format("-" if is_negative else "", num, unit)


async def get_disk_usage(disk: str = "/"):
	"""Gets the current disk usage properties and returns them.

	Args:
		disk (str):  Which disk to check

	Returns:
		(tuple): Results in a tuple format (total, used, free)
	"""

	# Get the disk usage
	total, used, free = shutil.disk_usage(disk)

	total_human = HumanBytes.format(total, metric=False, precision=1)
	used_human = HumanBytes.format(used, metric=False, precision=1)
	free_human = HumanBytes.format(free, metric=False, precision=1)

	return (total_human, used_human, free_human)


def _get_task_results(task_id):
	""" Return task info for the given task_id """

	return AsyncResult(task_id)


async def get_task_results(task_id:  str):

	log.debug(f"Checking results for task_id:  {task_id}")
	task_results = _get_task_results(task_id)

	if task_results.status != "SUCCESS":
		return { "current_status":  task_results.status,
				 "current_result": task_results.result }

	elif task_results.result != None:

		if sub_task_ids := (task_results.result).get("Queued background tasks", None):
			sub_tasks = []

			if len(sub_task_ids) == 1:
				return {
					"task_results": await replace_sensitive_strings(
						_get_task_results(sub_task_ids[0]).result)
				}

			for sub_task in sub_task_ids:

				if isinstance(sub_task, AsyncResult):
					sub_task_result = _get_task_results(sub_task.task_id)

				if isinstance(sub_task, str):
					sub_task_result = _get_task_results(sub_task)

				sub_tasks.append({sub_task_result.task_id: sub_task_result.status})

			return { "sub_task_results": sub_tasks }

		elif isinstance(task_results.result, dict):
			return { "task_results": await replace_sensitive_strings(task_results.result) }

	else:
		return { "task_completion_status":  task_results.status }


async def dict_parser(a_dict, key):

	if isinstance(a_dict, dict):

		for k, v in a_dict.items():
			if k == key:
				return v

			if isinstance(v, dict):
				return await dict_parser(v, key)

	elif isinstance(a_dict, list):
		for v in a_dict:
			return await dict_parser(v, key)


async def build_xml(root, parent, child, values, sub_element = None):

	# Create a root element
	root_element = ElementTree.Element(root)

	# Create a parent element in the root element
	parent_element = ElementTree.SubElement(root_element, parent)

	# Create a sub element in the parent element
	if sub_element:
		parent_element = ElementTree.SubElement(parent_element, sub_element)

	# Insert list into child elements
	for item in values:

		# Create a child element
		child_element = ElementTree.SubElement(parent_element, child)

		# Add elements (i.e. attributes) to the child element
		for key, value in item.items():
			name_element = ElementTree.SubElement(child_element, key)
			name_element.text = str(escape(value))

	return root_element


async def save_file(file: UploadFile, save_dir):

	try:
		with open(f"{save_dir}/{file.filename}", "wb") as file_obj:
			shutil.copyfileobj(file.file, file_obj)
	finally:
		await file.close()


async def save_icon(icon: UploadFile):

	static_dir = config.PkgBot.get("jinja_static")
	await save_file(icon, f"{static_dir}/icons")


async def receive_file_upload(file: UploadFile):

	# Read in the file contents
	file_contents = await file.read()
	file.file.close()
	return file_contents


async def parse_csv_contents(csv_file: bytes):

	# Convert the file contents to a file-like object that csv.DictReader can parse
	return csv.DictReader(StringIO(csv_file.decode()))
