from fastapi import APIRouter, Body, Depends, HTTPException, Response, Request, status

from pkgbot import api, config, core, settings
from pkgbot.db import schemas
from pkgbot.utilities import common as utility


config = config.load_config()
log = utility.log
router = APIRouter(
	prefix = "/tasks",
	tags = ["tasks"],
	responses = settings.api.custom_responses
)


@router.get("/results/{task_id}", summary="Get the results of an autopkg task",
	description="Check if a task has completed and it's results.",
	dependencies=[Depends(core.user.get_current)])
async def results(task_id:  str):

	return await utility.get_task_results(task_id)


@router.post("/receive", summary="Handles incoming task messages with autopkg results",
	description="This endpoint receives incoming messages from tasks and calls the required "
		"actions based on the message after verifying the authenticity of the source.")
async def receive(request: Request, task_id = Body()):

##### TODO:
	# To prevent memory allocation attacks
	# if content_length > 1_000_000:
	# 	log.error(f"Content too long ({content_length})")
	# 	response.status_code = 400
	# 	return {"result": "Content too long"}

	if not await api.verify_pkgbot_webhook(request):
		return HTTPException(
			status_code=status.HTTP_511_NETWORK_AUTHENTICATION_REQUIRED,
			detail="Failed to authenticate webhook."
		)

	task_id = task_id.get("task_id")
	log.debug(f"Receiving notification for task_id:  {task_id}")
	await core.events.event_handler(task_id)
	return Response(status_code=status.HTTP_200_OK)


@router.get("/cache_policies", summary="Adhoc cache policies from Jamf Pro",
	description="Force an adhoc cache of Jamf Pro Policies.",
	dependencies=[Depends(core.user.verify_admin)], response_model=dict)
async def cache_policies(user_object: schemas.PkgBotAdmin_In = Depends(core.user.get_current)):

	queued_task = await core.policy.cache_policies(source="API", called_by=user_object.username)
	return {
		"result": "Caching Policies.  See queued background task id for status.",
		"task_id": queued_task.id
	}
