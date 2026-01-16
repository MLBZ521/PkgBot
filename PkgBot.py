#!/usr/local/autopkg/python

import multiprocessing
import sys

# import asyncio
import secure
import uvicorn

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware

from pkgbot import config

config = config.load_config()

from pkgbot.utilities import common as utility
from pkgbot.db import models, schemas
from pkgbot import api, core, create_pkgbot


log = utility.log


@asynccontextmanager
async def life_span_events(app: FastAPI):

	# Ensure PkgBot Admins from PkgBot's settings are configured in the database.
	pkgbot_admins = config.PkgBot.Admins

	for admin in pkgbot_admins:
		user_object = schemas.PkgBotAdmin_In(
			username = admin,
			slack_id = pkgbot_admins.get(admin),
			full_admin =  True
		)
		await core.user.create_or_update(user_object)

	# Run `autopkg run` on startup, if configured
	if config.Services.execute_autopkg_run_on_start:
		log.debug("[NOTICE] Executing `autopkg run` on startup...")
		autopkg_cmd = models.AutoPkgCMD(**{"verb": "run", "ingress": "Schedule"})
		await core.autopkg.run_recipes(autopkg_cmd)

	yield


app = create_pkgbot(life_span_events=life_span_events)
celery = app.celery_app

app.mount("/static", StaticFiles(directory=config.PkgBot.jinja_static), name="static")
app.include_router(api.views.router)
app.include_router(api.auth.router)
app.include_router(api.autopkg.router)
app.include_router(api.package.router)
app.include_router(api.policy.router)
app.include_router(api.recipe.router)
app.include_router(api.chatbot.router)
app.include_router(api.build_msg.router)
app.include_router(api.send_msg.router)
app.include_router(api.user.router)
app.include_router(api.tasks.router)

# Add an exception handler to the app instance
# Used for the login/auth logic for the HTTP views
app.add_exception_handler(api.auth.NotAuthenticatedException, api.auth.exc_handler)
api.auth.login_manager.attach_middleware(app)

if config.PkgBot.enable_ssl:

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
		await secure_headers.set_headers_async(response)
		return response


async def number_of_workers():
	number_of_threads = (multiprocessing.cpu_count() * 2) - 1
	log.debug(f"Number of workers:  {number_of_threads}")
	return number_of_threads


if __name__ == "__main__":

	# asyncio.run(life_span_events())

	uvicorn.run(
		"PkgBot:app",
		reload = config.PkgBot.keep_alive,
		host = config.PkgBot.host,
		port = config.PkgBot.port,
		log_config = config.PkgBot.log_config,
		log_level = config.PkgBot.uvicorn_log_level,
		# workers = asyncio.run(number_of_workers()),
		ssl_keyfile = config.PkgBot.ssl_keyfile,
		ssl_certfile = config.PkgBot.ssl_certfile
	)
