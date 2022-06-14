#!/usr/local/autopkg/python

import hmac
import json
import ssl
import time
import certifi

from fastapi import APIRouter, BackgroundTasks, Request

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.webhook.async_client import AsyncWebhookClient

import config, utils
from db import models
from api import autopkg, package, recipe, settings, user
from api.slack import build_msg


config.load()
log = utils.log

SlackBot = None
ssl_context = ssl.create_default_context(cafile=certifi.where())
router = APIRouter(
	prefix = "/slackbot",
	tags = ["slackbot"],
	responses = settings.custom_responses
)


class SlackClient(object):

	def __init__(self, **kwargs):
		self.token = kwargs["token"]
		self.bot_name = kwargs["bot_name"]
		self.channel = kwargs["channel"]
		self.slack_id = kwargs["slack_id"]

		self.client = AsyncWebClient(token=self.token, ssl=ssl_context)


	async def post_message(self, blocks, text="Pkg status incoming..."):

		try:
			response = await self.client.chat_postMessage(
				channel = self.channel,
				text = text,
				blocks = await utils.replace_sensitive_strings(blocks),
				username = self.bot_name,
				icon_emoji = ":x:"
			)

		except SlackApiError as error:
			log.error("Slack encountered an error:  {}".format(error.response["error"]))
			raise error from error

		return response


	async def update_message(self, blocks, ts, text="Updated message..."):

		try:
			response = await self.client.chat_update(
				channel = self.channel,
				text = text,
				blocks = await utils.replace_sensitive_strings(blocks),
				ts = str(ts)
				# username = self.bot_name,
				# icon_emoji = ":x:"
			)

		except SlackApiError as error:
			log.error("Slack encountered an error:  {}".format(error.response["error"]))
			raise error from error

		return response


	async def delete_message(self, ts):

		try:
			await self.client.chat_delete(
				channel = self.channel,
				ts = str(ts)
			)

			return { "Result":  "Successfully deleted message" }

		except SlackApiError as error:
			log.error("Slack encountered an error:  {}".format(error.response["error"]))
			return error


	async def update_message_with_response_url(self, response_url, blocks, text="Pkg status update..."):

		try:
			webhook = AsyncWebhookClient(url=response_url, ssl=ssl_context)
			response = await webhook.send(
				text = text,
				blocks = await utils.replace_sensitive_strings(blocks),
				replace_original = True
			)

			if response.status_code != 200:
				log.error("Failed to update message! Status code:  {} | Error message:  {}".format(response.status_code, response.body))

			else:
				log.debug("Successfully updated msg via response_url")

			return response

		except SlackApiError as error:
			log.error("Slack encountered an error:  {}".format(error))
			log.error("Slack encountered an error.dir:  {}".format(dir(error)))
			log.error("Slack encountered an error.response['error']:  {}".format(error.response["error"]))
			raise error from error


	async def post_ephemeral_message(self, user, blocks, channel, text="Private Note"):

		try:
			response = await self.client.chat_postEphemeral(
				channel = self.channel,
				user = user,
				text = text,
				blocks = await utils.replace_sensitive_strings(blocks),
				username = self.bot_name,
				icon_emoji = ":x:"
			)

		except SlackApiError as error:
			log.error("Slack encountered an error:  {}".format(error.response["error"]))
			raise error from error

		return response


	async def file_upload(self, content=None, file=None, filename=None, filetype=None,
		title=None, text=None, thread_ts=None):

		try:
			response = await self.client.files_upload(
				channels = self.channel,
				content = content,
				file = file,
				filename = filename,
				filetype = filetype,
				title = title,
				initial_comment = await utils.replace_sensitive_strings(text),
				thread_ts = thread_ts,
				username = self.bot_name
			)

		except SlackApiError as error:
			log.error("Slack encountered an error:  {}".format(error.response["error"]))
			raise error from error

		return response


	async def invoke_reaction(self, **kwargs):

		kwargs.update(
			{
				"channel": kwargs.get("channel", self.channel),
				"timestamp": str(kwargs.get("ts"))
			}
		)

		if "ts" in kwargs:
			del kwargs["ts"]

		try:
			return await self.client.api_call(
				"reactions.{}".format(kwargs.get("action")),
				params = kwargs
			)

		except SlackApiError as error:
			error_key = error.response["error"]

			if not (
				kwargs.get("action") == "add" and error_key == "already_reacted" or
				kwargs.get("action") == "remove" and error_key == "no_reaction"
			):
				log.error("Slack encountered an error:  {}".format(error_key))
				raise error from error

			else:
				log.debug("Unable to perform the specified reaction action")


	async def reaction(self, action=None, emoji=None, ts=None, **kwargs):

		# log.debug("Args:\n\taction:  {}\n\temoji:  {}\n\tts:  {}\n\tkwargs:  {}".format(
		# 	action, emoji, ts, kwargs))

		# log.debug("Checking current reactions")

		# Force checking if this works or not.....
		# It's not....
		# response = await self.client.api_call(
		# 	"reactions.get",
		# 	http_verb = "GET",
		# 	params = {
		# 		'channel': 'C0266ANUEJZ',
		# 		'timestamp': '1646121180.754269'
		# 	}
		# )

