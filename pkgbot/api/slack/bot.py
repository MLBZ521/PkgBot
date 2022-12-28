import certifi
import hmac
import json
import ssl
import time

from fastapi import APIRouter, Depends, HTTPException, Request

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.webhook.async_client import AsyncWebhookClient

from pkgbot import api, config, settings
from pkgbot.db import models
from pkgbot.utilities import common as utility


config = config.load_config()
log = utility.log

SlackBot = None
ssl_context = ssl.create_default_context(cafile=certifi.where())
router = APIRouter(
	prefix = "/slackbot",
	tags = ["slackbot"],
	responses = settings.api.custom_responses
)


class SlackClient(object):

	def __init__(self, **kwargs):
		self.token = kwargs["token"]
		self.bot_name = kwargs["bot_name"]
		self.channel = kwargs["channel"]
		self.slack_id = kwargs["slack_id"]

		self.client = AsyncWebClient(token=self.token, ssl=ssl_context)


	async def post_message(self, blocks: str, text: str = "Pkg status incoming..."):

		try:
			return await self.client.chat_postMessage(
				channel = self.channel,
				text = text,
				blocks = blocks,
				username = self.bot_name
			)

		except SlackApiError as error:
			log.error(f"Failed to post message:  {error.response['error']}\n{error}")
			return { "Failed to post message":  error.response["error"] }


	async def update_message(self, blocks: str, ts: str, text: str = "Updated message..."):

		try:
			return await self.client.chat_update(
				channel = self.channel,
				text = text,
				blocks = blocks,
				ts = ts
			)

		except SlackApiError as error:
			log.error(f"Failed to update {ts}:  {error.response['error']}\n{error}")
			return { f"Failed to update {ts}":  error.response["error"] }


	async def delete_message(self, ts: str):

		try:
			await self.client.chat_delete(channel=self.channel, ts=ts)
			return { "result":  "Successfully deleted message" }

		except SlackApiError as error:
			log.error(f"Failed to delete {ts}:  {error.response['error']}\n{error}")
			return { f"Failed to delete {ts}":  error.response["error"] }


	async def update_message_with_response_url(
		self, response_url: str, blocks: str, text: str = "Pkg status update..."):

		try:
			webhook = AsyncWebhookClient(url=response_url, ssl=ssl_context)
			response = await webhook.send(
				text = text,
				blocks = blocks,
				replace_original = True
			)

			if response.status_code != 200:
				log.error(
					f"Failed to update message! Status code:  {response.status_code} | Error message:  {response.body}")
			else:
				log.debug("Successfully updated msg via response_url")

			return response

		except SlackApiError as error:
			log.error(
				f"Failed to update {response_url}\nFull Error:\n{error}\nerror.dir:  {dir(error)}\nerror.response['error']:  {error.response['error']}")
			return { f"Failed to update {response_url}":  error.response["error"] }


	async def post_ephemeral_message(
		self, user: str, blocks: str, channel: str = None, text: str = "Private Note"):

		try:
			return await self.client.chat_postEphemeral(
				channel = channel or self.channel,
				user = user,
				text = text,
				blocks = blocks,
				username = self.bot_name
			)

		except SlackApiError as error:
			log.error(
				f"Failed to post ephemeral message:  {error.response['error']}\nFull Error:\n{error}")
			return { "Failed to post ephemeral message":  error.response["error"] }


	async def file_upload(self, content=None, file=None, filename=None, filetype=None,
		title=None, text=None, thread_ts=None):

		try:
			return await self.client.files_upload(
				channels = self.channel,
				content = content,
				file = file,
				filename = filename,
				filetype = filetype,
				title = title,
				initial_comment = text,
				thread_ts = thread_ts,
				username = self.bot_name
			)

		except SlackApiError as error:
			log.error(f"Failed to upload {file}:  {error.response['error']}\nFull Error:\n{error}")
			return { f"Failed to upload {file}":  error.response["error"] }


	async def invoke_reaction(self, **kwargs):

		kwargs |= {
			"channel": kwargs.get("channel", self.channel),
			"timestamp": str(kwargs.get("ts"))
		}

		if "ts" in kwargs:
			del kwargs["ts"]

		try:
			return await self.client.api_call(
				f"reactions.{kwargs.get('action')}",
				params = kwargs
			)

		except SlackApiError as error:
			error_key = error.response["error"]

			if not (
				kwargs.get("action") == "add" and error_key == "already_reacted" or
				kwargs.get("action") == "remove" and error_key == "no_reaction"
			):
				result = { f"Failed to invoke reaction on {kwargs.get('timestamp')}":  error_key }
				log.error(result)
				return result

			else:
				log.debug("Unable to perform the specified reaction action")


	async def reaction(self, action: str = None, emoji: str = None, ts: str = None, **kwargs):

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


