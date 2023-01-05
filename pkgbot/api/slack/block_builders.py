from fastapi import Depends

from pkgbot import config
from pkgbot.utilities import common as utility
from pkgbot.db import models


log = utility.log
config = config.load_config()

secure = "s" if config.PkgBot.get("enable_ssl") else ""
pkgbot_server = f"http{secure}://{config.PkgBot.get('host')}:{config.PkgBot.get('port')}"


async def brick_header(pkg_object: models.Package_In = Depends(models.Package_In)):

	return {
		"type": "header",
		"text": {
			"type": "plain_text",
			"text": "New Software Version Available"
		}
	}


async def brick_main(pkg_object: models.Package_In = Depends(models.Package_In)):

	return {
		"type": "section",
		"text": {
			"type": "mrkdwn",
			"text": f"*Name:*  `{pkg_object.dict().get('name')}`\n*Version:*  `{pkg_object.dict().get('version')}`\n*Package Name:*  `{pkg_object.dict().get('pkg_name', 'Unknown')}`"
		},
		"accessory": {
			"type": "image",
			"image_url": f"{pkgbot_server}/static/icons/{pkg_object.dict().get('icon')}",
			"alt_text": ":new:"
		}
	}


async def brick_footer_dev(pkg_object: models.Package_In = Depends(models.Package_In)):

	return {
			"type": "context",
			"elements": [
				{
					"type": "mrkdwn",
					"text": f"*Dev*:  {pkg_object.dict().get('packaged_date')}\t*Uploaded by*:  @{config.Slack.get('bot_name')}"
				}
			]
		}


async def brick_footer_promote(pkg_object: models.Package_In = Depends(models.Package_In)):

	return {
			"type": "mrkdwn",
			"text": f"*Prod*:  {pkg_object.dict().get('promoted_date')}\t*Approved by*:  @{pkg_object.dict().get('status_updated_by')}"
		}


async def brick_footer_denied(pkg_object: models.Package_In = Depends(models.Package_In)):

	return {
			"type": "mrkdwn",
			"text": f"*Denied by*: @{pkg_object.dict().get('status_updated_by')}\t*On*:  {pkg_object.dict().get('last_update')}"
		}


async def brick_footer_denied_trust(trust_object):

	return {
			"type": "context",
			"elements": [
				{
					"type": "mrkdwn",
					"text": f"*Denied by*:  @{trust_object.dict().get('status_updated_by')}\t*On*:  {trust_object.dict().get('last_update')}"
				}
			]
		}


async def brick_button(pkg_object: models.Package_In = Depends(models.Package_In)):

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
				"image_url": f"{pkgbot_server}/static/icons/{config.PkgBot.get('icon_error')}",
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
					"text": f"*Updated by*:  @{trust_object.dict().get('status_updated_by')}\t*On*:  {trust_object.dict().get('last_update')}"
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
				"image_url": f"{pkgbot_server}/static/icons/{config.PkgBot.get('icon_error')}",
				"alt_text": ":x:"
			}
		}]


async def brick_deny_pkg(pkg_object: models.Package_In = Depends(models.Package_In)):

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
			"image_url": f"{pkgbot_server}/static/icons/{config.PkgBot.get('icon_denied')}",
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
			"image_url": f"{pkgbot_server}/static/icons/{config.PkgBot.get('icon_warning')}",
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
				"image_url": f"{pkgbot_server}/static/icons/{config.PkgBot.get('icon_permission_denied')}",
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


async def brick_accessory_image(image, alt_text=":notification:"):

	return {
		"accessory": {
			"type": "image",
			"image_url": f"{pkgbot_server}/static/icons/{image}",
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
				"image_url": f"{pkgbot_server}/static/icons/{image}",
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
