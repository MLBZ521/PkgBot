import time

from datetime import datetime
from tempfile import SpooledTemporaryFile

from fastapi import UploadFile

from pkgbot import api, config, core
from pkgbot.db import models
from pkgbot.utilities import common as utility


config = config.load_config()
log = utility.log


async def event_handler(task_id, loop_count=0):

	task_results = (await utility.get_task_results(task_id)).get("task_results")
	# log.debug(f"task_results: {task_results}")
	# log.debug(f"task_results.type: {type(task_results)}")

	try:
		event = task_results.get("event")

	except Exception:
		# Seeing a random issue where looking up the task_id returns "None" here, but if I manually
		# lookup the task_id later, the results are found and the task completed successfully...
		# It's almost always the _very last_ recipe to run as well (after ~100 recipes).
		# Ideas:
			# Due to task prioritization?
				# But...why when the task is essentially finished when the webhook is sent
				# And it just started (or I just started noticing it)
		if loop_count > 10:
			raise Exception(f"Failed getting task results for {task_id}")

		log.error(f"FAILED GETTING TASK RESULTS for {task_id} -- WHY?!?")
		log.debug(f"task_results:  {task_results}")
		# log.debug(f"task_results.result:  {task_results.result}")
		log.debug("Sleeping for one second...")
		time.sleep(1)
		return await event_handler(task_id, loop_count + 1)

	log.debug(f"event: {event}")
	task_results |= { "task_id": task_id }

	match event:

		case "verify_trust_info":
			await event_verify_trust_info(task_results)

		case "update_trust_info":
			await event_update_trust_info(task_results)

		case event if event in {
			"autopkg_repo_update", "disk_space_critical", "failed_pre_checks", "private_git_pull"}:
			await event_failed_pre_checks(task_results)

		case "disk_space_warning":
			await event_disk_space_warning(task_results)

		case "error" | "error" if not task_results.result.get("success"):
			await event_error(task_results)

		case event if event in ("recipe_run_dev", "recipe_run_prod"):
			await event_recipe_run(task_results)

		case "autopkg_version":
			await event_autopkg_version(task_results)

		case "repo-add":
			await event_autopkg_repo_add(task_results)


async def event_details(task_results):

	return (
		task_results.get("event"),
		task_results.get("event_id", ""),
		models.AutoPkgCMD(**task_results.get("autopkg_cmd")),
		task_results.get("recipe_id") if "recipe_id" in task_results.keys() else task_results.get("repo"),
		task_results.get("success"),
		task_results.get("stdout"),
		task_results.get("stderr")
	)
	# or: {
		# "event": task_results.result.get("event"),
		# "event_id": task_results.result.get("event_id", ""),
		# "autopkg_cmd": task_results.result.get("autopkg_cmd"),
		# "recipe_id": task_results.result.get("recipe_id"),
		# "success": task_results.result.get("success"),
		# "stdout": task_results.result.get("stdout"),
		# "stderr": task_results.result.get("stderr")
	# }


async def event_verify_trust_info(task_results):
	""" When a user has requested to run `autopkg verify-trust-info <recipe>` """

	event, event_id, autopkg_cmd, recipe_id, success, stdout, stderr = await event_details(task_results)

	if autopkg_cmd.ingress == "Slack":
		# Post ephemeral msg to Slack user
		log.debug(
			f"`{recipe_id}`'s trust info was checked via Slack command by {autopkg_cmd.egress}.")

		if success:
			text = f"Recipe trust info passed for `{recipe_id}`!  :link-success:"
		else:
			text = f"Recipe trust info failed for `{recipe_id}`!  :git-pr-check-failed:"

		await core.chatbot.send.direct_msg(
			user = autopkg_cmd.egress,
			text = text,
			alt_text = "Results from task...",
			channel = autopkg_cmd.channel,
			image = None,
			alt_image_text = None
		)

	if success:
		log.info(f"Trust info verified for:  {recipe_id}")

	else:
		# Send message that recipe_id failed verify-trust-info
		redacted_error = await utility.replace_sensitive_strings(stderr)
		await core.recipe.verify_trust_failed(recipe_id, redacted_error)


