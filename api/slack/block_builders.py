#!/usr/local/autopkg/python

from fastapi import Depends

import utils
from db import models

log = utils.log

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
			"text": "*Name:*  `{}`\n*Version:*  `{}`\n*Package Name:*  `{}`".format(
				pkg_object.dict().get("name"), pkg_object.dict().get("version"), 
				pkg_object.dict().get("pkg_name", "Unknown")
			)
		},
		"accessory": {
			"type": "image",
			"image_url": "{}/iconservlet/?id={}".format(pkg_object.dict().get("jps_url"), 
				pkg_object.dict().get("icon_id")
			),
			"alt_text": "computer thumbnail"
		}
	}


async def brick_footer_dev(pkg_object: models.Package_In = Depends(models.Package_In)):

	return {
			"type": "context",
			"elements": [
				{
					"type": "mrkdwn",
					"text": "*Dev*:  {}\t*Uploaded by*:  @{}".format(
						pkg_object.dict().get("packaged_date"), "PkgBot")
				}
			]
		}


async def brick_footer_promote(pkg_object: models.Package_In = Depends(models.Package_In)):

	return {
			"type": "mrkdwn",
			"text": "*Prod*:  {}\t*Approved by*:  @{}".format(
				pkg_object.dict().get("promoted_date"), pkg_object.dict().get("status_updated_by")
			)
		}


async def brick_footer_denied(pkg_object: models.Package_In = Depends(models.Package_In)):

	return {
			"type": "mrkdwn",
			"text": "*Denied by*: @{}\t*On*:  @{}".format(
				pkg_object.dict().get("status_updated_by"), pkg_object.dict().get("last_update"))
		}


async def brick_footer_denied_trust(error_object):

	return {
			"type": "context",
			"elements": [
				{
					"type": "mrkdwn",
					"text": "*Denied by*:  @{}\t*On*:  {}".format(
						error_object.dict().get("status_updated_by"), 
						error_object.dict().get("last_update"))
				}
			]
		}


async def brick_button(pkg_object: models.Package_In = Depends(models.Package_In)):

	return 	(
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
					"value": "Package:{}".format(pkg_object.dict().get("id"))
				},
				{
					"type": "button",
					"text": {
						"type": "plain_text",
						"emoji": True,
						"text": "Deny"
					},
					"style": "danger",
					"value": "Package:{}".format(pkg_object.dict().get("id"))
				}
			]
		}
	)


async def brick_error(recipe_id, error):

	return [{
			"type": "header",
			"text": {
				"type": "plain_text",
				"text": "Encountered an error in:  {}".format(recipe_id),
				"emoji": True
			}
		},
		{
			"type": "section",
			"text": {
				"type": "mrkdwn",
				"text": "```{}```".format(error)
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
			"text": "Trust info was updated for:  `{}`".format(
				error_object.dict().get("recipe_id"))
		}
	}


async def brick_footer_update_trust_success_msg(error_object):

	return {
			"type": "context",
			"elements": [
				{
					"type": "mrkdwn",
					"text": "*Updated by*:  @{}\t*On*:  {}".format(
						error_object.dict().get("status_updated_by"), 
						error_object.dict().get("last_update"))
				}
			]
		}


async def brick_update_trust_error_msg(error_object, msg):

	return [{
			"type": "header",
			"text": {
				"type": "plain_text",
				"text": "Failed to update trust info for `{}`".format(
					error_object.dict().get("recipe_id")),
				"emoji": True
			}
		},
		{
			"type": "section",
			"text": {
				"type": "mrkdwn",
				"text": "```{}```".format(msg)
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
			"text": "Denied update to trust info for `{}`".format(
				error_object.dict().get("recipe_id"))
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
			"text": "*Recipe:*  `{}`\n\n_Trust diff review required._\n\n".format(recipe)
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
				"text": "*Diff Output:*```{}```".format(error)
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
					"value": "Trust:{}".format(id)
				},
				{
					"type": "button",
					"text": {
						"type": "plain_text",
						"emoji": True,
						"text": "Deny"
					},
					"style": "danger",
					"value": "Trust:{}".format(id)
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
				"perform this action.\n\n`{}` will be reported to the "
				"robot overloads.".format(user)
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
				"text": "Failed to {} `{}`".format(text, recipe_id),
			},
			"accessory": {
				"type": "image",
				"image_url": "error",
				"alt_text": ":x:"
			}
		}
	]
