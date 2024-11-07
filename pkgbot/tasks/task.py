import asyncio
import collections
import hashlib
import json
import math
import os
import re
import threading

from datetime import datetime, timedelta, timezone

import git
import requests

from celery import chain, group, shared_task

from pkgbot import config, core
from pkgbot.db import models, schemas
from pkgbot.tasks import task_utils
from pkgbot.utilities import common as utility


config = config.load_config()
log = utility.log
thread_local = threading.local()


##################################################
# Helper Tasks/Functions


def determine_priority(default: int, ingress: str):

	return default + 1 if ingress == "Slack" else default


@shared_task(name="pkgbot:send_webhook", bind=True)
def send_webhook(self, task_id):
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


def get_or_create_event_loop():
	if not hasattr(thread_local, "loop") or thread_local.loop.is_closed():
		thread_local.loop = asyncio.new_event_loop()
		asyncio.set_event_loop(thread_local.loop)
	return thread_local.loop


##################################################
# Scheduled Tasks


@shared_task
def test(arg):
	log.debug(arg)


##################################################
# Pre-check Tasks


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


@shared_task(name="pkgbot:check_space", bind=True)
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

	if ( current_free_space_unit in {"B", "KB", "MB"} or
		float(current_free_space_int) <= minimum_free_space ):

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


@shared_task(name="git:pull_private_repo", bind=True)
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


##################################################
#  AutoPkg Tasks


@shared_task(name="autopkg:verb_parser", bind=True)
def autopkg_verb_parser(self, **kwargs):
	"""Handles `autopkg` tasks.

	Args:
		autopkg_cmd (dict): Contains options for `autopkg` and details on response method
		recipes (list): An optional list of recipes (in dicts,
			in which contains their configurations)
		repos (str|None): An optional str of AutoPkg recipe repo(s)
		event_id (int|None): ID of an event from the PkgBot database

	Returns:
		dict:  dict describing the results of the ran process
	"""

	# log.debug(f"Calling kwargs:  {kwargs}")

	# Track all child tasks that are queued by this parent task
	queued_tasks = []

	autopkg_cmd = kwargs.get("autopkg_cmd")
	recipes = kwargs.get("recipes")
	repos = kwargs.get("repos")
	event_id = kwargs.get("event_id")
	verb = autopkg_cmd.get("verb")

	match verb:

		case "repo-add":
			return autopkg_repo_add(repos, autopkg_cmd, task_id=self.request.id)

		case "version":
			return autopkg_version(autopkg_cmd, task_id=self.request.id)

		case _:

			if not autopkg_cmd.get("promote"):

				results_pre_check = perform_pre_checks(
					self.request.id, autopkg_cmd.get("ignore_parent_trust"))

				if isinstance(results_pre_check, dict):
					# An error occurred in a pre-check
					return results_pre_check

				queued_tasks.extend(results_pre_check)

			match verb:

				case "verify-trust-info":

					queued_task = autopkg_verify_trust.apply_async(
						(recipes, autopkg_cmd, self.request.id),
						queue="autopkg", priority=4
					)
					queued_tasks.append(queued_task.id)

				case "update-trust-info":

					queued_task = autopkg_update_trust.apply_async(
						(recipes, autopkg_cmd, event_id, self.request.id),
						queue="autopkg", priority=4
					)
					queued_tasks.append(queued_task.id)

				case "run":

					results = autopkg_run(recipes, autopkg_cmd, event_id=event_id)
					queued_tasks.extend(results)

			return { "Queued background tasks": queued_tasks }


@shared_task(name="autopkg:repo_update", bind=True)
def autopkg_repo_update(self):
	"""Performs an `autopkg repo-update all`"""

	log.info("Updating parent recipe repos...")
	autopkg_repo_update_command = ( f"{config.AutoPkg.get('binary')} repo-update all "
		f"--prefs=\'{os.path.abspath(config.JamfPro_Dev.get('autopkg_prefs'))}\'" )

	if task_utils.get_user_context():
		autopkg_repo_update_command = ( f"su - {task_utils.get_console_user()} -c"
			f"\"{autopkg_repo_update_command}\"" )

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


