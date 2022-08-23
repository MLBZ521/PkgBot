import hashlib
import hmac
import json
import os

from datetime import datetime

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request

from fastapi_utils.tasks import repeat_every


from pkgbot import api, config, settings
from pkgbot.db import models
from pkgbot.tasks import task, task_utils
from pkgbot.utilities import common as utility


from pkgbot.utilities.celery import get_task_info


config = config.load_config()
log = utility.log
router = APIRouter(
	prefix = "/autopkg",
	tags = ["autopkg"],
##### Temp removal for development/testing
	# dependencies = [Depends(user.verify_admin)],
	responses = settings.api.custom_responses
)


@router.post("/workflow/dev", summary="Dev Workflow",
	description="The Dev workflow will create a new package and post to chat.")
# async def dev(pkg_object: models.Package_In = Body(..., pkg_object=Depends(models.Package_In))):
async def workflow_dev(pkg_object: models.Package_In = Body()):
	"""Workflow to create a new package in the database and then post a message to chat.

	Args:
		pkg_object (models.Package_In): Details about a package object

	Returns:
		[JSON]: Result of the operation
	"""

	created_pkg = await api.package.create(pkg_object)
	results = await api.send_msg.new_pkg_msg(created_pkg)
	pkg_db_object = await models.Packages.filter(id=created_pkg.id).first()
	pkg_db_object.slack_ts = results.get("ts")
	pkg_db_object.slack_channel = results.get("channel")
	await pkg_db_object.save()

	return { "Result": "Success" }


@router.post("/workflow/prod", summary="Production Workflow",
	description="Workflow to move a package into production and update the Slack message.")
# async def prod(pkg_object: models.Package_In = Body(..., pkg_object=Depends(models.Package_In))):
async def workflow_prod(pkg_object: models.Package_In = Body()):

	if pkg_object.promoted_date is None:
		date_to_convert = datetime.now()

	else:
		date_to_convert = pkg_object.promoted_date

	pkg_object.promoted_date = await utility.utc_to_local(date_to_convert)

	pkg_object.status = "prod"

	packages = await models.Package_Out.from_queryset(
		models.Packages.filter(recipe_id=pkg_object.recipe_id, version=pkg_object.version))

	updated_pkg_object = await api.package.update(packages[-1].id, pkg_object)

	# try:
	results = await api.send_msg.promote_msg(updated_pkg_object)
	return { "Result": "Success" }

	# except:
	#     return { "statuscode": 400, "Result": "Failed to post message" }


# @router.post("/workflow/promote", summary="Promote package to production",
# description="Promote a package to production by id.")
# async def promote_package(background_tasks, id: int = Depends(package.get_package_by_id)):

# 	pkg_object = await package.get_package_by_id(id)

# 	background_tasks.add_task(
# 		recipe_runner.main,
# 		[
# 			"run",
# 			"--action", "promote",
# 			"--environment", "prod",
# 			"--recipe-identifier", pkg_object.dict().get("recipe_id"),
# 			"--pkg-name", f"{pkg_object.dict().get('pkg_name')}"
# 		]
# 	)

# 	return { "Result": "Queued background task..." }


# @router.post("/workflow/deny", summary="Do not promote package to production",
# 	description="Performs the necessary actions when a package is not approved to production use.")
# async def deny_package(background_tasks, id: int = Depends(package.get_package_by_id)):

# 	pkg_object = await package.get_package_by_id(id)

# 	background_tasks.add_task(
# 		recipe_manager.main,
# 		[
# 			"single",
# 			"--recipe-identifier", pkg_object.dict().get("recipe_id"),
# 			"--disable",
# 			"--force"
# 		]
# 	)

# 	await send_msg.deny_pkg_msg(pkg_object)






async def determine_callback(caller: str):

	if caller == "schedule":
		return "PkgBot"

	if caller == "slack":
		return "ephemeral"





##### Disabled until further testing is performed on all tasks
# @repeat_every(seconds=config.Services.get("autopkg_service_start_interval'))
@router.post("/run/recipes", summary="Run all recipes",
	description="Runs all recipes in a background task.")
