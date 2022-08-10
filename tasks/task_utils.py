import os
import re

from datetime import datetime, timedelta

import config, utils


config.load()


def get_task_info(task_id):
	"""
	return task info for the given task_id
	"""
	task_result = AsyncResult(task_id)
	result = {
		"task_id": task_id,
		"task_status": task_result.status,
		"task_result": task_result.result
	}
	return result


def get_user_context():

	return os.getlogin() == "root" and os.getenv("USER") is None


def get_console_user():

	# Get the Console User
	results_console_user = utils.execute_process("/usr/sbin/scutil", "show State:/Users/ConsoleUser")
	return re.sub("(Name : )|(\n)", "", ( re.search("Name : .*\n", results_console_user["stdout"])[0] ))


def check_recipe_schedule(interval, last_ran):
	"""Check if a recipe should be ran, based on the configured schedule.

	Args:
		interval (int): The "schedule" in number of days to not for
		last_ran (str): datetime object in str format when repice was last ran

	Returns:
		boolean:
			True:  Recipe should be ran
			False:  Recipe should not be ran
	"""

	if interval != 0 and last_ran != None:

		current_time = utils.utc_to_local(datetime.now())
		last_ran_time = datetime.fromisoformat(last_ran)
		interval_in_hours = interval * 24

		return current_time - last_ran_time > timedelta(hours=interval_in_hours)

	return True


def api_url_helper():

	secure = "s" if config.pkgbot_config.get("PkgBot.enable_ssl") else ""
	pkgbot_server = f"http{secure}://{config.pkgbot_config.get('PkgBot.host')}:{config.pkgbot_config.get('PkgBot.port')}"
	headers = { "Content-Type": "application/json" }
	return pkgbot_server, headers
