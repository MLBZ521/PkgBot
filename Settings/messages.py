import json

from pkgbot.db import schemas
from . import blocks as block


async def format_json(the_json, indent=4):

	return json.dumps(the_json, indent=indent)


async def new_pkg(pkg_object: schemas.Package_In):

	blocks = [
		await block.brick_header(pkg_object),
		await block.brick_main(pkg_object),
		await block.brick_footer_dev(pkg_object)
	]

	for brick in await block.brick_button(pkg_object):
		blocks.append(brick)

	return await format_json(blocks)


async def recipe_error(recipe_id: str, id: int, error: dict):

	return await format_json(await block.brick_error(recipe_id, error))


async def trust_diff(id: int, recipe: str, diff_msg: str = None):

	blocks = [
		await block.brick_trust_diff_header(),
		await block.brick_trust_diff_main(recipe)
	]

	if diff_msg:
		blocks.append(await block.brick_trust_diff_content(diff_msg))

	blocks.append(await block.brick_trust_diff_button(id))
	return await format_json(blocks)


async def deny_pkg(pkg_object: schemas.Package_In ):

	brick_footer = await block.brick_footer_dev(pkg_object)
	brick_footer.get("elements").append(
		await block.brick_footer_denied(pkg_object)
	)

	blocks = [
		await block.brick_deny_pkg(pkg_object),
		await block.brick_main(pkg_object),
		brick_footer
	]

	return await format_json(blocks)


async def deny_trust(result_object: schemas.RecipeResult_In):

	blocks = [
		await block.brick_deny_trust(result_object),
		await block.brick_footer_denied_trust(result_object)
	]

	return await format_json(blocks)


async def promote(pkg_object: schemas.Package_In):

	brick_footer = await block.brick_footer_dev(pkg_object)
	brick_footer.get("elements").append(
		await block.brick_footer_promote(pkg_object)
	)

	blocks = [
		await block.brick_main(pkg_object),
		brick_footer
	]

	return await format_json(blocks)


async def update_trust_success(result_object: schemas.RecipeResult_In):

	blocks = [
		await block.brick_update_trust_success_msg(result_object),
		await block.brick_footer_update_trust_success_msg(result_object)
	]

	return await format_json(blocks)


async def update_trust_error(msg: str, result_object: schemas.RecipeResult_In):

	blocks = await block.brick_update_trust_error_msg(result_object, msg)
	return await format_json(blocks)


async def unauthorized(user: str):

	return await format_json(await block.unauthorized(user))


async def basic_msg(msg_text: str,
	header_txt: str | None = None,
	buttons_details: List[tuple] = None,
	# button_text: str, button_value: str, button_style: str,
	image: str | None = None, alt_image_text: str | None = None):

	blocks = []

	if header_txt:
		blocks.append(await block.brick_header(header_txt))

	section_block = await block.brick_section_text(msg_text)

	if image:
		section_block = section_block | await block.brick_accessory_image(image, alt_image_text)

	blocks.append(section_block)

	if buttons_details:
		blocks.append(await block.brick_action_buttons(buttons_details))

	return await format_json(blocks)


async def modal_notification(title_txt: str, msg_text: str,
	button_text: str, image: str | None = None, alt_image_text: str | None = None):

	blocks = await block.brick_section_text(msg_text)

	if image:
		blocks = blocks | await block.brick_accessory_image(image, alt_image_text)

	blocks = await block.modal_notification(title_txt, button_text) | {"blocks": [blocks]}

	return await format_json(blocks)


async def modal_promote_pkg(pkg_name: str):

	return await format_json(await block.modal_promote_pkg(pkg_name))
