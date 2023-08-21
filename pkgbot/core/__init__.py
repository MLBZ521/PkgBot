from . import (
	autopkg,
	error,
	events,
	jamf_pro,
	package,
	policy,
	recipe,
	user,
	views
)

from pkgbot import config


config = config.load_config()

if config.Slack:
	from .chatbot import slack as chatbot
