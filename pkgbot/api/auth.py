import os
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi_login import LoginManager
from fastapi_login.exceptions import InvalidCredentialsException

from pkgbot import config, core, settings
from pkgbot.db import models
from pkgbot.utilities import common as utility


config = config.load_config()
log = utility.log
LOGIN_SECRET = os.urandom(1024).hex()
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


@login_manager.user_loader()
async def load_user(username: str):

	# Return the user object otherwise None if a user was not found
	return await core.user.get({"username": username}) or None


@router.post("/login", summary="Login to web views",
	description="Handles authentication on web views.")
async def login(
	request: Request, form_data: OAuth2PasswordRequestForm = Depends(OAuth2PasswordRequestForm)):

	user = await core.user.authenticate(form_data.username, form_data.password)

	if not user:
		log.debug("Invalid credentials or not a Jamf Pro Admin")
		return templates.TemplateResponse(
			"index.html",
			{
				"request": request,
				"session": {
					"access_denied": "You are not authorized to access this page!" ,
					"logged_in": False,
					"protected_page": True
				}
			}
		)

	access_token = login_manager.create_access_token(
		data = { "sub": form_data.username },
		expires = timedelta(minutes=config.PkgBot.get("token_valid_for"))
	)

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
async def create_token(form_data: OAuth2PasswordRequestForm = Depends(OAuth2PasswordRequestForm)):

	user_object = await core.user.authenticate(form_data.username, form_data.password)

	if not user_object:
		raise HTTPException(
			status_code = status.HTTP_401_UNAUTHORIZED,
			detail = "Invalid credentials or not a Site Admin"
		)

	return { "access_token": user_object.jps_token, "token_type": "bearer" }


# @router.get("/test", summary="Return user's JWT",
#     description="Test endpoint to return the current user's token.")
# async def test(user: models.PkgBotAdmin_In = Depends(user.get_current_user)):

#     return { "token": user.jps_token }


@router.get("/authorizations", summary="Check user permissions",
	description="Returns the authenticated user's permissions (e.g. Site access).")
async def authorizations(user_object: models.PkgBotAdmin_In = Depends(core.user.get_current)):

	return { "sites": await core.user.authorizations(user_object.jps_token) }
