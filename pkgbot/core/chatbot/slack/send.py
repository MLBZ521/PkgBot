import json
import os
import sys

from tortoise.expressions import Q

from pkgbot import core
from pkgbot.db import schemas
from pkgbot.utilities import common as utility

PKG_ROOT = f"{os.path.dirname(os.path.abspath('PkgBot.py'))}/PkgBot"
sys.path.insert(0, f"{PKG_ROOT}/Settings")

from Settings import messages, blocks as block


log = utility.log
MAX_CONTENT_SIZE = 1500


async def new_pkg_msg(pkg_object: schemas.Package_In):

	return await core.chatbot.SlackBot.post_message(
		await core.chatbot.build.new_pkg_msg(pkg_object),
		text=f"Update for {pkg_object.name}"
	)


async def promote_msg(pkg_object: schemas.Package_In):

	blocks = await core.chatbot.build.promote_msg(pkg_object)
	text = f"{pkg_object.pkg_name} was promoted to production"

	result = await core.chatbot.SlackBot.update_message_with_response_url(
		pkg_object.response_url,
		blocks,
		text=text
	)

	# If the first method fails, try the alternate
	if json.loads(result.body).get("error") == "expired_url":
		await core.chatbot.SlackBot.update_message(
			blocks,
			pkg_object.slack_ts,
			text=text
		)

	return await core.chatbot.SlackBot.reaction(
		action = "remove",
		emoji = "gear",
		ts = pkg_object.slack_ts
	)


async def recipe_error_msg(recipe_id: str, id: int, error: str, thread_ts: str | None = None):

	redacted_error = await utility.replace_sensitive_strings(error)

	if len(str(redacted_error)) > MAX_CONTENT_SIZE:
		blocks = await core.chatbot.build.recipe_error_msg(
			recipe_id, id, "_See thread for details..._")
	else:
		formatted_error = await core.chatbot.build.format_json(redacted_error)
		blocks = await core.chatbot.build.recipe_error_msg(
			recipe_id, id, f"```{formatted_error}```")

	response = await core.chatbot.SlackBot.post_message(
		blocks, text=f"Encountered error in {recipe_id}", thread_ts=thread_ts)

	if (
		response.get("result") != "Failed to post message"
		and len(str(redacted_error)) > MAX_CONTENT_SIZE
	):
		upload_response = await core.chatbot.SlackBot.file_upload(
			content = str(redacted_error),
			filename = f"{recipe_id}_error",
			filetype = "json",
			title = recipe_id,
			text = f"Error from `{recipe_id}`",
			thread_ts = response.get('ts')
		)

	return response


async def trust_diff_msg(diff_msg: str, result_object: schemas.RecipeResult_In):

	if len(diff_msg) > MAX_CONTENT_SIZE:
		blocks = await core.chatbot.build.trust_diff_msg(
			result_object.id, result_object.recipe.recipe_id)
	else:
		blocks = await core.chatbot.build.trust_diff_msg(
			result_object.id, result_object.recipe.recipe_id, diff_msg)

	response = await core.chatbot.SlackBot.post_message(
		blocks,
		text=f"Trust verification failed for `{trust_object.recipe_id}`"
	)

	trust_object.slack_ts = response.get('ts')
	await trust_object.save()

	if (
		response.get("result") != "Failed to post message"
		and len(diff_msg) > MAX_CONTENT_SIZE
	):
		response = await core.chatbot.SlackBot.file_upload(
			content = diff_msg,
			filename = f"{result_object.recipe.recipe_id}.diff",
			filetype = "diff",
			title = result_object.recipe.recipe_id,
			text = f"Diff Output for {result_object.recipe.recipe_id}",
			thread_ts = result_object.slack_ts
		)

	return response


