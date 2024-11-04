import hashlib
import hmac
import json

from fastapi import Request

from . import (
	auth,
	autopkg,
	build_msg,
	package,
	policy,
	send_msg,
	recipe,
	tasks,
	user,
	views
)

from pkgbot import config
from pkgbot.utilities import common as utility


log = utility.log
config = config.load_config()

if config.Slack:
	from . import slackbot as chatbot


async def verify_pkgbot_webhook(request: Request):

	try:
##### Add a timestamp check
		# slack_timestamp = request.headers.get("X-Slack-Request-Timestamp")

		# if abs(time.time() - int(slack_timestamp)) > 60 * 5:
		# 	# The request timestamp is more than five minutes from local time.
		# 	# It could be a replay attack, so let's ignore it.
		# 	return False

		body = json.loads(await request.body())

		digest = await utility.compute_hex_digest(
			config.PkgBot.get("webhook_secret").encode("UTF-8"),
			str(body).encode("UTF-8"),
			hashlib.sha512
		)

		if hmac.compare_digest(
			digest.encode("UTF-8"),
			(request.headers.get("x-pkgbot-signature")).encode("UTF-8")
		):
			# log.debug("Valid PkgBot Webhook message")
			return True

		log.warning("Invalid PkgBot Webhook message!")
		return False

	except Exception:
		log.error("Exception attempting to validate PkgBot Webhook!")
		return False
