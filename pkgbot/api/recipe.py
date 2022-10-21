from functools import reduce
from typing import List, Dict

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, status

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

	recipe_object = await models.Recipe_Out.from_queryset_single(models.Recipes.get(id=id))

	return recipe_object


@router.get("/recipe_id/{recipe_id}", summary="Get recipe by recipe_id", description="Get a recipe by its recipe_id.",
	dependencies=[Depends(api.user.get_current_user)], response_model=models.Recipe_Out)
async def get_by_recipe_id(recipe_id: str):

	recipe_object = await models.Recipe_Out.from_queryset_single(models.Recipes.get(recipe_id=recipe_id))

	return recipe_object


@router.post("/", summary="Create a recipe", description="Create a recipe.",
	dependencies=[Depends(api.user.verify_admin)], response_model=models.Recipe_Out)
# async def create(recipe_object: models.Recipe_In = Body(..., recipe_object=Depends(models.Recipe_In))):
async def create(recipe_object: models.Recipe_In = Body()):

	created_recipe = await models.Recipes.create(**recipe_object.dict(exclude_unset=True, exclude_none=True))

	return await models.Recipe_Out.from_tortoise_orm(created_recipe)


@router.put("/id/{id}", summary="Update recipe by id", description="Update a recipe by id.",
	dependencies=[Depends(api.user.verify_admin)], response_model=models.Recipe_Out)
async def update_by_id(id: int, recipe_object: models.Recipe_In = Depends(models.Recipe_In)):

	if type(recipe_object) != dict:
		recipe_object = recipe_object.dict(exclude_unset=True, exclude_none=True)

	await models.Recipes.filter(id=id).update(**recipe_object)

	return await models.Recipe_Out.from_queryset_single(models.Recipes.get(id=id))


@router.put("/recipe_id/{recipe_id}", summary="Update recipe by recipe_id", description="Update a recipe by recipe_id.",
	dependencies=[Depends(api.user.verify_admin)], response_model=models.Recipe_Out)
async def update_by_recipe_id(recipe_id: str,
	# recipe_object: models.Recipe_In = Body(..., recipe_object=Depends(models.Recipe_In))):
	recipe_object: models.Recipe_In = Body()):

	if type(recipe_object) != dict:
		recipe_object = recipe_object.dict(exclude_unset=True, exclude_none=True)

	await models.Recipes.filter(recipe_id=recipe_id).update(**recipe_object)

	return await models.Recipe_Out.from_queryset_single(models.Recipes.get(recipe_id=recipe_id))


@router.delete("/id/{id}", summary="Delete recipe by id", description="Delete a recipe by id.",
	dependencies=[Depends(api.user.verify_admin)])
async def delete_by_id(id: int):

	delete_object = await models.Recipes.filter(id=id).delete()

	if not delete_object:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe does not exist.")

	else:
		return { "result":  f"Successfully deleted recipe id:  {id}" }


@router.delete("/recipe_id/{recipe_id}", summary="Delete recipe by recipe_id",
	description="Delete a recipe by recipe_id.", dependencies=[Depends(api.user.verify_admin)])
async def delete_by_recipe_id(recipe_id: str):

	delete_object = await models.Recipes.filter(recipe_id=recipe_id).delete()

	if not delete_object:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe does not exist.")

	else:
		return { "result":  f"Successfully deleted recipe id:  {recipe_id}" }


@router.post("/error", summary="Handle recipe errors",
	description="This endpoint is called when a recipe errors out during an autopkg run.",
	dependencies=[Depends(api.user.verify_admin)])
async def recipe_error(recipe_id: str, error: str, task_id: str = None):

	# Create DB entry in errors table
	error_message = await models.ErrorMessages.create( recipe_id=recipe_id )

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
		"slack_ts": results.get('ts'),
		"slack_channel": results.get('channel')
	}

	await models.ErrorMessages.update_or_create(updates, id=error_message.id)

	# Mark the recipe disabled
	recipe_object = await models.Recipes.filter(recipe_id=recipe_id).first()

	if recipe_object:
		recipe_object.enabled = False
		recipe_object.recurring_fail_count = recipe_object.recurring_fail_count + 1
		await recipe_object.save()

	return { "Result": "Success" }


# @router.post("/trust", summary="Update recipe trust info",
@router.post("/trust/update", summary="Update recipe trust info",
	description="Update a recipe's trust information.  Runs `autopkg update-trust-info <recipe_id>`.",
	dependencies=[Depends(api.user.verify_admin)])