async def validate_slack_request(request: Request):

	try:
		slack_timestamp = request.headers.get("X-Slack-Request-Timestamp")

		if abs(time.time() - int(slack_timestamp)) > 60 * 5:
			# The request timestamp is more than five minutes from local time.
			# It could be a replay attack, so let's ignore it.
			return False

		slack_body = (await request.body()).decode("UTF-8")
		signature_basestring = (f"v0:{slack_timestamp}:{slack_body}").encode()

		computed_signature = "v0=" + await utility.compute_hex_digest(
			bytes(config.Slack.get("signing_secret"), "UTF-8"),
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
		token = config.Slack.get("bot_token"),
		bot_name = config.Slack.get("bot_name"),
		channel = config.Slack.get("channel"),
		slack_id = config.Slack.get("slack_id")
	)


@router.delete("/ts/{ts}", summary="Delete Slack message by timestamp",
	description="Delete a Slack message by its timestamp.",
	dependencies=[Depends(api.user.verify_admin)])
async def delete_slack_message(timestamps: str | list):

	if isinstance(timestamps, str):
		timestamps = [timestamps]

	results = {}

	for ts in timestamps:
		result = await SlackBot.delete_message(str(ts))

		try:
			results[ts] = result.response['error']
		except Exception:
			results[ts] = "Successfully deleted message"

	return results


@router.post("/receive", summary="Handles incoming messages from Slack",
	description="This endpoint receives incoming messages from Slack and performs the required "
		"actions based on the message after verifying the authenticity of the source.")
async def receive(request: Request):

	if not await validate_slack_request(request):
		log.warning("PkgBot received an invalid request!")
		return { "result":  500 }

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

	# log.debug("Incoming details:\n"
	# 	f"user id:  {user_id}\nusername:  {username}\nchannel:  {channel}\nmessage_ts:  "
	# 	f"{message_ts}\nresponse_url:  {response_url}\nbutton_text:  {button_text}\n"
	# 	f"button_value_type:  {button_value_type}\nbutton_value:  {button_value}\n"
	# )

	slack_user_object = models.PkgBotAdmin_In(
		username = username,
		slack_id = user_id
	)

	user_that_clicked = await api.user.get_user(slack_user_object)

##### Disabled for testing
##### Actually don't think this is needed........
	# try:
	# 	if user_that_clicked.full_admin:
	# 		full_admin = True

	# except:
	# 		full_admin = False

	# Verify and perform action only if a PkgBotAdmin clicked the button
	if user_that_clicked: # and full_admin:

		await SlackBot.reaction(
			action = "add",
			emoji = "gear",
			ts = message_ts
		)

		if button_text == "Approve":

			if button_value_type == "Package":
				log.info(f"PkgBotAdmin `{username}` is promoting package id: {button_value}")

				await api.package.update(button_value,
					{ "response_url": response_url, "updated_by": username })
				await api.package.promote_package(button_value)

			elif button_value_type == "Trust":
				log.info(
					f"PkgBotAdmin `{username}` has approved updates for trust id: {button_value}")

				updates = {
					"response_url": response_url,
					"updated_by": username,
					"slack_ts": message_ts
				}

				trust_object = await models.TrustUpdates.filter(id=button_value).first()
				await models.TrustUpdates.update_or_create(updates, id=trust_object.id)
				await api.recipe.recipe_trust_update(trust_object)

		elif button_text == "Deny":

			if button_value_type == "Package":
				log.info(f"PkgBotAdmin `{username}` has denied package id: {button_value}")

				await api.package.update(button_value,
					{ "response_url": response_url,
						"updated_by": username,
						"status": "Denied",
						"notes":  "This package was not approved for use in production." }
				)
				await api.package.deny_package(button_value)

			if button_value_type == "Trust":
				log.info(
					f"PkgBotAdmin `{username}` has denied updates for trust id: {button_value}")

				updates = {
					"response_url": response_url,
					"updated_by": username,
					"status": "Denied"
				}

				trust_object = await models.TrustUpdates.filter(id=button_value).first()
				await models.TrustUpdates.update_or_create(updates, id=trust_object.id)
				await api.recipe.recipe_trust_deny(button_value)

		elif button_text == "Acknowledge":

			if button_value_type == "Error":

				log.info(
					f"PkgBotAdmin `{username}` has acknowledged error message: {message_ts}")
				await SlackBot.delete_message(str(message_ts))

				updates = {
					"response_url": response_url,
					"status": "Acknowledged",
					"ack_by": username
				}

				return await models.ErrorMessages.update_or_create(updates, slack_ts=message_ts)

	else:
		log.warning(f"Unauthorized user:  `{username}` [{user_id}].")

		blocks = await api.build_msg.unauthorized_msg(username)
		await SlackBot.post_ephemeral_message(
			user_id, blocks, channel=channel, text="WARNING:  Unauthorized access attempted")

	return { "result":  200 }


