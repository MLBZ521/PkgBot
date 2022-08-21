import asyncio
import hashlib
import json
import os
import requests

import git
from celery import Celery, group, chain

import config, utilities.common as utility

from tasks import task_utils
import settings

import time  # Was used for testing tasks


config.load()
log = utility.log

celery = Celery()
celery.config_from_object(settings.celery.settings)


@celery.task(name="send_webhook", namebind=True)
def send_webhook(task_id):
	""" Sends webhook after a task is complete. """

	pkgbot_server, headers = task_utils.api_url_helper()

	data = {
		"task_id": task_id
		# "recipe_id": recipe_id,
		# "status": "Failed",
		# "task_type": "generic",
		# "stdout": parent_task_results["stdout"],
		# "stderr": parent_task_results["stderr"],
	}

	headers["x-pkgbot-signature"] = asyncio.run(utility.compute_hex_digest(
		config.pkgbot_config.get('PkgBot.webhook_secret').encode("UTF-8"),
		str(data).encode("UTF-8"),
		hashlib.sha512
	))

	requests.post(f"{pkgbot_server}/autopkg/receive",
		headers=headers,
		data=json.dumps(data),
	)


@celery.task(name="git:pull_private_repo", bind=True)
def git_pull_private_repo(self):
	"""Perform a `git pull` for the local private repo"""

	log.info("Checking for private repo updates...")

	# console_user = task_utils.get_console_user()

# 	git_pull_command = "{binary} -C \"{path}\" switch main > /dev/null && {binary} -C \"{path}\" pull && $( {binary} -C \"{path}\" rev-parse --verify trust-updates > /dev/null 2>&1 && {binary} -C \"{path}\" switch trust-updates > /dev/null || {binary} -C \"{path}\" switch -c trust-updates > /dev/null )".format(
# 		binary=config.pkgbot_config.get("Git.binary"),
# 		path=f"/Users/{console_user}/Library/AutoPkg/RecipeOverrides/"
# ##### Set this path in a config file some where?
# 	)

	# if task_utils.get_user_context():
	# 	git_pull_command = f"su - {console_user} -c \"{git_pull_command}\""

	# results_git_pull_command = utility.execute_process(git_pull_command)

	try:

		private_repo = git.Repo(os.path.expanduser(config.pkgbot_config.get("Git.local_repo_dir")))
		private_repo.git.checkout(config.pkgbot_config.get("Git.repo_primary_branch"))
		private_repo.remotes.origin.pull()

		if private_repo.is_dirty():
			if config.pkgbot_config.get("Git.repo_push_branch") not in private_repo.branches:
				private_repo.git.branch(config.pkgbot_config.get("Git.repo_push_branch"))
			private_repo.git.checkout(config.pkgbot_config.get("Git.repo_push_branch"))

		results_git_pull_command = {
			"stdout": "Success",
			"stderr": "",
			"status": 0,
			"success": True
		}

		log.info("Successfully updated private repo")

	except Exception as error:

		results_git_pull_command = {
			"stdout": "Error occurred during git operation",
			"stderr": error,
			"status": 1,
			"success": False
		}

##### This if statement could likely be removed...
	if not results_git_pull_command["success"]:
		log.error(f"stdout:\n{results_git_pull_command['stdout']}")
		log.error(f"stderr:\n{results_git_pull_command['stderr']}")

	results_git_pull_command["event"] = "private_git_pull"
	return results_git_pull_command


@celery.task(name="autopkg:repo_update", bind=True)
def autopkg_repo_update(self):
	"""Performs an `autopkg repo-update all`"""

	log.info("Updating parent recipe repos...")

	autopkg_repo_update_command = f"{config.pkgbot_config.get('AutoPkg.binary')} repo-update all --prefs=\"{os.path.abspath(config.pkgbot_config.get('JamfPro_Dev.autopkg_prefs'))}\""

	if task_utils.get_user_context():
		autopkg_repo_update_command = f"su - {task_utils.get_console_user()} -c \"{autopkg_repo_update_command}\""

	results_autopkg_repo_update = utility.execute_process(autopkg_repo_update_command)
	results_autopkg_repo_update["event"] = "autopkg_repo_update"

	if not results_autopkg_repo_update["success"]:
		log.error("Failed to update parent recipe repos")
		log.error(results_autopkg_repo_update['stderr'])

	return results_autopkg_repo_update


