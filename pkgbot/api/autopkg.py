import hashlib
import hmac
import json
import os

from datetime import datetime
from tempfile import SpooledTemporaryFile

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, UploadFile

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
async def workflow_prod(promoted_id: int, pkg_object: models.Package_In = Body()):

	if pkg_object.promoted_date is None:
		date_to_convert = datetime.now()
	else:
		date_to_convert = pkg_object.promoted_date

	pkg_db_object = await models.Packages.filter(id=promoted_id).first()

	pkg_object.promoted_date = await utility.utc_to_local(date_to_convert)
	pkg_object.recipe_id = pkg_db_object.recipe_id
	pkg_object.status = "prod"

	updated_pkg_object = await api.package.update(promoted_id, pkg_object)

	return await api.send_msg.promote_msg(updated_pkg_object)


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

	queued_task = task.autopkg_run.apply_async((recipes, switches.dict(), called_by), queue='autopkg', priority=6, link=None, link_error=None)

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
		queued_task = task.autopkg_run.apply_async(([ a_recipe.dict() ], switches.dict(), called_by), queue='autopkg', priority=6)

		return { "Result": "Queued background task..." , "task_id": queued_task.id }

	log.info(f"Recipe '{recipe_id}' is disabled.")

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

	task_id = task_id.get("task_id")

	log.debug(f"Receiving notification for task_id:  {task_id}")

	task_results = await utility.get_task_results(task_id)

	# log.debug(f"task_results:  {task_results}")

	event = task_results.get("event")
	event_id = task_results.get("event_id", "")
	recipe_id = task_results.get("recipe_id")
	success = task_results.get("success")
	stdout = task_results.get("stdout")
	stderr = task_results.get("stderr")


	if event == "failed_trust":
		""" Update Slack message that recipe_id failed verify-trust-info """
		redacted_error = await utility.replace_sensitive_strings(stderr)
		# await api.recipe.recipe_trust_verify_failed({"recipe_id": recipe_id, "msg": redacted_error})
		await api.recipe.recipe_trust_verify_failed(recipe_id, redacted_error)

	elif event == "update_trust_info":
		""" Update Slack message with result of update-trust-info attempt """

		if success:
			await api.recipe.recipe_trust_update_success(recipe_id, success, event_id)

		else:
			await api.recipe.recipe_trust_update_failed(recipe_id, success, event_id)

	elif event == "error" or not task_results.get("success"):

##### Failed running recipe
		# Post Slack Message with results
		log.error(f"Failed running:  {recipe_id}")
		# log.error(f"return code status:  {results_autopkg_run['status']}")
		# log.error(f"stdout:  {stdout}")
		# log.error(f"stderr:  {stderr}")

		try:
			plist_contents = await utility.find_receipt_plist(stdout)
			run_error = await utility.parse_recipe_receipt(plist_contents, "RecipeError")
		except Exception:
			run_error = stderr

		redacted_error = await utility.replace_sensitive_strings(run_error)

		if event == "recipe_run_prod":
			# Promotion Failed
##### Idea:  thread the error message with the original message?  Post Ephemeral Message to PkgBot Admin?

			# Get the recipe that failed to be promoted
			pkg_db_object = await models.Packages.filter(id=event_id).first()
			recipe_id = pkg_db_object.recipe_id
			software_title = pkg_db_object.name
			software_version = pkg_db_object.version

			redacted_error = { 
				"Failed to promote:": f"{software_title} v{software_version}",
				"Error:": redacted_error
			}
			log.error(f"Failed to promote:  {pkg_db_object.pkg_name}")

		await api.recipe.recipe_error(recipe_id, redacted_error)

	elif event in ("recipe_run_dev", "recipe_run_prod"):

		if task_results.get("success"):

			plist_contents = await utility.find_receipt_plist(stdout)

			# Get the log info for PackageUploader
			pkg_processor = await utility.parse_recipe_receipt(plist_contents, "JamfPackageUploader")

			pkg_name = pkg_processor.get("Output").get("pkg_name")
			pkg_data = {
				"name": (pkg_name).rsplit("-", 1)[0],
				"pkg_name": pkg_name,
				"recipe_id": recipe_id,
				"version": pkg_processor.get("Input").get("version"),
				"notes": pkg_processor.get("Input").get("pkg_notes")
			}

			try:
				# Get the log info for PolicyUploader
				policy_processor = await utility.parse_recipe_receipt(plist_contents, "JamfPolicyUploader")
				policy_results = policy_processor.get("Output").get("jamfpolicyuploader_summary_result").get("data")
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

			except:
				log.info("An icon was not identified, therefore it was not uploaded into PkgBot.")

			if event == "recipe_run_dev":

				# No, don't use this....instead see if it's already in the data base
				# if pkg_processor.get("Output").get("pkg_uploaded"):

				# Check if the package has already been created in the database
				pkg_db_object = await models.Packages.filter(pkg_name=pkg_name).first()

				if not pkg_db_object:
					log.debug("New software title posted to dev...")

					# pkg_data["jps_id_dev"] = jps_pkg_id
					# pkg_data["jps_url"] = config.JamfPro_Dev.get("jps_url")

					await workflow_dev(models.Package_In(pkg_data))

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

				await workflow_prod(event_id, models.Package_In(**pkg_data))






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


