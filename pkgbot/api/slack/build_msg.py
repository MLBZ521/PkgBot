import json

from fastapi import APIRouter, Depends

from pkgbot import api, settings
from pkgbot.db import models
from pkgbot.utilities import common as utility


log = utility.log
SlackBot = None
router = APIRouter(
	prefix = "/slackbot/build",
	tags = ["slackbot"],
	dependencies = [Depends(api.user.verify_admin)],
	responses = settings.api.custom_responses
)

async def format_json(the_json, indent=4):
	return json.dumps(the_json, indent=indent)


@router.get("/new-pkg-msg", summary="Build new package message",
	description="Builds a 'new package' message for Slack after "
	"a .pkg has been added to the dev environment.")
async def new_pkg_msg(pkg_object: models.Package_In = Depends(models.Package_In)):

	blocks = [
		await api.block_builders.brick_header(pkg_object),
		await api.block_builders.brick_main(pkg_object),
		await api.block_builders.brick_footer_dev(pkg_object)
	]

	for brick in await api.block_builders.brick_button(pkg_object):
		blocks.append(brick)

	return await format_json(blocks)


@router.get("/recipe-error", summary="Build error message",
	description="Builds an 'error' message for Slack after a recipe has returned an error.")
async def recipe_error_msg(recipe_id: str, id: int, error: dict):

	redacted_error = await utility.replace_sensitive_strings(error)
	blocks = await api.block_builders.brick_error(recipe_id, await format_json(redacted_error))
	return await format_json(blocks)


@router.get("/trust-diff-msg", summary="Build trust diff message",
	description="Builds a message with the trust diff contents "
	"for Slack after a recipe's parent trust info has changed.")
async def trust_diff_msg(id: int, recipe: str, diff_msg: str = None):

	blocks = [
		await api.block_builders.brick_trust_diff_header(),
		await api.block_builders.brick_trust_diff_main(recipe)
	]

	if diff_msg:
		blocks.append(await api.block_builders.brick_trust_diff_content(diff_msg))

	blocks.append(await api.block_builders.brick_trust_diff_button(id))
	return await format_json(blocks)


@router.get("/deny-pkg-msg", summary="Build deny package message",
	description="Builds a 'package denied message' for Slack when "
	"a .pkg is not approved for the production environment.")
async def deny_pkg_msg(pkg_object: models.Package_In = Depends(models.Package_In)):

	brick_footer = await api.block_builders.brick_footer_dev(pkg_object)
	brick_footer.get("elements").append(
		await api.block_builders.brick_footer_denied(pkg_object)
	)

	blocks = [
		await api.block_builders.brick_deny_pkg(pkg_object),
		await api.block_builders.brick_main(pkg_object),
		brick_footer
	]

	return await format_json(blocks)


@router.get("/deny-trust-msg", summary="Build deny trust message",
	description="Builds an message for Slack stating a recipe's "
	"parent trust info changes were not approved.")
async def deny_trust_msg(
	trust_object: models.TrustUpdate_In = Depends(models.TrustUpdate_In)):

	blocks = [
		await api.block_builders.brick_deny_trust(trust_object),
		await api.block_builders.brick_footer_denied_trust(trust_object)
	]

	return await format_json(blocks)


@router.get("/promote-msg", summary="Build promoted package message",
	description="Builds a 'package has been promoted' message for Slack "
	"after a .pkg has been approved for the production environment.")
async def promote_msg(pkg_object: models.Package_In = Depends(models.Package_In)):

	brick_footer = await api.block_builders.brick_footer_dev(pkg_object)
	brick_footer.get("elements").append(
		await api.block_builders.brick_footer_promote(pkg_object)
	)

	blocks = [
		await api.block_builders.brick_main(pkg_object),
		brick_footer
	]

	return await format_json(blocks)


@router.get("/update-trust-success-msg", summary="Build trust update success message",
	description="Builds a 'success' message for Slack when a "
	"recipe's trust info is updated successfully.")
async def update_trust_success_msg(
	trust_object: models.TrustUpdate_In = Depends(models.TrustUpdate_In)):

	blocks = [
		await api.block_builders.brick_update_trust_success_msg(trust_object),
		await api.block_builders.brick_footer_update_trust_success_msg(trust_object)
	]

	return await format_json(blocks)


@router.get("/update-trust-error-msg", summary="Build trust update error message",
	description="Builds an 'error' message for Slack when a recipe's trust info fails to update.")
async def update_trust_error_msg(msg: str,
	trust_object: models.TrustUpdate_In = Depends(models.TrustUpdate_In)):

	blocks = await api.block_builders.brick_update_trust_error_msg(trust_object, msg)
	blocks.append(await api.block_builders.brick_trust_diff_button(trust_object.dict().get('id')))
	return await format_json(blocks)


@router.get("/unauthorized-msg", summary="Build unauthorized message",
	description="Builds a 'unauthorized' message for Slack when a user attempts to "
	"perform a Slack interaction with PkgBot that they're not authorized to perform.")
async def unauthorized_msg(user):

	return await format_json(await api.block_builders.unauthorized(user))


@router.get("/missing-recipe-msg", summary="Build missing recipe message",
	description="Builds a 'missing recipe' message for Slack when unable to locate "
	"a recipe for a requested action.")
async def missing_recipe_msg(recipe_id, text):

	return await format_json(await api.block_builders.missing_recipe_msg(recipe_id, text))


@router.get("/disk-space-msg", summary="Build message regarding disk usage",
	description="Builds a message for Slack when there is a disk space size issue.")
async def disk_space_msg(header, msg, image):

	return await format_json(await api.block_builders.brick_disk_space_msg(header, msg, image))
