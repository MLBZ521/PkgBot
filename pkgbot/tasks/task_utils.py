import os
import re

from datetime import datetime, timedelta

from celery.result import AsyncResult

from pkgbot import config
from pkgbot.utilities import common as utility


config = config.load_config()


def get_task_info(task_id):
	""" Return task info for the given task_id """

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
	results_console_user = utility.execute_process("/usr/sbin/scutil", "show State:/Users/ConsoleUser")
	return re.sub("(Name : )|(\n)", "", ( re.search("Name : .*\n", results_console_user["stdout"])[0] ))


def check_recipe_schedule(interval, last_ran):
	"""Check if a recipe should be ran, based on the configured schedule.

	Args:
		interval (int): The "schedule" in number of days to not for
		last_ran (str): datetime object in str format when recipe was last ran

	Returns:
		boolean:
			True:  Recipe should be ran
			False:  Recipe should not be ran
	"""

	if interval != 0 and last_ran != None:

		current_time = utility.utc_to_local(datetime.now())
		last_ran_time = datetime.fromisoformat(last_ran)
		interval_in_hours = interval * 24

		return current_time - last_ran_time > timedelta(hours=interval_in_hours)

	return True


def api_url_helper():

	secure = "s" if config.PkgBot.get("enable_ssl") else ""
	pkgbot_server = f"http{secure}://{config.PkgBot.get('host')}:{config.PkgBot.get('port')}"
	headers = { "Content-Type": "application/json" }
	return pkgbot_server, headers


def generate_autopkg_args(**kwargs):

	final_opts = ""

	# AutoPkg args
	if kwargs.get("verbose"):
		final_opts = f"{final_opts} -{kwargs.get('verbose')}"
	# else:
	# 	final_opts = f"{final_opts} -vv"

	if kwargs.get("ignore_parent_trust"):
		final_opts = f"{final_opts} --ignore-parent-trust-verification-errors"

	if kwargs.get("prefs"):
		final_opts = f"{final_opts} --prefs=\'{kwargs.get('prefs')}\'"
	else:
		final_opts = f"{final_opts} --prefs=\'{os.path.abspath(config.JamfPro_Dev.get('autopkg_prefs'))}\'"

	# PkgBot args
	if kwargs.get("promote_recipe_id"):
		final_opts = f"{final_opts} --key \'RECIPE_ID={kwargs.get('promote_recipe_id')}\'"

	if kwargs.get("match_pkg"):
		final_opts = f"{final_opts} --key \'MATCH_PKG={kwargs.get('match_pkg')}\'"

	if kwargs.get("pkg_only"):
		final_opts = f"{final_opts} --key \'PKG_ONLY=True\'"

	# if kwargs.get("promote"):
	# 	promote = kwargs.get("promote")
	# 	final_opts = f"{final_opts} --key promote=True"

	return final_opts.lstrip()
