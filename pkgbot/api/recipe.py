from functools import reduce

from fastapi import APIRouter, Body, Depends, HTTPException, status

from pkgbot import api, settings
from pkgbot.db import models
from pkgbot.utilities import common as utility
from pkgbot.tasks import task


log = utility.log
router = APIRouter(
	prefix = "/recipe",
	tags = ["recipe"],
	responses = settings.api.custom_responses
)


@router.get("s/", summary="Get all recipes", description="Get all recipes in the database.",
	dependencies=[Depends(api.user.get_current_user)], response_model=dict)
async def get_recipes(recipe_filter: models.Recipe_Filter = Depends(models.Recipe_Filter)):

	if isinstance(recipe_filter, models.Recipe_Filter):
		recipes = await models.Recipe_Out.from_queryset(
			models.Recipes.filter(**recipe_filter.dict(exclude_unset=True, exclude_none=True)))
	else:
		recipes = await models.Recipe_Out.from_queryset(models.Recipes.all())

	return { "total": len(recipes), "recipes": recipes }


@router.get("/id/{id}", summary="Get recipe by id", description="Get a recipe by its id.",
	dependencies=[Depends(api.user.get_current_user)], response_model=models.Recipe_Out)
async def get_by_id(id: int):

	return await models.Recipe_Out.from_queryset_single(models.Recipes.get(id=id))


@router.get("/recipe_id/{recipe_id}", summary="Get recipe by recipe_id",
	description="Get a recipe by its recipe_id.",
	dependencies=[Depends(api.user.get_current_user)], response_model=models.Recipe_Out)
async def get_by_recipe_id(recipe_id: str):

	if recipe_object := await models.Recipes.filter(recipe_id__iexact=recipe_id).first():
		return await models.Recipe_Out.from_tortoise_orm(recipe_object)
	return recipe_object


@router.post("/", summary="Create a recipe", description="Create a recipe.",
	dependencies=[Depends(api.user.verify_admin)], response_model=models.Recipe_Out)
# async def create(recipe_object: models.Recipe_In = Body(..., recipe_object=Depends(models.Recipe_In))):
async def create(recipe_object: models.Recipe_In = Body()):

	created_recipe = await models.Recipes.create(
		**recipe_object.dict(exclude_unset=True, exclude_none=True))
	return await models.Recipe_Out.from_tortoise_orm(created_recipe)


@router.put("/id/{id}", summary="Update recipe by id", description="Update a recipe by id.",
	dependencies=[Depends(api.user.verify_admin)], response_model=models.Recipe_Out)
async def update_by_id(id: int, recipe_object: models.Recipe_In = Depends(models.Recipe_In)):

	if not isinstance(recipe_object, dict):
		recipe_object = recipe_object.dict(exclude_unset=True, exclude_none=True)

	await models.Recipes.filter(id=id).update(**recipe_object)
	return await models.Recipe_Out.from_queryset_single(models.Recipes.get(id=id))


@router.put("/recipe_id/{recipe_id}", summary="Update recipe by recipe_id",
	description="Update a recipe by recipe_id.",
	dependencies=[Depends(api.user.verify_admin)], response_model=models.Recipe_Out)
async def update_by_recipe_id(recipe_id: str,
	recipe_object: models.Recipe_In = Depends(models.Recipe_In)):

	if not isinstance(recipe_object, dict):
		recipe_object = recipe_object.dict(exclude_unset=True, exclude_none=True)

	if await models.Recipes.filter(recipe_id__iexact=recipe_id).update(**recipe_object):
		return await models.Recipe_Out.from_queryset_single(models.Recipes.get(recipe_id=recipe_id))

	raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown recipe id:  '{recipe_id}'")


@router.delete("/id/{id}", summary="Delete recipe by id", description="Delete a recipe by id.",
	dependencies=[Depends(api.user.verify_admin)])
async def delete_by_id(id: int):

	delete_object = await models.Recipes.filter(id=id).delete()

	if not delete_object:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"A recipe does not exist with id:  '{id}'")
	else:
		return { "result":  f"Successfully deleted recipe id:  {id}" }


@router.delete("/recipe_id/{recipe_id}", summary="Delete recipe by recipe_id",
	description="Delete a recipe by recipe_id.", dependencies=[Depends(api.user.verify_admin)])
async def delete_by_recipe_id(recipe_id: str):

	delete_object = await models.Recipes.filter(recipe_id__iexact=recipe_id).delete()

	if not delete_object:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown recipe id:  '{recipe_id}'")
	else:
		return { "result":  f"Successfully deleted recipe id:  {recipe_id}" }


@router.post("/error", summary="Handle recipe errors",
	description="This endpoint is called when a recipe errors out during an autopkg run.",
	dependencies=[Depends(api.user.verify_admin)])
async def recipe_error(recipe_id: str, error: str, task_id: str = None):

	# Create DB entry in errors table
	error_message = await models.ErrorMessages.create(type=f"recipe: {recipe_id}")

	# Post Slack Message
	try:
		error_list = error.split(': ')
		error_dict = reduce(lambda x, y: {y:x}, error_list[::-1])
	except Exception:
		error_dict = { recipe_id: error }

	# Add task_id to error message for easier lookup
	error_dict["Task ID"] = task_id

	results = await api.send_msg.recipe_error_msg(recipe_id, error_message.id, error_dict)

	updates = {
		"slack_channel": results.get('channel'),
		"slack_ts": results.get('ts'),
		"status": "Notified"
	}

	await models.ErrorMessages.update_or_create(updates, id=error_message.id)

	# Mark the recipe disabled
	recipe_object = await models.Recipes.filter(recipe_id=recipe_id).first()

	if recipe_object:
		recipe_object.enabled = False
		recipe_object.notes = "Disabled due to error during run."
		recipe_object.recurring_fail_count = recipe_object.recurring_fail_count + 1
		await recipe_object.save()

	return { "result": "Success" }