##### This is currently not working....
		# # Check if reaction exists or not...
		# response = await self.invoke_reaction(action="get", ts=ts, http_verb="GET")
		# # log.debug("forced get response:\n{}".format(response))
		# reactions = response.get("message").get("reactions")

		# for reaction in reactions:
			# if (
			# 	reaction.get("name") == kwargs.get("emoji") and
			# 	elf.slack_id in reaction.get("users")
			# ):
		# 		log.debug("Reaction already exists")
		# 		exists = True
		# 		break

		# 	log.debug("Reaction doesn't exist")
		# 	exists = False

		# if (
		# 	action == "add" and exists == False or
		# 	action == "remove" and exists == True
		# ):

		return await self.invoke_reaction(action=action, name=emoji, ts=ts, **kwargs)


async def verify_slack_request(request: Request):

	try:
		slack_timestamp = request.headers.get("X-Slack-Request-Timestamp")

		if abs(time.time() - int(slack_timestamp)) > 60 * 5:
			# The request timestamp is more than five minutes from local time.
			# It could be a replay attack, so let's ignore it.
			return False

		slack_body = (await request.body()).decode("UTF-8")
		signature_basestring = ("v0:{}:{}".format(slack_timestamp, slack_body)).encode()

		computed_signature = "v0=" + await utils.compute_hex_digest(
			bytes(config.pkgbot_config.get("Slack.signing_secret"), "UTF-8"),
			signature_basestring)

		slack_signature = request.headers.get("X-Slack-Signature")

		if hmac.compare_digest(computed_signature, slack_signature):
			log.debug("Valid Slack message")
			return True

		else:
			log.warning("Invalid Slack message!")
			return False

	except:

		return False


@router.on_event("startup")
async def startup_constructor():

	global SlackBot

	SlackBot = SlackClient(
		token = config.pkgbot_config.get("Slack.bot_token"),
		bot_name = config.pkgbot_config.get("Slack.bot_name"),
		channel = config.pkgbot_config.get("Slack.channel"),
		slack_id = config.pkgbot_config.get("Slack.slack_id")
	)


@router.post("/receive", summary="Handles incoming messages from Slack",
	description="This endpoint receives incoming messages from Slack and calls the required "
		"actions based on the message after verify the authenticity of the source.")
async def receive(request: Request, background_tasks: BackgroundTasks):

	valid_request = await verify_slack_request(request)

	if valid_request:

		form_data = await request.form()
		payload = form_data.get("payload")
		payload_object = json.loads(payload)

		user_id = payload_object.get("user").get("id")
		username = payload_object.get("user").get("username")
		channel = payload_object.get("channel").get("id")
		message_ts = payload_object.get("message").get("ts")
		response_url = payload_object.get("response_url")

		button_text = payload_object.get("actions")[0].get("text").get("text")
		button_value_type, button_value = (
			payload_object.get("actions")[0].get("value")).split(":")

		log.debug("Incoming details:\n"
			"user id:  {}\nusername:  {}\nchannel:  {}\nmessage_ts:  {}\nresponse_url:  {}\nbutton_text:  "
			"{}\nbutton_value_type:  {}\nbutton_value:  {}\n".format(
			user_id, username, channel, message_ts, response_url, button_text, button_value_type, button_value))

		slack_user_object = models.PkgBotAdmin_In(
			username = username,
			slack_id = user_id
		)

		user_that_clicked = await user.get_user(slack_user_object)

		# try:

		# 	if user_that_clicked.full_admin:
		# 		full_admin = True

		# except:
		# 		full_admin = False

		# Verify click was from a PkgBotAdmin...
		if user_that_clicked:

			# Perform action only if from a PkgBotAdmin
			log.debug("PkgBotAdmin clicked button:")

			if button_text == "Approve":
				log.debug("  -> APPROVE")

				if button_value_type == "Package":
					log.debug("  --> Promoting Package")
					await package.update(button_value,
						{ "response_url": response_url, "status_updated_by": username })

					background_tasks.add_task( autopkg.promote_package, background_tasks, button_value )
##### Testing this function -- can be removed
					# await SlackBot.reaction(
					# 	action = "remove",
					# 	emoji = "gear",
					# 	ts = message_ts
					# )

				elif button_value_type == "Trust":
					log.debug("  --> Updating Trust Info")

					error_object = await models.ErrorMessages.filter(id=button_value).first()

					updates = { "response_url": response_url, "status_updated_by": username, "slack_ts": message_ts }

					await models.ErrorMessages.update_or_create(updates, id=error_object.id)

					background_tasks.add_task( recipe.trust_recipe, button_value, background_tasks, user_id=user_id, channel=channel )

			elif button_text == "Deny":
				log.debug("  -> DENY")

				if button_value_type == "Package":
					log.debug("  --> Denying Package")

					await package.update( button_value,
						{ "response_url": response_url,
						"status_updated_by": username,
						"status": "Denied",
						"notes":  "This package was not approved for use in production." }
					)

					background_tasks.add_task( autopkg.deny_package,
						background_tasks, button_value )

				if button_value_type == "Trust":
					log.debug("  --> Disapprove Trust Changes")

					error_object = await models.ErrorMessages.filter(id=button_value).first()

					updates = {
						"response_url": response_url,
						"status_updated_by": username,
						"status": "Denied"
					}

					await models.ErrorMessages.update_or_create(updates, id=error_object.id)
					await recipe.disapprove_changes(button_value)

			await SlackBot.reaction(
				action = "add",
				emoji = "gear",
				ts = message_ts
			)

		else:

			log.warning("Unauthorized user:  `{}` [{}].".format(username, user_id))
			blocks = await build_msg.unauthorized_msg(username)

			await SlackBot.post_ephemeral_message(user_id, blocks, channel=channel, text="WARNING:  Unauthorized access attempted")

		return { "results":  200 }

	else:

		log.warning("Invalid request")
		return { "results":  500 }