@shared_task(name="autopkg:run", bind=True)
def autopkg_run(self, recipes: list, autopkg_cmd: dict, **kwargs):
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
						priority=determine_priority(3, autopkg_cmd.get("ingress"))
					)
				)()

				queued_tasks.extend([chain_results.parent, chain_results.task_id])

		else:
			log.info(f"Promoting to production: {autopkg_cmd['match_pkg']}")

			autopkg_cmd |= {
				"ignore_parent_trust": True,
				"prefs": os.path.abspath(config.JamfPro_Prod.get("autopkg_prefs")),
				"promote_recipe_id": recipe.get("recipe_id"),
				"verbose": autopkg_cmd.get("verbose")
			}

			if recipe.get("pkg_only"):
				# Only upload the .pkg, do not create/update a Policy
				recipe_id = config.JamfPro_Prod.get("recipe_template_pkg_only")
				autopkg_cmd |= { "pkg_only": True }
			else:
				recipe_id = config.JamfPro_Prod.get("recipe_template")

			queued_task = run_recipe.apply_async(
				({"event": "promote", "id": kwargs.get("event_id")},
					recipe_id,
					autopkg_cmd),
				queue="autopkg", priority=4
			)

			queued_tasks.append(queued_task.id)

	return queued_tasks


@shared_task(name="autopkg:run_recipe", bind=True)
def run_recipe(self, parent_task_results: dict, recipe_id: str, autopkg_cmd: dict):
	"""Runs the passed recipe id against `autopkg run`.

	Args:
		parent_task_results (dict): Results from the calling task
		recipe_id (str): Recipe ID of a recipe
		autopkg_cmd (dict): Contains options for `autopkg` and details on response method

	Returns:
		dict:  dict describing the results of the ran process
	"""

	run_type = "recipe_run_prod" if \
		parent_task_results.get("event") == "promote" else "recipe_run_dev"

	# Verify not a promote run and parent tasks results were success
	if (
		run_type != "recipe_run_prod"
		and parent_task_results
		and not parent_task_results["success"]
	):

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
			"stderr": parent_task_results["stderr"],
			"task_id": self.request.id
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
			"stderr": results["stderr"],
			"task_id": self.request.id
		}


@shared_task(name="autopkg:verify-trust", bind=True)
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
	_ = autopkg_cmd.pop("overrides", None)

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

	if autopkg_cmd.get("ingress") in { "api", "Slack" } and \
		autopkg_cmd.get("verb") == "verify-trust-info":
		send_webhook.apply_async((self.request.id,), queue="autopkg", priority=9)

		return {
			"event": "verify_trust_info",
			"autopkg_cmd": autopkg_cmd | {"completed": asyncio.run(utility.get_timestamp())},
			"recipe_id": recipe_id,
			"success": results["success"],
			"stdout": results["stdout"],
			"stderr": results["stderr"],
			"task_id": self.request.id
		}

	return results


@shared_task(name="autopkg:update-trust", bind=True)
def autopkg_update_trust(
	self, recipe_id: str, autopkg_cmd: dict, trust_id: int = None, task_id: str | None = None):
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

		if results["stdout"] == f"Didn\'t find a recipe for {recipe_id}.":

			results |= { "success": False }

		elif results["success"] and private_repo.git.diff():

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
		results |= {
			"success": False,
			"stdout": f"{error}",
			"stderr": f"{error}"
		}

	if stashed:
		private_repo.git.stash("pop")

	send_webhook.apply_async((self.request.id,), queue="autopkg", priority=9)

	return {
		"event": "update_trust_info",
		"event_id": trust_id,
		"autopkg_cmd": autopkg_cmd | {"completed": asyncio.run(utility.get_timestamp())},
		"recipe_id": recipe_id,
		"success": results["success"],
		"stdout": results["stdout"],
		"stderr": results["stderr"],
		"task_id": self.request.id
	}


@shared_task(name="autopkg:version", bind=True)
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
		send_webhook.apply_async((task_id or self.request.id,), queue="autopkg", priority=9)

		return {
			"event": "autopkg_version",
			"autopkg_cmd": autopkg_cmd | {"completed": asyncio.run(utility.get_timestamp())},
			"success": results["success"],
			"stdout": results["stdout"],
			"stderr": results["stderr"],
			"task_id": task_id or self.request.id
		}

	return results


@shared_task(name="autopkg:repo-add", bind=True)
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
		send_webhook.apply_async((task_id or self.request.id,), queue="autopkg", priority=9)

		return {
			"event": "repo-add",
			"autopkg_cmd": autopkg_cmd | {"completed": asyncio.run(utility.get_timestamp())},
			"repo": repo,
			"success": results["success"],
			"stdout": results["stdout"],
			"stderr": results["stderr"],
			"task_id": task_id or self.request.id
		}

	return results


