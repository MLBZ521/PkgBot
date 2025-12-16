from fastapi import APIRouter, Depends

from pkgbot import config, core, settings
from pkgbot.db import schemas


config = config.load_config()


if config.Slack:
	chatbot = "slackbot"
# Example:
# elif config.Teams:
# 	chatbot = "teamsbot"
else:
	chatbot = "chatbot"


router = APIRouter(
	prefix = f"/{chatbot}/send",
	tags = [f"{chatbot}"],
	dependencies = [Depends(core.user.verify_admin)],
	responses = settings.api.custom_responses
)


@router.post("/dev-msg", summary="Send new package message",
	description="Sends a message when a new .pkg is added to the dev environment.")
async def new_pkg_msg(pkg_object: schemas.Package_In = Depends(schemas.Package_In)):

	return await core.chatbot.send.new_pkg_msg(pkg_object)


@router.post("/promote-msg", summary="Send promoted package message",
	description="Sends a message when a .pkg is approved for the production environment.")
async def promote_msg(pkg_object: schemas.Package_In = Depends(schemas.Package_In)):

	return await core.chatbot.send.promote_msg(pkg_object)


@router.post("/recipe-error-msg", summary="Send error message",
	description="Sends a message when a recipe run results in an error.")
async def recipe_error_msg(recipe_id: str, id: int, error: str):

	return await core.chatbot.send.recipe_error_msg(recipe_id, id, error)

@router.post("/trust-diff-msg", summary="Send trust diff message",
	description="Sends a message with diff contents after a recipe fails verify-trust-info.")
async def trust_diff_msg(
	diff_msg: str, result_object: schemas.RecipeResult_In = Depends(schemas.RecipeResult_In)):

	return await core.chatbot.send.trust_diff_msg(diff_msg, result_object)


@router.put("/update-trust-success-msg", summary="Send trust update success message",
	description="Sends a message when a recipe's trust info is updated successfully.")
async def update_trust_success_msg(
	result_object: schemas.RecipeResult_In = Depends(schemas.RecipeResult_In)):

	return await core.chatbot.send.update_trust_success_msg(result_object)


@router.put("/update-trust-error-msg", summary="Send trust update error message",
	description="Sends a message when a recipe's trust info fails to update.")
async def update_trust_error_msg(msg: str,
	result_object: schemas.RecipeResult_In = Depends(schemas.RecipeResult_In)):

	return await core.chatbot.send.update_trust_error_msg(msg, result_object)


@router.put("/deny-pkg-msg", summary="Send deny package message",
	description="Sends a message after a .pkg was not approved for the production environment.")
async def deny_pkg_msg(pkg_object: schemas.Package_In = Depends(schemas.Package_In)):

	return await core.chatbot.send.deny_pkg_msg(pkg_object)


@router.put("/deny-trust-msg", summary="Send deny trust message",
	description="Send a message stating a recipe's parent trust info changes were denied.")
async def deny_trust_msg(
	result_object: schemas.RecipeResult_In = Depends(schemas.RecipeResult_In)):

	return await core.chatbot.send.deny_trust_msg(result_object)


@router.post("/disk-space-msg", summary="Send message regarding disk usage",
	description="Sends a message if there is a disk space size issue.")
async def disk_space_msg(header: str, msg: str, image: str):

	return await core.chatbot.send.acknowledge_msg(header, msg, image)


@router.post("/direct_msg", summary="Send ephemeral message",
	description="Sends a a ephemeral message to the specified user.")
async def direct_msg(user, text, channel: str | None = None, image: str | None = None,
	alt_text: str | None = None, alt_image_text: str | None = None):

	return await core.chatbot.send.direct_msg(user, text, channel, image, alt_text, alt_image_text)


@router.post("/basic-msg", summary="Send basic error message",
	description="Sends a basic error message to the specified user.")
async def basic_msg(text, image: str | None = None,
	alt_text: str | None = None, alt_image_text: str | None = None):

	return await core.chatbot.send.basic_msg(text, image, alt_text, alt_image_text)
