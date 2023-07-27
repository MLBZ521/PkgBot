from datetime import datetime

from celery import current_app as pkgbot_celery_app

from fastapi import HTTPException, status

from pkgbot import core
from pkgbot.db import models, schemas
from pkgbot.utilities import common as utility


log = utility.log


async def workflow_dev(pkg_object: schemas.Package_In, pkg_note_object: schemas.PackageNote_In):
	"""Workflow to create a new package in the database and then post a message to chat.

	Args:
		pkg_object (schemas.Package_In): Details about a package object
		pkg_note_object (schemas.Package_In): Note about a package object

	Returns:
		[JSON]: Result of the operation
	"""

	created_pkg = await core.package.create(pkg_object.dict())
	await core.package.create_note(pkg_note_object.dict())

	results = await core.chatbot.send.new_pkg_msg(
		await schemas.Package_Out.from_tortoise_orm(created_pkg))

	await core.package.update(
		{"id": created_pkg.id},
		{
			"slack_ts": results.get("ts"),
			"slack_channel": results.get("channel")
		}
	)

	return results


async def workflow_prod(promoted_id: int, pkg_object: schemas.Package_In):

	if pkg_object.promoted_date is None:
		date_to_convert = datetime.now()
	else:
		date_to_convert = pkg_object.promoted_date

	updated_pkg_object = await core.package.update(
		{"id": promoted_id},
		{
			"promoted_date": await utility.utc_to_local(date_to_convert),
			"status": "prod"
		}
	)

	return await core.chatbot.send.promote_msg(updated_pkg_object)


async def execute(autopkg_cmd: models.AutoPkgCMD, item: str | None = None):

	match autopkg_cmd.verb:

		case "run":
			if item:
				return await run_recipe(recipe_id=item, autopkg_cmd=autopkg_cmd)
			return await run_recipes(autopkg_cmd)

		case "repo-add":
			return await repo_add(autopkg_cmd)

		case "verify-trust-info":
			return await verify_recipe(recipe_id=item, autopkg_cmd=autopkg_cmd)

		case "update-trust-info":
			return await update_trust(recipe_id=item, autopkg_cmd=autopkg_cmd)

		case "version":
			return await version(autopkg_cmd)


async def repo_add(repo: str, autopkg_cmd: models.AutoPkgCMD_RepoAdd):
	"""Adds the passed recipe repo to the available parent search repos.

	Args:
		repo (str): Path (URL or [GitHub] user/repo) of an AutoPkg recipe repo
		autopkg_cmd (models.AutoPkgCMD): Object containing options for `autopkg`
			and details on response method

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	return pkgbot_celery_app.send_task(
		"autopkg:verb_parser",
		kwargs = {
			"repos": repo,
			"autopkg_cmd": autopkg_cmd.dict()
		},
		queue="autopkg",
		priority=6
	)


async def run_recipe(recipe_id: str, autopkg_cmd: models.AutoPkgCMD_Run):
	"""Runs the passed recipe id.

	Args:
		recipe_id (str): Recipe ID of a recipe
		autopkg_cmd (models.AutoPkgCMD): Object containing options for `autopkg`
			and details on response method

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	if not (a_recipe := await core.recipe.get({"recipe_id__iexact": recipe_id})):
		log.warning(f"Unknown recipe id:  '{recipe_id}'")

		return HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"Unknown recipe id:  '{recipe_id}'"
		)

	if autopkg_cmd.promote:
		pkg_object = await core.package.get({"recipe_id": recipe_id, "pkg_name": autopkg_cmd.match_pkg})
		return await core.package.promote(pkg_object.id, autopkg_cmd)

	if a_recipe.enabled:

		return pkgbot_celery_app.send_task(
			"autopkg:verb_parser",
			kwargs = {
				"recipes": [ a_recipe.dict() ],
				"autopkg_cmd": autopkg_cmd.dict()
			},
			queue="autopkg",
			priority=4
		)
		# return { "result": "Queued background task" , "task_id": queued_task.id }

	log.info(f"Recipe '{recipe_id}' is disabled.")
	return { "result": "Recipe is disabled" }


async def run_recipes(autopkg_cmd: models.AutoPkgCMD_Run):
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

	recipes = await core.recipe.get({"enabled": True, "manual_only": False})
	recipes = [ a_recipe.dict() for a_recipe in recipes ]
	log.debug(f"Number of recipes to run:  {len(recipes)}")

	return pkgbot_celery_app.send_task(
		"autopkg:verb_parser",
		kwargs = {
			"recipes": recipes,
			"autopkg_cmd": autopkg_cmd.dict()
		},
		queue="autopkg",
		priority=3
	)


async def update_trust(
	autopkg_cmd: models.AutoPkgCMD_UpdateTrustInfo,
	trust_object: dict | None, recipe_id: str | None = None):

	# Get recipe object
	if recipe_object := await core.recipe.get({"recipe_id__iexact": recipe_id}):
		event_id = None
		recipe_id = recipe_object.recipe_id

	elif trust_object:

		event_id = trust_object.id
		recipe_id = trust_object.recipe_id

	else:

		await core.chatbot.send.direct_msg(
			user = autopkg_cmd.egress,
			text = f":no_good: Unable to update trust info.  Unknown recipe id:  `{recipe_id}`",
			alt_text = ":no_good: Failed to update trust info for...",
			channel = autopkg_cmd.channel
		)
		return { "result": f"Unknown recipe id:  `{recipe_id}'" }

	return pkgbot_celery_app.send_task(
		"autopkg:verb_parser",
		kwargs = {
			"recipes": recipe_id,
			"event_id":  event_id,
			"autopkg_cmd": autopkg_cmd.dict()
		},
		queue="autopkg",
		priority=6
	)


async def verify_recipe(recipe_id: str, autopkg_cmd: models.AutoPkgCMD_VerifyTrustInfo):
	"""Runs the passed recipe id.

	Args:
		recipe_id (str): Recipe ID of a recipe
		autopkg_cmd (models.AutoPkgCMD): Object containing options for `autopkg`
			and details on response method

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	if not (a_recipe := await core.recipe.get({"recipe_id__iexact": recipe_id})):
		log.warning(f"Unknown recipe id:  '{recipe_id}'")

		return HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"Unknown recipe id:  '{recipe_id}'"
		)

	return pkgbot_celery_app.send_task(
		"autopkg:verb_parser",
		kwargs = {
			"recipes": a_recipe.recipe_id,
			"autopkg_cmd": autopkg_cmd.dict()
		},
		queue="autopkg",
		priority=6
	)


async def version(autopkg_cmd: models.AutoPkgCMD_Version):
	"""Gets the current version of AutoPkg installed.

	Args:
		autopkg_cmd (models.AutoPkgCMD): Object containing options for `autopkg`
			and details on response method

	Returns:
		dict:  Dict describing the results of the ran process
	"""

	return pkgbot_celery_app.send_task(
		"autopkg:verb_parser",
		kwargs = { "autopkg_cmd": autopkg_cmd.dict() },
		queue="autopkg"
	)