@router.post("/slashcmd", summary="Handles incoming slash commands from Slack",
	description="This endpoint receives incoming slash commands from Slack and performs the "
		"required actions based on the message after verifying the authenticity of the source.")
async def slashcmd(request: Request):

	if not await validate_slack_request(request):
		log.warning("PkgBot received an invalid request!")
		return { "result":  500 }

	form_data = await request.form()
	user_id = form_data.get("user_id")
	username = form_data.get("user_name")
	# channel = form_data.get("channel").get("id")
	command = form_data.get("command")
	cmd_text = form_data.get("text")
	response_url = form_data.get("response_url")

	slack_user_object = models.PkgBotAdmin_In(
		username = username,
		slack_id = user_id
	)

	user_that_clicked = await api.user.get_user(slack_user_object)

	log.debug("Incoming details:\n"
		f"user id:  {user_id}\nusername:  {username}\nfull admin:  {user_that_clicked.full_admin}"
		f"\ncommand:  {command}\ncmd_text:  {cmd_text}\nresponse_url:  {response_url}\n"
	)

##### TO DO:
	# Update below return statements to use an appropriate Slack message type
		# Current returns are simply place holders for verbosity and development work

	if not user_that_clicked.full_admin:
		return "Slash commands are in development and not available for public consumption at this time."

	verb, options = await utility.split_string(cmd_text)

	supported_options = {
		"pkgbot_admin": ["update-trust-info", "repo-add", "enable", "disable" ],
		"pkgbot_user": [ "run", "verify-trust-info", "version" ]
	}

	if not user_that_clicked.full_admin and verb not in supported_options.get("pkgbot_user"):
		return f"The autopkg verb {verb} is not supported by PkgBot users."
	elif (
		user_that_clicked.full_admin and
		verb not in supported_options.get("pkgbot_admin") + supported_options.get("pkgbot_user")
	):
		return f"The autopkg verb {verb} is not supported at this time by PkgBot."

	if " " not in options:
		recipe_id = options
		autopkg_options = models.AutoPkgCMD()
	else:
		recipe_id, cmd_options = await utility.split_string(options)

		try:
			options = await utility.parse_slash_cmd_options(cmd_options, verb)
		except Exception as error:
			return f"Error processing override --key | Error:  {error}"

		autopkg_options = models.AutoPkgCMD(**options)

	log.debug(f"[ verb:  {verb} ] | [ recipe_id:  {recipe_id} ] | [ autopkg_options:  {autopkg_options} ]")

	try:

		if verb in { "enable", "disable" }:
			results = await api.recipe.update_by_recipe_id(recipe_id, {"enabled": verb == "enable" })
			return f"Successfully {verb}d recipe id:  {recipe_id}"

		else:
			results = await api.autopkg.autopkg_run_recipe(recipe_id, "slack", autopkg_options)

			if results.get("result") == "Queued background task":
				return f"Queue task:  [ verb:  {verb} ] | [ recipe_id:  {recipe_id} ] | [ autopkg_options:  {autopkg_options} ] | task_id:  {results.get('task_id')}"

			elif results.get("result") == "Recipe is disabled":
				return f"Queue task:  [ verb:  {verb} ] | [ recipe_id:  {recipe_id} ] | [ autopkg_options:  {autopkg_options} ] | result: Recipe is disabled"

	except HTTPException as error:
		return f"Queue task:  [ verb:  {verb} ] | [ recipe_id:  {recipe_id} ] | [ autopkg_options:  {autopkg_options} ] | Unknown recipe id:  '{recipe_id}' "
