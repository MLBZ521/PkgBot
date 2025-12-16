import re
# import secrets

from fastapi import HTTPException

from pkgbot import config, core
from pkgbot.db import models
from pkgbot.utilities import common as utility


config = config.load_config()
log = utility.log


async def known_user(username, user_id, channel, trigger_id, user_object):

	if not user_object:
		log.warning(f"Unknown user:  `{username}` [{user_id}].")

		# Considered doing this:  https://api.slack.com/tutorials/tracks/account-binding
			# But I don't think it's needed at this time...
		# bind_token = secrets.token_urlsafe(64)
		# f"You can login here:  <https://{config.PkgBot.get('host')}/bind_token={bind_token}|{config.PkgBot.get('host')}/bind_token={bind_token}>"

		# core.user.create_or_update({
		# 	"username": username,
		# 	"slack_id": user_id,
		# 	"pkgbot_token": bind_token
		# })

		await core.chatbot.send.modal_notification(
			trigger_id,
			"Please login to PkgBot",
			"Hello, before you can utilize this function, you will need to login to PkgBot.\n\n"
				f"You can login here:  <https://{config.PkgBot.get('host')}|{config.PkgBot.get('host')}>",
			"Done",
			image = f"{config.PkgBot.get('icon_warning')}"
		)
		# Haven't decided which method to use yet...
		# await core.chatbot.send.direct_msg(
		# 	user_id,
		# 	"Hello, before you can utilize this function, you will need to login to PkgBot.\n\n"
		# 		f"You can login here:  <https://{config.PkgBot.get('host')}|{config.PkgBot.get('host')}>",
		# 	channel,
		# 	alt_text = "Please login to PkgBot"
		# )

		return False

	return True


async def unauthorized_function(username, user_id, trigger_id):

	log.warning(f"Unauthorized user:  `{username}` [{user_id}].")

	return await core.chatbot.send.modal_notification(
		trigger_id,
		"PERMISSION DENIED",
		"WARNING:  Unauthorized access attempted!\n\nOnly PkgBot Admins are authorized to "
			f"perform this action.\n\n`{username}` will be reported to the robot overloads.",
		"Ok",
		image = f"{config.PkgBot.get('icon_permission_denied')}"
	)


async def button_click(payload):

	user_id = payload.get("user").get("id")
	username = payload.get("user").get("username")
	channel = payload.get("channel").get("id")
	message_ts = payload.get("message").get("ts")
	trigger_id = payload.get("trigger_id")
	response_url = payload.get("response_url")
	button_text = payload.get("actions")[0].get("text").get("text")
	button_value_type, button_value = (payload.get("actions")[0].get("value")).split(":")
	user_that_clicked = await core.user.get({"username": username, "slack_id": user_id})

	# log.debug("Incoming details:\n"
	# 	f"user id:  {user_id}\nusername:  {username}\nchannel:  {channel}\nmessage_ts:  "
	# 	f"{message_ts}\nresponse_url:  {response_url}\nbutton_text:  {button_text}\n"
	# 	f"button_value_type:  {button_value_type}\nbutton_value:  {button_value}\n"
	# )

	if not await known_user(username = username, user_id = user_id, channel = channel,
		trigger_id = trigger_id, user_object = user_that_clicked):
		return

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

				await core.package.update(
					{ "id": button_value },
					{ "response_url": response_url, "updated_by": username, "slack_ts": message_ts }
				)
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
				recipe_result_object = await core.recipe.update_result({ "slack_ts": message_ts }, updates)
				await core.autopkg.update_trust(
					autopkg_cmd = autopkg_cmd, result_object = recipe_result_object)

		elif button_text == "Deny":

			if button_value_type == "Package":
				log.info(f"PkgBotAdmin `{username}` has denied package id: {button_value}")

				pkg_object = await core.package.update({"id": button_value},
					{ "response_url": response_url,
						"updated_by": username,
						"status": "Denied"
					}
				)
				await core.package.create_note({
					"notes":  "This package was not approved for use in production.",
					"package_id": pkg_object.dict().get("pkg_name"),
					"submitted_by": username
				})
				await core.package.deny(button_value)

			if button_value_type == "Trust":
				log.info(
					f"PkgBotAdmin `{username}` has denied updates for trust id: {button_value}")

				updates = {
					"response_url": response_url,
					"updated_by": username,
					"status": "Denied"
				}

				await core.recipe.update_result({ "slack_ts": message_ts }, updates)
				await core.recipe.deny_trust({ "slack_ts": message_ts })

		elif button_text == "Acknowledge":

			if button_value_type in ("Error", "Recipe_Error"):

				log.info(
					f"PkgBotAdmin `{username}` has acknowledged error message: {message_ts}")
				await core.chatbot.delete_messages(
					str(message_ts), channel, threaded_msgs=True, files=True)

				filter_obj = { "slack_ts": message_ts }
				updates = {
					"response_url": response_url,
					"status": "Acknowledged",
					"updated_by": username
				}

				if button_value_type == "Recipe_Error":
					return await core.recipe.update_result(filter_obj, updates)

				# For legacy errors...  Future cleanup/removal
				try:
					log.debug("Old recipe error")
					return await core.recipe.update_result(filter_obj, updates)
				except Exception:
					log.debug("Generic error")
					return await core.error.update(filter_obj, updates)

	else:
		await unauthorized_function(username, user_id, trigger_id)


