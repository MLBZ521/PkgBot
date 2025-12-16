from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from fastapi.responses import RedirectResponse, HTMLResponse

from pkgbot import api, config, core, settings
from pkgbot.db import models, schemas
from pkgbot.utilities import common as utility


config = config.load_config()
log = utility.log
jinja_templates = settings.api.jinja_templates

router = APIRouter(
	tags = ["view"],
	include_in_schema = False,
	dependencies = [Depends(api.auth.login_manager)]
)


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):

	return jinja_templates.TemplateResponse("index.html", { "request": request })


# @router.get("/login", response_class=HTMLResponse)
# async def userlogin(request: Request):

#	return jinja_templates.TemplateResponse("login.html", { "request": request })


@router.get("/error", response_class=HTMLResponse)
async def error(request: Request, error: str | None = None):

	if error:
		log.error(f"{error}")

	await core.views.notify(
		request,
		category = "danger",
		emphasize = "ERROR:  ",
		emphasize_type = "strong",
		message = error or "Something went wrong!"
	)

### TODO:
	# This isn't switching the page....need to figure out why...
	return jinja_templates.TemplateResponse("error.html", { "request": request, "error": error })


@router.get("/packages", response_class=HTMLResponse)
async def packages(request: Request):

	packages = await schemas.Packages_Out.from_queryset(models.Packages.all())

	table_headers = [
		"", "ID", "Name", "Version", "Status", "Updated By",
		"Packaged", "Promoted", "Holds", "Notes"
	]

	return jinja_templates.TemplateResponse("packages.html",
		{ "request": request, "table_headers": table_headers, "packages": packages })


@router.get("/package/{id}", response_class=HTMLResponse)
async def package(request: Request):

	if pkg := await core.package.get({"id": request.path_params['id']}):

		notes_table_headers = [ "Note", "Submitted By", "Time Stamp" ]
		pkg_holds_table_headers = [ "Site", "State", "Time Stamp", "Submitted By" ]
		policies_table_headers = [ "Site", "Policy ID", "Name" ]

		return jinja_templates.TemplateResponse("package.html",
			{
				"request": request,
				"package": pkg,
				"notes": pkg.notes,
				"notes_table_headers": notes_table_headers,
				"pkg_holds": pkg.holds,
				"pkg_holds_table_headers": pkg_holds_table_headers,
				"policies": pkg.policies,
				"policies_table_headers": policies_table_headers
		})

	else:
		await error(request, "The requested package does not exist.")


@router.post("/package/{id}", response_class=HTMLResponse)
async def update_package(request: Request):

	site_admin = request.state.user.get('username')
	site_admin_access = request.state.user.get('site_access')
	db_id = request.path_params.get("id")
	await core.package.get({"id": db_id})

	updates, pkg_note, enabled_sites_holds = await core.views.parse_form(request)

	await core.package.update({"id": db_id}, updates)

	if pkg_note:
		pkg_note["package_id"] = updates.get("pkg_name")
		await core.package.create_note(pkg_note)

	remove_sites_holds = [
		site for site in request.state.user.get("site_access") if site not in enabled_sites_holds ]

	for site in site_admin_access:

		pkg_hold_object = {
			"package_id": updates.get("pkg_name"),
			"site": site,
		}

		if enabled_sites_holds or remove_sites_holds:

			# Check for existing holds
			hold = await core.package.get_hold(pkg_hold_object)

			if site in enabled_sites_holds and ( not hold or not hold.enabled ):
				# Add Site Hold
				log.debug(
					f"Creating hold for `{site}` on {updates.get('pkg_name')} by `{site_admin}`.")
				pkg_hold_object |= {
					"enabled": True,
					"submitted_by": site_admin
				}
				await core.package.create_hold(pkg_hold_object)

			elif site in remove_sites_holds and hold and hold.enabled:
				# Remove Site Hold
				log.debug(
					f"Removing hold for `{site}` on {updates.get('pkg_name')} by `{site_admin}`.")
				pkg_hold_object |= {
					"enabled": False,
					"submitted_by": site_admin
				}
				await core.package.remove_hold(pkg_hold_object)


	await core.views.notify(
		request,
		category = "success",
		emphasize = "Successfully",
		emphasize_type = "strong",
		message = "updated the package!"
	)

	redirect_url = request.url_for(name="package", **{"id": db_id})
	return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/recipes", response_class=HTMLResponse)