@celery.task(name="autopkg:run", bind=True)
def autopkg_run(self, recipes: list, options: dict):
	"""Creates parent and individual recipe tasks.

	Args:
		recipe (str): Recipe ID of a recipe
		options (str):

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	log.debug(f"recipes:  {recipes}")
	# time.sleep(30) ## Used in testing tasks

	promote = options.pop("promote", False)

	if not promote:

		# Run checks if we're not promoting the recipe
##### Method 1 to run parent tasks
		# task_autopkg_repo_update = autopkg_repo_update.apply_async(queue='autopkg', priority=3).get(disable_sync_subtasks=False)
		# task_private_repo_update = git_pull_private_repo.apply_async(queue='autopkg', priority=3).get(disable_sync_subtasks=False)
##### Method 2 to run parent tasks -- likely final
		tasks = [
			autopkg_repo_update.signature(),
##### Disabled for testing
			# git_pull_private_repo.signature()
		]

		task_group = group(tasks)
		task_group_results = task_group.apply_async(queue='autopkg', priority=3)
		task_results = task_group_results.get(disable_sync_subtasks=False)

		# log.debug(f"task_results:  {task_results}")
		# log.debug(f"task_results.type:  {type(task_results)}")
		# log.debug(f"task_results.dir:  {dir(task_results)}")

		# Check results
		for task_result in task_results:

			if not task_result["success"]:

				send_webhook.apply_async((self.request.parent_id,), queue='autopkg', priority=2)

				return task_result

	for a_recipe in recipes:

		log.debug(f"a_recipe:  {a_recipe}")
		recipe_id = a_recipe.get("recipe_id")

		if not promote:
			log.debug("Not a promote run...")

			if (
				a_recipe.get("enabled") and 
				task_utils.check_recipe_schedule(a_recipe.get("schedule"), a_recipe.get("last_ran"))
			):

				# Verify trust info and wait
##### Method 1 to run parent task
				# task_autopkg_verify_trust = autopkg_verify_trust.apply_async((recipe_id, options), queue='autopkg', priority=7).get(disable_sync_subtasks=False)
				# task_autopkg_verify_trust.wait()

##### Method 3 to run parent task -- likely final
				recipe_run = chain(
					autopkg_verify_trust.signature((recipe_id, options)) | run_recipe.signature((recipe_id, options))
				)()

##### Need to determine which method will be used here
				# recipe_run.apply_async(queue='autopkg', priority=7, immutable=True)
##### Possible alternate method:
				# autopkg_verify_trust.apply_async((recipe_id, options), queue='autopkg', priority=7, link=run_recipe.apply_async((recipe_id, options), queue='autopkg', priority=7))

		else:
			log.debug(f"Promoting to production: {options['match_pkg']}")

##### Some changes need to be made to the below call for "promoting."
	# Working on this
		# Getting close (I think) -- testing my need to be performed

			# options["prefs"] = os.path.abspath(config.pkgbot_config.get("JamfPro_Prod.autopkg_prefs"))
			# options["promote_recipe_id"] = a_recipe.get("recipe_id")
			# extra_options = "--ignore-parent-trust-verification-errors"

			options |= {
				"ignore_parent_trust": True,
				"prefs": os.path.abspath(config.pkgbot_config.get("JamfPro_Prod.autopkg_prefs")),
				"promote_recipe_id": a_recipe.get("recipe_id"),
				"verbose": options.get('verbose', 'vv')
			}

			if a_recipe.get("pkg_only"):
				# Only upload the .pkg, do not create/update a Policy
				recipe_id = config.pkgbot_config.get("JamfPro_Prod.recipe_template_pkg_only")
				# extra_options = "{} --key PKG_ONLY=True".format(extra_options)
				options |= { "pkg_only": True }
			else:
				recipe_id = config.pkgbot_config.get("JamfPro_Prod.recipe_template")

##### Not yet supported
			# if options["override_keys"]:
			# 	for override_key in options["override_keys"]:
			# 		extra_options = f"{extra_options} --key '{override_key}'"

##### How will the extra_options be passed?
			run_recipe.apply_async(({"promote": True}, recipe_id, options), queue='autopkg', priority=6)
		# run_recipe.apply_async((None, {"recipe_id": recipe_id, "options": options}), queue='autopkg', priority=6)


@celery.task(name="autopkg:run_recipe", bind=True)
def run_recipe(self, parent_task_results: dict, recipe_id: str, options: dict, extra_args: str = None): #, run_type: str = "dev"):
	"""Runs the passed recipe id against `autopkg run`.

	Args:
		recipe (str): Recipe ID of a recipe
		options (str):

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	run_type = "recipe_run_prod" if parent_task_results.get("promote") else "recipe_run_dev"

	# Verify not a promote run, and parent tasks results were success
	if (
		run_type != "recipe_run_prod"
		and parent_task_results
		and not parent_task_results["success"]
	):

		# event_id = ""

		if f"{recipe_id}: FAILED" in parent_task_results["stderr"]:
			log_msg = "Failed to verify trust info for"
			event_type = "failed_trust"

		elif "Didn't find a recipe for" in parent_task_results["stdout"]:
			log_msg = "Failed to locate"
			event_type = "error"

		else:
			# Generic error
			log_msg = "Unknown failure occurred on"
			event_type = "error"

		log.error(f"{log_msg} recipe: {recipe_id}")

		send_webhook.apply_async((self.request.parent_id,), queue='autopkg', priority=2)
		return {
			"event": event_type,
			# "event_id": event_id,
			"recipe_id": recipe_id,
			"success": parent_task_results["success"],
			"stdout": parent_task_results["stdout"],
			"stderr": parent_task_results["stderr"],
		}

	else:

		log.info(f"Creating `autopkg run` task for recipe:  {recipe_id}")

		# Generate options
		options = task_utils.generate_autopkg_args(**options)

		# Build the autopkg command
		cmd = f"{config.pkgbot_config.get('AutoPkg.binary')} run {recipe_id} {options}"

		if task_utils.get_user_context():
			cmd = f"su - {task_utils.get_console_user()} -c \"{cmd}\""

		log.debug(f"Command to execute:  {cmd}")

		results = utility.execute_process(cmd)

		# Send task complete notification
		send_webhook.apply_async((self.request.id,), queue='autopkg', priority=4)

		return {
			"event": run_type,
			# "event_id": trust_id,
			"recipe_id": recipe_id,
			"success": results["success"],
			"stdout": results["stdout"],
			"stderr": results["stderr"],
		}