async def slash_cmd(incoming_cmd):

	user_id = incoming_cmd.get("user_id")
	username = incoming_cmd.get("user_name")
	channel = incoming_cmd.get("channel_id")
	trigger_id = incoming_cmd.get("trigger_id")
	command = incoming_cmd.get("command")
	cmd_text = incoming_cmd.get("text")
	response_url = incoming_cmd.get("response_url")
	user_that_clicked = await core.user.get({"username": username, "slack_id": user_id})

	log.debug("Incoming details:\n"
		f"channel:  {channel}\nuser id:  {user_id}\nusername:  {username}\n"
		f"user_that_clicked:  {user_that_clicked}\ncommand:  {command}\ncmd_text:  {cmd_text}"
		f"\nresponse_url:  {response_url}\ntrigger_id:  {trigger_id}"
	)

	if not await known_user(username = username, user_id = user_id, channel = channel,
		trigger_id = trigger_id, user_object = user_that_clicked):
		return

	if not user_that_clicked.full_admin and not config.Slack.get("slash_cmds_enabled"):
		return await core.chatbot.send.modal_notification(
			trigger_id,
			"PkgBot Slash Commands",
			"Slash commands are in development and not available for public consumption at this time.",
			"Ok.... :disappointed:"
		)

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
		return await core.chatbot.send.direct_msg(
			username,
			f"The autopkg verb `{verb}` is not supported by PkgBot users or is invalid.",
			channel,
			alt_text = "Unsupported autopkg verb..."
		)

	elif (
		user_that_clicked.full_admin and
		verb not in supported_options.get("pkgbot_admin") + supported_options.get("pkgbot_user")
	):
		return await core.chatbot.send.direct_msg(
			username,
			f"The autopkg verb `{verb}` is not supported at this time by PkgBot or is invalid.",
			channel,
			alt_text = "Unsupported autopkg verb..."
		)

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
				debug_status = ""

			log.debug(f"[ verb:  {verb} ] | [ recipe_id:  {recipe_id} ]{debug_status}")

			results = await core.recipe.update({"recipe_id": recipe_id}, updates)

			return await core.chatbot.send.direct_msg(
				username,
				f"Successfully {verb}d recipe id:  {recipe_id}",
				channel,
				alt_text = f"Successfully {verb}d recipe..."
			)

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
					return await core.chatbot.send.direct_msg(
						username,
						f"Error processing override --key | Error:  {error}",
						channel,
						alt_text = "Error processing override keys..."
					)

				options["verb"] = verb
				autopkg_cmd = models.AutoPkgCMD(**options)

			autopkg_cmd.__dict__.update(incoming_options)

			if target:
				target_type = "recipe" if verb == "run" else "repo"
				verbose_target = f"*{target_type}*:  `{target}`\n"
			else:
				verbose_target = ""

			# log.debug(f"{verbose_target}[ autopkg_cmd:  {autopkg_cmd} ]")
			results = await core.autopkg.execute(autopkg_cmd, target)

			# if results.get("result") == "Queued background task":
			return await core.chatbot.send.direct_msg(
				username,
				f"*Queued task_id*:  `{results}`\n{verbose_target}*autopkg_cmd*:  {autopkg_cmd}",
				channel,
				alt_text = "Queued task..."
			)

			# else:
				# return await core.chatbot.send.direct_msg(
				# 	username,
				# 	f"Queue task_id:  {verbose_target}[ autopkg_cmd:  {autopkg_cmd} ] | result: {results.get('result')}",
				# 	channel,
				# 	alt_text = "Queued task..."
				# )

	except HTTPException as error:

		return await core.chatbot.send.direct_msg(
			username,
			f"Failed to queue task due to unknown target:  '{target}'\n*autopkg_cmd*:  {autopkg_cmd}",
			channel,
			alt_text = "Failed to queue task..."
		)


