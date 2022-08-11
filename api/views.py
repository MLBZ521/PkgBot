import asyncio
import functools
import time

from datetime import datetime
from typing import Callable

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import config, utilities.common as utility

from api import auth
from api import package as package_api
from api import recipe as recipe_api


log = utility.log
config.load()


def template_filter_datetime(date, date_format=None):

	if date:

		if not date_format:
			date_format = "%Y-%m-%d %I:%M:%S"

		converted = datetime.fromisoformat(str(date))

		return converted.strftime(date_format)


session = { "logged_in": False }
templates = Jinja2Templates(directory=config.pkgbot_config.get("PkgBot.jinja_templates"))
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

#     return templates.TemplateResponse("login.html", { "request": request, "session": session })


@router.get("/packages", response_class=HTMLResponse)
async def package_history(request: Request, user = Depends(auth.login_manager)):

	session["logged_in"] = True

	pkgs = await package_api.get_packages()

	table_headers = [
		"", "", "Name", "Version", "Status", "Updated By",
		"Packaged", "Promoted", "COMMON", "Flags", "Notes"
	]

	return templates.TemplateResponse("packages.html",
		{ "request": request, "session": session,
			"table_headers": table_headers, "packages": pkgs.get("packages") })


@router.get("/package/{id}", response_class=HTMLResponse)
async def package(request: Request, user = Depends(auth.login_manager)):

	session["logged_in"] = True

	pkg = await package_api.get_package_by_id(request.path_params['id'])

	return templates.TemplateResponse("package.html",
		{ "request": request, "session": session, "package": pkg })


@router.get("/edit/{id}", response_class=HTMLResponse)
async def edit(request: Request, user = Depends(auth.login_manager)):

	pkg = await package_api.get_package_by_id(request.path_params['id'])

	return templates.TemplateResponse("edit.html",
		{ "request": request, "session": session, "package": pkg })


@router.get("/recipes", response_class=HTMLResponse)
async def recipe_list(request: Request, user = Depends(auth.login_manager)):

	session["logged_in"] = True

	pkgs = await recipe_api.get_recipes()

	table_headers = [
		"ID", "Recipe ID", "Name", "Enable", "Pkg Only", "Last Ran", "Schedule",  "Notes"
	]

	return templates.TemplateResponse("recipes.html",
		{ "request": request, "session": session,
			"table_headers": table_headers, "recipes": pkgs.get("recipes") })


@router.get("/recipe/{id}", response_class=HTMLResponse)
async def recipe_page(request: Request, user = Depends(auth.login_manager)):

	session["logged_in"] = True

	pkg = await recipe_api.get_by_id(request.path_params['id'])

	return templates.TemplateResponse("recipe.html",
		{ "request": request, "session": session, "recipe": pkg })
