from datetime import datetime

from fastapi import Request, status
from fastapi.templating import Jinja2Templates
from tortoise.contrib.fastapi import HTTPNotFoundError

from pkgbot import config


config = config.load_config()


def template_filter_datetime(datetime_string: str, format_string: str = "%Y-%m-%d %I:%M:%S"):

	if datetime_string:
		converted = datetime.fromisoformat(str(datetime_string))
		return converted.strftime(format_string)


def template_find_max(unsorted_list: list, key: str):

	if unsorted_list:
		return max(unsorted_list, key=lambda x: x.dict().get(key))


def parse_notification_messages(request: Request):

	return request.session.pop("pkgbot_msg") if "pkgbot_msg" in request.session else []


tags_metadata = [
	{
		"name": "auth",
		"description": "**Authentication** operations for users.",
	},
	{
		"name": "autopkg",
		"description": "Handles all **AutoPkg** processes.",
	},
	{
		"name": "package",
		"description": "Manage **Package** objects.",
	},
	{
		"name": "policy",
		"description": "Manage **Policy** objects.",
	},
	{
		"name": "recipe",
		"description": "Manage **Recipe** objects.",
	},
	{
		"name": "slackbot",
		"description": "Endpoints handle **SlackBot** messages and interactions.",
	},
	{
		"name": "user",
		"description": "Manage **User** objects.",
	}
]



custom_responses = {
	# 404: {"description": "Item not found"},
	# 302: {"description": "The item was moved"},
	status.HTTP_401_UNAUTHORIZED: { "description":
		"You must authenticate before utilizing this endpoint." },
	status.HTTP_403_FORBIDDEN: { "description":
		"You are not authorized to utilize this endpoint." },
	status.HTTP_404_NOT_FOUND: { "model": HTTPNotFoundError },
	status.HTTP_409_CONFLICT: { "description": "The object already exists." }
}


PkgBot_Cookie = "PkgBot_Cookie"


jinja_templates = Jinja2Templates(directory=config.PkgBot.get("jinja_templates"))
jinja_templates.env.filters.update(strftime=template_filter_datetime)
jinja_templates.env.filters.update(find_max=template_find_max)
jinja_templates.env.globals.update(parse_messages=parse_notification_messages)
