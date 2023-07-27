
import json
import os
import sys

from pkgbot.db import schemas

PKG_ROOT = f"{os.path.dirname(os.path.abspath('PkgBot.py'))}/PkgBot"
sys.path.insert(0, f"{PKG_ROOT}/Settings")

from Settings import messages


async def format_json(the_json, indent=4):

	return json.dumps(the_json, indent=indent)


async def new_pkg_msg(pkg_object: schemas.Package_In):

	return await messages.new_pkg(pkg_object)


async def recipe_error_msg(recipe_id: str, id: int, error: dict):

	return await messages.recipe_error(recipe_id, id, error)


async def trust_diff_msg(id: int, recipe: str, diff_msg: str = None):

	return await messages.trust_diff(id, recipe, diff_msg)


async def deny_pkg_msg(pkg_object: schemas.Package_In ):

	return await messages.deny_pkg(pkg_object)


async def deny_trust_msg(trust_object: schemas.RecipeResult_In):

	return await messages.deny_trust(trust_object)


async def promote_msg(pkg_object: schemas.Package_In):

	return await messages.promote(pkg_object)


async def update_trust_success_msg(trust_object: schemas.RecipeResult_In):

	return await messages.update_trust_success(trust_object)


async def update_trust_error_msg(msg: str, trust_object: schemas.RecipeResult_In):

	return await messages.update_trust_error(msg, trust_object)


async def unauthorized_msg(user: str):

	return await messages.unauthorized(user)


async def basic_msg(text: str, image: str | None = None, alt_image_text: str | None = None):

	return await messages.basic(text, image, alt_image_text)


async def disk_space_msg(header: str, msg: str, image: str | None = None):

	return await messages.disk_space(header, msg, image)


async def modal_notification(title_txt: str, msg_text: str,
	button_text: str, image: str | None = None, alt_image_text: str | None = None):

	return await messages.modal_notification(
		title_txt, msg_text, button_text, image, alt_image_text)


async def modal_promote_pkg(pkg_name: str):

	return await messages.modal_promote_pkg(pkg_name)
