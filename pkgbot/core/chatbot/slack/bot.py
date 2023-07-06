import asyncio
import certifi
import hmac
import re
import ssl
import time

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.webhook.async_client import AsyncWebhookClient

from fastapi import Request

from pkgbot import config, core
from pkgbot.utilities import common as utility


config = config.load_config()
log = utility.log
ssl_context = ssl.create_default_context(cafile=certifi.where())


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
			return { "result": "Failed to post message", "error": error.response["error"] }

		except asyncio.exceptions.TimeoutError as error:
			log.error(
				f"Failed to post message due to timeout.  Blocks:\n{blocks}\nFull error:  {error}")
			return { "result": "Failed to post message", "error": error }


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
			return { "result": f"Failed to update {ts}", "error": error.response["error"] }


	async def delete_message(self, ts: str, channel):

		while True:

			try:

				await self.client.chat_delete(
					channel = channel or self.channel,
					ts = ts
				)
				return { "result":  "Successfully deleted message" }

			except SlackApiError as error:

				if retry_after := error.response.headers.get('Retry-After'):
					log.debug(f"Rate Limit > Delay for:  {error.response.headers.get('Retry-After')}")
					time.sleep(float(retry_after))
					continue

				log.error(f"Failed to delete {ts}:  {error.response['error']}\n{error}")
				return { "Failed to delete": ts, "error": error.response["error"] }


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
			return response

		except asyncio.exceptions.TimeoutError as error:
			log.error(
				f"Failed to post message due to timeout.  Blocks:\n{blocks}\nFull error:  {error}")
			return { "result": "Failed to post message", "error": error }


	async def post_ephemeral_message(
		self, user_id: str, blocks: str, channel: str = None, text: str = "Private Note"):

		# `user` must match regex pattern:  ^[UW][A-Z0-9]{2,}$
		if not re.match(r"^[UW][A-Z0-9]{2,}$", user_id):
			user_object = await core.user.get({"username": user_id})
			user_id = user_object.slack_id

		try:
			return await self.client.chat_postEphemeral(
				channel = channel or self.channel,
				user = user_id,
				text = text,
				blocks = blocks,
				username = self.bot_name
			)

		except SlackApiError as error:
			log.error(
				f"Failed to post ephemeral message:  {error.response['error']}\nFull Error:\n{error}")
			return { "result": "Failed to post ephemeral message", "error": error.response["error"] }

		except asyncio.exceptions.TimeoutError as error:
			log.error(
				f"Failed to post message due to timeout.  Blocks:\n{blocks}\nFull error:  {error}")
			return { "result": "Failed to post message", "error": error }


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
			return { "result": f"Failed to upload {file}", "error": error.response["error"] }


	async def reaction(self, action: str = None, emoji: str = None, ts: str = None, **kwargs):

		try:

			match action:

				case "get":
					return await self.client.reactions_get(
						channel = self.channel,
						timestamp= ts
					)

				case "add":
					return await self.client.reactions_add(
						channel = self.channel,
						name = emoji,
						timestamp = ts
					)

				case "remove":
					return await self.client.reactions_remove(
						channel = self.channel,
						name = emoji,
						timestamp = ts
					)

		except SlackApiError as error:

			error_key = error.response["error"]

			if not (
				action == "add" and error_key == "already_reacted" or
				action == "remove" and error_key == "no_reaction"
			):

				result = { "result": f"Failed to {action} reaction on {ts}", "error": error_key }
				log.error(result)
				return result


	async def open_modal(self, trigger_id, blocks: str):

		try:
			return await self.client.views_open(
				trigger_id = trigger_id,
				view = blocks
			)

		except SlackApiError as error:
			log.error(f"Failed to post message:  {error.response['error']}\n{error}")
			return { "result": "Failed to post message", "error": error.response["error"] }

		except asyncio.exceptions.TimeoutError as error:
			log.error(
				f"Failed to post message due to timeout.  Blocks:\n{blocks}\nFull error:  {error}")
			return { "result": "Failed to post message", "error": error }


async def validate_request(request: Request):

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


async def delete_messages(timestamps: str | list, channel: str | None = None):

	if isinstance(timestamps, str):
		timestamps = [timestamps]

	results = {}

	for ts in timestamps:

		result = await core.chatbot.SlackBot.delete_message(str(ts), channel)
		results[ts] = result.get("error", "Successfully deleted message")

	return results
