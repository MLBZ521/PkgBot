from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordBearer

from pkgbot import core, settings
from pkgbot.db import models, schemas
from pkgbot.utilities import common as utility


log = utility.log
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")
router = APIRouter(
	prefix = "/user",
	tags = ["user"],
	responses = settings.api.custom_responses
)


@router.get("s/", summary="Get all users", description="Get all users in the database.",
	dependencies=[Depends(core.user.verify_admin)])
async def get_users():

	users = await core.user.get()
	return { "total": len(users), "users": users }


@router.post("/create", summary="Create a user", description="Creates a new PkgBot user.",
	dependencies=[Depends(core.user.verify_admin)], response_model=schemas.PkgBotAdmin_Out,
	response_model_exclude={ "slack_id", "jps_token" }, response_model_exclude_unset=True)
async def create_user(user_object: schemas.PkgBotAdmin_In = Depends(schemas.PkgBotAdmin_In)):

	if await core.user.get(user_object.dict()):
		raise HTTPException(status_code=status.HTTP_409_CONFLICT,
			detail=f"The user `{user_object.username}` already exists.")

	return await core.user.create_or_update(user_object)


@router.put("/update", summary="Update a user", description="Updates an existing PkgBot user.",
	dependencies=[Depends(core.user.verify_admin)], response_model=schemas.PkgBotAdmin_Out,
	response_model_exclude={ "slack_id", "jps_token" }, response_model_exclude_unset=True)
async def update_user(user_object: schemas.PkgBotAdmin_In = Depends(schemas.PkgBotAdmin_In)):

	return await core.user.create_or_update(user_object)


@router.get("/whoami", summary="Get user's info",
	description="Get the currently authenticated users information.",
	response_model=schemas.PkgBotAdmin_Out)
async def whoami(user_object: schemas.PkgBotAdmin_In = Depends(core.user.get_current)):

	return user_object