async def message_shortcut(payload):

	action_ts = payload.get("action_ts")
	user_id = payload.get("user").get("id")
	username = payload.get("user").get("username")
	channel = payload.get("channel").get("id")
	callback_id = payload.get("callback_id")
	trigger_id = payload.get("trigger_id")
	response_url = payload.get("response_url")
	message_ts = payload.get("message").get("ts")
	incoming_blocks = payload.get("message").get("blocks")

	log.debug("Incoming details:\n"
		f"action_ts:  {action_ts}\ncallback_id:  {callback_id}\ntrigger_id:  {trigger_id}\n"
		f"user id:  {user_id}\nusername:  {username}\nchannel:  {channel}\n"
		f"message_ts:  {message_ts}\nresponse_url:  {response_url}"
	)

	user_object = await core.user.get({"username": username})

	if not await known_user(username = username, user_id = user_id, channel = channel,
		trigger_id = trigger_id, user_object = user_object):
		return

	if not user_object.full_admin and not config.Slack.get("shortcuts_enabled"):
		return await core.chatbot.send.modal_notification(
			trigger_id,
			"PkgBot Shortcuts :jamf:",
			"Shortcuts are in development and not available for public consumption at this time.",
			"Ok.... :disappointed:"
		)

	if channel != config.Slack.get("channel"):
		return await core.chatbot.send.modal_notification(
			trigger_id,
			"PkgBot Shortcuts :jamf:",
			"This Shortcut is not supported in this channel!",
			"Ok.... :disappointed:"
		)

	for in_block in incoming_blocks:
		if in_block.get("type") == "section":
			message_text = in_block.get("text").get("text")
			package_name = re.findall(r"\*Package Name:\*\s\s`(.+)`", message_text)[0]
			break

	pkg_object = await core.package.get({"pkg_name": package_name})

	if callback_id == "add_pkg_to_policy":

		# Ensure the pkg has been promoted first
		if pkg_object.status == "dev":
			return await core.chatbot.send.modal_notification(
				trigger_id,
				"PkgBot Shortcuts :jamf:",
				"The pkg must be promoted to production before you can use this option!",
				"Oh... :looking:"
			)

		return await core.chatbot.send.modal_add_pkg_to_policy(trigger_id, pkg_object.pkg_name)


	elif callback_id == "promote_pkg_only":

		if not user_object.full_admin:
			return await unauthorized_function(username, user_id, trigger_id)

		log.info(f"PkgBotAdmin `{username}` is promoting package id: {pkg_object.id}")

		await core.chatbot.SlackBot.reaction(
			action = "add",
			emoji = "gear",
			ts = message_ts
		)

		await core.package.update(
			{ "id": pkg_object.id },
			{ "response_url": response_url, "updated_by": username, "slack_ts": message_ts }
		)

		autopkg_cmd = models.AutoPkgCMD(
			**{
				"verb": "run",
				"pkg_only": True,
				"promote": True,
				"match_pkg": pkg_object.pkg_name,
				"pkg_id": pkg_object.id
			}
		)

		await core.package.promote(pkg_object.id, autopkg_cmd)


async def external_lists(payload):

	action_id = payload.get("action_id")
	filter_value = payload.get("value")
	# private_metadata = payload.get("private_metadata")
	user_id = payload.get("user").get("id")
	username = payload.get("user").get("username")

	log.debug("Incoming details:\n"
		f"action_id:  {action_id}\nfilter_value:  {filter_value}\n"
		f"user id:  {user_id}\nusername:  {username}"
	)

	if action_id == "policy_list":
		return await core.chatbot.send.policy_list(filter_value, username)


async def view_submission(payload):

	action_ts = payload.get("action_ts")
	user_id = payload.get("user").get("id")
	username = payload.get("user").get("username")
	# channel = payload.get("channel").get("id")
	# callback_id = payload.get("callback_id")
	trigger_id = payload.get("trigger_id")
	private_metadata = payload.get("private_metadata")
	# response_url = payload.get("response_url")
	submission = payload.get("view").get("state").get("values")
	incoming_blocks = payload.get("view").get("blocks")

	selected_option = await utility.dict_parser(submission, "selected_option")

	for in_block in incoming_blocks:

		if in_block.get("type") == "section":
			message_text = in_block.get("text").get("text")

		if match := re.findall(r"^Package:\s\s`(.+)`", message_text):
			package_name = match[0]
			break

	policy_name = selected_option.get("text").get("text")
	policy_id = selected_option.get("value")

	log.debug("Incoming details:\n"
		f"action_ts:  {action_ts}\nuser id:  {user_id}\nusername:  {username}\n"
		f"policy_name:  {policy_name}\npolicy_id:  {policy_id}\n"
		f"package_name:  {package_name}\nprivate_metadata:  {private_metadata}"
	)

	policy_object = await core.policy.get({"name": policy_name, "policy_id": policy_id})
	pkg_object = await core.package.get({"pkg_name": package_name})

	await core.policy.update_policy(policy_object, pkg_object, username, trigger_id)