async def autopkg_run_recipes(switches: models.AutopkgCMD = Body(), called_by: str = "schedule"):
	"""Run all recipes in the database.

	Args:
		switches (dict): A dictionary that will be used as switches to the `autopkg` binary

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	log.info("Running all recipes")

	# callback = await determine_callback(called_by)

	recipes = (await api.recipe.get_recipes({ "enable": True, "manual_only": False })).get("recipes")

	recipes = [ a_recipe.dict() for a_recipe in recipes ]

	queued_task = task.autopkg_run.apply_async((recipes, switches.dict()), queue='autopkg', priority=6, link=None, link_error=None)

	return { "Result": "Queued background task..." , "task_id": queued_task.id }






@router.post("/run/recipe/{recipe_id}", summary="Executes a recipes",
	description="Executes a recipe in a background task.")
async def autopkg_run_recipe(recipe_id: str, switches: models.AutopkgCMD = Body(), called_by: str = "schedule"):
	"""Runs the passed recipe id.

	Args:
		recipe (str): Recipe ID of a recipe
		switches (str):

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	log.info(f"Running recipe:  {recipe_id}")

	a_recipe = await api.recipe.get_by_recipe_id(recipe_id)

	if a_recipe.dict().get("enabled"):
		# queued_task = task.autopkg_run.delay(a_recipe.dict()["recipe_id"], switches.dict())
		# queued_task = task.autopkg_run.delay((a_recipe.dict()["recipe_id"]), switches.dict(), priority=6)
		queued_task = task.autopkg_run.apply_async(([ a_recipe.dict() ], switches.dict()), queue='autopkg', priority=6)

		return { "Result": "Queued background task..." , "task_id": queued_task.id }

	return { "Result": "Recipe is disabled" }


@router.post("/verify-trust/recipe/{recipe_id}", summary="Validates a recipes trust info",
	description="Validates a recipes trust info in a background task.")
