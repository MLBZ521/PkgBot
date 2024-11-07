from itertools import groupby
from operator import itemgetter

from pkgbot import config


config = config.load_config()

SECURE = "s" if config.PkgBot.get("enable_ssl") else ""
PKGBOT_SERVER = f"http{SECURE}://{config.PkgBot.get('host')}"
if config.PkgBot.get('port'):
	PKGBOT_SERVER = f"{PKGBOT_SERVER}:{config.PkgBot.get('port')}"

async def brick_header(text):

	return {
		"type": "header",
		"text": {
			"type": "plain_text",
			"text": text
		}
	}


async def brick_section_text(text):

	return {
		"type": "section",
		"text": {
			"type": "mrkdwn",
			"text": text,
			"verbatim": True
		}
	}


async def brick_accessory_image(image, alt_text):

	alt_text = alt_text or ":notification:"

	return {
		"accessory": {
			"type": "image",
			"image_url": f"{PKGBOT_SERVER}/static/icons/{image}",
			"alt_text": alt_text
		}
	}


async def button_element_creator(text: str, style: str, value: str):
	#  Commonly used `style` options are:
		# primary
		# danger

	return {
		"type": "button",
		"text": {
			"type": "plain_text",
			"emoji": True,
			"text": text
		},
		"style": style,
		"value": value
	}


async def brick_action_buttons(button_details: list):
	# button_details = [("Approve", "primary", "Package:1"), ("Deny", "danger", "Deny:1")]

	elements = [
		await button_element_creator(text, type, value) for text, type, value in button_details ]

	return	(
		{
			"type": "actions",
			"elements": elements
		}
	)


async def footer_element_creator(text: str):

	return {
		"type": "mrkdwn",
		"text": text
	}


async def brick_footer(footer_details):

	return {
			"type": "context",
			"elements": [ await footer_element_creator(text) for text in footer_details ]
		}


async def modal_notification(title_txt: str, button_text: str):
	# An undocumented limitation:  maximum 26 characters in the `title.text` string

	return {
		"type": "modal",
		"callback_id": "notification",
		# "private_metadata": f"{private_metadata}",
		"title": {
			"type": "plain_text",
			"text": f"{title_txt}",
			"emoji": True
		},
		"close": {
			"type": "plain_text",
			"text": f"{button_text}",
			"emoji": True
		}
	}


async def modal_add_pkg_to_policy(pkg_name: str):

	return {
		"type": "modal",
		"callback_id": "add_pkg_to_policy",
		"private_metadata": f"{pkg_name}",
		"title": {
			"type": "plain_text",
			"text": "Add Package to Policy in Jamf Pro"
		},
		"submit": {
			"type": "plain_text",
			"text": "Add  :rocket:",
			"emoji": True
		},
		"close": {
			"type": "plain_text",
			"text": "Cancel"
		},
		"blocks": [
			{
				"type": "section",
				"text": {
					"type": "mrkdwn",
					"text": "Select Policy to add or update the existing version of the selected pkg."
				}
			},
			{
				"type": "divider"
			},
			{
				"type": "section",
				"text": {
					"type": "mrkdwn",
					"text": f"Package:  `{pkg_name}`"
					# If the value for `text`above is change, it will break logic in:
					# 	../../pkgbot/core/chatbot/slack/events/view_submission
				}
			},
			{
				"type": "input",
				"element": {
					"type": "external_select",
					"placeholder": {
						"type": "plain_text",
						"text": "Select a Policy",
						"emoji": True
					},
					"min_query_length": 5,
					"action_id": "policy_list"
				},
				"label": {
					"type": "plain_text",
					"text": "Select a Policy and :ship_it_parrot:",
					"emoji": True
				}
			}
		]
	}


async def policy_list(policies: str):

	option_groups = []
	policies = sorted(policies, key=itemgetter("site"))

	# This _is_ a documented limitation:  maximum of 100 options can be included in a list
	for site, value in groupby(policies[:99], key=itemgetter("site")):
		options = []

		for policy in value:
			options.append(await create_static_option(policy))

		if options:
			option_groups.append({
				"label": {
					"type": "plain_text",
					"text": f"Site:  {site}"
				},
				"options": options
			})

	return {
		"option_groups": option_groups
	}


async def create_static_option(policy):

	return {
		"text": {
			"type": "plain_text",
			# This seems to be an undocumented limitation:
				# maximum of 76 characters in the `text` string
			"text": policy.get("name")[:75],
			"emoji": True
		},
		"value": f"{policy.get('policy_id')}"
	}