##################################################
# Jamf Pro Tasks


@shared_task(name="pkgbot:cache_policies", bind=True)
def cache_policies(self, **kwargs):

	start = asyncio.run(utility.get_timestamp())
	source = kwargs.get("source")
	called_by = kwargs.get("called_by")

	if source == "Scheduled":
		log.info("Performing nightly task to cache Policies from Jamf Pro...")
	else:
		log.info(f"Cache Policies from Jamf Pro was requested by {called_by}")

	api_token, api_token_expires = asyncio.run(core.jamf_pro.get_token())
	all_policies_response = asyncio.run(core.jamf_pro.api(
		"get", "JSSResource/policies", api_token=api_token))

	if all_policies_response.status_code != 200:
		raise("Failed to get list of Policies!")

	all_policies = all_policies_response.json()
	log.debug(f"Number of Policies in Jamf Pro:  {len(all_policies.get('policies'))}")

	# Get the Policy IDs
	policy_ids = [ policy.get("id") for policy in all_policies.get("policies") ]
	# log.debug(f"Number of Policy IDs:  {len(policy_ids)}")

	# Get all cached Policies and their IDs
	all_cache_policies = asyncio.run(core.policy.get())
	cache_policy_ids = [ policy.policy_id for policy in all_cache_policies ]
	log.debug(f"Number of cached Policy IDs:  {len(cache_policy_ids)}")

	# Get Policy IDs from cached Policies if they aren't in the "new" Policy IDs list
	deleted_policy_ids = [
		policy_id for policy_id in cache_policy_ids if policy_id not in policy_ids ]
	log.debug(f"Number of cached Policies to delete:  {len(deleted_policy_ids)}")

	for policy_id in deleted_policy_ids:
		log.debug(f"Deleting Policy:  {policy_id}")
		asyncio.run(core.policy.delete( { "policy_id": policy_id } ))

	place_values = int(math.log10(len(all_policies.get('policies')))) + 1
	pattern = r'^\d'
	count = 1

	if place_values == 2:
		pattern = f"{pattern}0$"
	elif place_values == 3:
		pattern = f"{pattern}00$"
	elif place_values > 3:
		pattern = f"{pattern}+00$"

	log.debug("Updating Policies...")

	for policy in all_policies.get("policies"):

		if count < 11 or re.match(pattern, str(count)):
			log.debug(f"Policy Progress:  {count}")

		count = count + 1

		if datetime.now(timezone.utc) > (api_token_expires - timedelta(minutes=5)):
			log.debug("Replacing API Token...")
			api_token, api_token_expires = asyncio.run(core.jamf_pro.get_token())

		policy_details_response = asyncio.run(core.jamf_pro.api(
			"get", f"JSSResource/policies/id/{policy.get('id')}", api_token=api_token))

		if policy_details_response.status_code != 200:
			raise Exception(
				f"Failed to get policy details for:  {policy.get('id')}:{policy.get('name')}!")

		policy_details = policy_details_response.json()
		policy_general = policy_details.get("policy").get("general")
		policy_packages = policy_details.get("policy").get("package_configuration").get("packages")

		policy_obj, created = asyncio.run(core.policy.create_or_update(
			schemas.Policy_In(
				name = policy_general.get("name"),
				site = policy_general.get("site").get("name"),
				policy_id = policy_general.get("id")
			)
		))

		# Clear the current policy <-> package relationship (aka flush table of this Policy)
		asyncio.run(policy_obj.packages.clear())
		asyncio.run(policy_obj.packages_manual.clear())

		for package in policy_packages:

			# PkgBot Package -- if exists
			if not (pkg_object := asyncio.run(
				core.package.get_or_none({ "pkg_name": package.get("name") })
			)):
				# Manually uploaded Package
				pkg_name = package.get("name")

				try:
					version = re.sub("\.(pkg|dmg)", "", pkg_name.rsplit("-", 1)[1])
				except:
					version = "1.0"

				pkg_details = {
					"name": pkg_name.rsplit("-", 1)[0],
					"pkg_name": pkg_name,
					"version": version,
					"status": "prod"
				}

				pkg_object = (asyncio.run(core.package.get_or_create_manual_pkg(pkg_details)))[0]

			asyncio.run(pkg_object.policies.add(policy_obj))

	log.info("Caching Policies from Jamf Pro...COMPLETE")
	return {
		"event": "cache-policies",
		"source": source,
		"called_by": called_by,
		"start": start,
		"completed": asyncio.run(utility.get_timestamp()),
		"result": "Successfully cached all Policies from Jamf Pro.",
		"task_id": self.request.id
	}


