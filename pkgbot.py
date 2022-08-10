#!/usr/local/autopkg/python

import argparse
import multiprocessing
import sys

sys.path.insert(0, "/Library/AutoPkg/PkgBotPackages")

import asyncio
import secure
import uvicorn

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware

from tortoise.contrib.fastapi import register_tortoise

# from settings.celery_utils import create_celery

import config, utils
from db import models
from api import auth, autopkg, package, recipe, settings, user, views
from api.slack import bot, build_msg, send_msg


log = utils.log


# def create_app() -> FastAPI:
app = FastAPI(
	title="PkgBot API",
	description="A framework to manage software packaging, testing, and promoting from a "
		"development to production environment.",
	version="0.2.0",
	openapi_tags=settings.tags_metadata,
	docs_url="/api"
)

# app.celery_app = create_celery()

app.include_router(views.router)
app.include_router(auth.router)
app.include_router(autopkg.router)
app.include_router(package.router)
app.include_router(recipe.router)
app.include_router(bot.router)
app.include_router(build_msg.router)
app.include_router(send_msg.router)
app.include_router(user.router)

# return app


# app = create_app()
# celery = app.celery_app

register_tortoise(
	app,
	config = settings.TORTOISE_CONFIG,
	generate_schemas = True,
	add_exception_handlers = True
)


async def number_of_workers():
	number_of_threads = (multiprocessing.cpu_count() * 2) - 1
	log.debug("Number of workers:  {}".format(number_of_threads))
	return number_of_threads


def load_config(cli_args=None):

	log.debug('PkgBot.Load_Config:\n\tAll calling args:  {}'.format(cli_args))

	parser = argparse.ArgumentParser(description="PkgBot Main.")
	parser.add_argument(
		'--pkgbot_config', '-pc',
		metavar='./pkgbot.config',
		default=None, type=str, required=False,
		help='A config file with defined environmental configurations.')
	args = parser.parse_known_args(cli_args)

	log.debug('PkgBot.Load_Config:\n\tArgparse args:  {}'.format(args))

	if len(sys.argv) != 0:

		config.load(args)

	else:

		parser.print_help()
		sys.exit(0)


@app.on_event("startup")
async def startup_event():

	pkgbot_admins = config.pkgbot_config.get("PkgBot.Admins")

	for admin in pkgbot_admins:

		user_object = models.PkgBotAdmin_In(
			username = admin,
			slack_id = pkgbot_admins.get( admin ),
			full_admin =  True
		)

		await user.create_or_update_user( user_object )


# Add an exception handler to the app instance
# Used for the login/auth logic for the HTTP views
app.add_exception_handler(auth.NotAuthenticatedException, auth.exc_handler)
auth.login_manager.useRequest(app)

if config.pkgbot_config.get("PkgBot.enable_ssl"):

	# Enforces that all incoming requests must be https.
	app.add_middleware(HTTPSRedirectMiddleware)

	server = secure.Server().set("Secure")

	hsts = secure.StrictTransportSecurity().include_subdomains().preload().max_age(2592000)

	cache_value = secure.CacheControl().must_revalidate()

	secure_headers = secure.Secure(
		server=server,
		# csp=csp,
		hsts=hsts,
		# referrer=referrer,
		# permissions=permissions_value,
		cache=cache_value,
	)

	@app.middleware("http")
	async def set_secure_headers(request, call_next):
		response = await call_next(request)
		secure_headers.framework.fastapi(response)
		return response


if __name__ == "__main__":

	# Load Configuration
	load_config(cli_args=sys.argv)

	uvicorn.run(
		"pkgbot:app",
		reload = config.pkgbot_config.get("PkgBot.keep_alive"),
		host = config.pkgbot_config.get("PkgBot.host"),
		port = config.pkgbot_config.get("PkgBot.port"),
		log_config = config.pkgbot_config.get("PkgBot.log_config"),
		log_level = config.pkgbot_config.get("PkgBot.uvicorn_log_level"),
		# workers = asyncio.run( number_of_workers() ),
		# ssl_keyfile = config.pkgbot_config.get("PkgBot.ssl_keyfile"),
		# ssl_certfile = config.pkgbot_config.get("PkgBot.ssl_certfile")
	)