async def update_trust_success_msg(result_object: schemas.RecipeResult_In):

	blocks = await core.chatbot.build.update_trust_success_msg(result_object)

	response = await core.chatbot.SlackBot.update_message_with_response_url(
		result_object.dict().get("response_url"),
		blocks,
		text = f"Successfully updated trust info for {result_object.recipe.recipe_id}"
	)

	if response.status_code == 200:
		await core.chatbot.SlackBot.reaction(
			action = "remove",
			emoji = "gear",
			ts = result_object.slack_ts
		)

	return response


async def update_trust_error_msg(msg: str, result_object: schemas.RecipeResult_In):

	blocks = await core.chatbot.build.update_trust_error_msg(msg, result_object)

	return await core.chatbot.SlackBot.update_message_with_response_url(
		result_object.dict().get("response_url"),
		blocks,
		text = f"Failed to update trust info for {result_object.recipe.recipe_id}"
	)


async def deny_pkg_msg(pkg_object: schemas.Package_In):

	blocks = await core.chatbot.build.deny_pkg_msg(pkg_object)

	response = await core.chatbot.SlackBot.update_message_with_response_url(
		pkg_object.dict().get("response_url"),
		blocks,
		text=f"{pkg_object.pkg_name} was not approved for production"
	)

	if response.status_code == 200:
		await core.chatbot.SlackBot.reaction(
			action = "remove",
			emoji = "gear",
			ts = pkg_object.slack_ts
		)

	return response


async def deny_trust_msg(result_object: schemas.RecipeResult_In):

	blocks = await core.chatbot.build.deny_trust_msg(result_object)
	text = f"Trust info for {result_object.recipe.recipe_id} was not approved"

	response = await core.chatbot.SlackBot.update_message_with_response_url(
		result_object.dict().get("response_url"),
		blocks,
		text = text
	)

	# If the first method fails, try the alternate
	if json.loads(response.body).get("error") in ("used_url", "expired_url"):
		response = await core.chatbot.SlackBot.update_message(
			blocks,
			result_object.slack_ts,
			text = text
		)

	if response.status_code == 200:
		await core.chatbot.SlackBot.reaction(
			action = "remove",
			emoji = "gear",
			ts = result_object.slack_ts
		)

	return response


async def disk_space_msg(header: str, msg: str, image: str):

	blocks = await core.chatbot.build.disk_space_msg(header, msg, image)
	return await core.chatbot.SlackBot.post_message(blocks, text=f"Disk Space {header}")


async def direct_msg(user, text, channel: str | None = None, image: str | None = None,
	alt_text: str | None = None, alt_image_text: str | None = None):

	blocks = await core.chatbot.build.basic_msg(text, image, alt_image_text)

	return await core.chatbot.SlackBot.post_ephemeral_message(
		user, blocks,
		channel=channel,
		text=alt_text
	)


async def basic_msg(text, image: str | None = None,
	alt_text: str | None = None, alt_image_text: str | None = None):

	blocks = await core.chatbot.build.basic_msg(text, image, alt_image_text)
	return await core.chatbot.SlackBot.post_message(blocks, text=alt_text)


async def modal_notification(trigger_id: str, title_txt: str, msg_text: str,
	button_text: str, image: str | None = None, alt_image_text: str | None = None):

	blocks = await core.chatbot.build.modal_notification(
		title_txt, msg_text, button_text, image, alt_image_text)
	return await core.chatbot.SlackBot.open_modal(trigger_id, blocks)


async def modal_promote_pkg(trigger_id: str, pkg_name: str):

	blocks = await core.chatbot.build.modal_promote_pkg(pkg_name)
	return await core.chatbot.SlackBot.open_modal(trigger_id, blocks)


async def policy_list(filter_values: str, username: str):

	user_object = await core.user.get({"username": username})
	q_expression = Q()

	for filter_value in filter_values.split(" "):
		q_expression &= Q(name__icontains=filter_value)

	if not user_object.full_admin:
		sites = user_object.site_access.split(", ")
		q_expression &= Q(site__in=sites)

	policies_object = await core.policy.get(q_expression)

	if not isinstance(policies_object, list):
		policies_object = [policies_object]

	policies = [ policy.dict() for policy in policies_object ]
	return await block.policy_list(policies)
