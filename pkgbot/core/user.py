from fastapi import Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordBearer

from pkgbot import core
from pkgbot.db import models, schemas
from pkgbot.utilities import common as utility


log = utility.log
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
		return await get({ "jps_token": token })

	except:
		raise HTTPException(
			status_code = status.HTTP_401_UNAUTHORIZED,
			detail = "You must authenticate before utilizing this endpoint."
		)


async def verify_admin(response: Response,
	user_object: schemas.PkgBotAdmin_In = Depends(get_current)):

	if not user_object.full_admin:
		log.debug("User is NOT an admin")
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
			detail="You are not authorized to utilize this endpoint.")

	# log.debug("User is an admin")


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
				jps_token_expires = await utility.string_to_datetime(
					api_token_expires, "%Y-%m-%dT%H:%M:%S"),
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
	site_ids = []
	site_names = []

	try:

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
