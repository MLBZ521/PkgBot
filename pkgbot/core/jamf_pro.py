import httpx

from pkgbot import config


config = config.load_config()
jps_url = config.JamfPro_Prod.get("jps_url")
api_user = config.JamfPro_Prod.get("api_user")
api_password = config.JamfPro_Prod.get("api_password")


async def get_token(username: str = api_user, password: str = api_password):

	async with httpx.AsyncClient() as client:
		response_get_token = await client.post(
			f"{jps_url}/api/v1/auth/token", auth=(username, password))

	if response_get_token.status_code == 200:

		response_json = response_get_token.json()
		return response_json["token"], response_json["expires"]

	return False
