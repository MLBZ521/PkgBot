from fastapi import APIRouter, Depends, Response

import settings, utilities.common as utility
from db import models
from api import package, user
from api.slack import bot, build_msg


log = utility.log
SlackBot = None
router = APIRouter(
	prefix = "/slackbot/send",
	tags = ["slackbot"],
	dependencies = [Depends(user.verify_admin)],
	responses = settings.db.custom_responses
)

max_content_size = 1500


@router.post("/dev-msg", summary="Send new package message",
	description="Sends a 'new package' message to Slack after "
	"a .pkg has been added to the dev environment.")
async def new_pkg_msg(pkg_object: models.Package_In = Depends(models.Package_In)):

	return await bot.SlackBot.post_message(
		await build_msg.new_pkg_msg(pkg_object),
		text=f"Update for {pkg_object.name}"
	)


@router.post("/promote-msg", summary="Send promoted package message",
	description="Sends a 'package has been promoted' message to Slack "
	"after a .pkg has been approved for the production environment.")
async def promote_msg(pkg_object: models.Package_In = Depends(models.Package_In)):

	await bot.SlackBot.update_message_with_response_url(
		pkg_object.dict().get("response_url"),
		await build_msg.promote_msg(pkg_object),
		text=f"{pkg_object.pkg_name} was promoted to production"
	)

	return await bot.SlackBot.reaction(
		action = "remove",
		emoji = "gear",
		ts = pkg_object.slack_ts
	)


@router.post("/recipe-error-msg", summary="Send error message",
	description="Sends an 'error' message to Slack after a recipe has returned an error.")
async def recipe_error_msg(recipe_id: str, id: int, error: str):

	blocks = await build_msg.recipe_error_msg(recipe_id, id, error)

	return await bot.SlackBot.post_message(blocks, text=f"Encountered error in {recipe_id}")


@router.post("/trust-diff-msg", summary="Send trust diff message",
	description="Sends a message with the trust diff contents to "
	"Slack after a recipe's parent trust info has changed.")
async def trust_diff_msg(
	error_msg: str, error_object: models.ErrorMessage_In = Depends(models.ErrorMessage_In)):

	if len(error_msg) > max_content_size:

		blocks = await build_msg.trust_diff_msg(error_object.id, error_object.recipe_id)

	else:

		blocks = await build_msg.trust_diff_msg(error_object.id, error_object.recipe_id, error_msg)

	response = await bot.SlackBot.post_message(
		blocks,
		text=f"Trust verification failed for `{error_object.recipe_id}`"
	)

	error_object.slack_ts = response.get('ts')
	error_object.save()

	if len(error_msg) > max_content_size:

		response = await bot.SlackBot.file_upload(
			content = error_msg,
			filename = f"{error_object.recipe_id}.diff",
			filetype = "diff",
			title = error_object.recipe_id,
			text = f"Diff Output for {error_object.recipe_id}",
			thread_ts = error_object.slack_ts
		)

	return response


@router.put("/update-trust-success-msg", summary="Send trust update success message",
	description="Sends a 'success' message to Slack when "
	"a recipe's trust info is updated successfully.")
async def update_trust_success_msg(
	error_object: models.ErrorMessage_In = Depends(models.ErrorMessage_In)):

	blocks = await build_msg.update_trust_success_msg(error_object)

	response = await bot.SlackBot.update_message_with_response_url(
		error_object.dict().get("response_url"), blocks,
		text=f"Successfully updated trust info for {error_object.recipe_id}")

	if response.status_code == 200:
		await bot.SlackBot.reaction(
			action = "remove",
			emoji = "gear",
			ts = error_object.slack_ts
		)

	return response


@router.put("/update-trust-error-msg", summary="Send trust update error message",
	description="Sends an 'error' message to Slack when a recipe's trust info fails to update.")
async def update_trust_error_msg(msg: str,
	error_object: models.ErrorMessage_In = Depends(models.ErrorMessage_In)):

	blocks = await build_msg.update_trust_error_msg(error_object, msg)

	return await bot.SlackBot.update_message_with_response_url(
		error_object.dict().get("response_url"), blocks,
		text=f"Failed to update trust info for {error_object.recipe_id}")


@router.put("/deny-pkg-msg", summary="Send deny package message",
	description="Sends a 'package denied message' to Slack when "
	"a .pkg is not approved for the production environment.")
async def deny_pkg_msg(pkg_object: models.Package_In = Depends(models.Package_In)):

	blocks = await build_msg.deny_pkg_msg(pkg_object)

	response = await bot.SlackBot.update_message_with_response_url(
		pkg_object.dict().get("response_url"), blocks,
		text=f"{pkg_object.pkg_name} was not approved for production")

	if response.status_code == 200:
		await bot.SlackBot.reaction(
			action = "remove",
			emoji = "gear",
			ts = pkg_object.slack_ts
		)

	return response


@router.put("/deny-trust-msg", summary="Send deny trust message",
	description="Send an message to Slack stating a recipe's "
	"parent trust info changes were not approved.")
async def deny_trust_msg(
	error_object: models.ErrorMessage_In = Depends(models.ErrorMessage_In)):

	blocks = await build_msg.deny_trust_msg(error_object)

	response = await bot.SlackBot.update_message_with_response_url(
		error_object.dict().get("response_url"), blocks,
		text=f"Trust info for {error_object.recipe_id} was not approved")

	if response.status_code == 200:
		await bot.SlackBot.reaction(
			action = "remove",
			emoji = "gear",
			ts = error_object.slack_ts
		)

	return response


@router.delete("/ts/{ts}", summary="Delete message by TS",
	description="Delete a Slack message by its TS.",
	dependencies=[Depends(user.verify_admin)])
async def delete_by_ts(ts: int):

	return await bot.SlackBot.delete_message(ts)
