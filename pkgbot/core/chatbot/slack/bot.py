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


	async def post_message(
		self, blocks: str, text: str = "Pkg status incoming...", thread_ts = None):

		try:
			return await self.client.chat_postMessage(
				channel = self.channel,
				text = text,
				blocks = blocks,
				username = self.bot_name,
				thread_ts = thread_ts or None ##### Need to test/verify
			)

		except SlackApiError as error:
			log.error(f"Failed to post message:  {error.response['error']}"
				f"\nError:\n{error}\Blocks:\n{blocks}")
			return { "result": "Failed to post message", "error": error.response["error"] }

		except asyncio.exceptions.TimeoutError as error:
			log.error(
				f"Failed to post message due to timeout.  Blocks:\n{blocks}\nFull error:  {error}")
			return { "result": "Failed to post message", "error": error }


	async def update_message(self, blocks: str, ts: str, text: str = "Updated message..."):

		try:
			response = await self.client.chat_update(
				channel = self.channel,
				text = text,
				blocks = blocks,
				ts = ts
			)

			if response.status_code != 200:
				log.error(f"Failed to update message! Status code:  "
			  		f"{response.status_code} | Error message:  {response.body}")
			else:
				log.debug("Successfully updated msg via response_url")

			return response

		except SlackApiError as error:
			log.error(f"Failed to update {ts}:  {error.response['error']}\n{error}")
			return { "result": f"Failed to update {ts}", "error": error.response["error"] }


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
				if json.loads(response.body).get("error") == "expired_url":
					log.error("Failed to update message due to expired Response URL! Status "
						f"code:  {response.status_code} | Error message:  {response.body}")
				else:
					log.error(
						f"Failed to update message! Status code:  "
							f"{response.status_code} | Error message:  {response.body}")
			else:
				log.debug("Successfully updated msg via response_url")

			return response

		except SlackApiError as error:
			log.error(f"Failed to update {response_url}\nFull Error:\n{error}\n"
			 	f"error.dir:  {dir(error)}\nerror.response['error']:  {error.response['error']}")
			return response

		except asyncio.exceptions.TimeoutError as error:
			log.error(
				f"Failed to post message due to timeout.  Blocks:\n{blocks}\nFull error:  {error}")
			return { "result": "Failed to post message", "error": error }


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
					log.debug(
						f"Rate Limit > Delay for:  {error.response.headers.get('Retry-After')}")
					time.sleep(float(retry_after))
					continue

				log.error(f"Failed to delete {ts}:  {error.response['error']}\n{error}")
				return { "Failed to delete": ts, "result": error.response["error"] }


	async def check_for_threaded_message(self, ts: str, channel):

		try:

			response = await self.client.conversations_replies(
				channel = channel or self.channel,
				ts = ts,
			)

			messages = response.get("messages")

			if child_messages := [
				message.get("ts")
				for message in messages
				if message.get("ts") != ts and message.get("user") == self.slack_id
			]:
				ts_is_thread = True
				result = {
					"length": messages[0].get("reply_count"),
					"parent_message": ts,
					"child_messages": child_messages,
					"messages": messages,
					"files": [
						file.get("id")
						for message in messages
						if message.get("files") and message.get("user") == self.slack_id
						for file in message.get("files")
					]
				}

			else:
				ts_is_thread = False
				result = "Not a threaded message."

			return { "is_thread": ts_is_thread, "result": result }


		except SlackApiError as error:

			if error.response.get("error") == "thread_not_found":
				return { "thread": False, "result": "Message not found." }

			log.error(f"Failed to post message:  {error.response['error']}\n{error}")
			return { "result": "Failed to post message", "error": error.response["error"] }

		except asyncio.exceptions.TimeoutError as error:
			log.error(f"Failed to post message due to timeout.  Full error:  {error}")
			return { "result": "Failed to post message", "error": error }


	async def post_ephemeral_message(self, user_id: str, blocks: str, channel: str = None,
		text: str = "Private Note", thread_ts=None):

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
				username = self.bot_name,
				thread_ts=thread_ts
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


	async def delete_file(self, file_id):

		while True:

			try:
				await self.client.files_delete(file = file_id)
				return { "result":  "Successfully deleted file" }

			except SlackApiError as error:

				if retry_after := error.response.headers.get('Retry-After'):
					log.debug(f"Rate Limit > Delay for:  {error.response.headers.get('Retry-After')}")
					time.sleep(float(retry_after))
					continue

				if error.response.get("error") == "file_deleted":
					return { "result":  "File was already deleted" }

				log.error(f"Failed to delete {file_id}:  {error.response['error']}\n{error}")
				return { "Failed to delete": file_id, "result": error.response["error"] }


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


async def delete_messages(timestamps: str | list,
	channel: str | None = None, threaded_msgs: bool = False, files: bool = False):

	if isinstance(timestamps, str):
		timestamps = [timestamps]

	deleted_files = {}
	deleted_msgs = {}

	if threaded_msgs and files:
		child_message_ts = []
		files_in_threads = []

		for ts in timestamps:
			response = await check_for_thread(ts, channel)

			if response.get("is_thread"):
				child_message_ts.extend(response.get("result").get("child_messages"))
				files_in_threads.extend(response.get("result").get("files"))

		timestamps.extend(child_message_ts)

		for file in files_in_threads:
			file_result = await core.chatbot.SlackBot.delete_file(file)
			deleted_files[file] = file_result.get("result")

	for ts in timestamps:
		msg_result = await core.chatbot.SlackBot.delete_message(str(ts), channel)
		deleted_msgs[ts] = msg_result.get("result")

	return { "deleted_messages":  deleted_msgs, "deleted_files": deleted_files }


async def check_for_thread(ts: str, channel: str | None = None):

	return await core.chatbot.SlackBot.check_for_threaded_message(
		channel = channel,
		ts = ts
	)
