from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordBearer

from pkgbot import settings
from pkgbot.db import models
from pkgbot.utilities import common as utility


log = utility.log
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")
router = APIRouter(
	prefix = "/user",
	tags = ["user"],
	responses = settings.api.custom_responses
)


async def create_or_update_user(user: models.PkgBotAdmin_In):

	user_dict = { **user.dict(exclude_unset=True, exclude_none=True, exclude={"username"}) }

	result, result_bool = await models.PkgBotAdmins.update_or_create(
		user_dict, username=user.username)

	return await models.PkgBotAdmin_Out.from_tortoise_orm(result)


async def get_user(user: models.PkgBotAdmin_In):

	return await models.PkgBotAdmins.filter(**user.dict(exclude_unset=True, exclude_none=True)).first()


async def get_current_user(token: str = Depends(oauth2_scheme)):

	try:
		return await models.PkgBotAdmins.get(jps_token = token)

	except:
		raise HTTPException(
			status_code = status.HTTP_401_UNAUTHORIZED,
			detail = "You must authenticate before utilizing this endpoint."
		)


async def verify_admin(response: Response,
	user: models.PkgBotAdmin_In = Depends(get_current_user)):

	if not user.full_admin:
		log.debug("User is NOT an admin")
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
			detail="You are not authorized to utilize this endpoint.")

	# log.debug("User is an admin")


@router.get("s/", summary="Get all users", description="Get all users in the database.",
	dependencies=[Depends(verify_admin)])
async def get_users():

	users = await models.PkgBotAdmin_Out.from_queryset(models.PkgBotAdmins.all())

	return { "total": len(users), "users": users }


@router.post("/create", summary="Create a user", description="Creates a new PkgBot user.",
	dependencies=[Depends(verify_admin)], response_model=models.PkgBotAdmin_Out,
	response_model_exclude={ "slack_id", "jps_token" }, response_model_exclude_unset=True)
async def create_user(response: Response,
	user: models.PkgBotAdmin_In = Depends(models.PkgBotAdmin_In)):

	if await get_user(user):
		raise HTTPException(status_code=status.HTTP_409_CONFLICT,
			detail=f"The user `{user.username}` already exists.")

	return await create_or_update_user(user)


@router.put("/update", summary="Update a user", description="Updates an existing PkgBot user.",
	dependencies=[Depends(verify_admin)], response_model=models.PkgBotAdmin_Out,
	response_model_exclude={ "slack_id", "jps_token" }, response_model_exclude_unset=True)
async def update_user(response: Response,
	user: models.PkgBotAdmin_In = Depends(models.PkgBotAdmin_In)):

	return await create_or_update_user(user)


@router.get("/whoami", summary="Get user's info",
	description="Get the currently authenticated users information.",
	dependencies=[Depends(get_current_user)], response_model=models.PkgBotAdmin_Out)
async def whoami(user: models.PkgBotAdmin_In = Depends(get_current_user)):

	return user
