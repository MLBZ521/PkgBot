import asyncio
import hashlib
import json
import os
import requests

import git
from celery import Celery, group, chain

from pkgbot import config, settings
from pkgbot.tasks import task_utils
from pkgbot.utilities import common as utility


config = config.load_config()
log = utility.log
celery = Celery()
celery.config_from_object(settings.celery.settings)


def determine_priority(default: int, ingress: str):

	return default + 1 if ingress == "Slack" else default


def perform_pre_checks(task_id: str, ignore_parent_trust: bool):
	"""Perform pre-checks before running `autopkg run`

	Args:
		task_id (str): Calling tasks' task_id
		ignore_parent_trust (bool): Whether --ignore-parent-trust-verification-info was passed

	Returns:
		dict|list:
			if dict: contains error information from failed pre-checks
			if list: contains child `task_id`s
	"""

	# Track all child tasks that are queued
	queued_tasks = []
	failed_pre_checks = []

	pre_checks = [check_space.signature(), git_pull_private_repo.signature()]

	if not ignore_parent_trust:
		pre_checks.extend([autopkg_repo_update.signature()])

	tasks_results = (
		group(pre_checks).apply_async(queue="autopkg", priority=8)).get(disable_sync_subtasks=False)

	# Check results
	for task_result in tasks_results:

		if not task_result["success"]:
			send_webhook.apply_async((task_id,), queue='autopkg', priority=9)
			failed_pre_checks.append(task_result["task_id"])

		queued_tasks.append(task_result["task_id"])

	if failed_pre_checks:
		return {
			"event": "failed_pre_checks",
			"stdout": "Error",
			"stderr": "Error",
			"status": 1,
			"success": False,
			"task_id": failed_pre_checks
		}

	return queued_tasks


