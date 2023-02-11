from itertools import groupby
from operator import itemgetter

from pkgbot import config
from pkgbot.db import models


config = config.load_config()

SECURE = "s" if config.PkgBot.get("enable_ssl") else ""
PKGBOT_SERVER = f"http{SECURE}://{config.PkgBot.get('host')}:{config.PkgBot.get('port')}"


async def brick_header(pkg_object: models.Package_In):

	return {
		"type": "header",
		"text": {
			"type": "plain_text",
			"text": "New Software Version Available"
		}
	}


async def brick_main(pkg_object: models.Package_In):

	return {
		"type": "section",
		"text": {
			"type": "mrkdwn",
			"text": f"*Name:*  `{pkg_object.dict().get('name')}`\n*Version:*  `{pkg_object.dict().get('version')}`\n*Package Name:*  `{pkg_object.dict().get('pkg_name', 'Unknown')}`"
		},
		"accessory": {
			"type": "image",
			"image_url": f"{PKGBOT_SERVER}/static/icons/{pkg_object.dict().get('icon')}",
			"alt_text": ":new:"
		}
	}


async def brick_footer_dev(pkg_object: models.Package_In):

	return {
			"type": "context",
			"elements": [
				{
					"type": "mrkdwn",
					"text": f"*Dev*:  {pkg_object.dict().get('packaged_date')}\t*Uploaded by*:  @{config.Slack.get('bot_name')}"
				}
			]
		}


async def brick_footer_promote(pkg_object: models.Package_In):

	return {
			"type": "mrkdwn",
			"text": f"*Prod*:  {pkg_object.dict().get('promoted_date')}\t*Approved by*:  @{pkg_object.dict().get('updated_by')}"
		}


async def brick_footer_denied(pkg_object: models.Package_In):

	return {
			"type": "mrkdwn",
			"text": f"*Denied by*: @{pkg_object.dict().get('updated_by')}\t*On*:  {pkg_object.dict().get('last_update')}"
		}


async def brick_footer_denied_trust(trust_object):

	return {
			"type": "context",
			"elements": [
				{
					"type": "mrkdwn",
					"text": f"*Denied by*:  @{trust_object.dict().get('updated_by')}\t*On*:  {trust_object.dict().get('last_update')}"
				}
			]
		}


async def brick_button(pkg_object: models.Package_In):

	return	(
		{
			"type": "section",
			"text": {
				"type": "mrkdwn",
				"text": "_Promote to production?_"
			}
		},
		{
			"type": "actions",
			"elements": [
				{
					"type": "button",
					"text": {
						"type": "plain_text",
						"emoji": True,
						"text": "Approve"
					},
					"style": "primary",
					"value": f"Package:{pkg_object.dict().get('id')}"
				},
				{
					"type": "button",
					"text": {
						"type": "plain_text",
						"emoji": True,
						"text": "Deny"
					},
					"style": "danger",
					"value": f"Package:{pkg_object.dict().get('id')}"
				}
			]
		}
	)


async def brick_error(recipe_id, error):

	return [{
			"type": "header",
			"text": {
				"type": "plain_text",
				"text": f"Encountered an error in:  {recipe_id}",
				"emoji": True
			}
		},
		{
			"type": "section",
			"text": {
				"type": "mrkdwn",
				"text": f"{error}",
				"verbatim": True
			},
			"accessory": {
				"type": "image",
				"image_url": f"{PKGBOT_SERVER}/static/icons/{config.PkgBot.get('icon_error')}",
				"alt_text": ":x:"
			}
		},
		{
			"type": "actions",
			"elements": [
				{
					"type": "button",
					"text": {
						"type": "plain_text",
						"emoji": True,
						"text": "Acknowledge"
					},
					"style": "danger",
					"value": "Error:ack"
				}
			]
		}]


async def brick_update_trust_success_msg(trust_object):

	return {
		"type": "section",
		"text": {
			"type": "mrkdwn",
			"text": f"Trust info was updated for:  `{trust_object.dict().get('recipe_id')}`",
			"verbatim": True
		}
	}


async def brick_footer_update_trust_success_msg(trust_object):

	return {
			"type": "context",
			"elements": [
				{
					"type": "mrkdwn",
					"text": f"*Updated by*:  @{trust_object.dict().get('updated_by')}\t*On*:  {trust_object.dict().get('last_update')}"
				}
			]
		}


