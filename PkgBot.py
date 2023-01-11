#!/usr/local/autopkg/python

import multiprocessing
import sys

# import asyncio
import secure
import uvicorn

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware

from tortoise.contrib.fastapi import register_tortoise

from pkgbot import config, settings

config = config.load_config(cli_args=tuple(sys.argv[1:]))

from pkgbot.utilities import common as utility
from pkgbot.db import models
from pkgbot import api


log = utility.log

app = FastAPI(
	title="PkgBot API",
	description="A framework to manage software packaging, testing, and promoting from a "
		"development to production environment.",
	version="0.3.0",
	openapi_tags=settings.api.tags_metadata,
	docs_url="/api"
)

register_tortoise(
	app,
	config = settings.db.TORTOISE_CONFIG,
	generate_schemas = True,
	add_exception_handlers = True
)

app.mount("/static", StaticFiles(directory="/Library/AutoPkg/PkgBot/pkgbot/static"), name="static")
app.include_router(api.views.router)
app.include_router(api.auth.router)
app.include_router(api.autopkg.router)
app.include_router(api.package.router)
app.include_router(api.recipe.router)
app.include_router(api.bot.router)
app.include_router(api.build_msg.router)
app.include_router(api.send_msg.router)
app.include_router(api.user.router)

# Add an exception handler to the app instance
# Used for the login/auth logic for the HTTP views
app.add_exception_handler(api.auth.NotAuthenticatedException, api.auth.exc_handler)
api.auth.login_manager.useRequest(app)

if config.PkgBot.get("enable_ssl"):

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


async def number_of_workers():
	number_of_threads = (multiprocessing.cpu_count() * 2) - 1
	log.debug(f"Number of workers:  {number_of_threads}")
	return number_of_threads


@app.on_event("startup")
async def startup_event():

	pkgbot_admins = config.PkgBot.get("Admins")

	for admin in pkgbot_admins:
		user_object = models.PkgBotAdmin_In(
			username = admin,
			slack_id = pkgbot_admins.get(admin),
			full_admin =  True
		)
		await api.user.create_or_update_user(user_object)


if __name__ == "__main__":

	uvicorn.run(
		"PkgBot:app",
		reload = config.PkgBot.get("keep_alive"),
		host = config.PkgBot.get("host"),
		port = config.PkgBot.get("port"),
		log_config = config.PkgBot.get("log_config"),
		log_level = config.PkgBot.get("uvicorn_log_level"),
		# workers = asyncio.run(number_of_workers()),
		ssl_keyfile = config.PkgBot.get("ssl_keyfile"),
		ssl_certfile = config.PkgBot.get("ssl_certfile")
	)
