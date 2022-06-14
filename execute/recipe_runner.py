#!/usr/local/autopkg/python

import argparse
import ast
import asyncio
import getpass
import os
import re
import sys

from datetime import datetime, timedelta

sys.path.insert(0, "/Library/AutoPkg/PkgBot")

import config, utils
from api import recipe
from execute import api_helper


log = utils.log

async def check_recipe_schedule(interval, last_ran):
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

		current_time = await utils.utc_to_local(datetime.now())
		last_ran_time = datetime.fromisoformat(last_ran)
		interval_in_hours = interval * 24

		return current_time - last_ran_time > timedelta(hours=interval_in_hours)

	return True


async def autopkg_verify_trust(recipe_id, console_user):
	"""Runs the passed recipe against `autopkg verify-trust-info`.

	Args:
		recipe_id (str): Recipe identifier of a recipe.

	Returns:
		dict: Dict describing the results of the ran process
	"""

	log.info("Verifying trust info...")

	autopkg_prefs = os.path.abspath(config.pkgbot_config.get("JamfPro_Dev.autopkg_prefs"))

	command_autopkg_recipe_trust = "{binary} verify-trust-info {run_recipe} --prefs=\"{prefs}\" -vvv".format(
		binary=config.pkgbot_config.get("AutoPkg.binary"),
		run_recipe=recipe_id,
		prefs=autopkg_prefs
	)

	if await get_user_context():
		command_autopkg_recipe_trust = "su - {console_user} -c \"{command}\"".format(
			console_user=console_user,
			command=command_autopkg_recipe_trust,
		)

	results_autopkg_recipe_trust = await utils.run_process_async(command_autopkg_recipe_trust)

	# Verify success
	if not results_autopkg_recipe_trust['success']:

		if "Didn't find a recipe for" in results_autopkg_recipe_trust['stdout']:
			log.error("Failed to locate recipe!")
			await api_helper.chat_recipe_error(recipe_id, results_autopkg_recipe_trust['stdout'] )

		else:
			# Post Slack Message with recipe trust info
			log.error("Failed to verify trust info!")
			await api_helper.chat_failed_trust(recipe_id, results_autopkg_recipe_trust['stderr'] )

		return False

	return True