# async def trust_recipe(id: int, background_tasks: BackgroundTasks, user_id: str, channel: str):
# async def recipe_trust_update(id: int, background_tasks: BackgroundTasks, user_id: str, channel: str):
async def recipe_trust_update(trust_object: models.TrustUpdate_In, switches: dict = None):

	# Get recipe object
	recipe_object = await models.Recipes.filter(recipe_id=trust_object.recipe_id).first()

##### Maybe create a trust_object db entry if one doesn't exist for direct call to endpoint (without first a failure)

	if recipe_object:

		queued_task = task.autopkg_update_trust.apply_async((trust_object.recipe_id, switches, trust_object.id), queue='autopkg', priority=6)

		return { "Result": "Queued background task..." , "task_id": queued_task.id }

	else:

		blocks = await api.build_msg.missing_recipe_msg(trust_object.recipe_id, "update trust for")

		await api.bot.SlackBot.post_ephemeral_message(
			trust_object.status_updated_by, blocks,
			channel=trust_object.slack_channel,
			text=f"Encountered error attempting to update trust for `{trust_object.recipe_id}`"
		)


# @router.post("/do-not-trust", summary="Do not approve trust changes",
@router.post("/trust/deny", summary="Do not approve trust changes",
	description="This endpoint will update that database to show that the "
		"changes to parent recipe(s) were not approved.",
	dependencies=[Depends(api.user.verify_admin)])
async def recipe_trust_deny(trust_object_id: int):
# async def recipe_trust_deny(trust_object: models.TrustUpdate_Out = Depends(get_by_recipe_id)):

	# Get TrustUpdates ID
	trust_object = await models.TrustUpdate_Out.from_queryset_single(models.TrustUpdates.get(id=trust_object_id))

	await api.send_msg.deny_trust_msg(trust_object)


# @router.post("/trust-update-success", summary="Trust info was updated successfully",
@router.post("/trust/update/success", summary="Trust info was updated successfully",
	description="Performs the necessary actions after trust info was successfully updated.",
	dependencies=[Depends(api.user.verify_admin)])
# async def trust_update_success(recipe_id: str, msg: str):
async def recipe_trust_update_success(recipe_id: str, msg: str, trust_id: int):

	# Get DB Entry
	trust_object = await models.TrustUpdate_Out.from_queryset_single(models.TrustUpdates.get(id=trust_id))

	# Re-enable the recipe
	await update_by_recipe_id(trust_object.recipe_id, {"enabled": True})
	if trust_object:
		return await api.send_msg.update_trust_success_msg(trust_object)

	# else:
##### Post message to whomever requested the update?
		# await bot.SlackBot.post_ephemeral_message(
		# 	trust_object.status_updated_by, blocks,
		# 	channel=trust_object.slack_channel,
		# 	text=f"Encountered error attempting to update trust for `{trust_object.recipe_id}`"
		# )


# @router.post("/trust-update-error", summary="Trust info failed to update",
@router.post("/trust/update/failed", summary="Failed to update recipe trust info",
	description="Performs the necessary actions after trust info failed to update.",
	dependencies=[Depends(api.user.verify_admin)])
# async def trust_update_error(recipe_id: str, msg: str): #,
async def recipe_trust_update_failed(recipe_id: str, msg: str):

	# Get DB entry
	trust_object = await models.TrustUpdate_Out.from_queryset_single(models.TrustUpdates.get(recipe_id=recipe_id))

	results = await api.send_msg.update_trust_error_msg(msg, trust_object)

	updates = {
		"slack_ts": results.get('ts'),
		"slack_channel": results.get('channel')
	}

	await models.TrustUpdates.update_or_create(updates, id=trust_object.id)

	# Mark the recipe disabled
	recipe_object = await models.Recipes.filter(recipe_id=trust_object.recipe_id).first()
	recipe_object.enabled = False
	await recipe_object.save()

	return { "Result": "Success" }


# @router.post("/trust-verify-error", summary="Parent trust info has changed",
@router.post("/trust/verify/failed", summary="Parent trust info has changed",
	description="Performs the necessary actions after parent recipe trust info has changed.",
	dependencies=[Depends(api.user.verify_admin)])
# async def trust_error(payload: dict = Body(...)):
async def recipe_trust_verify_failed(recipe_id: str, diff_msg: str = Body()):
# async def recipe_trust_verify_failed(recipe_id: str, msg: str):
	""" When `autopkg verify-trust-info <recipe_id>` fails """

	# Create DB entry in TrustUpdates table
	trust_object = await models.TrustUpdates.create(recipe_id=recipe_id)

	# Post Slack Message
	await api.send_msg.trust_diff_msg(diff_msg, trust_object)

	# Mark the recipe disabled
	recipe_object = await models.Recipes.filter(recipe_id=trust_object.recipe_id).first()
	recipe_object.enabled = False
	await recipe_object.save()

	return { "Result": "Success" }