async def event_update_trust_info(task_results):
	""" Update message with result of update-trust-info attempt """

	event, event_id, autopkg_cmd, recipe_id, success, stdout, stderr = await event_details(task_results)

	if event_id:
		await core.recipe.update_trust_result(success, event_id, str(stderr))

	elif autopkg_cmd.ingress == "Slack":
		# Post ephemeral msg to Slack user
		log.debug("Recipe trust info was updated via Slack command.")

		if success:
			text = f"Recipe trust info successfully updated for `{recipe_id}`!  :link-success:"
		else:
			text = f"Failed to update recipe trust info for `{recipe_id}`!  :git-pr-check-failed:"

		await core.chatbot.send.direct_msg(
			user = autopkg_cmd.egress,
			text = text,
			alt_text = "Results from task...",
			channel = autopkg_cmd.channel,
			image = None,
			alt_image_text = None
		)


async def event_disk_space_warning(task_results):
	""" If cache volume has low disk space """

	event, event_id, autopkg_cmd, recipe_id, success, stdout, stderr = await event_details(task_results)

	# Post Slack Message
	results = await core.chatbot.send.disk_space_msg(
		"Warning", stderr, config.PkgBot.get('icon_warning'))

	# Create DB entry
	await models.ErrorMessages.create(
		type = event,
		slack_ts = results.get('ts'),
		slack_channel = results.get('channel'),
		status = "Acknowledged"
	)


async def event_failed_pre_checks(task_results):
	""" When a pre-check task fails """

	event, event_id, autopkg_cmd, recipe_id, success, stdout, stderr = await event_details(task_results)

	for task_id in task_results.get("task_id"):

		task_results = await utility.get_task_results(task_id)
		event = task_results.get("event")

		if event == "autopkg_repo_update":
##### TODO:
			pass

		if event == "disk_space_critical":
			""" If cache volume has insufficient disk space """

			results = await core.chatbot.send.disk_space_msg(
				"Critical",
				task_results.get("stderr"),
				config.PkgBot.get('icon_error')
			)

			# Create DB entry
			await models.ErrorMessages.create(
				type = event,
				slack_ts = results.get('ts'),
				slack_channel = results.get('channel'),
				status = "Notified"
			)

		if event == "private_git_pull":
##### TODO:
			pass


async def event_error(task_results):
	""" When a recipe run or unknown event fails """

	event, event_id, autopkg_cmd, recipe_id, success, stdout, stderr = await event_details(task_results)

	await handle_autopkg_error(task_id = task_results.get("task_id"), event = event, event_id = event_id,
		autopkg_cmd = autopkg_cmd, recipe_id = recipe_id, success = success, stdout = stdout,
		stderr = stderr
	)