async def autopkg_verify_recipe(recipe_id: str, switches: models.AutopkgCMD = Depends(models.AutopkgCMD), called_by: str = "slack"):
	"""Runs the passed recipe id.

	Args:
		recipe (str): Recipe ID of a recipe
		switches (str):

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	a_recipe = await api.recipe.get_by_recipe_id(recipe_id)

	queued_task = task.autopkg_verify_trust.apply_async(
		(a_recipe.dict().get("recipe_id"), switches.dict(exclude_unset=True, exclude_none=True), "api_direct"),
		queue='autopkg', priority=5)

	return { "Result": "Queued background task..." , "task_id": queued_task.id }



async def verify_pkgbot_webhook(request: Request):

	try:
##### Add a timestamp check
		# slack_timestamp = request.headers.get("X-Slack-Request-Timestamp")

		# if abs(time.time() - int(slack_timestamp)) > 60 * 5:
		# 	# The request timestamp is more than five minutes from local time.
		# 	# It could be a replay attack, so let's ignore it.
		# 	return False

		body = json.loads(await request.body())

		digest = await utility.compute_hex_digest(
			config.PkgBot.get('webhook_secret').encode("UTF-8"),
			str(body).encode("UTF-8"),
			hashlib.sha512
		)

		if hmac.compare_digest(
			digest.encode("UTF-8"),
			(request.headers.get("x-pkgbot-signature")).encode("UTF-8")
		):
			log.debug("Valid PkgBot Webhook message")
			return True

		else:
			log.warning("Invalid PkgBot Webhook message!")
			return False

	except Exception:
		log.error("Exception attempting to validate PkgBot Webhook!")
		return False


@router.post("/receive", summary="Handles incoming task messages with autopkg results",
	description="This endpoint receives incoming messages from tasks and calls the required "
		"actions based on the message after verifying the authenticity of the source.")
async def receive(
	request: Request,
	# payload: models.AutoPkgTaskResults = Body(),
	task_id = Body(),
	# webhook_input: WebhookData,
	# response: Response,
	# content_length: int = Header(...),
	# x_hook_signature: str = Header(None)
):

	# To prevent memory allocation attacks
	# if content_length > 1_000_000:
	# 	log.error(f"Content too long ({content_length})")
	# 	response.status_code = 400
	# 	return {"result": "Content too long"}

	if not await verify_pkgbot_webhook(request):
		raise HTTPException(status_code=401, detail="Failed to authenticate webhook.")

	log.debug(f"Receiving notification for task_id:  {task_id}")

	task_results = await utility.get_task_results(task_id)

	event = task_results.get("event")
	event_id = task_results.get("event_id", "")
	recipe_id = task_results.get("recipe_id")
	success = task_results.get("success")
	stdout = task_results.get("stdout")
	stderr = task_results.get("stderr")

	if event == "error":
		await api.recipe.error(recipe_id, stdout)

	elif event == "failed_trust":
		""" Update Slack message that recipe_id failed verify-trust-info """
		await api.recipe.recipe_trust_verify_failed({ "recipe_id": recipe_id, "msg": stderr })

	elif event == "update_trust_info":
		""" Update Slack message with result of update-trust-info attempt """

		if success:
			await api.recipe.recipe_trust_update_success(recipe_id, success, event_id)

		else:
			await api.recipe.recipe_trust_update_failed(recipe_id, success, event_id)

	elif event in ("recipe_run_dev", "recipe_run_prod"):

		plist_contents = await utility.find_receipt_plist(stdout)

		if task_results.get("success"):

			pkg_processor = await utility.parse_recipe_receipt(plist_contents, "JamfPackageUploader")
			policy_processor = await utility.parse_recipe_receipt(plist_contents, "JamfPolicyUploader")
##### Do we care about Policy updates at all?  (I don't think so...)
	# Need the icon from it?
			pkg_data = {
				"name": pkg_processor.get("Input").get("pkg_name").rsplit("-", 1)[0],
				"pkg_name": pkg_processor.get("Output").get("pkg_name"),
				"recipe_id": recipe_id,
				"version": pkg_processor.get("Output").get("data").get("version"),
				"pkg_notes": pkg_processor.get("Input").get("pkg_notes")
			}

			if event == "recipe_run_dev":

				if pkg_processor.get("Output").get("pkg_uploaded"):

					log.debug("Posted to dev...")

					# pkg_data["jps_id_dev"] = jps_pkg_id
					# pkg_data["jps_url"] = config.JamfPro_Dev.get("jps_url')

##### Need to figure out icon logic
					policy_results = policy_processor.get("Output").get("jamfpolicyuploader_summary_result").get("data")
					pkg_data["icon"] = policy_results.get("icon")
					await views.upload_icon(policy_results.get("policy_icon_path"))
					await workflow_dev(pkg_data)

				# else:
					# No new pkg

				# Update the "Last Ran" attribute for this recipe
				recipe_object = await models.Recipes.filter(recipe_id=recipe_id).first()
				recipe_object.last_ran = await utility.utc_to_local(datetime.now())
				recipe_object.recurring_fail_count = 0
				await recipe_object.save()

			elif event == "recipe_run_prod":
				log.debug("Promoted to production...")

				format_string = "%Y-%m-%d %H:%M:%S.%f"
				promoted_date = datetime.strftime(datetime.now(), format_string)

				# pkg_data["jps_id_prod"] = jps_pkg_id,
				pkg_data["promoted_date"] = promoted_date

				# if jps_icon_id:
				# 	pkg_data["icon_id"] = jps_icon_id
				# 	pkg_data["jps_url"] = jps_url

				await workflow_prod(pkg_data)


		else:

##### Failed running recipe
			# Post Slack Message with results
			log.error(f"Failed running:  {recipe_id}")
			# log.error(f"return code status:  {results_autopkg_run['status']}")
			# log.error(f"stdout:  {stdout}")
			# log.error(f"stderr:  {stderr}")

			try:
				run_error = await utility.parse_recipe_receipt(plist_contents, "RecipeError")
			except Exception:
				run_error = stderr

			redacted_error = await utility.replace_sensitive_strings(run_error)


			if event == "recipe_run_prod":
				# Promotion Failed
				log.error("Failed to promote pkg!")
##### Need the promotion event_id here!  Or....?
				# event_id = ""
##### Can we determine more info to relate it to an event id?
				redacted_error = { "Failed to promote a pkg": redacted_error }

			await api.recipe.recipe_error(recipe_id, redacted_error)








# curl -X 'POST' \
#   'http://localhost:8000/autopkg/receive' \
#   -H 'accept: application/json' \
#   -H 'content-length: 10000' \
#   -H 'x-hook-signature: asdf' \
#   -H 'Content-Type: application/json' \
#   -d '{
#   "action": "run",
#   "recipe_id":  "local.jamf.Chrome",
#   "prefs": "/some/path/to/preferences.plist",
#   "verbose": "vvvv"
# }'


