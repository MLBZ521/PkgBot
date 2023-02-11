import json

from fastapi import APIRouter, Depends, HTTPException, Response, Request, status

from pkgbot import core, config, settings
from pkgbot.utilities import common as utility


config = config.load_config()
log = utility.log

router = APIRouter(
	prefix = "/slackbot",
	tags = ["slackbot"],
	responses = settings.api.custom_responses
)


@router.delete("/delete/{ts}", summary="Delete Slack message by timestamp",
	description="Delete a Slack message by its timestamp.",
	dependencies=[Depends(core.user.verify_admin)])
async def delete_slack_message(timestamps: str | list, channel: str | None = None):

	return await core.chatbot.delete_messages(timestamps, channel)


@router.post("/receive", summary="Handles incoming messages from Slack",
	description="This endpoint receives incoming messages from Slack and performs the required "
		"actions based on the message after verifying the authenticity of the source.")
async def receive(request: Request):

	if not await core.chatbot.validate_request(request):
		log.warning("PkgBot received an invalid request!")
		return HTTPException(
			status_code=status.HTTP_511_NETWORK_AUTHENTICATION_REQUIRED,
			detail="Failed to authenticate request."
		)

	form_data = await request.form()
	payload = form_data.get("payload")
	payload_object = json.loads(payload)
	payload_type = payload_object.get("type")
	# log.debug(f"Received Payload Type:  {payload_type}")

	match payload_type:

		case "block_actions":
			if payload_object.get("actions")[0].get("type") == "button":
				await core.chatbot.events.button_click(payload_object)

		case "block_suggestion":
			return await core.chatbot.events.external_lists(payload_object)

		case "message_action":
			await core.chatbot.events.message_shortcut(payload_object)

		case "view_submission":
			await core.chatbot.events.view_submission(payload_object)

	return Response(status_code=status.HTTP_200_OK)


@router.post("/slashcmd", summary="Handles incoming slash commands from Slack",
	description="This endpoint receives incoming slash commands from Slack and performs the "
		"required actions based on the message after verifying the authenticity of the source.")
async def slashcmd(request: Request):

	if not await core.chatbot.bot.validate_request(request):
		log.warning("PkgBot received an invalid request!")
		return HTTPException(
			status_code=status.HTTP_511_NETWORK_AUTHENTICATION_REQUIRED,
			detail="Failed to authenticate request."
		)

	await core.chatbot.events.slash_cmd(await request.form())
	return Response(status_code=status.HTTP_200_OK)
