from fastapi import Depends

from pkgbot import config
from pkgbot.utilities import common as utility
from pkgbot.db import models


log = utility.log
config = config.load_config()


async def brick_header(pkg_object: models.Package_In = Depends(models.Package_In)):

	return {
		"type": "header",
		"text": {
			"type": "plain_text",
			"text": "New Software Version Available"
		}
	}


async def brick_main(pkg_object: models.Package_In = Depends(models.Package_In)):

	secure = "s" if config.PkgBot.get("enable_ssl") else ""
	pkgbot_server = f"http{secure}://{config.PkgBot.get('host')}:{config.PkgBot.get('port')}"

	return {
		"type": "section",
		"text": {
			"type": "mrkdwn",
			"text": f"*Name:*  `{pkg_object.dict().get('name')}`\n*Version:*  `{pkg_object.dict().get('version')}`\n*Package Name:*  `{pkg_object.dict().get('pkg_name', 'Unknown')}`"
		},
		"accessory": {
			"type": "image",
			"image_url": f"{pkgbot_server}/static/icons/{pkg_object.dict().get('icon')}",
			"alt_text": "computer thumbnail"
		}
	}


async def brick_footer_dev(pkg_object: models.Package_In = Depends(models.Package_In)):

	return {
			"type": "context",
			"elements": [
				{
					"type": "mrkdwn",
					"text": f"*Dev*:  {pkg_object.dict().get('packaged_date')}\t*Uploaded by*:  @PkgBot"
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
			"text": f"*Denied by*: @{pkg_object.dict().get('status_updated_by')}\t*On*:  @{pkg_object.dict().get('last_update')}"
		}


async def brick_footer_denied_trust(error_object):

	return {
			"type": "context",
			"elements": [
				{
					"type": "mrkdwn",
					"text": f"*Denied by*:  @{error_object.dict().get('status_updated_by')}\t*On*:  {error_object.dict().get('last_update')}"
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
				"text": f"```{error}```"
			},
			"accessory": {
				"type": "image",
				"image_url": "computer thumbnail",
				"alt_text": ":x:"
			}
		}]


async def brick_update_trust_success_msg(error_object):

	return {
		"type": "section",
		"text": {
			"type": "mrkdwn",
			"text": f"Trust info was updated for:  `{error_object.dict().get('recipe_id')}`"
		}
	}


async def brick_footer_update_trust_success_msg(error_object):

	return {
			"type": "context",
			"elements": [
				{
					"type": "mrkdwn",
					"text": f"*Updated by*:  @{error_object.dict().get('status_updated_by')}\t*On*:  {error_object.dict().get('last_update')}"
				}
			]
		}


async def brick_update_trust_error_msg(error_object, msg):

	return [{
			"type": "header",
			"text": {
				"type": "plain_text",
				"text": f"Failed to update trust info for `{error_object.dict().get('recipe_id')}`",
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
				"image_url": "computer thumbnail",
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


async def brick_deny_trust(error_object):

	return {
		"type": "section",
		"text": {
			"type": "mrkdwn",
			"text": f"Denied update to trust info for `{error_object.dict().get('recipe_id')}`"
		},
		# "accessory": {
		# 	"type": "image",
		# 	"image_url": "computer thumbnail",
		# 	"alt_text": ":x:"
		# }
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
			"text": f"*Recipe:*  `{recipe}`\n\n_Trust diff review required._\n\n"
		},
		# "accessory": {
		# 	"type": "image",
		# 	"image_url": "computer thumbnail",
		# 	"alt_text": ":x:"
		# }
	}


async def brick_trust_diff_content(error):

	return {
			"type": "section",
			"text": {
				"type": "mrkdwn",
				"text": f"*Diff Output:*```{error}```"
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
				"image_url": "https://as1.ftcdn.net/jpg/01/81/82/24/500_F_181822453_iQYjSxsW1AXa8FHOA6ecgdZEmrBdfInD.jpg",
				"alt_text": ":x:"
			}
		}
	]


async def missing_recipe_msg(recipe_id, text):

	return [
		{
			"type": "section",
			"text": {
				"type": "mrkdwn",
				"text": f"Failed to {text} `{recipe_id}`"
			},
			"accessory": {
				"type": "image",
				"image_url": "error",
				"alt_text": ":x:"
			}
		}
	]