async def event_recipe_run(task_results):

	event, event_id, autopkg_cmd, recipe_id, success, stdout, stderr = await event_details(task_results)

	if not success:
		return await event_error(task_results)

	plist_contents = await utility.find_receipt_plist(stdout)

	# Get the log info for PackageUploader
	pkg_processor = await utility.parse_recipe_receipt(
		plist_contents, "JamfPackageUploader")
	pkg_name = pkg_processor.get("Output").get("pkg_name")
	pkg_data = {
		"name": (pkg_name).rsplit("-", 1)[0],
		"pkg_name": pkg_name,
		"recipe_id": recipe_id,
		"version": pkg_processor.get("Input").get("version"),
		"notes": pkg_processor.get("Input").get("pkg_notes")
	}

	if event == "recipe_run_dev":

		try:
			# Get the log info for PolicyUploader
			policy_processor = await utility.parse_recipe_receipt(
				plist_contents, "JamfPolicyUploader")
			policy_results = policy_processor.get(
				"Output").get("jamfpolicyuploader_summary_result").get("data")
			pkg_data["icon"] = policy_results.get("icon")

			# Create a temporary file to hold the icon data and upload it.
			# This is required since we're not actually using an
			# HTTP client to interface with the API endpoint.
			icon_data = SpooledTemporaryFile()
			with open(policy_results.get("icon_path"), "rb") as icon_path:
				icon_data.write(icon_path.read())
			_ = icon_data.seek(0)
			icon = UploadFile(filename=pkg_data["icon"], file=icon_data)
			await api.views.upload_icon(icon)

		except Exception:
			log.info(
				f"An icon was not identified, therefore it was not uploaded into PkgBot.  Review task_id:  {task_results}")

		try:

			# No, don't check the processor summary...
			# if pkg_processor.get("Output").get("pkg_uploaded"):

			# Instead, check if the package has already been created in the database, this
			# ensures a message is posted if it failed to post previously.
			pkg_db_object = await models.Packages.filter(pkg_name=pkg_name).first()

			if pkg_db_object:
				slack_msg = f"`{task_results.get('task_id')}`:  Recipe run for `{recipe_id}` did not find a new version."

			else:
				log.info(f"New package posted to dev:  {pkg_name}")

				pkg_object = models.Package_In(**pkg_data)
				await core.autopkg.workflow_dev(pkg_object)
				slack_msg = f"`{task_results.get('task_id')}`:  Recipe run for `{recipe_id}` found a new version `{pkg_data.get('version')}`!"

			if autopkg_cmd.ingress == "Slack":
				await core.chatbot.send.direct_msg(
					user = autopkg_cmd.egress,
					text = slack_msg,
					alt_text = "Results from task...",
					channel = autopkg_cmd.channel,
					image = None,
					alt_image_text = None
				)

			# Update attributes for this recipe
			recipe_object = await models.Recipes.filter(recipe_id=recipe_id).first()
			recipe_object.last_ran = await utility.utc_to_local(datetime.now())
			recipe_object.recurring_fail_count = 0
			await recipe_object.save()

		except Exception as exception:

			await handle_exception(task_id = task_results.get("task_id"), event = event, event_id = event_id,
				autopkg_cmd = autopkg_cmd, recipe_id = recipe_id, success = success,
				exception = exception
			)

	elif event == "recipe_run_prod":
		log.info(f"Package promoted to production:  {pkg_name}")

		format_string = "%Y-%m-%d %H:%M:%S.%f"
		promoted_date = datetime.strftime(datetime.now(), format_string)
		pkg_data["promoted_date"] = promoted_date

		await core.autopkg.workflow_prod(event_id, models.Package_In(**pkg_data))


async def event_autopkg_version(task_results):
	""" When a user requests `autopkg version` """

	event, event_id, autopkg_cmd, target, success, stdout, stderr = await event_details(task_results)

	if autopkg_cmd.ingress in [ "Schedule", "API" ]:

		if success:
			# This shouldn't ever be called?
			log.debug(f"AutoPkg version:  {stdout}")

		else:
			# Send error message
			redacted_error = await utility.replace_sensitive_strings(stderr)
			await core.chatbot.send.basic_msg(
				f"Failed to obtain the AutoPkg Version.\nError:  {redacted_error}",
				config.PkgBot.get("icon_error"),
				alt_image_text="Error"
			)

	elif autopkg_cmd.ingress == "Slack":
		# Post ephemeral msg to Slack user
		log.debug(f"{autopkg_cmd.egress} requested the AutoPkg version.")

		if success:
			text = f"AutoPkg version:  `{stdout}`  :link-success:"
		else:
			text = f"Uh oh!  Something with wrong:  `{stderr}`!  :git-pr-check-failed:"

		await core.chatbot.send.direct_msg(
			user = autopkg_cmd.egress,
			text = text,
			alt_text = "Results from task...",
			channel = autopkg_cmd.channel,
			image = None,
			alt_image_text = None
		)


