from .bot import SlackClient, check_for_thread, delete_messages, validate_request
from . import events, send
from .. import build

from pkgbot import config
from pkgbot.utilities import common as utility


log = utility.log
config = config.load_config()
SlackBot = bot.SlackClient(
	token = config.Slack.bot_token,
	bot_name = config.Slack.bot_name,
	channel = config.Slack.channel,
	slack_id = config.Slack.slack_id
)
