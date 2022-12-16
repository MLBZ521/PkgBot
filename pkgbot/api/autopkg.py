import hashlib
import hmac
import json

from datetime import datetime
from tempfile import SpooledTemporaryFile

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, UploadFile

from fastapi_utils.tasks import repeat_every

from celery.result import AsyncResult

from pkgbot import api, config, settings
from pkgbot.db import models
from pkgbot.tasks import task, task_utils
from pkgbot.utilities import common as utility


config = config.load_config()
log = utility.log
router = APIRouter(
	prefix = "/autopkg",
	tags = ["autopkg"],
	responses = settings.api.custom_responses
)


@router.get("/results/{task_id}", summary="Get the results of an autopkg task",
	description="Check if a task has completed and it's results.",
	dependencies=[Depends(api.user.get_current_user)])
async def results(task_id:  str):

	log.debug(f"Checking results for task_id:  {task_id}")
	task_results = task_utils.get_task_results(task_id)

	if task_results.status != "SUCCESS":
		return { "current_status":  task_results.status,
				 "current_result": task_results.result }

	elif task_results.result != None:

		if sub_task_ids := (task_results.result).get("Queued background tasks", None):
			sub_tasks = []

			for sub_task in sub_task_ids:

				if isinstance(sub_task, AsyncResult):
					sub_task_result = task_utils.get_task_results(sub_task.task_id)

				if isinstance(sub_task, str):
					sub_task_result = task_utils.get_task_results(sub_task)

				sub_tasks.append({sub_task_result.task_id: sub_task_result.status})

			return { "sub_task_results": sub_tasks }

		elif isinstance(task_results.result, dict):
			return { "task_results": await utility.replace_sensitive_strings(task_results.result) }

	else:
		return { "task_completion_status":  task_results.status }


@router.post("/workflow/dev", summary="Dev Workflow",
	description="The Dev workflow will create a new package and post to chat.",
	dependencies=[Depends(api.user.verify_admin)])
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
	return { "result": "Success" }


@router.post("/workflow/prod", summary="Production Workflow",
	description="Workflow to move a package into production and update the Slack message.",
	dependencies=[Depends(api.user.verify_admin)])
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


@router.on_event("startup")
@repeat_every(seconds=config.Services.get("autopkg_service_start_interval"), wait_first=True)
@router.post("/run/recipes", summary="Run all recipes",
	description="Runs all recipes in a background task.",
	dependencies=[Depends(api.user.verify_admin)])
async def autopkg_run_recipes(
	autopkg_options: models.AutoPkgCMD = Depends(models.AutoPkgCMD), called_by: str = "schedule"):
	"""Run all recipes in the database.

	Args:
		autopkg_options (dict): A dictionary that will be used as
			autopkg_options to the `autopkg` binary

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	log.info("Running all recipes")

	if not isinstance(autopkg_options, models.AutoPkgCMD):
		autopkg_options = models.AutoPkgCMD()

	# callback = await determine_callback(called_by)
	recipe_filter = models.Recipe_Filter(**{"enabled": True, "manual_only": False})
	recipes = (await api.recipe.get_recipes(recipe_filter)).get("recipes")
	recipes = [ a_recipe.dict() for a_recipe in recipes ]
	log.debug(f"Number of recipes to run:  {len(recipes)}")
	queued_task = task.autopkg_run.apply_async(
		(recipes, autopkg_options.dict(), called_by), queue="autopkg", priority=3)
	return { "result": "Queued background task" , "task_id": queued_task.id }


@router.post("/run/recipe/{recipe_id}", summary="Executes a recipes",
	description="Executes a recipe in a background task.",
	dependencies=[Depends(api.user.get_current_user)])
async def autopkg_run_recipe(recipe_id: str, called_by: str = "schedule",
	autopkg_options: models.AutoPkgCMD = Depends(models.AutoPkgCMD)):
	"""Runs the passed recipe id.

	Args:
		recipe (str): Recipe ID of a recipe
		autopkg_options (str):

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	log.info(f"Running recipe:  {recipe_id}")

	if autopkg_options.dict().get("promote"):

		pkg_object = await models.Package_Out.from_queryset_single(
			models.Packages.get(
				recipe_id=recipe_id, pkg_name=autopkg_options.dict().get("match_pkg"))
		)

		return await api.package.promote_package(id=pkg_object.dict().get("id"))

	a_recipe = await api.recipe.get_by_recipe_id(recipe_id)

	if a_recipe.dict().get("enabled"):
		queued_task = task.autopkg_run.apply_async(
			([ a_recipe.dict() ], autopkg_options.dict(), called_by), queue="autopkg", priority=3)

		return { "result": "Queued background task" , "task_id": queued_task.id }

	log.info(f"Recipe '{recipe_id}' is disabled.")
	return { "result": "Recipe is disabled" }


@router.post("/verify-trust/recipe/{recipe_id}", summary="Validates a recipes trust info",
	description="Validates a recipes trust info in a background task.",
	dependencies=[Depends(api.user.get_current_user)])
