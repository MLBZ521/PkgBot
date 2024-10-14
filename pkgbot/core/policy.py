import re

from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree

from tortoise.expressions import Q

from pkgbot import config, core
from pkgbot.db import models, schemas
from pkgbot.utilities import common as utility


config = config.load_config()
log = utility.log


async def get(policy_filter: dict | Q | None = None):

	if not policy_filter:
		return await models.Policies.all()
	elif isinstance(policy_filter, dict):
		results = await schemas.Policy_Out.from_queryset(models.Policies.filter(**policy_filter))
	elif isinstance(policy_filter, Q):
		results = await schemas.Policy_Out.from_queryset(models.Policies.filter(policy_filter))

	return results[0] if len(results) == 1 else results


async def delete(recipe_filter: dict):

	return await models.Policies.filter(**recipe_filter).delete()


async def cache_policies():

	log.debug("Caching Policies from Jamf Pro...")
	api_token, api_token_expires = await core.jamf_pro.get_token()
	all_policies_response = await core.jamf_pro.api(
		"get", "JSSResource/policies", api_token=api_token)

	if all_policies_response.status_code != 200:
		raise("Failed to get list of Policies!")

	all_policies = all_policies_response.json()
	log.debug(f"Number of Policies found:  {len(all_policies.get('policies'))}")

	# Get the Policy IDs
	policy_ids = [ policy.get("id") for policy in all_policies.get("policies") ]
	# log.debug(f"Number of Policy IDs:  {len(policy_ids)}")

	# Get all cached Policies and their IDs
	all_cache_policies = await get()
	cache_policy_ids = [ policy.policy_id for policy in all_cache_policies ]
	# log.debug(f"Number of cached Policy IDs:  {len(cache_policy_ids)}")

	# Get Policy IDs from cached Policies if they aren't in the "new" Policy IDs list
	deleted_policy_ids = [
		policy_id for policy_id in cache_policy_ids if policy_id not in policy_ids ]
	log.debug(f"Number of cached Policies to delete:  {len(deleted_policy_ids)}")

	for policy_id in deleted_policy_ids:
		log.debug(f"Deleting Policy:  {policy_id}")
		await delete( { "policy_id": policy_id } )

	for policy in all_policies.get("policies"):

		if datetime.now(timezone.utc) > (api_token_expires - timedelta(minutes=5)):
			log.debug("Replacing API Token...")
			api_token, api_token_expires = await core.jamf_pro.get_token()

		policy_details_response = await core.jamf_pro.api(
			"get", f"JSSResource/policies/id/{policy.get('id')}", api_token=api_token)

		if policy_details_response.status_code != 200:
			raise(f"Failed to get policy details for:  {policy.get('id')}:{policy.get('name')}!")

		policy_details = policy_details_response.json()
		policy_general = policy_details.get("policy").get("general")

		result, result_bool = await models.Policies.update_or_create(
			defaults = {
				"name": policy_general.get("name"),
				"site": policy_general.get("site").get("name"),
			},
			policy_id = policy_general.get("id")
		)

		# Clear the current policy <-> package relationship (aka flush table of this Policy)
		await result.packages.clear()
		await result.packages_manual.clear()

		policy_packages = policy_details.get("policy").get("package_configuration").get("packages")

		for package in policy_packages:
			pkg_object = await models.Packages.get_or_none(**{ "pkg_name": package.get("name")})
			if pkg_object:
				await result.packages.add(pkg_object)
			else:
				pkg_name = package.get("name")

				try:
					version = re.sub("\.(pkg|dmg)", "", pkg_name.rsplit("-", 1)[1])
				except re.ex:
					version = "1.0"

				pkg_details = {
					"name": pkg_name.rsplit("-", 1)[0],
					"pkg_name": pkg_name,
					"version": version,
					"status": "prod"
				}

				pkg_object = (await models.PackagesManual.get_or_create(**pkg_details))[0]
				await result.packages_manual.add(pkg_object)

	log.debug("Caching Policies from Jamf Pro...COMPLETE")
	return


async def update_policy(policy_object, pkg_object, username, trigger_id):

	# api_token, api_token_expires = await core.jamf_pro.get_token()

	log.debug(f"Getting details for Policy ID:  {policy_object.policy_id}")
	policy_xml_response  = await core.jamf_pro.api(
		"get",
		f"JSSResource/policies/id/{policy_object.policy_id}",
		in_content_type = "xml",
		# api_token = api_token
	)

	if policy_xml_response.status_code != 200:
		raise(f"Failed to get policy details for:  {policy_object.policy_id}:{policy_object.name}!")

	policy_xml = policy_xml_response.text
	current_packages = await core.jamf_pro.get_packages_from_policy(policy_xml, "xml")
	log.debug(f"Current Policy Packages:  {current_packages}")
	log.debug(f"New Package to Add:  {pkg_object.pkg_name}")

	pkg_name = pkg_object.pkg_name.split("-", 1)[0]
	pkg_name = re.sub(r"\s\((Universal|Intel|ARM)\)", "", pkg_name)
	pkg_name = re.sub(r"\s", "[ _-]", pkg_name)

	for pkg in current_packages:
		if re.search(pkg_name, pkg.get("name")):
			log.debug(f"Removing package:  {pkg.get('name')}")
			current_packages.remove(pkg)
		pkg |= {"action": "Install"}

	current_packages.append({"name": pkg_object.pkg_name, "action": "Install"})
	log.debug(f"Packages to add to Policy:  {current_packages}")

	new_xml_object = await utility.build_xml(
		"policy", "package_configuration", "package", current_packages, sub_element="packages")
	new_policy_xml = (ElementTree.tostring(new_xml_object)).decode("UTF-8")

	update_policy_results = await core.jamf_pro.api(
		"put",
		f"JSSResource/policies/id/{policy_object.policy_id}",
		out_content_type = "xml",
		data = new_policy_xml,
		# api_token = api_token
	)

	if update_policy_results.status_code != 201:
		log.error(f"Failed to promote a package!  Details:\nUser:  {username}\n"
			f"Policy ID:  {policy_object.policy_id}\nnew_policy_xml:  {new_policy_xml}\n"
			f"Reason:  {update_policy_results.text}"
		)
		restore_policy_results = await core.jamf_pro.api(
			"put",
			f"JSSResource/policies/id/{policy_object.policy_id}",
			out_content_type = "xml",
			data = (ElementTree.tostring(policy_xml)).decode("UTF-8"),
			# api_token = api_token
		)

		if restore_policy_results.status_code != 201:
			log.error(f"Failed to restore the policy!  Details:\nUser:  {username}\n"
				f"Policy ID:  {policy_object.policy_id}\nReason:  {restore_policy_results.text}"
			)

	log.debug(f"{username} added {pkg_object.pkg_name} into {policy_object.site} "
		f"{policy_object.policy_id} {policy_object.name}")

	await core.chatbot.send.modal_notification(
		trigger_id,
		"Added Package",
		f"Successfully added `{pkg_object.pkg_name}` into:\n*Site*:  `{policy_object.site}`\n"
			f"*Policy ID*:  `{policy_object.policy_id}`\n*Policy Name*:  `{policy_object.name}`",
		":yayblob: :jamf:"
	)

	return
