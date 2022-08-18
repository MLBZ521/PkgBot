import json

from fastapi import APIRouter, Depends, Response

import settings, utilities.common as utility
from db import models
from api import user
from api.slack import block_builders


log = utility.log
SlackBot = None
router = APIRouter(
	prefix = "/slackbot/build",
	tags = ["slackbot"],
	dependencies = [Depends(user.verify_admin)],
	responses = settings.api.custom_responses
)


@router.get("/new-pkg-msg", summary="Build new package message",
	description="Builds a 'new package' message for Slack after "
	"a .pkg has been added to the dev environment.")
async def new_pkg_msg(pkg_object: models.Package_In = Depends(models.Package_In)):

	blocks = [
		await block_builders.brick_header(pkg_object),
		await block_builders.brick_main(pkg_object),
		await block_builders.brick_footer_dev(pkg_object)
	]

	for brick in await block_builders.brick_button(pkg_object):
		blocks.append(brick)

	return json.dumps(blocks, indent=4)


@router.get("/recipe-error", summary="Build error message",
	description="Builds an 'error' message for Slack after a recipe has returned an error.")
async def recipe_error_msg(recipe_id: str, id: int, error: dict):

	formatted_error = json.dumps(error, indent=4)
	brick_error = await block_builders.brick_error(recipe_id, formatted_error)

	return json.dumps(brick_error, indent=4)


@router.get("/trust-diff-msg", summary="Build trust diff message",
	description="Builds a message with the trust diff contents "
	"for Slack after a recipe's parent trust info has changed.")
async def trust_diff_msg(id: int, recipe: str, error: str = None):

	blocks = [
		await block_builders.brick_trust_diff_header(),
		await block_builders.brick_trust_diff_main(recipe)
	]

	if error:
		blocks.append( await block_builders.brick_trust_diff_content(error) )

	blocks.append( await block_builders.brick_trust_diff_button(id) )

	return json.dumps(blocks, indent=4)


@router.get("/deny-pkg-msg", summary="Build deny package message",
	description="Builds a 'package denied message' for Slack when "
	"a .pkg is not approved for the production environment.")
async def deny_pkg_msg(pkg_object: models.Package_In = Depends(models.Package_In)):

	brick_footer = await block_builders.brick_footer_dev(pkg_object)
	brick_footer.get("elements").append(
		await block_builders.brick_footer_denied(pkg_object)
	)

	blocks = [
		await block_builders.brick_deny_pkg(pkg_object),
		await block_builders.brick_main(pkg_object),
		brick_footer
	]

	return json.dumps(blocks, indent=4)


@router.get("/deny-trust-msg", summary="Build deny trust message",
	description="Builds an message for Slack stating a recipe's "
	"parent trust info changes were not approved.")
async def deny_trust_msg(
	error_object: models.ErrorMessage_In = Depends(models.ErrorMessage_In)):

	blocks = [
		await block_builders.brick_deny_trust(error_object),
		await block_builders.brick_footer_denied_trust(error_object)
	]

	return json.dumps(blocks, indent=4)


@router.get("/promote-msg", summary="Build promoted package message",
	description="Builds a 'package has been promoted' message for Slack "
	"after a .pkg has been approved for the production environment.")
async def promote_msg(pkg_object: models.Package_In = Depends(models.Package_In)):

	brick_footer = await block_builders.brick_footer_dev(pkg_object)
	brick_footer.get("elements").append(
		await block_builders.brick_footer_promote(pkg_object)
	)

	blocks = [
		await block_builders.brick_main(pkg_object),
		brick_footer
	]

	return json.dumps(blocks, indent=4)


@router.get("/update-trust-success-msg", summary="Build trust update success message",
	description="Builds a 'success' message for Slack when a "
	"recipe's trust info is updated successfully.")
async def update_trust_success_msg(
	error_object: models.ErrorMessage_In = Depends(models.ErrorMessage_In)):

	blocks = [
		await block_builders.brick_update_trust_success_msg(error_object),
		await block_builders.brick_footer_update_trust_success_msg(error_object)
	]

	return json.dumps(blocks, indent=4)


@router.get("/update-trust-error-msg", summary="Build trust update error message",
	description="Builds an 'error' message for Slack when a recipe's trust info fails to update.")
async def update_trust_error_msg(msg: str,
	error_object: models.ErrorMessage_In = Depends(models.ErrorMessage_In)):

	return json.dumps(
		[ await block_builders.brick_update_trust_error_msg(error_object, msg) ],
		indent=4
	)


@router.get("/unauthorized-msg", summary="Build unauthorized message",
	description="Builds a 'unauthorized' message for Slack when a user attempts to "
	"perform a Slack interation with PkgBot that they're not authorized to perform.")
async def unauthorized_msg(user):

	return json.dumps(
		await block_builders.unauthorized(user),
		indent=4
	)


@router.get("/missing-recipe-msg", summary="Build unauthorized message",
	description="Builds a 'missing recipe' message for Slack when unable to locate "
	"a recipe for a requested action.")
async def missing_recipe_msg(recipe_id, text):

	return json.dumps(
		await block_builders.missing_recipe_msg(recipe_id, text),
		indent=4
	)
