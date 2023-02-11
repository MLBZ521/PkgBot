import httpx

from xml.etree import ElementTree

from pkgbot import config


config = config.load_config()
JPS_URL = config.JamfPro_Prod.get("jps_url")
API_USER = config.JamfPro_Prod.get("api_user")
API_PASSWORD = config.JamfPro_Prod.get("api_password")


async def get_token(username: str = API_USER, password: str = API_PASSWORD):

	async with httpx.AsyncClient() as client:
		response_get_token = await client.post(
			f"{JPS_URL}/api/v1/auth/token", auth=(username, password))

	if response_get_token.status_code == 200:

		response_json = response_get_token.json()
		return response_json["token"], response_json["expires"]

	return False


async def api(method: str, endpoint: str, in_content_type: str = "json", out_content_type = "xml",
	data: str | dict | None = None, api_token: str = None, username: str = API_USER,
	password: str = API_PASSWORD):

	if not api_token:
		api_token, api_token_expires = await get_token(username, password)

	async with httpx.AsyncClient() as client:

		match method:

			case "get":

				return await client.get(
					url = f"{JPS_URL}/{endpoint}",
					headers={
						"Authorization": f"jamf-token {api_token}",
						"Accept": f"application/{in_content_type}"
					}
				)

			case "post" | "create":

				return await client.post(
					url = f"{JPS_URL}/{endpoint}",
					headers={
						"Authorization": f"jamf-token {api_token}",
						"Content_type": f"application/{out_content_type}"
					},
					data = data
				)

			case "put" | "update":

				return await client.put(
					url = f"{JPS_URL}/{endpoint}",
					headers={
						"Authorization": f"jamf-token {api_token}",
						"Content_type": f"application/{out_content_type}"
					},
					data = data
				)

			case "delete":

				return await client.delete(
					url = f"{JPS_URL}/{endpoint}",
					headers={ "Authorization": f"jamf-token {api_token}" }
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
