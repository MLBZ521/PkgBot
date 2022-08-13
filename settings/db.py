import config


config.load()

TORTOISE_CONFIG = {
	"connections": {
		# "default": "sqlite://:memory:"
		"default": f"sqlite:/{config.pkgbot_config.get('Database.location')}"
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
