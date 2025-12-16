import re

from xml.etree import ElementTree

from celery import current_app as pkgbot_celery_app

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


async def create_or_update(policy_object: schemas.Policy_In):

	return await models.Policies.update_or_create(
		defaults = {
			"name": policy_object.dict().get("name"),
			"site": policy_object.dict().get("site"),
		},
		policy_id = policy_object.dict().get("policy_id")
	)


async def delete(policy_filter: dict):

	policy_obj = await models.Policies.filter(**policy_filter).first()
	return await policy_obj.delete()


async def cache_policies(source: str | None = None, called_by: str | None = None):

	return pkgbot_celery_app.send_task(
		"pkgbot:cache_policies",
		kwargs = {
			"source": source,
			"called_by": called_by
		},
		queue="pkgbot",
		priority=3
	)


async def update_policy(policy_object, pkg_object, username, trigger_id):

	log.debug(f"Getting details for Policy ID:  {policy_object.policy_id}")
	policy_xml_response  = await core.jamf_pro.api(
		"get",
		f"JSSResource/policies/id/{policy_object.policy_id}",
		in_content_type = "xml",
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
	)

	if update_policy_results.status_code != 201:
		log.error(f"Failed to add package to Policy!  Details:\nUser:  {username}\n"
			f"Policy ID:  {policy_object.policy_id}\nnew_policy_xml:  {new_policy_xml}\n"
			f"Reason:  {update_policy_results.text}"
		)
		restore_policy_results = await core.jamf_pro.api(
			"put",
			f"JSSResource/policies/id/{policy_object.policy_id}",
			out_content_type = "xml",
			data = (ElementTree.tostring(policy_xml)).decode("UTF-8"),
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
