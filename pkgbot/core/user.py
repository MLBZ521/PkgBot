from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer

from pkgbot import core, config, settings
from pkgbot.db import models, schemas
from pkgbot.utilities import common as utility


log = utility.log
config = config.load_config()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


async def get(user_filter: dict | None = None):

	if not user_filter:
		return await models.PkgBotAdmins.all()

	results = await schemas.PkgBotAdmin_Out.from_queryset(models.PkgBotAdmins.filter(**user_filter))
	return results[0] if len(results) == 1 else results


async def create_or_update(user_object: schemas.PkgBotAdmin_In):

	result, result_bool = await models.PkgBotAdmins.update_or_create(
		user_object.dict(exclude_unset=True, exclude_none=True, exclude={"username"}),
		username=user_object.username
	)

	return result


async def get_current(token: str = Depends(oauth2_scheme)):
	"""Get current user from it's jps_token.

	Args:
		token (str): The users' jps_token. Defaults to Depends(oauth2_scheme).

	Raises:
		HTTPException: If the user doesn't exist in the database.

	Returns:
		models.PkgBotAdmins: User object for the the current user.
	"""

	try:
		if user := await get({ "jps_token": token }):
			return user

		raise HTTPException(status_code = status.HTTP_401_UNAUTHORIZED,
			detail = "You must authenticate before utilizing this endpoint.")

	except HTTPException as error:
		raise error


async def get_current_user_from_cookie(request: Request):
	"""Get the current user from the cookies in the request.

	This function can be used from inside other routes to get the current user. Allowing it to be
	used for views that should work for both logged in, and not logged in users.


	Args:
		request (Request): Request (from FastAPI/Starlette)

	Returns:
		models.PkgBotAdmins | None: User object for the the current user, or None.
	"""

	token = request.cookies.get(settings.api.PkgBot_Cookie)
	return await get({ "pkgbot_token": token })


async def verify_admin(request: Request,
	user_object: schemas.PkgBotAdmin_In = Depends(get_current)):

	if ( request.state.user and request.state.user.get("full_admin") ) \
		or ( user_object and user_object.dict().get("full_admin") ):
		log.debug("User is an admin")
		return
	
	log.debug("User is NOT an admin")
	raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
		detail="You are not authorized to utilize this endpoint.")


async def authenticate(username: str, password: str):

	# Request a token with the provided credentials
	api_token, api_token_expires = await core.jamf_pro.get_token(username, password)

	if api_token:

		sites = await authorizations(api_token)
		user_already_exists = await get({"username": username})

		return await create_or_update(
			schemas.PkgBotAdmin_In(
				username = username,
				full_admin = user_already_exists.full_admin if user_already_exists else False,
				jps_token = api_token,
				jps_token_expires = api_token_expires,
				site_access = ', '.join(sites)
			)
		)

	return False


async def authorizations(token: str = Depends(oauth2_scheme)):

	# Get user details
	user_details_response = await core.jamf_pro.api("get", "api/v1/auth", api_token=token)

	if user_details_response.status_code != 200:
		raise("Failed to get user authorizations!")

	user_details = user_details_response.json()

	sites_unauthorized = config.JamfPro_Prod.get("unauthorized_sites")

	try:
		return [
			site["name"]
			for site in user_details["sites"]
			if site["name"] not in sites_unauthorized
		]

	except Exception:
		return