async def brick_update_trust_error_msg(trust_object, msg):

	return [{
			"type": "header",
			"text": {
				"type": "plain_text",
				"text": f"Failed to update trust info for `{trust_object.dict().get('recipe_id')}`",
				"emoji": True
			}
		},
		{
			"type": "section",
			"text": {
				"type": "mrkdwn",
				"text": f"```{msg}```"
			},
			"accessory": {
				"type": "image",
				"image_url": f"{PKGBOT_SERVER}/static/icons/{config.PkgBot.get('icon_error')}",
				"alt_text": ":x:"
			}
		}]


async def brick_deny_pkg(pkg_object: models.Package_In):

	return {
		"type": "header",
		"text": {
			"type": "plain_text",
			"text": "This software package was denied"
		}
	}


async def brick_deny_trust(trust_object):

	return {
		"type": "section",
		"text": {
			"type": "mrkdwn",
			"text": f"Denied update to trust info for `{trust_object.dict().get('recipe_id')}`",
			"verbatim": True
		},
		"accessory": {
			"type": "image",
			"image_url": f"{PKGBOT_SERVER}/static/icons/{config.PkgBot.get('icon_denied')}",
			"alt_text": ":denied:"
		}
	}


async def brick_trust_diff_header():

	return {
		"type": "header",
		"text": {
			"type": "plain_text",
			"text": "Trust Verification Failure"
		}
	}


async def brick_trust_diff_main(recipe):

	return {
		"type": "section",
		"text": {
			"type": "mrkdwn",
			"text": f"*Recipe:*  `{recipe}`\n\n_Trust diff review required._\n\n",
			"verbatim": True
		},
		"accessory": {
			"type": "image",
			"image_url": f"{PKGBOT_SERVER}/static/icons/{config.PkgBot.get('icon_warning')}",
			"alt_text": ":warning:"
		}
	}


async def brick_trust_diff_content(error):

	return {
			"type": "section",
			"text": {
				"type": "mrkdwn",
				"text": f"*Diff Output:*```{error}```",
				"verbatim": True
			}
		}


async def brick_trust_diff_button(id):

	return {
			"type": "actions",
			"elements": [
				{
					"type": "button",
					"text": {
						"type": "plain_text",
						"emoji": True,
						"text": "Approve"
					},
					"style": "primary",
					"value": f"Trust:{id}"
				},
				{
					"type": "button",
					"text": {
						"type": "plain_text",
						"emoji": True,
						"text": "Deny"
					},
					"style": "danger",
					"value": f"Trust:{id}"
				}
			]
		}


async def unauthorized(user):
	return [
		{
			"type": "header",
			"text": {
				"type": "plain_text",
				"text": "PERMISSION DENIED:  Unauthorized User",
				"emoji": True
			}
		},
		{
			"type": "section",
			"text": {
				"type": "mrkdwn",
				"text": "_*Warning:*_  you are not a PkgBot admin and are not authorized to "
				f"perform this action.\n\n`{user}` will be reported to the "
				"robot overloads."
			},
			"accessory": {
				"type": "image",
				"image_url": f"{PKGBOT_SERVER}/static/icons/{config.PkgBot.get('icon_permission_denied')}",
				"alt_text": ":denied:"
			}
		}
	]


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


async def brick_disk_space_msg(header, msg, image):

	return [
		{
			"type": "header",
			"text": {
				"type": "plain_text",
				"text": f"Disk Usage {header}",
				"emoji": True
			}
		},
		{
			"type": "section",
			"text": {
				"type": "mrkdwn",
				"text": msg,
				"verbatim": True
			},
			"accessory": {
				"type": "image",
				"image_url": f"{PKGBOT_SERVER}/static/icons/{image}",
				"alt_text": ":warning:"
			}
		},
		{
			"type": "actions",
			"elements": [
				{
					"type": "button",
					"text": {
						"type": "plain_text",
						"emoji": True,
						"text": "Acknowledge"
					},
					"style": "danger",
					"value": "Error:ack"
				}
			]
		}
	]


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


async def modal_promote_pkg(pkg_name: str):

	return {
		"type": "modal",
		"callback_id": "promote_pkg",
		"private_metadata": f"{pkg_name}",
		"title": {
			"type": "plain_text",
			"text": "Promote pkg to Jamf Pro"
		},
		"submit": {
			"type": "plain_text",
			"text": "Promote  :rocket:",
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
					"text": f"Pkg to promote:  `{pkg_name}`"
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
