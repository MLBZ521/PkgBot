import json

from typing import List

from pkgbot import config
from pkgbot.db import schemas
from pkgbot.utilities import common as utility
from . import blocks as block


config = config.load_config()
SECURE = "s" if config.PkgBot.get("enable_ssl") else ""
PKGBOT_HOST = config.PkgBot.get('host')
PKGBOT_SERVER = f"http{SECURE}://{PKGBOT_HOST}:{config.PkgBot.get('port')}"


async def format_json(the_json, indent=4):

	return json.dumps(the_json, indent=indent)


async def new_pkg(pkg_object: schemas.Package_In):

	section_block = await block.brick_section_text(
		f"*Name:*  `{pkg_object.dict().get('name')}`\n"
		f"*Version:*  `{pkg_object.dict().get('version')}`\n"
		f"*Package Name:*  `{pkg_object.dict().get('pkg_name', 'Unknown')}`"
	)

	if pkg_object.dict().get("icon"):
		section_block = section_block | await block.brick_accessory_image(
			pkg_object.dict().get("icon"), ":new:")


	blocks = [
		await block.brick_header("New Software Version Available"),
		section_block,
		await block.brick_footer([
			f"*Dev*:  {pkg_object.dict().get('packaged_date')}\t"
			f"*Uploaded by*:  @{config.Slack.get('bot_name')}"
		]),
		await block.brick_section_text("_Promote to production?_"),
		await block.brick_action_buttons([
			("Approve", "primary", f"Package:{pkg_object.dict().get('id')}"),
			("Deny", "danger", f"Package:{pkg_object.dict().get('id')}")
		])
	]

	return await format_json(blocks)


async def recipe_error(recipe_id: str, id: int, error: dict):

	blocks = [
		await block.brick_header(f"Encountered an error in:  {recipe_id}"),
		await block.brick_section_text(f"{error}") | \
			await block.brick_accessory_image(config.PkgBot.get("icon_error"), ":x:"),
		await block.brick_action_buttons([("Acknowledge", "danger", "Recipe_Error:ack")])
	]

	return await format_json(blocks)


async def trust_diff(id: int, recipe: str, diff_msg: str = None):

	blocks = [
		await block.brick_header("Trust Verification Failure"),
		await block.brick_section_text(
			f"*Recipe:*  `{recipe}`\n\n_Trust diff review required._\n\n") | \
			await block.brick_accessory_image(config.PkgBot.get("icon_warning"), ":warning:"),
	]

	if diff_msg:
		blocks.append(await block.brick_section_text(f"*Diff Output:*```{diff_msg}```"))

	blocks.append(
		await block.brick_action_buttons([
			("Approve", "primary", f"Trust:{id}"),
			("Deny", "danger", f"Trust:{id}")
		])
	)

	return await format_json(blocks)


async def deny_pkg(pkg_object: schemas.Package_In ):

	section_block = await block.brick_section_text(
		f"*Name:*  `{pkg_object.dict().get('name')}`\n"
		f"*Version:*  `{pkg_object.dict().get('version')}`\n"
		f"*Package Name:*  `{pkg_object.dict().get('pkg_name', 'Unknown')}`"
	)

	if pkg_object.dict().get("icon"):
		section_block = section_block | await block.brick_accessory_image(
			pkg_object.dict().get("icon"), ":new:")


	blocks = [
		await block.brick_header("This software package was denied"),
		section_block,
		await block.brick_footer([
			f"*Dev*:  {pkg_object.dict().get('packaged_date')}\t"
			f"*Uploaded by*:  @{config.Slack.get('bot_name')}",
			f"*Denied by*: @{pkg_object.dict().get('updated_by')}\t"
			f"*On*:  {pkg_object.dict().get('last_update')}"
		])
	]

	return await format_json(blocks)


async def deny_trust(result_object: schemas.RecipeResult_In):

	blocks = [
		await block.brick_section_text(
			f"Denied update to trust info for `{result_object.recipe.recipe_id}`") | \
			await block.brick_accessory_image(config.PkgBot.get("icon_denied"), ":denied:"),
		await block.brick_footer([
			f"*Denied by*:  @{result_object.dict().get('updated_by')}\t"
			f"*On*:  {result_object.dict().get('last_update')}"
		])
	]

	return await format_json(blocks)


async def promote(pkg_object: schemas.Package_In):

	section_block = await block.brick_section_text(
		f"*Name:*  `{pkg_object.dict().get('name')}`\n"
		f"*Version:*  `{pkg_object.dict().get('version')}`\n"
		f"*Package Name:*  `{pkg_object.dict().get('pkg_name', 'Unknown')}`"
	)

	if pkg_object.dict().get("icon"):
		section_block = section_block | await block.brick_accessory_image(
			pkg_object.dict().get("icon"), ":new:")


	blocks = [
		section_block,
		await block.brick_footer([
			f"*Dev*:  {pkg_object.dict().get('packaged_date')}\t"
			f"*Uploaded by*:  @{config.Slack.get('bot_name')}",
			f"*Prod*:  {pkg_object.dict().get('promoted_date')}\t"
			f"*Approved by*:  @{pkg_object.dict().get('updated_by')}"
		])
	]

	return await format_json(blocks)


async def update_trust_success(result_object: schemas.RecipeResult_In):

	blocks = [
		await block.brick_section_text(
			f"Trust info was updated for:  `{result_object.recipe.recipe_id}`"),
		await block.brick_footer([
			f"*Updated by*:  @{result_object.dict().get('updated_by')}\t"
			f"*On*:  {result_object.dict().get('last_update')}"
		])
	]

	return await format_json(blocks)


async def update_trust_error(msg: str, result_object: schemas.RecipeResult_In):

	section_block = await block.brick_section_text(f"```{msg}```") | \
		await block.brick_accessory_image(config.PkgBot.get("icon_error"), ":x:")

	blocks = [
		await block.brick_header(
			f"Failed to update trust info for `{result_object.recipe.recipe_id}`"),
		section_block
	]

	return await format_json(blocks)


async def unauthorized(user: str):

	blocks = [
		await block.brick_header("PERMISSION DENIED:  Unauthorized User"),
		await block.brick_section_text(
			"_*Warning:*_  you are not a PkgBot admin and are not authorized to perform this "
			f"action.\n\n`{user}` will be reported to the robot overloads."
		) | \
			await block.brick_accessory_image(
				config.PkgBot.get("icon_permission_denied"), ":denied:")
	]

	return await format_json(blocks)


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


async def modal_add_pkg_to_policy(pkg_name: str):

	return await format_json(await block.modal_add_pkg_to_policy(pkg_name))


async def package_cleanup_report(total_package_count, packages_in_use, **kwargs):

	date_stamp = await utility.get_timestamp(format_string="%Y-%m-%d")
	message = (f"Package retirement report is attached.  Identified packages will be removed "
		"after the 1st of the following month.\n\nWe highly recommend that Site Admins review the "
		"list of packages in the attached report and the Policies that are still using these "
		f"packages.\n\nDetails:\n• {total_package_count} packages identified\n• {packages_in_use} "
		"packages currently assigned to Policies\n\nIf a specific package version is required by "
		f"your Site, you can \"hold\" it on <{PKGBOT_SERVER}|{PKGBOT_HOST}>")

	blocks = [
		await block.brick_header(
			f":mega::bangbang: Jamf Pro Monthly Package Retirement Report {date_stamp} :bangbang::mega:"),
		await block.brick_section_text(message) # | \
			# await block.brick_accessory_image(config.PkgBot.get("icon_warning"), ":warning:")
	]

	return await format_json(blocks)
