# import asyncio
import hashlib
# import hmac
import json
import os
# import re
import requests
import time

import httpx

from celery import Celery, group, chain
from celery import shared_task
from celery.result import AsyncResult

# Internal modules
import config, utils

# from api import recipe
# from api.slack import bot
# from api.recipe import reciepe_trust_verify_failed
# from db import models
from tasks import task_utils

# import api.settings


from settings.celery_config import settings
# from collections.abc import Callable

config.load()
log = utils.log


# register_tortoise(
# 	pkgbot.app,
# 	config = api.settings.TORTOISE_CONFIG,
# 	generate_schemas = True,
# 	add_exception_handlers = True
# )

# from tortoise import Tortoise

# asyncio.run(Tortoise.init(config = api.settings.TORTOISE_CONFIG))

# # Generate the schema
# asyncio.run(Tortoise.generate_schemas())

# asyncio.run(bot.startup_constructor())


# async def wrap_db_ctx(func: Callable, *args, **kwargs) -> None:
# 	# try:
# 		# await connect_db()
# 	await Tortoise.init(config = api.settings.TORTOISE_CONFIG)
# 	await Tortoise.generate_schemas()
# 	await func(*args, **kwargs)
# 	# finally:
# 		# await disconnect_db()
# 	await Tortoise.close_connections()


# def async_to_sync(func: Callable, *args, **kwargs) -> None:
# 	# print(f"func:  {func}")
# 	# print(f"args:  {args}")
# 	# print(f"kwargs:  {kwargs}")
# 	asyncio.run(wrap_db_ctx(func, *args, **kwargs))







celery = Celery()
celery.config_from_object(settings)
# celery = Celery(
# 	'tasks',
# 	broker = "amqp://guest:guest@localhost:5672//",
# 	backend = "rpc://"
# )


@celery.task(namebind=True)
def send_webhook(self, task_id):

	# pkgbot_server, headers = asyncio.run(task_utils.api_url_helper())
	pkgbot_server, headers = task_utils.api_url_helper()

	data = {
		"task_id": task_id
		# "recipe_id": recipe_id,
		# "status": "Failed",
		# "task_type": "generic",
		# "stdout": parent_task_results["stdout"],
		# "stderr": parent_task_results["stderr"],
	}

	# log.debug(f"data:  {str(json.dumps(data)).encode('utf-8')}")
	# digest = hmac.new(
	# 	bytes(f"{config.pkgbot_config.get('PkgBot.webhook_secret')}", "utf-8"),
	# 	msg=str(json.dumps(data)).encode("utf-8"),
	# 	digestmod='sha512'
	# ).hexdigest()
	# log.debug(f"digest:  {digest}")

	# headers["x-hook-signature"] = task_utils.generate_hook_signature(data)
	headers["x-hook-signature"] = utils.compute_hex_digest(
		bytes(config.pkgbot_config.get('PkgBot.webhook_secret'), "utf-8"),
		(request.body()),#.decode("UTF-8")
		hashlib.sha512
	)
	# with httpx.AsyncClient() as client:

		# asyncio.run(client.post(f"{pkgbot_server}/autopkg/receive",
	# asyncio.run(httpx.AsyncClient().post(f"{pkgbot_server}/autopkg/receive",
	# 	headers=headers,
	# 	data=data,
	# 	json=data
	# ))

	requests.post(f"{pkgbot_server}/autopkg/receive",
		headers=headers,
		data=json.dumps(data),
	)





@celery.task(name="git:pull_private_repo")
def git_pull_private_repo():

	log.info("Checking for private repo updates...")

	console_user = task_utils.get_console_user()

	git_pull_command = "{binary} -C \"{path}\" switch main > /dev/null && {binary} -C \"{path}\" pull && $( {binary} -C \"{path}\" rev-parse --verify trust-updates > /dev/null 2>&1 && {binary} -C \"{path}\" switch trust-updates > /dev/null || {binary} -C \"{path}\" switch -c trust-updates > /dev/null )".format(
		binary=config.pkgbot_config.get("Git.binary"),
		path=f"/Users/{console_user}/Library/AutoPkg/RecipeOverrides/"
##### Set this path in a config file some where?
	)

	if task_utils.get_user_context():
		git_pull_command = f"su - {console_user} -c \"{git_pull_command}\""

	results_git_pull_command = utils.execute_process(git_pull_command)

	if not results_git_pull_command["success"]:
		log.error("stdout:\n{}".format(results_git_pull_command["stdout"]))
		log.error("stderr:\n{}".format(results_git_pull_command["stderr"]))

	else:
		log.info("Successfully updated private local autopkg repo.")
		log.debug(results_git_pull_command["stdout"])

	results_git_pull_command["event"] = "private_git_pull"
	return results_git_pull_command





