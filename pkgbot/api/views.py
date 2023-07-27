from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request, UploadFile, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from pkgbot import api, config, core
# from pkgbot.db import models
from pkgbot.utilities import common as utility


config = config.load_config()

router = APIRouter(
	tags = ["view"],
	include_in_schema = False,
	dependencies = [Depends(api.auth.login_manager)
	]
)


def template_filter_datetime(date, date_format="%Y-%m-%d %I:%M:%S"):

	if date:
		converted = datetime.fromisoformat(str(date))
		return converted.strftime(date_format)


templates = Jinja2Templates(directory=config.PkgBot.get("jinja_templates"))
templates.env.filters["strftime"] = template_filter_datetime


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):

	return templates.TemplateResponse("index.html", { "request": request })


# @router.get("/login", response_class=HTMLResponse)
# async def userlogin(request: Request):

#	return templates.TemplateResponse("login.html", { "request": request })


@router.get("/packages", response_class=HTMLResponse)
async def package_history(request: Request):

	packages = await core.package.get()

	table_headers = [
		"", "", "Name", "Version", "Status", "Updated By",
		"Packaged", "Promoted", "Flags", "Notes"
	]

	return templates.TemplateResponse("packages.html",
		{ "request": request, "table_headers": table_headers, "packages": packages })


@router.get("/package/{id}", response_class=HTMLResponse)
async def get_package(request: Request):

	pkg = await core.package.get({"id": request.path_params['id']})
	notes = await core.package.get_note({ "package_id": pkg.pkg_name })
	pkg_holds = await core.package.get_hold({ "package_id": pkg.pkg_name })

	notes_table_headers = [ "Note", "Submitted By", "Time Stamp" ]
	pkg_holds_table_headers = [ "Site", "State", "Time Stamp", "Submitted By" ]

	return templates.TemplateResponse("package.html",
		{
			"request": request,
			"package": pkg,
			"notes": notes,
			"notes_table_headers": notes_table_headers,
			"pkg_holds": pkg_holds,
			"pkg_holds_table_headers": pkg_holds_table_headers
	})


@router.post("/package/{id}", response_class=HTMLResponse)
async def update_package(request: Request):

	db_id = request.path_params.get("id")
	await core.package.get({"id": db_id})

	updates, pkg_note, site_tags = await parse_form(request)

	await core.package.update({"id": db_id}, updates)

	if pkg_note:
		pkg_note["package_id"] = updates.get("pkg_name")
		await core.package.create_note(pkg_note)

##### Need to setup
	remove_site_tags = [ site for site in (request.state.user.site_access).split(", ") if site not in site_tags ]

	for site in site_tags:
		await core.package.create_hold({
			"enabled": True,
			"package_id": updates.get("pkg_name"),
			"site": site,
			"submitted_by": request.state.user.username
		})
##### Determine which version to use...
		# Maintains a single record for package/site combination...
		# result, result_bool = await models.PackageHold.update_or_create(
		# 	{
		# 			"enabled": True,
		# 			"package_id": updates.get("pkg_name"),
		# 			"site": site,
		# 			"submitted_by": request.state.user.username
		# 	},
		# 	site=site
		# )

	session_vars = { "action_result": "updated the recipe!" }

	try:
		request.state.pkgbot = session_vars
	except:
		request.state.pkgbot |= session_vars

	redirect_url = request.url_for(name="get_package", **{"id": db_id})
	return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/recipes", response_class=HTMLResponse)
async def recipe_list(request: Request):

	recipes = await core.recipe.get()

	table_headers = [ "ID", "Recipe ID", "Enable", "Manual Only",
		"Pkg Only", "Last Ran", "Schedule", "Status", "Notes" ]

	return templates.TemplateResponse("recipes.html",
		{ "request": request, "table_headers": table_headers, "recipes": recipes })


@router.get("/recipe/{id}", response_class=HTMLResponse)
async def get_recipe(request: Request):

	recipe = await core.recipe.get({"id": request.path_params['id']})
	results = await core.recipe.get_result({"recipe_id": recipe.recipe_id})
	notes = await core.recipe.get_note({"recipe_id": recipe.recipe_id})

	notes_table_headers = [ "Note", "Submitted By", "Time Stamp" ]
	results_table_headers = [ "Event", "Status", "Last Update", "Updated By", "Task ID", "Details" ]

	return templates.TemplateResponse("recipe.html",
		{
			"request": request,
			"recipe": recipe,
			"notes": notes,
			"notes_table_headers": notes_table_headers,
			"results": results,
			"results_table_headers": results_table_headers
		}
	)


@router.post("/recipe/{id}", response_class=HTMLResponse)
async def update_recipe(request: Request):

	db_id = request.path_params.get("id")
	recipe, recipe_note, _ = await parse_form(request)

	await core.recipe.update({"id": db_id}, recipe)

	if recipe_note:
		recipe_note["recipe_id"] = recipe.get("recipe_id")
		await core.recipe.create_note(recipe_note)

	redirect_url = request.url_for(name="get_recipe", **{"id": db_id})
	return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/create/recipe", response_class=HTMLResponse)
async def new_recipe(request: Request):

	if request.state.user.get("full_admin"):
		return templates.TemplateResponse("recipe_create.html", { "request": request })


@router.post("/create/recipe", response_class=HTMLResponse,
	dependencies=[Depends(core.user.verify_admin)])
async def create_recipe(
	request: Request):

	recipe, recipe_note, _ = await parse_form(request)
	results = await core.recipe.create(recipe)

	if recipe_note:
		recipe_note["recipe_id"] = recipe.get("recipe_id")
		await core.recipe.create_note(recipe_note)

	redirect_url = request.url_for(name="get_recipe", **{"id": results.id})
	return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/icons")
async def upload_icon(icon: UploadFile):

	await utility.save_icon(icon)
	return { "result": "Successfully uploaded icon", "filename": icon.filename }


async def parse_form(request):

	form_submission = await request.form()
	restricted_form_items = {
		"recipe_id", "enabled", "pkg_only", "manual_only", "schedule", "pkg_name",
		"packaged_date", "promoted_date", "last_update", "pkg_status"
	}
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
			note = {
				"note": value,
				"submitted_by": request.state.user.username
			}

		else:
			updates[key] = value

	return updates, note, site_tags