async def event_autopkg_repo_add(task_results):
	""" When a recipe repo is added """

	event, event_id, autopkg_cmd, repo, success, stdout, stderr = await event_details(task_results)

	if autopkg_cmd.ingress in [ "Schedule", "API" ]:

		if success:
			# This shouldn't ever be called?
			log.debug(f"Added recipe repo(s):  {repo}")

		else:
			# Send error message
			redacted_error = await utility.replace_sensitive_strings(stderr)
			await core.chatbot.send.basic_msg(
				f"Failed to add recipe repo(s):  {repo}.\nError:  {redacted_error}",
				config.PkgBot.get("icon_error"),
				alt_image_text="Error"
			)

	elif autopkg_cmd.ingress == "Slack":
		# Post ephemeral msg to Slack user
		log.debug(f"{autopkg_cmd.egress} requested to add recipe repo:  {repo}.")

		if success:
			text = f"Added recipe repo(s):  `{repo}`  :link-success:"
		else:
			text = f"Uh oh!  Something with wrong:  `{stderr}`!  :git-pr-check-failed:"

		await core.chatbot.send.direct_msg(
			user = autopkg_cmd.egress,
			text = text,
			alt_text = "Results from task...",
			channel = autopkg_cmd.channel,
			image = None,
			alt_image_text = None
		)


async def handle_autopkg_error(**kwargs):

	task_id = kwargs.get("task_id")
	event = kwargs.get("event")
	event_id = kwargs.get("event_id")
	autopkg_cmd = kwargs.get("autopkg_cmd")
	recipe_id = kwargs.get("recipe_id")
	success = kwargs.get("success")
	stdout = kwargs.get("stdout")
	stderr = kwargs.get("stderr")

	# Post message with results
	log.error(f"Failed running:  {recipe_id}")

	try:
		plist_contents = await utility.find_receipt_plist(stdout)
		run_error = await utility.parse_recipe_receipt(plist_contents, "RecipeError")
	except Exception:
		run_error = stderr

	redacted_error = await utility.replace_sensitive_strings(run_error)

	if event == "recipe_run_prod":
		# Promotion Failed
##### TODO:
# Possible ideas:
	# Thread the error message with the original message?
	# Post Ephemeral Message to PkgBot Admin?

		# Get the recipe that failed to be promoted
		pkg_db_object = await models.Packages.filter(id=event_id).first()
		recipe_id = pkg_db_object.recipe_id
		software_title = pkg_db_object.name
		software_version = pkg_db_object.version
		log.error(f"Failed to promote:  {pkg_db_object.pkg_name}")

		redacted_error = {
			"Failed to promote:": f"{software_title} v{software_version}",
			"Error:": redacted_error
		}

	await core.recipe.error(recipe_id, redacted_error, task_id)


async def handle_exception(**kwargs):

	task_id = kwargs.pop("task_id")
	recipe_id = kwargs.pop("recipe_id")
	event = kwargs.get("event")
	event_id = kwargs.get("event_id")
	autopkg_cmd = kwargs.get("autopkg_cmd")
	success = kwargs.get("success")
	exception = await utility.replace_sensitive_strings(kwargs.get("exception"))

	redacted_error = {
		"Encountered Exception:": {
			"Recipe ID:": recipe_id,
			"Event:": event,
			"Event ID:": event_id,
			"Success:": success,
			"Called By:": {
				"ingress": autopkg_cmd.ingress,
				"egress": autopkg_cmd.egress,
				"channel": autopkg_cmd.channel,
				"start": autopkg_cmd.start,
				"completed": autopkg_cmd.completed
			},
			"Exception:": exception
		}
	}

	await core.recipe.error(recipe_id, redacted_error, task_id)