@router.post("/trust/update", summary="Update recipe trust info",
	description="Update a recipe's trust information.  Runs `autopkg update-trust-info`.",
	dependencies=[Depends(api.user.verify_admin)])
async def recipe_trust_update(
	recipe_id: str | None = None,
	autopkg_cmd: models.AutoPkgCMD = Depends(models.AutoPkgCMD),
	trust_object: models.TrustUpdate_In | None = Depends(models.TrustUpdate_In)
):

	# Get recipe object
	if recipe_object := await models.Recipes.filter(recipe_id__iexact=recipe_id).first():
		log.debug(f"recipe_object:  {recipe_object}")
		event_id = None
		recipe_id = recipe_object.recipe_id

	elif isinstance(trust_object, (models.TrustUpdates, models.TrustUpdate_In)):

		if isinstance(trust_object, models.TrustUpdate_In):
			# If object is not a ORM model, get an ORM model
			trust_object = await models.TrustUpdates.filter(
				**trust_object.dict(exclude_unset=True, exclude_none=True)).first()

		event_id = trust_object.id
		recipe_id = trust_object.recipe_id

	else:

		await api.slack.send_msg.ephemeral_msg(
			user = autopkg_cmd.egress,
			text = f":no_good: Unable to update trust info.  Unknown recipe id:  `{recipe_id}`",
			alt_text = ":no_good: Failed to update trust info for...",
			channel = autopkg_cmd.channel
		)
		return { "result": f"Unknown recipe id:  `{recipe_id}'" }

	queued_task = task.autopkg_verb_parser.apply_async(
		kwargs = {
			"recipes": recipe_id,
			"event_id":  event_id,
			"autopkg_cmd": autopkg_cmd.dict()
		},
		queue="autopkg",
		priority=6
	)

	return { "result": "Queued background task" , "task_id": queued_task.id }


@router.post("/trust/deny", summary="Do not approve trust changes",
	description="This endpoint will update that database to show that the "
		"changes to parent recipe(s) were not approved.",
	dependencies=[Depends(api.user.verify_admin)])
async def recipe_trust_deny(trust_object_id: int):

	trust_object = await models.TrustUpdate_Out.from_queryset_single(
		models.TrustUpdates.get(id=trust_object_id))
	await api.send_msg.deny_trust_msg(trust_object)


@router.post("/trust/update/success", summary="Trust info was updated successfully",
	description="Performs the necessary actions after trust info was successfully updated.",
	dependencies=[Depends(api.user.verify_admin)])
async def recipe_trust_update_success(trust_id: int):

	trust_object = await models.TrustUpdate_Out.from_queryset_single(models.TrustUpdates.get(id=trust_id))

	# Re-enable the recipe
	await update_by_recipe_id(trust_object.recipe_id, {"enabled": True, "notes": ""})

	if trust_object:
		return await api.send_msg.update_trust_success_msg(trust_object)

	# else:
##### Post message to whomever requested the update?
		# await bot.SlackBot.post_ephemeral_message(
		# 	trust_object.updated_by, blocks,
		# 	channel=trust_object.slack_channel,
		# 	text=f"Encountered error attempting to update trust for `{trust_object.recipe_id}`"
		# )


@router.post("/trust/update/failed", summary="Failed to update recipe trust info",
	description="Performs the necessary actions after trust info failed to update.",
	dependencies=[Depends(api.user.verify_admin)])
async def recipe_trust_update_failed(trust_id: int, msg: str):

	# Get DB entry
	trust_object = await models.TrustUpdate_Out.from_queryset_single(
		models.TrustUpdates.get(id=trust_id))

	await api.send_msg.update_trust_error_msg(msg, trust_object)

	# Ensure the recipe is marked disabled
	recipe_object = await models.Recipes.filter(recipe_id=trust_object.recipe_id).first()
	recipe_object.enabled = False
	await recipe_object.save()
	return { "result": "Success" }


@router.post("/trust/verify/failed", summary="Parent trust info has changed",
	description="Performs the necessary actions after parent recipe trust info has changed.",
	dependencies=[Depends(api.user.verify_admin)])
async def recipe_trust_verify_failed(recipe_id: str, diff_msg: str = Body()):
	""" When `autopkg verify-trust-info <recipe_id>` fails """

	# Create DB entry in TrustUpdates table
	trust_object = await models.TrustUpdates.create(recipe_id=recipe_id)

	# Post Slack Message
	await api.send_msg.trust_diff_msg(diff_msg, trust_object)

	# Mark the recipe disabled
	recipe_object = await models.Recipes.filter(recipe_id=trust_object.recipe_id).first()
	recipe_object.enabled = False
	recipe_object.notes = "Disabled due to failing parent recipe trust verification."
	await recipe_object.save()
	return { "result": "Success" }