@shared_task(name="pkgbot:package_cleanup", bind=True)
def package_cleanup(self, **kwargs):

	loop = get_or_create_event_loop()
	start = loop.run_until_complete(utility.get_timestamp())
	source = kwargs.get("source")
	called_by = kwargs.get("called_by")

	if source == "Scheduled":
		log.info("Running scheduled Package Cleanup Task...")
	else:
		log.info(f"Adhoc Package Cleanup was requested by {called_by}")

	log.debug("Getting all packages...")
	pkg_cleanup_config = config.PkgBot.get("Package_Cleanup")
	versions_to_keep = kwargs.get("versions_to_keep", pkg_cleanup_config.get("versions_to_keep"))
	dry_run = kwargs.get("dry_run", pkg_cleanup_config.get("dry_run"))
	max_allowed_pkgs_to_delete = kwargs.get("maximum_allowed_packages_to_delete")

	packages_json_response = loop.run_until_complete(
		core.jamf_pro.api("get", "JSSResource/packages"))
	pkgs = packages_json_response.json().get("packages")
	groups = collections.defaultdict(list)
	report = []

	for pkg in pkgs:

		try:
			head = re.sub(
				r'\s\((Universal|ARM|Intel)\)',
				"",
				re.findall(r'.+?(?=-)', pkg["name"])[0]
			)
		except IndexError:
			head = pkg["name"]

		groups[head].append(pkg)

	for k,v in groups.items():
		log.debug(f"Software Title:  {k}")
		# log.debug(f"Software Title:  {k}\nVersions:  {v}")

		if len(v) > versions_to_keep:
			# Sort by ID -- presumed newer pkg versions have higher integers
			v = sorted(v, key=lambda item: item["id"], reverse=False)[:-2]

			# Check that we're not going to delete too many packages
			if len(v) > max_allowed_pkgs_to_delete:
				log.debug(
					f"Found {len(v)} packages.  "
					f"Maximum allowed is {max_allowed_pkgs_to_delete}.  "
					"Override by setting the 'maximum_allowed_packages_to_delete' argument."
				)

			# Divide the packages into those to keep and those to delete
			if packages_to_delete := v[:max_allowed_pkgs_to_delete]:
				packages_in_use = 0

				for pkg in packages_to_delete:

					if pkgbot_pkg := loop.run_until_complete(
						core.package.get({ "pkg_name": pkg.get("name") })):
						pass
					elif manual_pkg := (loop.run_until_complete(
						schemas.Package_Manual_Out.from_queryset(
							models.PackagesManual.filter(**{ "pkg_name": pkg.get("name") })
					))):
						pkgbot_pkg = manual_pkg[0]

					if pkgbot_pkg:
						policy_report = pkgbot_pkg.dict(
							exclude = { "recipe", "icon", "notes",
				  				"slack_channel", "slack_ts", "response_url" },
							exclude_unset = True
						)

						# Check if packages are in use...
						if policy_report.get("policies"):
							packages_in_use = packages_in_use + 1

							for policy in policy_report.get("policies"):
								# log.debug(f'{policy = }')
								policy.pop("packages", None)
								policy.pop("packages_manual", None)

						report.append(policy_report)
					else:
						report.append(pkg)

				log.debug(f"Number of packages to delete:  {len(packages_to_delete)}")
				log.debug(f"Number of packages in use:  {packages_in_use}")

	total_in_use = len([ pkg for pkg in report if pkg.get("policies") ])
	log.debug(f"Total packages in report:  {len(report) }")
	log.debug(f"Total packages in use:  {total_in_use}")

	header = ("id", "name", "version", "pkg_name", "packaged_date", "promoted_date",
		"last_update", "status", "updated_by", "holds", "notes", "policies")

	csv_file = loop.run_until_complete(utility.create_csv(
		data = report,
		header = header,
		file_name = "Package Retirement Report.csv",
		save_path = "/tmp"
	))

	send_webhook.apply_async((self.request.id,), queue="pkgbot", priority=9)

	return {
		"event": "package-cleanup",
		"source": source,
		"called_by": called_by,
		"start": start,
		"completed": loop.run_until_complete(utility.get_timestamp()),
		"result": "Package cleanup report has been generated.",
		"results": {
			"packages_to_delete": len(report),
			"packages_in_use": total_in_use,
			"csv_file": csv_file,
		},
		"task_id": self.request.id
	}
