import os
from datetime import datetime, timedelta

import httpx

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi_login import LoginManager
from fastapi_login.exceptions import InvalidCredentialsException

from pkgbot import config, settings
from pkgbot.api import user
from pkgbot.db import models
from pkgbot.utilities import common as utility


config = config.load_config()
log = utility.log
LOGIN_SECRET = os.urandom(1024).hex()

jps_url = config.JamfPro_Prod.get("jps_url")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")
login_manager = LoginManager(LOGIN_SECRET, token_url="/auth/login", use_cookie=True)
login_manager.cookie_name = "PkgBot_Cookie"
templates = Jinja2Templates(directory=config.PkgBot.get("jinja_templates"))

router = APIRouter(
	prefix = "/auth",
	tags = ["auth"],
	responses = settings.api.custom_responses
)


class NotAuthenticatedException(Exception):
	pass


login_manager.not_authenticated_exception = NotAuthenticatedException


async def exc_handler(request, exc):
	session = { "logged_in": False, "protected_page": True }
	return templates.TemplateResponse("index.html", { "request": request, "session": session })


async def authenticate_user(username: str, password: str):

	# Request a token based on the provided credentials
	async with httpx.AsyncClient() as client:
		response_get_token = await client.post(
			f"{jps_url}/api/v1/auth/token", auth=(username, password))

	if response_get_token.status_code == 200:

		response_json = response_get_token.json()
		sites = await user_authorizations( response_json["token"] )

		user_model = models.PkgBotAdmin_In(
			username = username,
		)

		user_exists = await user.get_user( user_model )

		if len(user_exists) <= 1:

			user_details = models.PkgBotAdmin_In(
				username = username,
				full_admin = user_exists[0].full_admin if user_exists else False,
				jps_token = response_json["token"],
				jps_token_expires = await utility.string_to_datetime(
					response_json["expires"], "%Y-%m-%dT%H:%M:%S.%fZ"),
				site_access = ', '.join(sites)
			)

			return await user.create_or_update_user(user_details)

	return False


async def user_authorizations(token: str = Depends(oauth2_scheme)):

	# Get all user details
	async with httpx.AsyncClient() as client:
		response_user_details = await client.get(
			f"{jps_url}/api/v1/auth", headers={ "Authorization": f"jamf-token {token}" })

	# Get the response content from the API
	user_details = response_user_details.json()

	try:

		site_ids = []
		site_names = []

		for group in user_details["accountGroups"]:
			for privilege in group["privileges"]:
				if privilege == "Enroll Computers and Mobile Devices":
					site_ids.append(group["siteId"])

		for site in user_details["sites"]:
			if int(site["id"]) in site_ids:
				site_names.append(site["name"])

	except Exception:
		pass

	return site_names


@login_manager.user_loader()
async def load_user(username: str):
##### This can be improved ^^^
	user_model = models.PkgBotAdmin_In(username = username,)
	user_object = await user.get_user(user_model)

	# Return the user object otherwise None if a user was not found
	return user_object or None


@router.post("/login", summary="Login to web views",
	description="Handles authentication on web views.")
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):

	user = await authenticate_user( form_data.username, form_data.password )

	if not user:
		session = { "logged_in": False }
		return templates.TemplateResponse("index.html", { "request": request, "session": session })

	access_token = login_manager.create_access_token(
		data = { "sub": form_data.username }, expires = timedelta(minutes=config.PkgBot.get("token_valid_for")))

	response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
	login_manager.set_cookie(response, access_token)

	return response


@router.post("/logout", summary="Logout of web views",
	description="Handles logging out of web views.")
async def logout(response: HTMLResponse):

	response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
	response.delete_cookie(key=login_manager.cookie_name)
	return response


@router.post("/token", summary="Request a JWT",
	description="Handles acquiring a JSON Web Token for use with the PkgBot API.")
async def create_token(form_data: OAuth2PasswordRequestForm = Depends()):

	user = await authenticate_user( form_data.username, form_data.password )

	if not user:

		raise HTTPException(
			status_code = status.HTTP_401_UNAUTHORIZED,
			detail = "Invalid credentials or not a Site Admin"
		)

	return { "access_token": user.jps_token, "token_type": "bearer" }


# @router.get("/test", summary="Return user's JWT",
#     description="Test endpoint to return the current user's token.")
# async def test(user: models.PkgBotAdmin_In = Depends(user.get_current_user)):

#     return { "token": user.jps_token }


@router.get("/authorizations", summary="Check user permissions",
	description="Returns the authenticated user's permissions (e.g. Site access).")
async def authorizations(user: models.PkgBotAdmin_In = Depends(user.get_current_user)):

	sites = await user_authorizations( user.jps_token )

	return { "sites": sites }
