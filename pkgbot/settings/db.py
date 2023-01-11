from pkgbot import config


config = config.load_config()

TORTOISE_CONFIG = {
	"connections": {
		# "default": "sqlite://:memory:"
		"default": f"sqlite:{config.Database.get('location')}"
	},
	"apps": {
		"pkgbot": {
			"models": [ "pkgbot.db.models" ],
			"default_connection": "default"
		}
	},
	"use_tz": False,
	"timezone": config.Common.get("timezone")
}