@celery.task(name="autopkg:verify-trust", bind=True)
def autopkg_verify_trust(self, recipe_id: str, options: dict, source: str):
	"""Runs the passed recipe id against `autopkg verify-trust-info`.

	Args:
		recipe (str): Recipe ID of a recipe
		options (dict):

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	log.info(f"Verifying trust info for:  {recipe_id}")

	# Not overriding verbose when verifying trust info
	_ = options.pop('verbose')

	options |= {
		"prefs": os.path.abspath(config.pkgbot_config.get("JamfPro_Dev.autopkg_prefs")),
		"verbose": "vvv"
	}

	# Generate options
	options = task_utils.generate_autopkg_args(**options)

	cmd = f"{config.pkgbot_config.get('AutoPkg.binary')} verify-trust-info {recipe_id} {options}"

	if task_utils.get_user_context():
		cmd = f"su - {task_utils.get_console_user()} -c \"{cmd}\""

	log.debug(f"Command to execute:  {cmd}")

	if source == "api_direct":
		results = utility.execute_process(cmd)

		send_webhook.apply_async((self.request.id,), queue='autopkg', priority=4)

		return {
			"event": "update_trust_info",
			"recipe_id": recipe_id,
			"success": results["success"],
			"stdout": results["stdout"],
			"stderr": results["stderr"],
		}

	return utility.execute_process(cmd)


@celery.task(name="autopkg:update-trust", bind=True)
def autopkg_update_trust(self, recipe_id: str, options: dict, trust_id: int = None):
	"""Runs the passed recipe id against `autopkg update-trust-info`.

	Args:
		recipe (str): Recipe ID of a recipe
		options (str):

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	log.info(f"Updating trust info for:  {recipe_id}")

	# Generate options
	options = task_utils.generate_autopkg_args(
		prefs=os.path.abspath(config.pkgbot_config.get("JamfPro_Dev.autopkg_prefs")))

	cmd = f"{config.pkgbot_config.get('AutoPkg.binary')} update-trust-info {recipe_id} {options}"

	if task_utils.get_user_context():
		cmd = f"su - {task_utils.get_console_user()} -c \"{cmd}\""

	log.debug(f"Command to execute:  {cmd}")

	results = utility.execute_process(cmd)

	send_webhook.apply_async((self.request.id,), queue='autopkg', priority=4)

	return {
		"event": "update_trust_info",
		"event_id": trust_id,
		"recipe_id": recipe_id,
		"success": results["success"],
		"stdout": results["stdout"],
		"stderr": results["stderr"],
	}
