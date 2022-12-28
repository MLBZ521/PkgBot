import os
import shutil

from datetime import datetime

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from pkgbot import config
from pkgbot.utilities import common as utility
from pkgbot.api import auth, package, recipe


log = utility.log
config = config.load_config()


def template_filter_datetime(date, date_format="%Y-%m-%d %I:%M:%S"):

	if date:
		converted = datetime.fromisoformat(str(date))
		return converted.strftime(date_format)


session = { "logged_in": False }
templates = Jinja2Templates(directory=config.PkgBot.get("jinja_templates"))
templates.env.filters["strftime"] = template_filter_datetime
router = APIRouter(
	tags = ["view"],
	include_in_schema = False
)


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):

	if request.state.user:
		session["logged_in"] = True
	else:
		session["logged_in"] = False

	return templates.TemplateResponse("index.html", { "request": request, "session": session })


# @router.get("/login", response_class=HTMLResponse)
# async def userlogin(request: Request):

#	return templates.TemplateResponse("login.html", { "request": request, "session": session })


@router.get("/packages", response_class=HTMLResponse)
async def package_history(request: Request, user = Depends(auth.login_manager)):

	session["logged_in"] = True
	pkgs = await package.get_packages()

	table_headers = [
		"", "", "Name", "Version", "Status", "Updated By",
		"Packaged", "Promoted", "Flags", "Notes"
	]

	return templates.TemplateResponse("packages.html",
		{ "request": request, "session": session,
			"table_headers": table_headers, "packages": pkgs.get("packages") })


@router.get("/package/{id}", response_class=HTMLResponse)
async def get_package(request: Request, user = Depends(auth.login_manager)):

	session["logged_in"] = True
	pkg = await package.get_package_by_id(request.path_params['id'])

	return templates.TemplateResponse("package.html",
		{ "request": request, "session": session, "package": pkg })


@router.get("/edit/{id}", response_class=HTMLResponse)
async def edit(request: Request, user = Depends(auth.login_manager)):

	pkg = await package.get_package_by_id(request.path_params['id'])

	return templates.TemplateResponse("edit.html",
		{ "request": request, "session": session, "package": pkg })


@router.get("/recipes", response_class=HTMLResponse)
async def recipe_list(request: Request, user = Depends(auth.login_manager)):

	session["logged_in"] = True
	pkgs = await recipe.get_recipes()

	table_headers = [ "ID", "Recipe ID", "Name", "Enable", "Manual Only", 
		"Pkg Only", "Last Ran", "Schedule",  "Notes" ]

	return templates.TemplateResponse("recipes.html",
		{ "request": request, "session": session,
			"table_headers": table_headers, "recipes": pkgs.get("recipes") })


@router.get("/recipe/{id}", response_class=HTMLResponse)
async def get_recipe(request: Request, user = Depends(auth.login_manager)):

	session["logged_in"] = True
	pkg = await recipe.get_by_id(request.path_params['id'])

	return templates.TemplateResponse("recipe.html",
		{ "request": request, "session": session, "recipe": pkg })


@router.post("/icons")
async def upload_icon(icon: UploadFile, user = Depends(auth.login_manager)):

	pkg_dir = os.path.abspath(os.path.join(os.path.abspath(os.path.dirname(__file__)), os.pardir))

	try:
		with open(f"{pkg_dir}/static/icons/{icon.filename}", "wb") as icon_obj:
			shutil.copyfileobj(icon.file, icon_obj)
	finally:
		await icon.close()

	return { "results":  200, "icon": icon.filename }