async def recipes(request: Request):

	all_recipes = await schemas.Recipe_Out.from_queryset(models.Recipes.all())

	table_headers = [ "ID", "Recipe ID", "Enable", "Manual Only",
		"Pkg Only", "Last Ran", "Schedule", "Notes" ]

	return jinja_templates.TemplateResponse("recipes.html",
		{ "request": request, "table_headers": table_headers, "recipes": all_recipes })


@router.get("/recipe/{id}", response_class=HTMLResponse)
async def recipe(request: Request):

	if recipe_object := await core.recipe.get({"id": request.path_params['id']}):

		notes_table_headers = [ "Note", "Submitted By", "Time Stamp" ]
		results_table_headers = [ "Event", "Status", "Last Update", "Updated By", "Task ID", "Details" ]

		return jinja_templates.TemplateResponse("recipe.html",
			{
				"request": request,
				"recipe": recipe_object,
				"notes": recipe_object.notes,
				"notes_table_headers": notes_table_headers,
				"results": recipe_object.results,
				"results_table_headers": results_table_headers
		})

	else:
		await error(request, "The requested recipe does not exist.")


@router.post("/recipe/{id}", response_class=HTMLResponse)
async def update_recipe(request: Request):

	db_id = request.path_params.get("id")
	recipe, recipe_note, _ = await core.views.parse_form(request)

	await core.recipe.update({"id": db_id}, recipe)

	if recipe_note:
		recipe_note["recipe_id"] = recipe.get("recipe_id")
		await core.recipe.create_note(recipe_note)

	await core.views.notify(
		request,
		category = "success",
		emphasize = "Successfully",
		emphasize_type = "strong",
		message = "updated the recipe!"
	)

	redirect_url = request.url_for(name="recipe", **{"id": db_id})
	return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/create/recipe", response_class=HTMLResponse)
async def create_recipe_form(request: Request,
	user_object: schemas.PkgBotAdmin_In = Depends(core.user.get_current_user_from_cookie)):

	if not user_object or not user_object.dict().get("full_admin"):
		return await core.views.notify_not_authorized(request, "recipes")

	return jinja_templates.TemplateResponse("recipe_create.html", { "request": request })


@router.post("/create/recipe", response_class=HTMLResponse)
async def create_recipe(request: Request,
	user_object: schemas.PkgBotAdmin_In = Depends(core.user.get_current_user_from_cookie)):

	if not user_object or not user_object.dict().get("full_admin"):
		return await core.views.notify_not_authorized(request, "recipes")

	recipe, recipe_note, _ = await core.views.parse_form(request)

	referral, path_params, result = await core.views.from_web_create_recipe(recipe, recipe_note)
	redirect_url = request.url_for(name=referral, **path_params)

	await core.views.notify_create_recipe_result(request, **{ result: 1 })
	return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/create/recipes", response_class=HTMLResponse)
async def create_recipes(request: Request, file: UploadFile = File(),
	user_object: schemas.PkgBotAdmin_In = Depends(core.user.get_current_user_from_cookie)):

	if not user_object or not user_object.dict().get("full_admin"):
		return await core.views.notify_not_authorized(request, "recipes")

	redirect_url = await core.views.from_web_create_recipes(request, file)
	return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/icons")
async def upload_icon(icon: UploadFile):

	await utility.save_icon(icon)
	return { "result": "Successfully uploaded icon", "filename": icon.filename }