@celery.task(name="autopkg:repo_update")
def autopkg_repo_update():

	log.info("Updating parent recipe repos...")

	autopkg_repo_update_command = f"{config.pkgbot_config.get('AutoPkg.binary')} repo-update all --prefs=\"{os.path.abspath(config.pkgbot_config.get('JamfPro_Dev.autopkg_prefs'))}\""

	if task_utils.get_user_context():
		autopkg_repo_update_command = f"su - {console_user} -c \"{autopkg_repo_update_command}\""

	results_autopkg_repo_update = utils.execute_process(autopkg_repo_update_command)

	##### TO DO:
	###### * Add parent recipe repos update success
			# To what.....?  What was I thinking here..??

	if not results_autopkg_repo_update["success"]:
		log.error("Failed to update parent recipe repos")
		log.error("{}".format(results_autopkg_repo_update["stderr"]))

	results_autopkg_repo_update["event"] = "autopkg_repo_update"
	return results_autopkg_repo_update






@celery.task(name="autopkg:run", bind=True)
def autopkg_run(self, recipes: list, switches: dict):
	"""Runs the passed recipe id against `autopkg run`.

	Args:
		recipe (str): Recipe ID of a recipe
		switches (str):

	Returns:
		dict:  Dict describing the results of the ran process
	"""


	log.debug(f"recipes:  {recipes}")
	# time.sleep(30)

	# console_user = task_utils.get_console_user()


	# if (
		# switches.get("action") != "promote" #and
		# git_pull_private_repo()["success"] and
		# autopkg_repo_update()["success"]
	# ):

	if switches.get("action") != "promote":

		# Run checks if we're not promoting the recipe
		# task_autopkg_repo_update = autopkg_repo_update.apply_async(queue='autopkg', priority=3).get(disable_sync_subtasks=False)
		# task_private_repo_update = git_pull_private_repo.apply_async(queue='autopkg', priority=3).get(disable_sync_subtasks=False)
		tasks = [
			autopkg_repo_update.signature(),
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

				send_webhook.apply_async((self.request.parent_id), queue='autopkg', priority=2)

				return task_result


	for a_recipe in recipes:

		log.debug(f"a_recipe:  {a_recipe}")

		if a_recipe.get("enabled") and task_utils.get_console_user(
			recipe_config["schedule"], recipe_config["last_ran"]):

			recipe_id = a_recipe.get("recipe_id")
			action = switches.pop("action", None)

			if action != "promote":
				log.debug("Not a promote run...")

				# Verify trust info and wait
				# task_autopkg_verify_trust = autopkg_verify_trust.apply_async((recipe_id, switches), queue='autopkg', priority=5).get(disable_sync_subtasks=False)
				# task_autopkg_verify_trust.wait()

				recipe_run = chain(
					autopkg_verify_trust.signature((recipe_id, switches)) | run_recipe.signature((recipe_id, switches))
				)()

				# recipe_run.apply_async(queue='autopkg', priority=5, immutable=True)
				# autopkg_verify_trust.apply_async((recipe_id, switches), queue='autopkg', priority=5, link=run_recipe.apply_async((recipe_id, switches), queue='autopkg', priority=5))


			else:

				run_recipe.apply_async((None, recipe_id, switches), queue='autopkg', priority=5)
			# run_recipe.apply_async((None, {"recipe_id": recipe_id, "switches": switches}), queue='autopkg', priority=5)





@celery.task(name="autopkg:run_recipe", bind=True)
def run_recipe(self, parent_task_results: str, recipe_id: str, switches: dict):

	# Verify success
	if parent_task_results and not parent_task_results["success"]:

		if "Didn't find a recipe for" in parent_task_results["stdout"]:
			log.error("Failed to locate recipe!")

#### Do not keep the try/except here:
			# try:
			# 	async_to_sync(recipe.recipe_error, recipe_id, task_autopkg_verify_trust["stdout"])
			# except:
			# 	pass

			send_webhook.apply_async((self.request.parent_id), queue='autopkg', priority=2)

			return {
				"event": "error",
				"recipe_id": recipe_id,
				"success": parent_task_results["success"],
				"stdout": parent_task_results["stdout"],
				"stderr": parent_task_results["stderr"],
			}


		else:
			# Post Slack Message with recipe trust info
			log.error("Failed to verify trust info!")
##### Should some verificatino here happen to confirm it was the trust that failed?
			send_webhook.apply_async((self.request.parent_id), queue='autopkg', priority=2)

			return {
				"event": "failed_trust",
				"recipe_id": recipe_id,
				"success": parent_task_results["success"],
				"stdout": parent_task_results["stdout"],
				"stderr": parent_task_results["stderr"],
			}

	else:

		log.info(f"Creating `autopkg run` task for recipe:  {recipe_id}")

		# print(switches)
		# Build the autopkg command
		cmd = f"{config.pkgbot_config.get('AutoPkg.binary')} run {recipe_id} -{switches.pop('verbose', 'v')}"
		# print(switches)
		for k, v in switches.items():
			cmd = f"{cmd} --{k} '{v}'"

		if task_utils.get_user_context():
			# cmd = f"su - {console_user} -c \"{cmd}\""
			cmd = f"su - {task_utils.get_console_user()} -c \"{cmd}\""

		log.debug(f"Command to execute:  {cmd}")

		results = utils.execute_process(cmd)
		# return results  ### <-- NO, not doing this
		# Instead, need to convert the PkgBot AutoPkg Post Processor into logic here

	##### Need to parse results here and then do something
		# If dev run:
			# Create pkg:  package.create()
				# & Slack msg
					# Does package.create() also send a slack msg?
		# If prod run:
			# update existing Slack msg
		return results




@celery.task(name="autopkg:verify-trust")
def autopkg_verify_trust(recipe_id: str, switches: dict):
	"""Runs the passed recipe id against `autopkg verify-trust-info`.

	Args:
		recipe (str): Recipe ID of a recipe
		switches (str):

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	log.info("`autopkg verify-trust-info`")
	log.info("Verifying trust info...")

#### Only if needed...
	# autopkg_prefs = os.path.abspath(config.pkgbot_config.get("JamfPro_Dev.autopkg_prefs"))

	# Build the autopkg command
	# cmd = f"{config.pkgbot_config.get('AutoPkg.binary')} " + \
	# 	  f"verify-trust-info {recipe_id} " + \
	# 	  f"-{switches.pop('verbose', 'vvv')}"
	cmd = f"{config.pkgbot_config.get('AutoPkg.binary')} verify-trust-info {recipe_id} -{switches.pop('verbose', 'vvv')}"

	for k, v in switches.items():
		cmd = f"{cmd} --{k} '{v}'"

	if task_utils.get_user_context():
		cmd = f"su - {task_utils.get_console_user()} -c \"{cmd}\""

	log.debug(f"Command to execute:  {cmd}")

	results = utils.execute_process(cmd)

	return results





@celery.task(name="autopkg:update-trust", bind=True)
def autopkg_update_trust(self, recipe_id: str, switches: dict):
	"""Runs the passed recipe id against `autopkg update-trust-info`.

	Args:
		recipe (str): Recipe ID of a recipe
		switches (str):

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	log.info("`autopkg update-trust-info`")
	log.info("Updating trust info...")

#### Only if needed...
	# autopkg_prefs = os.path.abspath(config.pkgbot_config.get("JamfPro_Dev.autopkg_prefs"))

	# Build the autopkg command
	# cmd = f"{config.pkgbot_config.get('AutoPkg.binary')} " + \
	# 	  f"update-trust-info {recipe_id} " + \
	# 	  f"-{switches.pop('verbose', 'vvv')}"
	cmd = f"{config.pkgbot_config.get('AutoPkg.binary')} update-trust-info {recipe_id}"

	for k, v in switches.items():
		cmd = f"{cmd} --{k} '{v}'"

	if task_utils.get_user_context():
		cmd = f"su - {task_utils.get_console_user()} -c \"{cmd}\""

	log.debug(f"Command to execute:  {cmd}")

	results = utils.execute_process(cmd)

	send_webhook.apply_async((self.request.id), queue='autopkg', priority=4)

	return {
		"event": "update_trust_info",
		"recipe_id": recipe_id,
		"success": results["success"],
		"stdout": results["stdout"],
		"stderr": results["stderr"],
	}