async def autopkg_update_trust(recipe_id, console_user, error_id):
	"""Runs the passed recipe against `autopkg update-trust-info`.

	Args:
		recipe_id (str): Recipe identifier of a recipe.

	Returns:
		dict: Dict describing the results of the ran process
	"""

	log.info("Updating trust info...")

	autopkg_prefs = os.path.abspath(config.pkgbot_config.get("JamfPro_Dev.autopkg_prefs"))

	command_autopkg_update_trust = "{binary} update-trust-info {run_recipe} --prefs=\"{prefs}\"".format(
		binary=config.pkgbot_config.get("AutoPkg.binary"),
		run_recipe=recipe_id,
		prefs=autopkg_prefs
	)

	if await get_user_context():
		command_autopkg_update_trust = "su - {console_user} -c \"{command}\"".format(
			console_user=console_user,
			command=command_autopkg_update_trust,
		)

	results_autopkg_update_trust = await utils.run_process_async(command_autopkg_update_trust)

	if not results_autopkg_update_trust['success']:
		log.error("Failed to update trust info")
		log.error("results_autopkg_update_trust[stdout]:  {}".format(results_autopkg_update_trust['stdout']))
		log.error("results_autopkg_update_trust[stderr]:  {}".format(results_autopkg_update_trust['stderr']))
		# await api_helper.chat_update_trust_msg(recipe_id, result=results_autopkg_update_trust['stdout'])

	else:
		log.info("Successfully updated trust for:  {}".format(recipe_id))

		recipe_file_path = results_autopkg_update_trust["stdout"].split("Wrote updated ")[-1]

		# Verify if there are changes that need to be committed
		git_updated_filename_command = "{} -C \"/Users/{}/Library/AutoPkg/RecipeOverrides/\" diff --exit-code \"{}\"".format(
			config.pkgbot_config.get("Git.binary"),
			console_user,
			recipe_file_path
		)
		results_git_updated_filename_command = await utils.run_process_async(git_updated_filename_command)

		if results_git_updated_filename_command["status"] == 1:

			log.debug("Updated recipe filename:  {}".format(recipe_file_path))

			# Switch branches
			git_switch_branch_command = "{binary} -C \"{path}\" switch trust-updates > /dev/null || ( {binary} -C \"{path}\" switch -c trust-updates > /dev/null && {binary} -C \"{path}\" push origin trust-updates )".format(
				binary=config.pkgbot_config.get("Git.binary"),
				path="/Users/{}/Library/AutoPkg/RecipeOverrides/".format(console_user)
			)
			results_git_stage_file_command = await utils.run_process_async(git_switch_branch_command)

			if results_git_stage_file_command["success"]:

				# Stage updated recipe
				git_stage_file_command = "{} -C \"/Users/{}/Library/AutoPkg/RecipeOverrides/\" add \"{}\"".format(
					config.pkgbot_config.get("Git.binary"),
					console_user,
					recipe_file_path
				)
				results_git_stage_file_command = await utils.run_process_async(git_stage_file_command)


				if results_git_stage_file_command["success"]:

					log.debug("Staged recipe in git:  {}".format(recipe_id))

					# Commit changes
					git_commit_file_command = "{} -C \"/Users/{}/Library/AutoPkg/RecipeOverrides/\" commit --message \"Updated Trust Info\"  --message \"Recipe:  {}\" --message \"By:  PkgBot\"".format(
						config.pkgbot_config.get("Git.binary"),
						console_user,
						recipe_id
					)
					results_git_commit_file_command = await utils.run_process_async(git_commit_file_command)

					if results_git_commit_file_command["success"]:

						log.debug("Commit recipe locally:  {}".format(recipe_id))

						# Commented out due to changes in my insitution's remote git environment (use of protected branches, no deploy key, etc.)
						# Or do this?
						# git push --set-upstream origin trust-updates

						# git_push_commit_command = "cd \"/Users/{}/Library/AutoPkg/RecipeOverrides/\"; /usr/local/bin/gh pr create --fill --base \"trust-updates\"".format(
						# 	console_user
						# )

						##### Can't use git to push
						#### Will need to submit a PR here to the non-main branch
						# git_push_commit_command = "{} -C \"/Users/{}/Library/AutoPkg/RecipeOverrides/\" push".format(
						# 	config.pkgbot_config.get("Git.binary"),
						# 	console_user
						# )

						# if await get_user_context():
						# 	git_push_commit_command = "su - {console_user} -c \"{command}\"".format(
						# 	console_user=console_user,
						# 	command=git_push_commit_command,
						# 	)

						# results_git_push_commit_command = await utils.run_process_async(git_push_commit_command)

						# if results_git_push_commit_command["success"]:

						# 	log.debug("Successfully pushed commit for:  {}".format(recipe_id))

						# else:

						# 	log.error("Failed to push commit for:  {}".format(recipe_id))
					else:

						log.error("Failed commit locally for:  {}".format(recipe_id))

				else:

					log.error("Failed to stage:  {}".format(recipe_id))

			else:

				log.error("Failed to switch branch:  {}".format(recipe_id))

		else:

			log.error("Failed to get file name for:  {}".format(recipe_id))


		await api_helper.chat_update_trust_msg(recipe_id, result="success", error_id = error_id)


