
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
