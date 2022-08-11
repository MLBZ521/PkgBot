#!/usr/local/autopkg/python

import asyncio
import sys

sys.path.insert(0, "/Library/AutoPkg/PkgBot")

import httpx

import config, utilities.common as utility


config.load()
log = utility.log


async def request(method, endpoint, data=None, json=None):

	pkgbot_server, headers = await _api_url_helper()

	async with httpx.AsyncClient() as client:

		if method == "get":
			return await client.get('{}{}'.format(pkgbot_server, endpoint), 
				headers=headers
			)

		elif method == "post":
			return await client.post('{}{}'.format(pkgbot_server, endpoint), 
				headers=headers, 
				data=data,
				json=json
			)

		elif method == "delete":
			return await client.delete('{}{}'.format(pkgbot_server, endpoint), 
				headers=headers
			)


async def _api_url_helper():

	if config.pkgbot_config.get("PkgBot.enable_ssl"):
		secure = "s"
	else:
		secure = ""

	pkgbot_server = "http{}://{}:{}".format(
		secure,
		config.pkgbot_config.get("PkgBot.host"), 
		config.pkgbot_config.get("PkgBot.port")
	)

	token = await authenticate_with_pkgbot( 
		pkgbot_server,
		config.pkgbot_config.get("JamfPro_Prod.api_user"),
		config.pkgbot_config.get("JamfPro_Prod.api_password")
	)

	headers = { 
		"Authorization": "Bearer {}".format(token),
		"accept": "application/json", 
		"Content-Type": "application/json"
	}

	return pkgbot_server, headers


async def authenticate_with_pkgbot(server: str, username: str, password: str):

	headers = { 
		"accept": "application/json", 
		"Content-Type": "application/x-www-form-urlencoded"
	}

	data = {
		"username": username,
		"password": password
	}

	async with httpx.AsyncClient() as client:
		response_get_token = await client.post("{}/auth/token".format(server), 
				headers=headers, 
				data=data
			)

	if response_get_token.status_code == 200:

		response_json = response_get_token.json()

		return response_json["access_token"]


async def chat_failed_trust(recipe_id, msg):
	""" Update Slack message that recipe_id failed verify-trust-info """

	payload = {
		"recipe_id": recipe_id,
		"msg": msg
	}

	await request( "post", "/recipe/trust/verify/failed", json=payload )


async def chat_update_trust_msg(recipe_id, result, error_id):
	""" Update slack message that recipe_id was trusted """

	if result == "success":
		endpoint = "trust/update/success"
	else:
		endpoint = "trust/update/failed"

	await request( 
		"post", "/recipe/{}?recipe_id={}&msg={}&error_id={}".format(endpoint, recipe_id, result, error_id) )


async def chat_recipe_error(recipe_id, msg):

	await request( 
		"post", "/recipe/error?recipe_id={}&error={}".format(recipe_id, msg) )


async def webhook_flare(recipe_id, action):
	""" Send webhook when all other options fail.
	
	No implemented at this time.
	"""

	pass


async def get_recipes():

	return await request("get", "/recipes/")


async def get_recipe(id):

	return await request("get", "/recipe/id/{}".format(id))


async def get_recipe_by_recipe_id(recipe_id):
	return await request("get", "/recipe/recipe_id/{}".format(recipe_id))


async def create_recipe(data):

	return await request("post", "/recipe/", data=data)


async def update_recipe_by_recipe_id(recipe_id, data):

	return await request("put", "/recipe/recipe_id/{}".format(recipe_id), data=data)


async def delete_recipe(id):

	return await request("delete", "/recipe/id/{}".format(id))


async def delete_recipe_by_recipe_id(recipe_id):

	return await request("delete", "/recipe/recipe_id/{}".format(recipe_id))
