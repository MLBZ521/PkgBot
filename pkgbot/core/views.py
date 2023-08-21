from datetime import datetime

from fastapi import Request, status
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

from pkgbot import config, core
from pkgbot.db import models
from pkgbot.utilities import common as utility


config = config.load_config()
log = utility.log
jinja_templates = Jinja2Templates(directory=config.PkgBot.get("jinja_templates"))


def template_filter_datetime(date, date_format="%Y-%m-%d %I:%M:%S"):

	if date:
		converted = datetime.fromisoformat(str(date))
		return converted.strftime(date_format)


def parse_notification_messages(request: Request):

	return request.session.pop("pkgbot_msg") if "pkgbot_msg" in request.session else []


jinja_templates.env.filters.update(strftime=template_filter_datetime)
jinja_templates.env.globals.update(parse_messages=parse_notification_messages)


async def notify(request: Request, message: any, emphasize: str = "",
	emphasize_type: str = "strong", category: str = "primary"):

	if "pkgbot_msg" not in request.session:
		request.session.update(pkgbot_msg = [
			{
				"category": category,
				"emphasize": emphasize,
				"emphasize_type": emphasize_type,
				"message": message,
			}
		]
	)


async def notify_create_recipe_result(
	request: Request, success: int = 0, failure: int = 0, exists: int = 0):

	if success:
		if success == 1:
			message = "created the recipe!"
		elif success > 1:
			message = f"created {success} recipes!"

		await notify(
			request,
			category = "success",
			emphasize = "Successfully",
			emphasize_type = "strong",
			message = message
		)

	if failure:
		if failure == 1:
			message = "to create the recipe!"
		elif failure > 1:
			message = f"to create {failure} recipes!"

		await notify(
			request,
			category = "danger",
			emphasize = "Failed",
			emphasize_type = "strong",
			message = message
		)

	if exists:
		if exists == 1:
			message = "Recipe already exists!"
		elif exists > 1:
			message = f"{exists} recipes already exist!"

		await notify(
			request,
			category = "warning",
			emphasize = "Warning:  ",
			emphasize_type = "strong",
			message = message
		)


async def notify_not_authorized(request: Request, redirect: str = "index"):

	await notify(
		request,
		category = "danger",
		emphasize = "Access Denied:  ",
		emphasize_type = "strong",
		message = "You are not authorized to utilize this endpoint."
	)

	redirect_url = request.url_for(name=redirect)
	return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


async def parse_form(request):

	form_submission = await request.form()
	check_box_attributes = { "enabled", "pkg_only", "manual_only" }
	restricted_form_items = check_box_attributes.union({
		"recipe_id", "schedule", "pkg_name",
		"packaged_date", "promoted_date", "last_update", "pkg_status"
	})
	form_items = restricted_form_items.union({ "note", "site_tag" })
	note = {}
	site_tags = []
	updates = {}

	for key, value in form_submission.multi_items():

		if key not in form_items or (
			key in restricted_form_items and not request.state.user.get("full_admin")
		):
			continue

		elif key == "site_tag":
			site_tags.append(value)

		elif key == "note":
			if value:
				note = {
					"note": value,
					"submitted_by": request.state.user.get("username")
				}

		elif value:
				updates[key] = value

	if "recipe_id" in form_submission.keys():
		for check_box in check_box_attributes:
			updates[check_box] = form_submission.get(check_box, False)

	return updates, note, site_tags


async def from_web_create_recipe(recipe: dict, recipe_note: dict):

	path_params = {}

	if not recipe.get("recipe_id"):
		log.debug("Recipe ID was not provided")
		redirect_url = "create_recipe"
		result = "failure"

	elif test := await core.recipe.get({ "recipe_id": recipe.get("recipe_id") }):
		log.debug("Recipe ID already exists!")
		redirect_url = "recipes"
		result = "exists"

	else:
		# log.debug("Recipe ID provided")
		results = await core.recipe.create(recipe)

		if recipe_note:
			recipe_note["recipe_id"] = recipe.get("recipe_id")
			await core.recipe.create_note(recipe_note)

		redirect_url = "recipe"
		path_params = {"id": results.id}
		result = "success"

	return redirect_url, path_params, result