@celery.task(name="pkgbot:send_webhook", namebind=True)
def send_webhook(task_id):
	""" Sends webhook after a task is complete. """

	pkgbot_server, headers = task_utils.api_url_helper()
	data = { "task_id": task_id }

	headers["x-pkgbot-signature"] = asyncio.run(utility.compute_hex_digest(
		config.PkgBot.get("webhook_secret").encode("UTF-8"),
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

	repo_primary_branch = config.Git.get("repo_primary_branch")
	repo_push_branch = config.Git.get("repo_push_branch")
	stashed = False
	use_remote_push = False

	try:

		private_repo = git.Repo(os.path.expanduser(config.Git.get("local_repo_dir")))

		if private_repo.is_dirty():
			_ = private_repo.git.stash()
			stashed = True

		active_branch = private_repo.active_branch
		local_branches = [ branch.name for branch in private_repo.branches ]

		_ = private_repo.remotes.origin.fetch()
		# remote_branches = [ ref.name.split("/")[1] for ref in private_repo.remote().refs ]

		if active_branch != repo_primary_branch:
			_ = private_repo.git.checkout(repo_primary_branch)

			if repo_push_branch in local_branches:
				push_branch_commits_ahead, push_branch_commits_behind = task_utils.compare_branch_heads(
					private_repo, repo_push_branch, repo_primary_branch)

				if push_branch_commits_ahead == 0 and push_branch_commits_behind > 0:
					# private_repo.delete_head(repo_push_branch)
					# For safety, just renaming the branch for now and after a bit of real world
					# testing, switch to deleting the branch
					timestamp = asyncio.run(utility.get_timestamp("%Y-%m-%d_%I-%M-%S"))
					private_repo.branches[repo_push_branch].rename(
						f"{repo_push_branch}_{timestamp}")

				elif push_branch_commits_ahead > 0:
					use_remote_push = True

		primary_branch_commits_ahead, primary_branch_commits_behind = task_utils.compare_branch_heads(
			private_repo, repo_primary_branch, repo_primary_branch)

		if primary_branch_commits_ahead != 0 and repo_primary_branch != repo_push_branch:
			log.error("Local primary branch is ahead of remote primary branch.")
			raise

		_ = private_repo.remotes.origin.pull()

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

	finally:

		if use_remote_push:
			_ = private_repo.git.checkout(repo_push_branch)

		if stashed:
			private_repo.git.stash("pop")

##### This if statement can be removed after further real world testing...
	if not results_git_pull_command["success"]:
		log.error(f"stdout:\n{results_git_pull_command['stdout']}")
		log.error(f"stderr:\n{results_git_pull_command['stderr']}")

	results_git_pull_command |= {
		"event": "private_git_pull",
		"task_id": self.request.id
	}

	return results_git_pull_command


@celery.task(name="autopkg:repo_update", bind=True)
def autopkg_repo_update(self):
	"""Performs an `autopkg repo-update all`"""

	log.info("Updating parent recipe repos...")
	autopkg_repo_update_command = f"{config.AutoPkg.get('binary')} repo-update all --prefs=\'{os.path.abspath(config.JamfPro_Dev.get('autopkg_prefs'))}\'"

	if task_utils.get_user_context():
		autopkg_repo_update_command = f"su - {task_utils.get_console_user()} -c \"{autopkg_repo_update_command}\""

	results_autopkg_repo_update = asyncio.run(utility.execute_process(autopkg_repo_update_command))

##### This if statement can be removed after further real world testing...
	if not results_autopkg_repo_update["success"]:
		log.error("Failed to update parent recipe repos")
		log.error(f"stdout:\n{results_autopkg_repo_update['stdout']}")
		log.error(f"stderr:\n{results_autopkg_repo_update['stderr']}")

	results_autopkg_repo_update |= {
		"event": "autopkg_repo_update",
		"task_id": self.request.id
	}

	return results_autopkg_repo_update


@celery.task(name="pkgbot:check_space", bind=True)
def check_space(self):
	"""Checks free space on PkgBot storage volume"""

	minimum_free_space = config.AutoPkg.get("minimum_free_space")
	warning_free_space = config.AutoPkg.get("warning_free_space")
	cache_volume = config.AutoPkg.get("cache_volume")
	log.debug(f"Checking available free space on:  {cache_volume}")
	current_free_space = asyncio.run(utility.get_disk_usage(cache_volume))[2]
	current_free_space_int, current_free_space_unit = current_free_space.split(" ")
	log.debug(f"Free space:  {current_free_space}")
	success = True
	status = 0

	if current_free_space_unit in {"B", "KB", "MB"} or float(current_free_space_int) <= minimum_free_space:
		event = "disk_space_critical"
		msg = f"Not enough free space available to execute an AutoPkg run:  {current_free_space}"
		success = False
		status = 2
		log.error(msg)

	elif float(current_free_space_int) <= warning_free_space:
		event = "disk_space_warning"
		msg = f"AutoPkg cache volume is running low on disk space:  {current_free_space}"
		status = 1
		log.warning(msg)
		send_webhook.apply_async((self.request.id,), queue="autopkg", priority=9)

	else:
		event = "disk_space_passed"
		msg = "Disk Check:  Passed"

	return {
		"event": event,
		"stdout": msg,
		"stderr": msg,
		"status": status,
		"success": success,
		"task_id": self.request.id
	}


@celery.task(name="autopkg:verb_parser", bind=True)
def autopkg_verb_parser(self, autopkg_cmd: dict, targets: list | str | None = None):
	"""Handles `autopkg` tasks.

	Args:
		autopkg_cmd (dict): Contains options for `autopkg` and details on response method
		targets (list|None): A optional list of recipes (in dicts,
			in which contains their configurations) or AutoPkg recipe repos

	Returns:
		dict:  dict describing the results of the ran process
	"""

	# log.debug(f"Calling autopkg_cmd:  {autopkg_cmd}")
	# log.debug(f"targets:  {targets}")

	# Track all child tasks that are queued by this parent task
	queued_tasks = []

	verb = autopkg_cmd.get("verb")

	if verb in { "repo-add", "update-trust-info", "verify-trust-info", "version"}:

		# if verb == "update-trust-info":
##### TODO:  Add Support
			# pass

		if verb == "verify-trust-info":
			# if recipes == None:
			# if isinstance(recipes, list) and len(recipes) == 1:
			# if isinstance(recipes, str):
			return autopkg_verify_trust(targets, autopkg_cmd, task_id=self.request.id)

		elif verb == "repo-add":
			return autopkg_repo_add(targets, autopkg_cmd, task_id=self.request.id)

		elif verb == "version":
			return autopkg_version(autopkg_cmd, task_id=self.request.id)

		# queued_tasks.append(queued_task.id)

	else:

		if not autopkg_cmd.get("promote"):
			# Run pre-checks if not promoting a pkg
			results_pre_check = perform_pre_checks(self.request.id, autopkg_cmd.get("ignore_parent_trust"))

			if isinstance(results_pre_check, dict):
				# An error occurred in a pre-check
				return results_pre_check

			queued_tasks.extend(results_pre_check)

		results = autopkg_run(targets, autopkg_cmd)
		queued_tasks.extend(results)

	return { "Queued background tasks": queued_tasks }


@celery.task(name="autopkg:run", bind=True)
def autopkg_run(self, recipes: list, autopkg_cmd: dict):
	"""Creates parent and individual recipe tasks.

	Args:
		recipes (list): A list of recipes (in dicts, in which contains their configurations)
		autopkg_cmd (dict): Contains options for `autopkg` and details on response method

	Returns:
		dict:  dict describing the results of the ran process
	"""

	# log.debug(f"Calling autopkg_cmd:  {autopkg_cmd}")
	# log.debug(f"recipes:  {recipes}")

	# Track all child tasks that are queued by this parent task
	queued_tasks = []
	promote = autopkg_cmd.pop("promote", False)

	for recipe in recipes:

		# log.debug(f"recipe:  {recipe}")
		recipe_id = recipe.get("recipe_id")

		if not promote:

			if (
				autopkg_cmd.get("ingress") == "Schedule" and
				not task_utils.check_recipe_schedule(recipe.get("schedule"), recipe.get("last_ran"))
			):
				log.debug(f"Recipe {recipe_id} is out of schedule")
				continue

			_ = autopkg_cmd.pop("match_pkg", None)
			_ = autopkg_cmd.pop("pkg_only", None)
			_ = autopkg_cmd.pop("pkg_id", None)

			# If ignore parent trust, don't run autopkg_verify_trust
			if autopkg_cmd.get("ignore_parent_trust"):

				queued_task = run_recipe.apply_async(
					({"success": True}, recipe_id, autopkg_cmd),
					queue="autopkg",
					priority=determine_priority(3, autopkg_cmd.get("ingress"))
				)

				queued_tasks.append(queued_task.id)

			else:

				# Perform `verify-trust-info` and pass the results to next task.
				# `verify-trust-info` task has a lower priority _here_ so that `recipe_run`
				# tasks can run after; instead of all `verify-trust-info` tasks running first.
				chain_results = chain(
					autopkg_verify_trust.signature(
						(recipe_id, autopkg_cmd),
						queue="autopkg",
						priority=determine_priority(2, autopkg_cmd.get("ingress"))
					) |
					run_recipe.signature(
						(recipe_id, autopkg_cmd),
						queue="autopkg",
						priority=determine_priority(4, autopkg_cmd.get("ingress"))
					)
				)()

				queued_tasks.extend([chain_results.parent, chain_results.task_id])

		else:
			log.info(f"Promoting to production: {autopkg_cmd['match_pkg']}")

			autopkg_cmd |= {
				"ignore_parent_trust": True,
				"prefs": os.path.abspath(config.JamfPro_Prod.get("autopkg_prefs")),
				"promote_recipe_id": recipe.get("recipe_id"),
				"verbose": autopkg_cmd.get("verbose", None)
			}

			if recipe.get("pkg_only"):
				# Only upload the .pkg, do not create/update a Policy
				recipe_id = config.JamfPro_Prod.get("recipe_template_pkg_only")
				autopkg_cmd |= { "pkg_only": True }
			else:
				recipe_id = config.JamfPro_Prod.get("recipe_template")

			queued_task = run_recipe.apply_async(
				({"event": "promote", "id": autopkg_cmd.pop("pkg_id")},
					recipe_id,
					autopkg_cmd),
				queue="autopkg", priority=4
			)

			queued_tasks.append(queued_task.id)

	return queued_tasks


@celery.task(name="autopkg:run_recipe", bind=True)
def run_recipe(self, parent_task_results: dict, recipe_id: str, autopkg_cmd: dict):
	"""Runs the passed recipe id against `autopkg run`.

	Args:
		parent_task_results (dict): Results from the calling task
		recipe_id (str): Recipe ID of a recipe
		autopkg_cmd (dict): Contains options for `autopkg` and details on response method

	Returns:
		dict:  dict describing the results of the ran process
	"""

	run_type = "recipe_run_prod" if parent_task_results.get("event") == "promote" else "recipe_run_dev"

	# Verify not a promote run and parent tasks results were success
	if (
		run_type != "recipe_run_prod"
		and parent_task_results
		and not parent_task_results["success"]
	):

		# event_id = ""

		if f"{recipe_id}: FAILED" in parent_task_results["stderr"]:
			log_msg = "Failed to verify trust info for"
			event_type = "verify_trust_info"

		elif "Didn't find a recipe for" in parent_task_results["stdout"]:
			log_msg = "Failed to locate"
			event_type = "error"

		else:
			# Generic error
			log_msg = "Unknown failure occurred on"
			event_type = "error"

		log.error(f"{log_msg} recipe: {recipe_id}")
		send_webhook.apply_async((self.request.id,), queue="autopkg", priority=9)

		return {
			"event": event_type,
			# "event_id": event_id,
			"autopkg_cmd": autopkg_cmd | {"completed": asyncio.run(utility.get_timestamp())},
			"recipe_id": recipe_id,
			"success": parent_task_results["success"],
			"stdout": parent_task_results["stdout"],
			"stderr": parent_task_results["stderr"]
		}

	else:
		log.info(f"Creating `autopkg run` task for recipe:  {recipe_id}")

		# Generate AutoPkg options
		options = task_utils.generate_autopkg_args(**autopkg_cmd)
		# Build the autopkg command
		cmd = f"{config.AutoPkg.get('binary')} run {recipe_id} {options}"

		if task_utils.get_user_context():
			cmd = f"su - {task_utils.get_console_user()} -c \"{cmd}\""

		# log.debug(f"Command to execute:  {cmd}")
		results = asyncio.run(utility.execute_process(cmd))

		# Send task complete notification
		send_webhook.apply_async((self.request.id,), queue="autopkg", priority=9)

		return {
			"autopkg_cmd": autopkg_cmd | {"completed": asyncio.run(utility.get_timestamp())},
			"event": run_type,
			"event_id": parent_task_results.get("id"),
			"recipe_id": recipe_id,
			"success": results["success"],
			"stdout": results["stdout"],
			"stderr": results["stderr"]
		}


@celery.task(name="autopkg:verify-trust", bind=True)
def autopkg_verify_trust(self, recipe_id: str, autopkg_cmd: dict, task_id: str | None = None):
	"""Runs the passed recipe id against `autopkg verify-trust-info`.

	Args:
		recipe_id (str): Recipe ID of a recipe
		autopkg_cmd (dict): Contains options for `autopkg` and details on response method

	Returns:
		dict:  dict describing the results of the ran process
	"""

	log.info(f"Verifying trust info for:  {recipe_id}")

	# Not overriding verbose when verifying trust info
	_ = autopkg_cmd.pop("quiet", None)
	_ = autopkg_cmd.pop("verbose", None)

	autopkg_cmd |= {
		"prefs": os.path.abspath(config.JamfPro_Dev.get("autopkg_prefs")),
		"verbose": "vvv"
	}

	# Generate AutoPkg options
	options = task_utils.generate_autopkg_args(**autopkg_cmd)
	# Build the autopkg command
	cmd = f"{config.AutoPkg.get('binary')} verify-trust-info {recipe_id} {options}"

	if task_utils.get_user_context():
		cmd = f"su - {task_utils.get_console_user()} -c \"{cmd}\""

	# log.debug(f"Command to execute:  {cmd}")
	results = asyncio.run(utility.execute_process(cmd))

	if autopkg_cmd.get("ingress") in {"api", "Slack"} and not self.request.parent_id:
		send_webhook.apply_async((task_id,), queue="autopkg", priority=9)

		return {
			"event": "verify_trust_info",
			"autopkg_cmd": autopkg_cmd | {"completed": asyncio.run(utility.get_timestamp())},
			"recipe_id": recipe_id,
			"success": results["success"],
			"stdout": results["stdout"],
			"stderr": results["stderr"],
		}

	return results


@celery.task(name="autopkg:update-trust", bind=True)
def autopkg_update_trust(self, recipe_id: str, trust_id: int = None):
	"""Runs the passed recipe id against `autopkg update-trust-info`.

	Args:
		recipe_id (str): Recipe ID of a recipe
		trust_id (int): The database id to associate the results to the record

	Returns:
		dict:  dict describing the results of the ran process
	"""

	log.info(f"Updating trust info for:  {recipe_id}")

	# Generate AutoPkg options
	autopkg_options = task_utils.generate_autopkg_args(
		prefs=os.path.abspath(config.JamfPro_Dev.get("autopkg_prefs")))

	repo_push_branch = config.Git.get("repo_push_branch")
	stashed = False

	try:

		private_repo = git.Repo(os.path.expanduser(config.Git.get("local_repo_dir")))

		if private_repo.is_dirty():
			_ = private_repo.git.stash()
			stashed = True

		active_branch = private_repo.active_branch
		local_branches = [ branch.name for branch in private_repo.branches ]

		if repo_push_branch not in local_branches:
			_ = private_repo.git.branch(repo_push_branch)

		if repo_push_branch != active_branch:
			_ = private_repo.git.checkout(repo_push_branch)

		cmd = f"{config.AutoPkg.get('binary')} update-trust-info {recipe_id} {autopkg_options}"

		if task_utils.get_user_context():
			cmd = f"su - {task_utils.get_console_user()} -c \"{cmd}\""

		# log.debug(f"Command to execute:  {cmd}")
		results = asyncio.run(utility.execute_process(cmd))

		if results["success"] and private_repo.git.diff():

			log.info(f"Successfully updated trust for:  {recipe_id}")
			recipe_file_path = results["stdout"].split("Wrote updated ")[-1]
			# log.debug(f"Updated recipe filename:  {recipe_file_path}")
			# Stage recipe_file_path
			_ = private_repo.index.add([recipe_file_path])

			_ = private_repo.git.commit(
				"--message", "Updated Trust Info", "--message",
				f"By:  {config.Slack.get('bot_name')}"
			)

			_ = private_repo.git.push("--set-upstream", "origin", repo_push_branch)
			log.info("Successfully updated private repo")

	except Exception as error:
		log.error(f"Failed to updated private repo due to:\n{error}")
		results = {
			"success": False,
			"stdout": error,
			"stderr": error
		}

	if stashed:
		private_repo.git.stash("pop")

	send_webhook.apply_async((self.request.id,), queue="autopkg", priority=9)

	return {
		"event": "update_trust_info",
		"event_id": trust_id,
		"recipe_id": recipe_id,
		"success": results["success"],
		"stdout": results["stdout"],
		"stderr": results["stderr"],
	}


@celery.task(name="autopkg:version", bind=True)
def autopkg_version(self, autopkg_cmd: dict, task_id: str | None = None):
	"""Runs `autopkg version`.

	Args:
		autopkg_cmd (dict): Contains options for `autopkg` and details on response method

	Returns:
		dict:  dict describing the results of the ran process
	"""

	# Build the autopkg command
	cmd = f"{config.AutoPkg.get('binary')} version"

	if task_utils.get_user_context():
		cmd = f"su - {task_utils.get_console_user()} -c \"{cmd}\""

	# log.debug(f"Command to execute:  {cmd}")
	results = asyncio.run(utility.execute_process(cmd))

	if autopkg_cmd.get("ingress") in {"api", "Slack"} and not self.request.parent_id:
		send_webhook.apply_async((task_id,), queue="autopkg", priority=9)

		return {
			"event": "autopkg_version",
			"autopkg_cmd": autopkg_cmd | {"completed": asyncio.run(utility.get_timestamp())},
			"success": results["success"],
			"stdout": results["stdout"],
			"stderr": results["stderr"],
		}

	return results


@celery.task(name="autopkg:repo-add", bind=True)
def autopkg_repo_add(self, repo: str, autopkg_cmd: dict, task_id: str | None = None):
	"""Runs the passed recipe id against `autopkg verify-trust-info`.

	Args:
		repo (str): Path (URL or [GitHub] user/repo) of an AutoPkg recipe repo
		autopkg_cmd (dict): Contains options for `autopkg` and details on response method

	Returns:
		dict:  dict describing the results of the ran process
	"""

	log.info(f"Adding repo:  {repo}")

	autopkg_options = {
		"prefs": os.path.abspath(config.JamfPro_Dev.get("autopkg_prefs")),
	}

	# Generate AutoPkg options
	options = task_utils.generate_autopkg_args(**autopkg_options)
	# Build the autopkg command
	cmd = f"{config.AutoPkg.get('binary')} repo-add {repo} {options}"

	if task_utils.get_user_context():
		cmd = f"su - {task_utils.get_console_user()} -c \"{cmd}\""

	log.debug(f"Command to execute:  {cmd}")
	results = asyncio.run(utility.execute_process(cmd))

	if autopkg_cmd.get("ingress") in {"api", "Slack"} and not self.request.parent_id:
		send_webhook.apply_async((task_id,), queue="autopkg", priority=9)

		return {
			"event": "repo-add",
			"autopkg_cmd": autopkg_cmd | {"completed": asyncio.run(utility.get_timestamp())},
			"repo": repo,
			"success": results["success"],
			"stdout": results["stdout"],
			"stderr": results["stderr"],
		}

	return results
