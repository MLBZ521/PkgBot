import hashlib
import hmac
import json
import os

from datetime import datetime

from fastapi import APIRouter, Body, Depends, Header, Request

import config, settings, utilities.common as utility
from db import models
from api import package, recipe, user
from api.slack import send_msg
# from execute import recipe_manager, recipe_runner
from tasks import task, task_utils


from utilities.celery import get_task_info



config.load()
log = utility.log
router = APIRouter(
	prefix = "/autopkg",
	tags = ["autopkg"],
##### Temp removal for development/testing
	# dependencies = [Depends(user.verify_admin)],
	responses = settings.db.custom_responses
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

	created_pkg = await package.create(pkg_object)
	results = await send_msg.new_pkg_msg(created_pkg)
	pkg_db_object = await models.Packages.filter(id=created_pkg.id).first()
	pkg_db_object.slack_ts = results.get("ts")
	pkg_db_object.slack_channel = results.get("channel")
	await pkg_db_object.save()

	# Update the "Last Ran" attribute for this recipe
	recipe_object = await models.Recipes.filter(recipe_id=pkg_db_object.recipe_id).first()
	recipe_object.last_ran = pkg_db_object.packaged_date
	await recipe_object.save()

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

	updated_pkg_object = await package.update(packages[-1].id, pkg_object)

	# try:
	results = await send_msg.promote_msg(updated_pkg_object)
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
# 			"--pkg-name", "{}".format(pkg_object.dict().get("pkg_name"))
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

	recipes = (await recipe.get_recipes()).get("recipes")

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

	a_recipe = await recipe.get_by_recipe_id(recipe_id)

	if a_recipe.dict().get("enabled"):
		# queued_task = task.autopkg_run.delay(a_recipe.dict()["recipe_id"], switches.dict())
		# queued_task = task.autopkg_run.delay((a_recipe.dict()["recipe_id"]), switches.dict(), priority=6)
		queued_task = task.autopkg_run.apply_async(([ a_recipe.dict() ], switches.dict()), queue='autopkg', priority=6)

		return { "Result": "Queued background task..." , "task_id": queued_task.id }

	return { "Result": "Recipe is disabled" }


@router.post("/verify-trust/recipe/{recipe_id}", summary="Validates a recipes trust info",
	description="Validates a recipes trust info in a background task.")
async def autopkg_verify_recipe(recipe_id: str, switches: models.AutopkgCMD = Body(), called_by: str = "slack"):
	"""Runs the passed recipe id.

	Args:
		recipe (str): Recipe ID of a recipe
		switches (str):

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	log.info(f"Verify trust in  on recipe:  {recipe_id}")

	a_recipe = await recipe.get_by_recipe_id(recipe_id)

	# queued_task = task.autopkg_verify_trust.delay(a_recipe, switches)
	queued_task = task.autopkg_verify_trust.apply_async((a_recipe.dict()["recipe_id"], switches.dict()), queue='autopkg', priority=5)

	return { "Result": "Queued background task..." , "task_id": queued_task.id }



async def verify_pkgbot_webhook(request: Request):

	try:
		# slack_timestamp = request.headers.get("X-Slack-Request-Timestamp")

		# if abs(time.time() - int(slack_timestamp)) > 60 * 5:
		# 	# The request timestamp is more than five minutes from local time.
		# 	# It could be a replay attack, so let's ignore it.
		# 	return False

		if hmac.compare_digest(
				utility.compute_hex_digest(
					bytes(config.pkgbot_config.get('PkgBot.webhook_secret'), "utf-8"),
					(await request.body()),#.decode("UTF-8")
					hashlib.sha512
				),
				(request.headers.get("x_hook_signature")).encode()
			):

			log.debug("Valid PkgBot Webhook message")
			return True

		else:
			log.warning("Invalid PkgBot Webhook message!")
			return False

	except Exception:

		return False


@router.post("/receive", summary="Handles incoming task messages with autopkg results",
	description="This endpoint receives incoming messages from tasks and calls the required "
		"actions based on the message after verifying the authenticity of the source.")
async def receive(
	request: Request,
	# payload: models.AutoPkgTaskResults = Body(),
	task_id: str = Body(),
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



	# log.debug(f"payload:  {str(json.dumps(payload.dict())).encode('utf-8')}")
	# log.debug(f"x_hook_signature:  {x_hook_signature}")

	# if x_hook_signature and not hmac.compare_digest(
	# 	task_utils.generate_hook_signature(task_id),
	# 	x_hook_signature
	# ):

		# raw_input = str(json.dumps(payload.dict())).encode("utf-8")

		# input_hmac = hmac.new(
		# 	key=bytes(config.pkgbot_config.get('PkgBot.webhook_secret'), "utf-8"),
		# 	msg=raw_input,
		# 	digestmod="sha512"
		# )
		# log.debug(f"input_hmac.hexdigest():  {input_hmac.hexdigest()}")

		# log.error("Invalid message signature")
		# # response.status_code = 400
		# # log.warning("Invalid request")
		# # return { "results":  500 }
		# return {"Result": "Invalid message signature"}


	# log.info("Message signature checked ok")

	if await verify_pkgbot_webhook(request):

	# request_body = await request.body()
	# request_json = await request.body()
	# log.debug(f"request:  {request}")
	# log.debug(f"request.dir:  {dir(request)}")
	# log.debug(f"request.body():  {await request.body()}")
	# log.debug(f"request.body().decoded:  {(await request.body()).decode()}")
	# log.debug(f"request.body().decoded.type:  {type((await request.body()).decode())}")
	# log.debug(f"request.json():  {await request.json()}")
	# log.debug(f"request.keys():  {request.keys()}")
	# log.debug(f"request.values():  {request.values()}")
	# log.debug(f"request_json:  {request_json}")


	# task_id = (await request.body()).decode().split("=")[1]
	# log.debug(f"task_id: {task_id}")
	# log.debug(get_task_info(task_id))

		log.debug(f"task_id:  {task_id}")
	# recipe_id = payload.get("recipe_id")
	# log.debug(f"recipe_id:  {recipe_id}")
	# log.debug(f"recipe_id.type:  {type(recipe_id)}")
	# error_msg = payload.get("msg")
	# log.debug(f"error_msg:  {error_msg}")


	# else:
	# 	log.info("No message signature to check")
	# return {"result": "ok"}


		task_results = await get_task_results(task_id)

		event = task_results.get("event")
		recipe_id = task_results.get("recipe_id")
		success = task_results.get("success")
		stdout = task_results.get("stdout")
		stderr = task_results.get("stderr")

		if event == "error":
			# api_helper.chat_recipe_error(recipe_id, results_autopkg_recipe_trust['stdout'] )
			await recipe.error(recipe_id, stdout)


		elif event == "failed_trust":
			""" Update Slack message that recipe_id failed verify-trust-info """
			# api_helper.chat_failed_trust(recipe_id, results_autopkg_recipe_trust['stderr'] )

			# payload = {
			# 	"recipe_id": recipe_id,
			# 	"msg": stderr
			# }

			# await request( "post", "/recipe/trust/verify/failed", json=payload )

			await recipe.reciepe_trust_verify_failed(payload)


		elif event == "update_trust_info":
			""" Update slack message that recipe_id was trusted """
		# or failed
			# if result == "success":
			# 	endpoint = "trust/update/success"
			# 	api_helper.chat_update_trust_msg(recipe_id, result="success", error_id = error_id)
			# else:
			# 	endpoint = "trust/update/failed"

##### Need to figure out where the error_id is coming from...  (How it's going to be passed to/back)
			if success:

				await recipe_trust_update_success(recipe_id, msg, error_id)

			else:

				await recipe_trust_update_failed(recipe_id, msg, error_id)



		elif event in ("recipe_run_dev", "recipe_run_prod") :

			plist_contents = await utility.find_receipt_plist(stdout)


			if task_results.get("success"):

				pkg_results = await utility.parse_recipe_receipt(plist_contents, "JamfPackageUploader")
				policy_results = await utility.parse_recipe_receipt(plist_contents, "JamfPolicyUploader")

				pkg_data = {
					"name": pkg_results.get("Input").get("pkg_name").rsplit("-", 1)[0],
					"pkg_name": pkg_results.get("Input").get("pkg_name"),
					"recipe_id": recipe_id,
					"version": pkg_results.get("Input").get("version"),
					"pkg_notes": pkg_results.get("Input").get("pkg_notes")
				}



				if pkg_results.get("Input").get("JSS_URL") == config.pkgbot_config.get('JamfPro_Dev.jps_url'):
				# if event == "recipe_run_dev":
					log.debug("Posted to dev...")

					pkg_data["icon"] = "/path/to/icon"
					# pkg_data["jps_id_dev"] = jps_pkg_id
					# pkg_data["jps_url"] = config.pkgbot_config.get('JamfPro_Dev.jps_url')

					await workflow_dev(pkg_data)

				# if event == "recipe_run_prod":
				elif pkg_results.get("Input").get("JSS_URL") == config.pkgbot_config.get('JamfPro_Prod.jps_url'):
					log.debug("Promoted to Production...")

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
				log.error("Failed running:  {}".format(recipe_id))
				# log.error("return code status:  {}".format(results_autopkg_run['status']))
				# log.error("stdout:  {}".format(stdout))
				# log.error("stderr:  {}".format(stderr))

				try:
					# run_receipt = re.search(
					# 	r'Receipt written to (.*)', stdout).group(1)
					# plist_contents = await utils.plist_reader(run_receipt)

					# for step in reversed(plist_contents):
					# 	if step.get("RecipeError") != None:
					# 		run_error = step.get("RecipeError")
					# 		break
					# run_error = utils.find_and_parse_recipe_receipt(stdout, "RecipeError")
					pkg_results = await utility.parse_recipe_receipt(plist_contents, "RecipeError")


				except:
					run_error = stderr

				redacted_error = await utility.replace_sensitive_strings(run_error)

				await recipe.error(recipe_id, redacted_error)









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


