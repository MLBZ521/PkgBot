import os
import shutil

from datetime import datetime

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from pkgbot import api, config, core


config = config.load_config()

router = APIRouter(
	tags = ["view"],
	include_in_schema = False
)


def template_filter_datetime(date, date_format="%Y-%m-%d %I:%M:%S"):

	if date:
		converted = datetime.fromisoformat(str(date))
		return converted.strftime(date_format)


session = { "logged_in": False }
templates = Jinja2Templates(directory=config.PkgBot.get("jinja_templates"))
templates.env.filters["strftime"] = template_filter_datetime


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):

	session["logged_in"] = bool(request.state.user)
	return templates.TemplateResponse("index.html", { "request": request, "session": session })


# @router.get("/login", response_class=HTMLResponse)
# async def userlogin(request: Request):

#	return templates.TemplateResponse("login.html", { "request": request, "session": session })


@router.get("/packages", response_class=HTMLResponse,
	dependencies=[Depends(api.auth.login_manager)])
async def package_history(request: Request):

	session["logged_in"] = True
	packages = await core.package.get()

	table_headers = [
		"", "", "Name", "Version", "Status", "Updated By",
		"Packaged", "Promoted", "Flags", "Notes"
	]

	return templates.TemplateResponse("packages.html",
		{ "request": request, "session": session,
			"table_headers": table_headers, "packages": packages })


@router.get("/package/{id}", response_class=HTMLResponse,
	dependencies=[Depends(api.auth.login_manager)])
async def get_package(request: Request):

	session["logged_in"] = True
	pkg = await core.package.get({"id": request.path_params['id']})

	return templates.TemplateResponse("package.html",
		{ "request": request, "session": session, "package": pkg })


@router.get("/edit/{id}", response_class=HTMLResponse,
	dependencies=[Depends(api.auth.login_manager)])
async def edit(request: Request):

	pkg = await core.package.get({"id": request.path_params['id']})

	return templates.TemplateResponse("edit.html",
		{ "request": request, "session": session, "package": pkg })


@router.get("/recipes", response_class=HTMLResponse,
	dependencies=[Depends(api.auth.login_manager)])
async def recipe_list(request: Request):

	session["logged_in"] = True
	recipes = await core.recipe.get()

	table_headers = [ "ID", "Recipe ID", "Enable", "Manual Only",
		"Pkg Only", "Last Ran", "Schedule", "Status", "Notes" ]

	return templates.TemplateResponse("recipes.html",
		{ "request": request, "session": session,
			"table_headers": table_headers, "recipes": recipes })


@router.get("/recipe/{id}", response_class=HTMLResponse,
	dependencies=[Depends(api.auth.login_manager)])
async def get_recipe(request: Request):

	session["logged_in"] = True
	pkg = await core.recipe.get({"id": request.path_params['id']})

	return templates.TemplateResponse("recipe.html",
		{ "request": request, "session": session, "recipe": pkg })


@router.post("/icons", dependencies=[Depends(api.auth.login_manager)])
async def upload_icon(icon: UploadFile):

	pkg_dir = os.path.abspath(os.path.join(os.path.abspath(os.path.dirname(__file__)), os.pardir))

	try:
		with open(f"{pkg_dir}/static/icons/{icon.filename}", "wb") as icon_obj:
			shutil.copyfileobj(icon.file, icon_obj)
	finally:
		await icon.close()

	return { "results":  200, "icon": icon.filename }
