import re

from fastapi import HTTPException

from pkgbot import config, core
from pkgbot.db import models
from pkgbot.utilities import common as utility


config = config.load_config()
log = utility.log


async def button_click(payload):

	user_id = payload.get("user").get("id")
	username = payload.get("user").get("username")
	channel = payload.get("channel").get("id")
	message_ts = payload.get("message").get("ts")
	response_url = payload.get("response_url")
	button_text = payload.get("actions")[0].get("text").get("text")
	button_value_type, button_value = (payload.get("actions")[0].get("value")).split(":")
	user_that_clicked = await core.user.get({"username": username, "slack_id": user_id})

	# log.debug("Incoming details:\n"
	# 	f"user id:  {user_id}\nusername:  {username}\nchannel:  {channel}\nmessage_ts:  "
	# 	f"{message_ts}\nresponse_url:  {response_url}\nbutton_text:  {button_text}\n"
	# 	f"button_value_type:  {button_value_type}\nbutton_value:  {button_value}\n"
	# )

	# Verify and perform action only if a PkgBotAdmin clicked the button
	if user_that_clicked and user_that_clicked.full_admin:

		await core.chatbot.SlackBot.reaction(
			action = "add",
			emoji = "gear",
			ts = message_ts
		)

		if button_text == "Approve":

			if button_value_type == "Package":
				log.info(f"PkgBotAdmin `{username}` is promoting package id: {button_value}")

				await core.package.update({"id": button_value},
					{ "response_url": response_url, "updated_by": username })
				await core.package.promote(button_value)

			elif button_value_type == "Trust":
				log.info(
					f"PkgBotAdmin `{username}` has approved updates for trust id: {button_value}")

				updates = {
					"response_url": response_url,
					"updated_by": username,
					"slack_ts": message_ts
				}

				autopkg_cmd = models.AutoPkgCMD(**{
					"verb": "update-trust-info",
					"ingress": "Slack",
					"egress": username,
					"channel": channel
				})

				trust_object = await models.TrustUpdates.filter(id=button_value).first()
				await models.TrustUpdates.update_or_create(updates, id=trust_object.id)
				await core.autopkg.update_trust(
					autopkg_cmd = autopkg_cmd, trust_object = trust_object)

		elif button_text == "Deny":

			if button_value_type == "Package":
				log.info(f"PkgBotAdmin `{username}` has denied package id: {button_value}")

				await core.package.update({"id": button_value},
					{ "response_url": response_url,
						"updated_by": username,
						"status": "Denied",
						"notes":  "This package was not approved for use in production." }
				)
				await core.package.deny(button_value)

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
				await core.recipe.deny_trust(button_value)

		elif button_text == "Acknowledge":

			if button_value_type == "Error":

				log.info(
					f"PkgBotAdmin `{username}` has acknowledged error message: {message_ts}")
				await core.chatbot.SlackBot.delete_message(str(message_ts))

				updates = {
					"response_url": response_url,
					"status": "Acknowledged",
					"ack_by": username
				}

				return await models.ErrorMessages.update_or_create(updates, slack_ts=message_ts)

	else:
		log.warning(f"Unauthorized user:  `{username}` [{user_id}].")

		blocks = await core.chatbot.build.unauthorized_msg(username)
		await core.chatbot.SlackBot.post_ephemeral_message(
			user_id, blocks, channel=channel, text="WARNING:  Unauthorized access attempted")


async def slash_cmd(incoming_cmd):

	user_id = incoming_cmd.get("user_id")
	username = incoming_cmd.get("user_name")
	channel = incoming_cmd.get("channel_id")
	command = incoming_cmd.get("command")
	cmd_text = incoming_cmd.get("text")
	response_url = incoming_cmd.get("response_url")
	user_that_clicked = await core.user.get({"username": username, "slack_id": user_id})

	log.debug("Incoming details:\n"
		f"channel:  {channel}\nuser id:  {user_id}\nusername:  {username}\n"
		f"full admin:  {user_that_clicked.full_admin}\ncommand:  {command}\ncmd_text:  {cmd_text}"
		f"\nresponse_url:  {response_url}\n"
	)

