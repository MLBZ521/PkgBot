import json

from fastapi import APIRouter, Depends

from pkgbot import api, settings
from pkgbot.db import models
from pkgbot.utilities import common as utility


log = utility.log
SlackBot = None
router = APIRouter(
	prefix = "/slackbot/send",
	tags = ["slackbot"],
	dependencies = [Depends(api.user.verify_admin)],
	responses = settings.api.custom_responses
)

max_content_size = 1500


@router.post("/dev-msg", summary="Send new package message",
	description="Sends a 'new package' message to Slack after "
	"a .pkg has been added to the dev environment.")
async def new_pkg_msg(pkg_object: models.Package_In = Depends(models.Package_In)):

	return await api.bot.SlackBot.post_message(
		await api.build_msg.new_pkg_msg(pkg_object),
		text=f"Update for {pkg_object.name}"
	)


@router.post("/promote-msg", summary="Send promoted package message",
	description="Sends a 'package has been promoted' message to Slack "
	"after a .pkg has been approved for the production environment.")
async def promote_msg(pkg_object: models.Package_In = Depends(models.Package_In)):

	blocks = await api.build_msg.promote_msg(pkg_object)
	text = f"{pkg_object.pkg_name} was promoted to production"

	result = await api.bot.SlackBot.update_message_with_response_url(
		pkg_object.response_url,
		blocks,
		text=text
	)

	# If the first method fails, try the alternate
	if json.loads(result.body).get("error") == "expired_url":
		await api.bot.SlackBot.update_message(
			blocks,
			pkg_object.slack_ts,
			text=text
		)

	return await api.bot.SlackBot.reaction(
		action = "remove",
		emoji = "gear",
		ts = pkg_object.slack_ts
	)


@router.post("/recipe-error-msg", summary="Send error message",
	description="Sends an 'error' message to Slack after a recipe has returned an error.")
async def recipe_error_msg(recipe_id: str, id: int, error: str):

	blocks = await api.build_msg.recipe_error_msg(recipe_id, id, error)
	return await api.bot.SlackBot.post_message(blocks, text=f"Encountered error in {recipe_id}")


@router.post("/trust-diff-msg", summary="Send trust diff message",
	description="Sends a message with the trust diff contents to "
	"Slack after a recipe's parent trust info has changed.")
async def trust_diff_msg(
	diff_msg: str, trust_object: models.TrustUpdate_In = Depends(models.TrustUpdate_In)):

	if len(diff_msg) > max_content_size:
		blocks = await api.build_msg.trust_diff_msg(trust_object.id, trust_object.recipe_id)
	else:
		blocks = await api.build_msg.trust_diff_msg(
			trust_object.id, trust_object.recipe_id, diff_msg)

	response = await api.bot.SlackBot.post_message(
		blocks,
		text=f"Trust verification failed for `{trust_object.recipe_id}`"
	)

	trust_object.slack_ts = response.get('ts')
	await trust_object.save()

	if len(diff_msg) > max_content_size:
		response = await api.bot.SlackBot.file_upload(
			content = diff_msg,
			filename = f"{trust_object.recipe_id}.diff",
			filetype = "diff",
			title = trust_object.recipe_id,
			text = f"Diff Output for {trust_object.recipe_id}",
			thread_ts = trust_object.slack_ts
		)

	return response


@router.put("/update-trust-success-msg", summary="Send trust update success message",
	description="Sends a 'success' message to Slack when "
	"a recipe's trust info is updated successfully.")
async def update_trust_success_msg(
	trust_object: models.TrustUpdate_In = Depends(models.TrustUpdate_In)):

	blocks = await api.build_msg.update_trust_success_msg(trust_object)

	response = await api.bot.SlackBot.update_message_with_response_url(
		trust_object.dict().get("response_url"),
		blocks,
		text=f"Successfully updated trust info for {trust_object.recipe_id}"
	)

	if response.status_code == 200:
		await api.bot.SlackBot.reaction(
			action = "remove",
			emoji = "gear",
			ts = trust_object.slack_ts
		)

	return response


@router.put("/update-trust-error-msg", summary="Send trust update error message",
	description="Sends an 'error' message to Slack when a recipe's trust info fails to update.")
async def update_trust_error_msg(msg: str,
	trust_object: models.TrustUpdate_In = Depends(models.TrustUpdate_In)):

	blocks = await api.build_msg.update_trust_error_msg(msg, trust_object)

	return await api.bot.SlackBot.update_message_with_response_url(
		trust_object.dict().get("response_url"),
		blocks,
		text=f"Failed to update trust info for {trust_object.recipe_id}"
	)


@router.put("/deny-pkg-msg", summary="Send deny package message",
	description="Sends a 'package denied message' to Slack when "
	"a .pkg is not approved for the production environment.")
async def deny_pkg_msg(pkg_object: models.Package_In = Depends(models.Package_In)):

	blocks = await api.build_msg.deny_pkg_msg(pkg_object)

	response = await api.bot.SlackBot.update_message_with_response_url(
		pkg_object.dict().get("response_url"),
		blocks,
		text=f"{pkg_object.pkg_name} was not approved for production"
	)

	if response.status_code == 200:
		await api.bot.SlackBot.reaction(
			action = "remove",
			emoji = "gear",
			ts = pkg_object.slack_ts
		)

	return response


@router.put("/deny-trust-msg", summary="Send deny trust message",
	description="Send an message to Slack stating a recipe's "
	"parent trust info changes were not approved.")
async def deny_trust_msg(
	trust_object: models.TrustUpdate_In = Depends(models.TrustUpdate_In)):

	blocks = await api.build_msg.deny_trust_msg(trust_object)

	response = await api.bot.SlackBot.update_message_with_response_url(
		trust_object.dict().get("response_url"),
		blocks,
		text=f"Trust info for {trust_object.recipe_id} was not approved"
	)

	if response.status_code == 200:
		await api.bot.SlackBot.reaction(
			action = "remove",
			emoji = "gear",
			ts = trust_object.slack_ts
		)

	return response


@router.post("/disk-space-msg", summary="Send message regarding disk usage",
	description="Sends a message to Slack if there is a disk space size issue.")
async def disk_space_msg(header: str, msg: str, image: str):

	blocks = await api.build_msg.disk_space_msg(header, msg, image)
	return await api.bot.SlackBot.post_message(blocks, text=f"Disk Space {header}")


@router.post("/ephemeral_msg", summary="Send ephemeral message", 
	description="Sends a a ephemeral message to the specified user.")
async def ephemeral_msg(user, text, channel: str | None = None, image: str | None = None, 
	alt_text: str | None = None, alt_image_text: str | None = None):

	blocks = await api.build_msg.basic_msg(text, image, alt_image_text)

	return await api.bot.SlackBot.post_ephemeral_message(
		user, blocks,
		channel=channel,
		text=alt_text
	)
