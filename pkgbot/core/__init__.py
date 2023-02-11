from . import autopkg
from . import error
from . import jamf_pro
from . import package
from . import policy
from . import recipe
from . import user

from pkgbot import config


config = config.load_config()

if config.Slack:
	from .chatbot import slack as chatbot