##### TO DO:
	# Update below return statements to use an appropriate Slack message type
		# Current returns are simply place holders for verbosity and development work

	if not user_that_clicked.full_admin:
		return "Slash commands are in development and not available for public consumption at this time."

	if " " in cmd_text:
		verb, options = await utility.split_string(cmd_text)
	else:
		verb = cmd_text
		options = ""

	supported_options = {
		"pkgbot_admin": ["update-trust-info", "repo-add", "enable", "disable" ],
		"pkgbot_user": [ "help", "run", "verify-trust-info", "version" ]
	}

	if not user_that_clicked.full_admin and verb not in supported_options.get("pkgbot_user"):
		return f"The autopkg verb `{verb}` is not supported by PkgBot users or is invalid."
	elif (
		user_that_clicked.full_admin and
		verb not in supported_options.get("pkgbot_admin") + supported_options.get("pkgbot_user")
	):
		return f"The autopkg verb `{verb}` is not supported at this time by PkgBot or is invalid."

	try:

		if verb == "help":

			help_text = f"""Hello {username}!

I support a variety of commands to help run AutoPkg on your behalf.  Please see the below options and examples:

*PkgBot Users are able to utilize the following commands:*
>`/pkgbot help`
>	Prints this help info.
>
>`/pkgbot version`
>	Returns the current version of the AutoPkg framework installed on the AutoPkg runner.
>
>`/pkgbot verify-trust-info <recipe>`
>	Checks the trust-info of the provided recipe.
>
>`/pkgbot run <recipe> [options]`
>	Runs the passed recipe against `autopkg run`.  Several customizable options are supported:
>		`--ignore-parent-trust-verification-errors`
>		`--verbose | -[v+]` (default is `-vvv`)
>		`--key | -k '<OVERRIDE_VARIABLE>=<value>'`

*PkgBot Admins are able to utilize the following commands:*
>`/pkgbot update-trust-info <recipe>`
>	Updates the trust-info of the provided recipe.
>
>`/pkgbot repo-add <repo>`
>	Adds the passed recipe repo(s) to the available parent search repos.
>		`<repo>` can be one or more of a path (URL or [GitHub] user/repo) of an AutoPkg recipe repo.
>
>`/pkgbot enable <recipe>`
>	Enables the recipe in the PkgBot database.
>
>`/pkgbot disable <recipe>`
>	Disables the recipe in the PkgBot database."""

			await core.chatbot.send.direct_msg(
				user = user_id,
				text = help_text,
				alt_text = "PkgBot Help Info...",
				channel = channel,
				image = None,
				alt_image_text = None
			)

# return Response(status_code=status.HTTP_200_OK)

		elif verb in {"enable", "disable"}:

			updates = {"enabled": verb == "enable"}

			if " " in options:
				recipe_id, status = await utility.split_string(options)
				debug_status = f" | [ status:  {status} ]"

			else:
				recipe_id = options
				status = ""
				debug_status = ""

			if status:
				updates |= {"status": status}

			log.debug(f"[ verb:  {verb} ] | [ recipe_id:  {recipe_id} ]{debug_status}")

			results = await core.recipe.update({"recipe_id": recipe_id}, updates)
			return f"Successfully {verb}d recipe id:  {recipe_id}"

		else:

			incoming_options = {"verb": verb, "ingress": "Slack", "egress": username, "channel": channel}

			if " " not in options:
				target = options
				autopkg_cmd = models.AutoPkgCMD(**incoming_options)
			else:
				target, cmd_options = await utility.split_string(options)

				try:
					options = await utility.parse_slash_cmd_options(cmd_options, verb)
				except Exception as error:
					return f"Error processing override --key | Error:  {error}"

				autopkg_cmd = models.AutoPkgCMD(**options)

			autopkg_cmd.__dict__.update(incoming_options)

			log.debug(f"[ target:  {target} ] | [ autopkg_cmd:  {autopkg_cmd} ]")

			results = await core.autopkg.execute(autopkg_cmd, target)

			# if results.get("result") == "Queued background task":
			return f"Queue task:  [ target:  {target} ] | [ autopkg_cmd:  {autopkg_cmd} ] | task_id:  {results}"

			# else:
			# 	return f"Queue task:  [ target:  {target} ] | [ autopkg_cmd:  {autopkg_cmd} ] | result: {results.get('result')}"

	except HTTPException as error:
		return f"Queue task:  [ target:  {target} ] | [ autopkg_cmd:  {autopkg_cmd} ] | Unknown target:  '{target}' "
