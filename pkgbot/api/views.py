from datetime import datetime

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from pkgbot import api, config, core
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
	return templates.TemplateResponse("package.html", { "request": request, "package": pkg })


@router.get("/edit/{id}", response_class=HTMLResponse)
async def edit(request: Request):

	pkg = await core.package.get({"id": request.path_params['id']})

	return templates.TemplateResponse("edit.html",
		{ "request": request, "package": pkg })


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
	pkg = await core.recipe.get({"id": request.path_params['id']})

	return templates.TemplateResponse("recipe.html",
		{ "request": request, "recipe": pkg })


@router.post("/icons")
async def upload_icon(icon: UploadFile):

	await utility.save_icon(icon)
	return { "result":  "Successfully uploaded icon", "filename": icon.filename }
