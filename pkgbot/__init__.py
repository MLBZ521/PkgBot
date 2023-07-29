from fastapi import FastAPI

from tortoise.contrib.fastapi import register_tortoise

from pkgbot import settings
from pkgbot.utilities.celery import celery_app


def create_pkgbot() -> FastAPI:

	app = FastAPI(
		title="PkgBot API",
		description="A framework to manage software packaging, testing, and promoting from a "
			"development to production environment.",
		version="0.5.0",
		openapi_tags=settings.api.tags_metadata,
		docs_url="/api"
	)

	# Initialize Tortoise ORM (aka, the database)
	register_tortoise(
		app,
		config = settings.db.TORTOISE_CONFIG,
		generate_schemas = True,
		add_exception_handlers = True
	)

	# Initialize the Celery app
	app.celery_app = celery_app

	return app
