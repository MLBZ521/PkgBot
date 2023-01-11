import hashlib
import hmac
import json

from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Response, Request, status

from fastapi_utils.tasks import repeat_every

from celery.result import AsyncResult

from pkgbot import api, config, settings
from pkgbot.api.autopkg import events
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

			if len(sub_task_ids) == 1:
				return {
					"task_results": await utility.replace_sensitive_strings(
						task_utils.get_task_results(sub_task_ids[0]).result)
				}

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
async def autopkg_run_recipes(autopkg_cmd: models.AutoPkgCMD = Depends(models.AutoPkgCMD)):
	"""Run all recipes in the database; recipes are filtered to match:
		* enabled
		* _not_ manual only

	Args:
		autopkg_cmd (models.AutoPkgCMD): Object containing options for `autopkg`
			and details on response method

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	log.info("Running all recipes")

	if not isinstance(autopkg_cmd, models.AutoPkgCMD):
		autopkg_cmd = models.AutoPkgCMD(**{"verb": "run"})

	recipe_filter = models.Recipe_Filter(**{"enabled": True, "manual_only": False})
	recipes = (await api.recipe.get_recipes(recipe_filter)).get("recipes")
	recipes = [ a_recipe.dict() for a_recipe in recipes ]
	log.debug(f"Number of recipes to run:  {len(recipes)}")

	queued_task = task.autopkg_verb_parser.apply_async(
		kwargs = {
			"recipes": recipes,
			"autopkg_cmd": autopkg_cmd.dict()
		},
		queue="autopkg",
		priority=3
	)

	return { "result": "Queued background task" , "task_id": queued_task.id }


@router.post("/run/recipe/{recipe_id}", summary="Executes a recipes",
	description="Executes a recipe in a background task.",
	dependencies=[Depends(api.user.get_current_user)])
async def autopkg_run_recipe(recipe_id: str,
	autopkg_cmd: models.AutoPkgCMD = Depends(models.AutoPkgCMD)):
	"""Runs the passed recipe id.

	Args:
		recipe_id (str): Recipe ID of a recipe
		autopkg_cmd (models.AutoPkgCMD): Object containing options for `autopkg`
			and details on response method

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	autopkg_cmd.verb = "run"
	a_recipe = await api.recipe.get_by_recipe_id(recipe_id)

	if not a_recipe:
		log.warning(f"Unknown recipe id:  '{recipe_id}'")
		return HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"Unknown recipe id:  '{recipe_id}'"
		)

	if autopkg_cmd.promote:

		pkg_object = await models.Package_Out.from_queryset_single(
			models.Packages.get(
				recipe_id=recipe_id, pkg_name=autopkg_cmd.match_pkg)
		)

		return await api.package.promote_package(id=pkg_object.id, autopkg_cmd=autopkg_cmd)

	if a_recipe.enabled:

		queued_task = task.autopkg_verb_parser.apply_async(
			kwargs = {
				"recipes": [ a_recipe.dict() ],
				"autopkg_cmd": autopkg_cmd.dict()
			},
			queue="autopkg",
			priority=4
		)

		return { "result": "Queued background task" , "task_id": queued_task.id }

	log.info(f"Recipe '{recipe_id}' is disabled.")
	return { "result": "Recipe is disabled" }


@router.post("/verify-trust/recipe/{recipe_id}", summary="Validates a recipes trust info",
	description="Validates a recipes trust info in a background task.",
	dependencies=[Depends(api.user.get_current_user)])
async def autopkg_verify_recipe(recipe_id: str,
	autopkg_cmd: models.AutoPkgCMD = Depends(models.AutoPkgCMD)):
	"""Runs the passed recipe id.

	Args:
		recipe_id (str): Recipe ID of a recipe
		autopkg_cmd (models.AutoPkgCMD): Object containing options for `autopkg`
			and details on response method

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	autopkg_cmd.verb = "verify-trust-info"
	a_recipe = await api.recipe.get_by_recipe_id(recipe_id)

	queued_task = task.autopkg_verb_parser.apply_async(
		kwargs = {
			"recipes": a_recipe.recipe_id,
			"autopkg_cmd": autopkg_cmd.dict()
		},
		queue="autopkg",
		priority=6
	)

	return { "result": "Queued background task" , "task_id": queued_task.id }


@router.get("/version", summary="Get AutoPkg version",
	description="Gets the current version of AutoPkg installed.",
	dependencies=[Depends(api.user.get_current_user)])
async def get_version(autopkg_cmd: models.AutoPkgCMD = Depends(models.AutoPkgCMD)):
	"""Gets the current version of AutoPkg installed.

	Args:
		autopkg_cmd (models.AutoPkgCMD): Object containing options for `autopkg`
			and details on response method

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	autopkg_cmd.verb = "version"

	queued_task = task.autopkg_verb_parser.apply_async(
		kwargs = { "autopkg_cmd": autopkg_cmd.dict() },
		queue="autopkg"
	)

	return { "result": "Queued background task" , "task_id": queued_task.id }


@router.post("/repo-add/{repo}", summary="Add new recipe repos from URL",
	description="Add one or more new recipe repos.  Supports native `autopkg repo-add` functionality.",
	dependencies=[Depends(api.user.get_current_user)])
async def autopkg_repo_add(repo: str,
	autopkg_cmd: models.AutoPkgCMD = Depends(models.AutoPkgCMD)):
	"""Adds the passed recipe repo to the available parent search repos.

	Args:
		repo (str): Path (URL or [GitHub] user/repo) of (an) AutoPkg recipe repo(s)
		autopkg_cmd (models.AutoPkgCMD): Object containing options for `autopkg`
			and details on response method

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	autopkg_cmd.verb = "repo-add"

	queued_task = task.autopkg_verb_parser.apply_async(
		kwargs = {
			"repos": repo,
			"autopkg_cmd": autopkg_cmd.dict()
		},
		queue="autopkg",
		priority=6
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
		return HTTPException(
			status_code=status.HTTP_511_NETWORK_AUTHENTICATION_REQUIRED,
			detail="Failed to authenticate webhook."
		)

	task_id = task_id.get("task_id")
	log.debug(f"Receiving notification for task_id:  {task_id}")
	await events.event_handler(task_id)
	return Response(status_code=status.HTTP_200_OK)


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
