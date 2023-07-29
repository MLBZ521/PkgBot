from pkgbot import core
from pkgbot.db import models, schemas
from pkgbot.utilities import common as utility


log = utility.log


async def get(recipe_filter: dict | None = None):

	if not recipe_filter:
		return await models.Recipes.all()

	results = await schemas.Recipe_Out.from_queryset(models.Recipes.filter(**recipe_filter))
	return results[0] if len(results) == 1 else results


async def get_note(note_filter: dict | None = None):

	if not note_filter:
		return await models.RecipeNotes.all()

	results = await schemas.RecipeNote_Out.from_queryset(models.RecipeNotes.filter(**note_filter))
	return results[0] if len(results) == 1 else results


async def get_result(result_filter: dict | None = None):

	if not result_filter:
		return await models.RecipeResults.all()

	results = await schemas.RecipeResult_Out.from_queryset(models.RecipeResults.filter(**result_filter))
	return results[0] if len(results) == 1 else results


async def create(recipe_object: dict):

	return await models.Recipes.create(**recipe_object)


async def create_result(recipe_result: dict):

	return await models.RecipeResults.create(**recipe_result)


async def create_note(note_object: dict):

	return await models.RecipeNotes.create(**note_object)


async def update(recipe_filter: dict, updates: dict):

	return await models.Recipes.filter(**recipe_filter).update(**updates)


async def update_result(result_filter: dict, updates: dict):

	result = await models.RecipeResults.filter(**result_filter).first()
	await (result.update_from_dict(updates)).save()
	return await schemas.RecipeResult_Out.from_tortoise_orm(result)


async def delete(recipe_filter: dict):

	return await models.Recipes.filter(**recipe_filter).delete()


async def error(recipe_id: str, event: str, error: str, task_id: str = None):

	# Create DB entry in errors table
	recipe_result = await create_result({
		"type": event,
		"recipe_id": recipe_id,
		"task_id": task_id,
		"details": error
	})

	# Construct error content
	error_dict = await core.error.construct_msg(recipe_id, error, task_id)

	# Send error message
	results = await core.chatbot.send.recipe_error_msg(recipe_id, recipe_result.id, error_dict)

	# Update error message
	await update_result(
		{ "id": recipe_result.id },
		{
			"slack_channel": results.get('channel'),
			"slack_ts": results.get('ts'),
			"status": "Notified"
		}
	)

	# Mark the recipe disabled
	if recipe := await get({ "recipe_id": recipe_id }):

		await update(
			{ "recipe_id": recipe_id },
			{
				"enabled": False,
				"recurring_fail_count": recipe.recurring_fail_count + 1
			}
		)


async def verify_trust_failed(recipe_id: str, diff_msg: str, task_id: str):
	""" When `autopkg verify-trust-info <recipe_id>` fails """

	# Create DB entry in RecipeResults table
	result_object = await core.recipe.create_result({
		"type": "trust",
		"recipe_id": recipe_id,
		"task_id": task_id,
		"details": diff_msg,
		"status": "Failed parent recipe trust verification."
	})

	# Post Slack Message
	await core.chatbot.send.trust_diff_msg(diff_msg, result_object)

	# Mark the recipe disabled
	await update({ "recipe_id": result_object.id }, { "enabled": False })
	return { "result": "Success" }


async def deny_trust(filter_object: dict):

	result_object = await get_result(filter_object)
	await core.chatbot.send.deny_trust_msg(result_object)


async def update_trust_result(
	success: bool, result_filter: dict, error_msg: str, updated_by: str = None):

	# Get DB entry
	if result_object := await get_result(result_filter):

		if success:
			# Enable the recipe
			await update({ "recipe_id": result_object.recipe.recipe_id }, { "enabled": True })
			await update_result(result_filter, { "status": "", "updated_by": updated_by })
			return await core.chatbot.send.update_trust_success_msg(result_object)

		# Ensure the recipe is marked disabled
		await update({ "recipe_id": result_object.recipe.recipe_id }, { "enabled": False })

		await update_result(
			result_filter, { "status": "Failed to update trust info", "updated_by": updated_by })
		return await core.chatbot.send.update_trust_error_msg(error_msg, result_object)
