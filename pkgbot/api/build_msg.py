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
	prefix = f"/{chatbot}/build",
	tags = [f"{chatbot}"],
	dependencies = [Depends(core.user.verify_admin)],
	responses = settings.api.custom_responses
)


@router.get("/new-pkg-msg", summary="Build new package message",
	description="Builds a 'new package' message after a .pkg is added to the dev environment.")
async def new_pkg_msg(pkg_object: schemas.Package_In = Depends(schemas.Package_In)):

	return await core.chatbot.build.new_pkg_msg(pkg_object)


@router.get("/recipe-error", summary="Build error message",
	description="Builds an 'error' message when a recipe run resulted in an error.")
async def recipe_error_msg(recipe_id: str, id: int, error: dict):

	return await core.chatbot.build.recipe_error_msg(recipe_id, id, error)


@router.get("/trust-diff-msg", summary="Build trust diff message",
	description="Builds a message with diff contents after a recipe fails verify-trust-info.")
async def trust_diff_msg(id: int, recipe: str, diff_msg: str = None):

	return await core.chatbot.build.trust_diff_msg(id, recipe, diff_msg)


@router.get("/deny-pkg-msg", summary="Build deny package message",
	description="Builds a message after a .pkg was not approved for the production environment.")
async def deny_pkg_msg(pkg_object: schemas.Package_In = Depends(schemas.Package_In)):

	return await core.chatbot.build.deny_pkg_msg(pkg_object)

@router.get("/deny-trust-msg", summary="Build deny trust message",
	description="Builds a message stating a recipe's parent trust info changes were denied.")
async def deny_trust_msg(
	result_object: schemas.RecipeResult_In = Depends(schemas.RecipeResult_In)):

	return await core.chatbot.build.deny_trust_msg(result_object)


@router.get("/promote-msg", summary="Build promoted package message",
	description="Builds a message after a .pkg is promoted to the production environment.")
async def promote_msg(pkg_object: schemas.Package_In = Depends(schemas.Package_In)):

	return await core.chatbot.build.promote_msg(pkg_object)


@router.get("/update-trust-success-msg", summary="Build trust update success message",
	description="Builds a message when a recipe's trust info is updated successfully.")
async def update_trust_success_msg(
	result_object: schemas.RecipeResult_In = Depends(schemas.RecipeResult_In)):

	return await core.chatbot.build.update_trust_success_msg(result_object)


@router.get("/update-trust-error-msg", summary="Build trust update error message",
	description="Builds a message when a recipe's trust info failed to update.")
async def update_trust_error_msg(msg: str,
	result_object: schemas.RecipeResult_In = Depends(schemas.RecipeResult_In)):

	return await core.chatbot.build.update_trust_error_msg(result_object)


@router.get("/unauthorized-msg", summary="Build unauthorized message",
	description="Builds a message when a user attempts to "
	"perform an unauthorized interaction with PkgBot.")
async def unauthorized_msg(user: str):

	return await core.chatbot.build.unauthorized_msg(user)


@router.get("/basic-msg", summary="Build generic message",
	description="Builds a simple message.")
async def basic_msg(text, image: str | None = None, alt_image_text: str | None = None):

	return await core.chatbot.build.basic_msg(text, image, alt_image_text)


@router.get("/disk-space-msg", summary="Build message regarding disk usage",
	description="Builds a message when there is a disk space size issue.")
async def disk_space_msg(header, msg, image):

	return await core.chatbot.build.disk_space_msg(header, msg, image)