async def autopkg_verify_recipe(recipe_id: str, called_by: str = "slack",
	autopkg_options: models.AutoPkgCMD = Depends(models.AutoPkgCMD)):
	"""Runs the passed recipe id.

	Args:
		recipe (str): Recipe ID of a recipe
		autopkg_options (str):

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	a_recipe = await api.recipe.get_by_recipe_id(recipe_id)

	queued_task = task.autopkg_verify_trust.apply_async(
		(
			a_recipe.dict().get("recipe_id"),
			autopkg_options.dict(exclude_unset=True, exclude_none=True),
			called_by
		),
		queue="autopkg", priority=6
	)

	return { "result": "Queued background task" , "task_id": queued_task.id }


@router.post("/receive", summary="Handles incoming task messages with autopkg results",
	description="This endpoint receives incoming messages from tasks and calls the required "
		"actions based on the message after verifying the authenticity of the source.")
async def receive(request: Request, task_id = Body()):

	# To prevent memory allocation attacks
	# if content_length > 1_000_000:
	# 	log.error(f"Content too long ({content_length})")
	# 	response.status_code = 400
	# 	return {"result": "Content too long"}

	if not await verify_pkgbot_webhook(request):
		raise HTTPException(status_code=401, detail="Failed to authenticate webhook.")

	task_id = task_id.get("task_id")
	log.debug(f"Receiving notification for task_id:  {task_id}")
	task_results = task_utils.get_task_results(task_id)
	event = task_results.result.get("event")
	event_id = task_results.result.get("event_id", "")
	called_by = task_results.result.get("called_by")
	recipe_id = task_results.result.get("recipe_id")
	success = task_results.result.get("success")
	stdout = task_results.result.get("stdout")
	stderr = task_results.result.get("stderr")

	if event == "verify_trust_info":
		callback = await determine_callback(called_by)

		if callback == "PkgBot":

			if success:
				# This shouldn't ever be called?
				log.info(f"Trust info verified for:  {recipe_id}")

			else:
				# Send message that recipe_id failed verify-trust-info
				redacted_error = await utility.replace_sensitive_strings(stderr)
				await api.recipe.recipe_trust_verify_failed(recipe_id, redacted_error)

		elif callback == "ephemeral":
##### TO DO:
			log.debug("Recipe trust info was checked via Slack command.")
			# Post ephemeral msg to Slack user

			if success:
				# trust info verified msg
				pass
			else:
				# trust info invalid msg
				pass

	elif event == "update_trust_info":
		""" Update message with result of update-trust-info attempt """

		if success:
			await api.recipe.recipe_trust_update_success(event_id)
		else:
			await api.recipe.recipe_trust_update_failed(event_id, str(stderr))

	elif event == "error" or not success:

		await handle_autopkg_error(task_id = task_id, event = event, event_id = event_id, 
			called_by = called_by, recipe_id = recipe_id, success = success, stdout = stdout,
			stderr = stderr
		)

	elif event in ("recipe_run_dev", "recipe_run_prod"):

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
					f"An icon was not identified, therefore it was not uploaded into PkgBot.  Review task_id:  {task_id}")

			try:

				# No, don't check the processor summary...
				# if pkg_processor.get("Output").get("pkg_uploaded"):

				# Instead, check if the package has already been created in the database, this
				# ensures a message is posted if it failed to post previously.
				pkg_db_object = await models.Packages.filter(pkg_name=pkg_name).first()

				if not pkg_db_object:
					log.info(f"New package posted to dev:  {pkg_name}")
					await workflow_dev(models.Package_In(**pkg_data))

				# Update attributes for this recipe
				recipe_object = await models.Recipes.filter(recipe_id=recipe_id).first()
				recipe_object.last_ran = await utility.utc_to_local(datetime.now())
				recipe_object.recurring_fail_count = 0
				await recipe_object.save()

			except Exception as exception:

				await handle_exception(task_id = task_id, event = event, event_id = event_id,
					called_by = called_by, recipe_id = recipe_id, success = success, 
					exception = exception
				)

		elif event == "recipe_run_prod":
			log.info(f"Package promoted to production:  {pkg_name}")

			format_string = "%Y-%m-%d %H:%M:%S.%f"
			promoted_date = datetime.strftime(datetime.now(), format_string)
			pkg_data["promoted_date"] = promoted_date

			await workflow_prod(event_id, models.Package_In(**pkg_data))

	return { "result":  200 }


async def determine_callback(caller: str):

	if caller == "schedule":
		return "PkgBot"

	if caller == "slack":
		return "ephemeral"

	if caller == "api":
		return "api"


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
			config.PkgBot.get("webhook_secret").encode("UTF-8"),
			str(body).encode("UTF-8"),
			hashlib.sha512
		)

		if hmac.compare_digest(
			digest.encode("UTF-8"),
			(request.headers.get("x-pkgbot-signature")).encode("UTF-8")
		):
			# log.debug("Valid PkgBot Webhook message")
			return True

		log.warning("Invalid PkgBot Webhook message!")
		return False

	except Exception:
		log.error("Exception attempting to validate PkgBot Webhook!")
		return False


async def handle_autopkg_error(**kwargs):

	task_id = kwargs.get("task_id")
	event = kwargs.get("event")
	event_id = kwargs.get("event_id")
	called_by = kwargs.get("called_by")
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
##### Possible ideas:
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

	await api.recipe.recipe_error(recipe_id, redacted_error, task_id)


async def handle_exception(**kwargs):

	task_id = kwargs.pop("task_id")
	recipe_id = kwargs.pop("recipe_id")
	event = kwargs.get("event")
	event_id = kwargs.get("event_id")
	called_by = kwargs.get("called_by")
	success = kwargs.get("success")
	exception = await utility.replace_sensitive_strings(kwargs.get("exception"))

	redacted_error = {
		"Encountered Exception:": {
			"Event:": event,
			"Event ID:": event_id,
			"Success:": success,
			# "Called By:": called_by,
			"Exception:": exception
		}
	}

	await api.recipe.recipe_error(recipe_id, redacted_error, task_id)
