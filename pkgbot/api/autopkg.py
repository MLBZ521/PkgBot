from fastapi import APIRouter, Body, Depends, HTTPException, Response, Request, status

from fastapi_utils.tasks import repeat_every

from pkgbot import api, config, core, settings
from pkgbot.db import models, schemas
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
	dependencies=[Depends(core.user.get_current)])
async def results(task_id:  str):

	return await utility.get_task_results(task_id)


@router.post("/workflow/dev", summary="Dev Workflow",
	description="The Dev workflow will create a new package and post to chat.",
	dependencies=[Depends(core.user.verify_admin)])
async def workflow_dev(pkg_object: schemas.Package_In = Depends(schemas.Package_In)):
	"""Workflow to create a new package in the database and then post a message to chat.

	Args:
		pkg_object (schemas.Package_In): Details about a package object

	Returns:
		[JSON]: Result of the operation
	"""

	await core.autopkg.workflow_dev(pkg_object)
	return Response(status_code=status.HTTP_200_OK)


@router.post("/workflow/prod", summary="Production Workflow",
	description="Workflow to move a package into production and update the Slack message.",
	dependencies=[Depends(core.user.verify_admin)])
async def workflow_prod(promoted_id: int, pkg_object: schemas.Package_In = Depends(schemas.Package_In)):

	return await core.autopkg.workflow_prod(promoted_id, pkg_object)


@router.on_event("startup")
@repeat_every(seconds=config.Services.get("autopkg_service_start_interval"), wait_first=True)
@router.post("/run/recipes", summary="Run all recipes",
	description="Runs all recipes in a background task.",
	dependencies=[Depends(core.user.verify_admin)])
async def autopkg_run_recipes(autopkg_cmd: models.AutoPkgCMD_Run = Depends(models.AutoPkgCMD_Run)):
	"""Run all recipes in the database; recipes are filtered to match:
		* enabled
		* _not_ manual only

	Args:
		autopkg_cmd (models.AutoPkgCMD): Object containing options for `autopkg`
			and details on response method

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	if not isinstance(autopkg_cmd, models.AutoPkgCMD):
		autopkg_cmd = models.AutoPkgCMD(**{"verb": "run"})

	queued_task = await core.autopkg.execute(autopkg_cmd)

	return { "result": "Queued background task" , "task_id": queued_task.id }


@router.post("/run/recipe/{recipe_id}", summary="Executes a recipes",
	description="Executes a recipe in a background task.",
	dependencies=[Depends(core.user.get_current)])
async def autopkg_run_recipe(recipe_id: str = Depends(core.recipe.get),
	autopkg_cmd: models.AutoPkgCMD_Run = Depends(models.AutoPkgCMD_Run)):
	"""Runs the passed recipe id.

	Args:
		recipe_id (str): Recipe ID of a recipe
		autopkg_cmd (models.AutoPkgCMD): Object containing options for `autopkg`
			and details on response method

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	queued_task = await core.autopkg.execute(autopkg_cmd, recipe_id.recipe_id)

	if isinstance(queued_task, dict):
		return queued_task

	return { "result": "Queued background task" , "task_id": queued_task.id }


@router.post("/verify-trust/recipe/{recipe_id}", summary="Validates a recipes trust info",
	description="Validates a recipes trust info in a background task.",
	dependencies=[Depends(core.user.get_current)])
async def autopkg_verify_recipe(recipe_id: str = Depends(core.recipe.get),
	autopkg_cmd: models.AutoPkgCMD_VerifyTrustInfo = Depends(models.AutoPkgCMD_VerifyTrustInfo)):
	"""Runs the passed recipe id.

	Args:
		recipe_id (str): Recipe ID of a recipe
		autopkg_cmd (models.AutoPkgCMD): Object containing options for `autopkg`
			and details on response method

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	queued_task = await core.autopkg.execute(autopkg_cmd, recipe_id.recipe_id)
	return { "result": "Queued background task" , "task_id": queued_task.id }


@router.get("/version", summary="Get AutoPkg version",
	description="Gets the current version of AutoPkg installed.",
	dependencies=[Depends(core.user.get_current)])
async def get_version(autopkg_cmd: models.AutoPkgCMD_Version = Depends(models.AutoPkgCMD_Version)):
	"""Gets the current version of AutoPkg installed.

	Args:
		autopkg_cmd (models.AutoPkgCMD): Object containing options for `autopkg`
			and details on response method

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	queued_task = await core.autopkg.execute(autopkg_cmd)
	return { "result": "Queued background task" , "task_id": queued_task.id }


@router.post("/repo-add/{repo}", summary="Add new recipe repos from URL",
	description="Add one or more new recipe repos.  Supports native `autopkg repo-add` functionality.",
	dependencies=[Depends(core.user.get_current)])
async def autopkg_repo_add(repo: str,
	autopkg_cmd: models.AutoPkgCMD_RepoAdd = Depends(models.AutoPkgCMD_RepoAdd)):
	"""Adds the passed recipe repo to the available parent search repos.

	Args:
		repo (str): Path (URL or [GitHub] user/repo) of an AutoPkg recipe repo
		autopkg_cmd (models.AutoPkgCMD): Object containing options for `autopkg`
			and details on response method

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	queued_task = await core.autopkg.execute(autopkg_cmd)
	return { "result": "Queued background task" , "task_id": queued_task.id }


@router.post("/receive", summary="Handles incoming task messages with autopkg results",
	description="This endpoint receives incoming messages from tasks and calls the required "
		"actions based on the message after verifying the authenticity of the source.")
async def receive(request: Request, task_id = Body()):

##### TODO:
	# To prevent memory allocation attacks
	# if content_length > 1_000_000:
	# 	log.error(f"Content too long ({content_length})")
	# 	response.status_code = 400
	# 	return {"result": "Content too long"}

	if not await api.verify_pkgbot_webhook(request):
		return HTTPException(
			status_code=status.HTTP_511_NETWORK_AUTHENTICATION_REQUIRED,
			detail="Failed to authenticate webhook."
		)

	task_id = task_id.get("task_id")
	log.debug(f"Receiving notification for task_id:  {task_id}")
	await core.events.event_handler(task_id)
	return Response(status_code=status.HTTP_200_OK)


@router.post("/trust/update", summary="Update recipe trust info",
	description="Update a recipe's trust information.  Runs `autopkg update-trust-info`.",
	dependencies=[Depends(core.user.verify_admin)])
async def autopkg_update_recipe_trust(recipe_id: str = Depends(core.recipe.get),
	autopkg_cmd: models.AutoPkgCMD_UpdateTrustInfo = Depends(models.AutoPkgCMD_UpdateTrustInfo)):
	# result_object: schemas.RecipeResult_In | None = Depends(schemas.RecipeResult_In)
	# Removed -- not sure this will be used via the API...

	queued_task = await core.autopkg.update_trust(autopkg_cmd, recipe_id)
	return { "result": "Queued background task" , "task_id": queued_task.id }
