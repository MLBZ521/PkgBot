import re

from datetime import datetime, timezone
from xml.etree import ElementTree

import httpx

from pkgbot import config
from pkgbot.utilities import common as utility


log = utility.log
config = config.load_config()
JPS_URL = config.JamfPro_Prod.get("jps_url")
API_USER = config.JamfPro_Prod.get("api_user")
API_PASSWORD = config.JamfPro_Prod.get("api_password")
API_TOKEN = None
API_TOKEN_EXPIRES = 0


async def get_token(username: str = API_USER, password: str = API_PASSWORD):

	try:

		async with httpx.AsyncClient() as client:
			response_get_token = await client.post(
				f"{JPS_URL}/api/v1/auth/token", auth=(username, password))

		if response_get_token.status_code == 200:

			response_json = response_get_token.json()
			return response_json["token"], await fixup_token_expiration(response_json["expires"])

		log.error(
			"Failed to get token?\n"
			f"{response_get_token.status_code = }\n"
			f"{response_get_token.text = }"
		)

		return False, 0

	except httpx.ReadTimeout as timeout:
		log.error(f"Login timed out for:  {username}")
		return False, False



async def fixup_token_expiration(token_expires: str):

	try:
	# token_expires.rsplit(".", maxsplit=1)[0]
		return datetime.fromisoformat(
			re.sub(r"(\.\d+)?Z", "", token_expires)
		).replace(tzinfo=timezone.utc)
		# expires = datetime.strptime(token_expires, "%Y-%m-%dT%H:%M:%S")

	except:
		log.warning(f"Failed fixing up the API Token Expiration:  {token_expires}")
		return 0


async def api(method: str, endpoint: str, in_content_type: str = "json", out_content_type = "xml",
	data: str | dict | None = None, api_token: str = API_TOKEN, username: str = API_USER,
	password: str = API_PASSWORD):

	if api_token:
		API_TOKEN = api_token
		# API_TOKEN_EXPIRES = API_TOKEN_EXPIRES
	else:
		API_TOKEN, API_TOKEN_EXPIRES = await get_token(username, password)

	# try:
	# if API_TOKEN_EXPIRES:
	# 	if datetime.now(timezone.utc) > (API_TOKEN_EXPIRES - timedelta(minutes=5)):
	# 		log.debug("Renewing API Token...")
	# 		API_TOKEN, API_TOKEN_EXPIRES = await core.jamf_pro.get_token()
	# except:
		# log.warning(f"Something is wrong with API_TOKEN_EXPIRES:  {API_TOKEN_EXPIRES}")


	# log.debug(f"{API_TOKEN = }")

	async with httpx.AsyncClient() as client:

		match method:

			case "get":

				return await client.get(
					url = f"{JPS_URL}/{endpoint}",
					headers = {
						"Authorization": f"jamf-token {API_TOKEN}",
						"Accept": f"application/{in_content_type}"
					}
				)

			case "post" | "create":

				return await client.post(
					url = f"{JPS_URL}/{endpoint}",
					headers = {
						"Authorization": f"jamf-token {API_TOKEN}",
						"Content_type": f"application/{out_content_type}"
					},
					data = data
				)

			case "put" | "update":

				return await client.put(
					url = f"{JPS_URL}/{endpoint}",
					headers = {
						"Authorization": f"jamf-token {API_TOKEN}",
						"Content_type": f"application/{out_content_type}"
					},
					data = data
				)

			case "delete":

				return await client.delete(
					url = f"{JPS_URL}/{endpoint}",
					headers = { "Authorization": f"jamf-token {API_TOKEN}" }
				)

	return False


async def get_packages_from_policy(policy_object: str, content_type: str = "xml"):
	# Get the packages currently in the Policy configuration

	pkgs = []
	xml_object = ElementTree.ElementTree(ElementTree.fromstring(policy_object))

	for element in xml_object.getroot():
		if element.tag == "package_configuration":
			for packages in element.iter("packages"):
				for pkg in packages.iter("package"):
					pkgs.append({"id": pkg.find("id").text, "name": pkg.find("name").text})

	return pkgs