async def autopkg_runner(**kwargs):
	"""Runs the passed recipe against `autopkg run`.

	Args:
		recipe (str): Recipe ID of a recipe
		prefs (str): Path to a autopkg preference file

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	recipe_id = kwargs["recipe_id"]
	pkg_only = kwargs['pkg_only']
	promote = kwargs['promote']
	console_user = kwargs['console_user']
	pkg_name = kwargs['pkg_name']
	extra_switches = "--key 'DISABLE_CODE_SIGNATURE_VERIFICATION=True'"

	log.info("Running...")

	if promote:
		recipe_to_run = config.pkgbot_config.get("JamfPro_Prod.recipe_template")
		autopkg_prefs = os.path.abspath(config.pkgbot_config.get("JamfPro_Prod.autopkg_prefs"))
		extra_switches = "--ignore-parent-trust-verification-errors --key 'match_pkg={}'".format(pkg_name)

		if pkg_only:
			extra_switches = "{} --key jss_pkg_only=True".format(extra_switches)

	else:
		recipe_to_run = recipe_id
		autopkg_prefs = os.path.abspath(config.pkgbot_config.get("JamfPro_Dev.autopkg_prefs"))

	# Build the command to run
	command_autopkg_run = "{binary} run {run_recipe} --key 'recipe_id={id}' --prefs='{prefs}' --ignore-parent-trust-verification-errors --postprocessor PkgBot {extras} -vv".format(
		binary=config.pkgbot_config.get("AutoPkg.binary"),
		run_recipe=recipe_to_run,
		id=recipe_id,
		prefs=autopkg_prefs,
		extras=extra_switches
	)

	if await get_user_context():
		command_autopkg_run = "su - {console_user} -c \"{command}\"".format(
			console_user=console_user,
			command=command_autopkg_run,
		)

	results_run = await utils.run_process_async(command_autopkg_run)

	return results_run


async def autopkg_process_wrapper(**kwargs):

	recipe_config = kwargs["recipe_config"]
	recipe_id = recipe_config.get("recipe_id")
	action = kwargs["action"]
	console_user = kwargs["console_user"]
	pkg_name = kwargs["pkg_name"]
	error_id = kwargs.get("error_id", "")

	log.info("Recipe:  {}".format(recipe_id))

	if action == "trust":
		await autopkg_update_trust(recipe_id, console_user, error_id)

	else:

		if action is None:
			# Run checks if we're not promoting the recipe

			if not recipe_config["enabled"]:
				log.info("Recipe is disabled; exiting...")
				return

			if not await check_recipe_schedule(
				recipe_config["schedule"], recipe_config["last_ran"] ):
				# Do not run recipe due to scheduled interval
				return

			if not await autopkg_verify_trust(recipe_id, console_user):
				# Failed Trust Verification
				return

		# Passed Trust Verification
		results_autopkg_run = await autopkg_runner(
			recipe_id=recipe_id, pkg_only=recipe_config["pkg_only"], promote=action, pkg_name=pkg_name, console_user=console_user)

		# Verify success
		if results_autopkg_run['success']:
			log.info("Successfully ran:  {}".format(recipe_id))

##### Do not care about success here, as the PkgBot Post-Processor will handle the rest
			# run_receipt = re.search(r'Receipt written to (.*)', results_autopkg_run['stdout']).group(1)
			# plist_contents = await utils.plist_reader(run_receipt)
			# log.debug("recipe_runner > plist_contents:  \n{}\n*** End of plist_contents***".format(plist_contents))
			# for step in reversed(plist_contents):
			# 	jssimporter_results = step
			# 	break

			# changes = jssimporter_results.get('Output').get('jss_changed_objects')
			# # Post Slack Message with results
			# chatbot.post_dev_results(changes)
#####
		if not results_autopkg_run['success']:

			# Post Slack Message with results
			log.error("Failed running:  {}".format(recipe_id))
			log.error("return code status:  {}".format(results_autopkg_run['status']))
			log.error("stdout:  {}".format(results_autopkg_run['stdout']))
			log.error("stderr:  {}".format(results_autopkg_run['stderr']))

			try:
				run_receipt = re.search(
					r'Receipt written to (.*)', results_autopkg_run['stdout']).group(1)
				plist_contents = await utils.plist_reader(run_receipt)

				for step in reversed(plist_contents):
					if step.get('RecipeError') != None:
						run_error = step.get('RecipeError')
						break

			except:
				run_error = results_autopkg_run['stderr']

			redacted_error = await utils.replace_sensitive_strings(run_error)

			await api_helper.chat_recipe_error(recipe_id, redacted_error)


async def get_user_context():

	return os.getlogin() == "root" and os.getenv('USER') is None


async def main(run_args=sys.argv[1:]):
	# log.debug('Recipe Runner:\n\tAll calling args:  {}'.format(run_args))

	##################################################
	# Setup Argparse

	parser = argparse.ArgumentParser(description="Run recipe overrides through AutoPkg.")

	run_type = parser.add_mutually_exclusive_group(required=True)
	run_type.add_argument('--all', '-a', action='store_true', required=False,
		help='Runs all the recipes in the database.')
	run_type.add_argument('--recipe-identifier', '-i', metavar='local.Firefox', type=str,
		required=False, help='A recipe identifier.')

	parser.add_argument('--pkgbot-config', '-p', metavar='./config.yaml', type=str,
		required=False, help='A config file with defined environmental configurations.')
	parser.add_argument('--environment', '-e', type=str, default="dev", required=False,
		help='Which environment to use.')
	parser.add_argument('--action', choices=[ "promote", "trust" ], required=False,
		help='Perform the requested action on the passed recipe id.')
	parser.add_argument('--pkg-name', '-n', metavar='Firefox-90.0.pkg', type=str,
		required=False, help='The name of the package to match.  This is to ensure the version \
			that is promoted matches what is intended.')
	parser.add_argument('--error-id', '-id', type=str, required=False,
		help='Error ID to map down stream functions too.')

	##################################################
	# Parse Script Arguments

	args, _ = parser.parse_known_args(run_args)
	# log.debug('Recipe Runner:\n\tArgparse args:  {}'.format(args))

	if len(run_args) == 0:
		parser.print_help()
		sys.exit(0)

	elif args.action == "promote" and not args.pkg_name:
		parser.print_help()
		parser.error('The --promote argument requires the --pkg-name argument.')

	##################################################
	# Bits staged...

	if args.pkgbot_config:
		config.load(pkgbot_config=args.pkgbot_config)

	else:
		config.load()

	# Get the Console User
	results_console_user = await utils.run_process_async("/usr/sbin/scutil", "show State:/Users/ConsoleUser")
	console_user = re.sub("(Name : )|(\n)", "", ( re.search("Name : .*\n", results_console_user['stdout']).group(0) ))

	if args.environment == "dev" and not args.action:

		log.info("Checking for private repo updates...")
		git_pull_command = "{binary} -C \"{path}\" switch main > /dev/null && {binary} -C \"{path}\" pull && $( {binary} -C \"{path}\" rev-parse --verify trust-updates > /dev/null 2>&1 && {binary} -C \"{path}\" switch trust-updates > /dev/null || {binary} -C \"{path}\" switch -c trust-updates > /dev/null )".format(
			binary=config.pkgbot_config.get("Git.binary"),
			path="/Users/{}/Library/AutoPkg/RecipeOverrides/".format(console_user)
		)

		if await get_user_context():
			git_pull_command = "su - {} -c \"{}\"".format(
				console_user, git_pull_command,
			)

		results_git_pull_command = await utils.run_process_async(git_pull_command)

		if results_git_pull_command["success"]:
			log.info(results_git_pull_command["stdout"])

		else:
			log.error("stdout\n:{}".format(results_git_pull_command["stdout"]))
			log.error("stderr\n:{}".format(results_git_pull_command["stderr"]))
			sys.exit(1)

		log.info("Updating parent recipe repos...")
		autopkg_prefs = os.path.abspath(config.pkgbot_config.get("JamfPro_Dev.autopkg_prefs"))

		autopkg_repo_update_command = "{binary} repo-update all --prefs=\"{prefs}\"".format(
			binary=config.pkgbot_config.get("AutoPkg.binary"),
			prefs=autopkg_prefs
		)

		if await get_user_context():
			autopkg_repo_update_command = "su - {console_user} -c \"{autopkg_repo_update_command}\"".format(
				console_user=console_user,
				autopkg_repo_update_command=autopkg_repo_update_command,
			)

		results_autopkg_repo_update = await utils.run_process_async(autopkg_repo_update_command)

##### TO DO:
###### * Add parent recipe repos update success

		if not results_autopkg_repo_update["success"]:
			log.error("Failed to update parent recipe repos")
			log.error("{}".format(results_autopkg_repo_update["stderr"]))
			sys.exit(1)

	if args.recipe_identifier:

		recipe_id = args.recipe_identifier

		recipe_result = ( await api_helper.get_recipe_by_recipe_id(recipe_id) ).json()

		if recipe_id != recipe_result.get("recipe_id"):
			log.error("Recipe `{}` was not found in the database".format(recipe_id))
			sys.exit(1)

		recipes = [ recipe_result ]

	else:
		results_recipes = ( await api_helper.get_recipes() ).json()
		recipes = results_recipes.get("recipes")

	for a_recipe in recipes:

		await autopkg_process_wrapper(
			recipe_config=a_recipe,
			action=args.action,
			console_user=console_user,
			pkg_name=args.pkg_name,
			error_id=args.error_id
		)

	log.info("Recipe Runner:  Complete!")


if __name__ == "__main__":
	log.debug("Running recipe_runner.main")
	asyncio.run( main(sys.argv) )
