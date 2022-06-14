#!/usr/local/autopkg/python

from fastapi import  status
from tortoise.contrib.fastapi import HTTPNotFoundError


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
		"description": "Manage package objects.",
	},
	{
		"name": "recipe",
		"description": "Manage recipe objects.",
	},
	{
		"name": "slackbot",
		"description": "Endpoints handle SlackBot messages and interactions.",
	},
	{
		"name": "user",
		"description": "Manage user objects.",
	}
]

TORTOISE_CONFIG = {
	"connections": {
		# "default": "sqlite://:memory:"
		"default": "sqlite://db/db.sqlite3"
	},
	"apps": {
		"app": {
			"models": [ "db.models" ],
			"default_connection": "default"
		}
	},
	"use_tz": False,
	"timezone": "America/Phoenix"
}

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
