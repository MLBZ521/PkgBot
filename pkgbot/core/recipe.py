from pkgbot import core
from pkgbot.db import models
from pkgbot.utilities import common as utility


log = utility.log


async def get(recipe_filter: dict | None = None):

	if not recipe_filter:
		return await models.Recipes.all()

	results = await models.Recipe_Out.from_queryset(models.Recipes.filter(**recipe_filter))
	return results[0] if len(results) == 1 else results


async def create(recipe_object: dict):

	return await models.Recipes.create(**recipe_object)


async def update(filter: dict, updates: dict):

	return await models.Recipes.filter(**filter).update(**updates)


async def delete(filter: dict):

	return await models.Recipes.filter(**filter).delete()


async def error(recipe_id: str, error: str, task_id: str = None):

	# Create DB entry in errors table
	error_message = await core.error.create_error(type=f"recipe: {recipe_id}")

	 # Construct error content
	error_dict = await core.error.construct_error_msg(recipe_id, error, task_id)

	# Send error message
	results = await core.chatbot.send.recipe_error_msg(recipe_id, error_message.id, error_dict)

	# Update error message
	await core.error.update_error(
		{ "id": error_message.id },
		{
			"slack_channel": results.get('channel'),
			"slack_ts": results.get('ts'),
			"status": "Notified"
		}
	)

	# Mark the recipe disabled
	if recipe:= await get({"recipe_id": recipe_id}):

		await update(
			{"recipe_id": recipe_id},
			{
				"enabled": False,
				"status": "Error after last run.",
				"recurring_fail_count": recipe.recurring_fail_count + 1
			}
		)


async def verify_trust_failed(recipe_id: str, diff_msg: str):
	""" When `autopkg verify-trust-info <recipe_id>` fails """

	# Create DB entry in TrustUpdates table
	trust_object = await models.TrustUpdates.create(recipe_id=recipe_id)

	# Post Slack Message
	await core.chatbot.send.trust_diff_msg(diff_msg, trust_object)

	# Mark the recipe disabled
	await update(
		{"recipe_id": trust_object.recipe_id},
		{
			"enabled": False,
			"status": "Failed parent recipe trust verification."
		}
	)

	return { "result": "Success" }


async def deny_trust(trust_object_id: int):

	trust_object = await models.TrustUpdate_Out.from_queryset_single(
		models.TrustUpdates.get(id=trust_object_id))

	await core.chatbot.send.deny_trust_msg(trust_object)


async def update_trust_result(success: bool, trust_id: int, error_msg: str):

	# Get DB entry
	if trust_object:= await models.TrustUpdate_Out.from_queryset_single(
		models.TrustUpdates.get(id=trust_id)):

		if success:
			# Enable the recipe
			await update({"recipe_id": trust_object.recipe_id}, {"enabled": True, "status": ""})
			return await core.chatbot.send.update_trust_success_msg(trust_object)

		# Ensure the recipe is marked disabled
		await update(
			{"recipe_id": trust_object.recipe_id},
			{"enabled": False, "status": "Failed to update trust info"}
		)

		return await core.chatbot.send.update_trust_error_msg(error_msg, trust_object)
