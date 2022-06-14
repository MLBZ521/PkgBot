#!/usr/local/autopkg/python

import argparse
import asyncio
import os
import re
import sys

sys.path.insert(0, "/Library/AutoPkg/PkgBot")

import utils
from execute import api_helper


log = utils.log


def create_recipe_config(recipe_object, **kwargs):

	# Run through parameters
	if kwargs.get('disable'):
		recipe_object["enabled"] = False

	elif kwargs.get('enable'):
		recipe_object["enabled"] = True

	else:
		recipe_object.setdefault("enabled", True)

	if kwargs.get('pkg_only'):
		recipe_object["pkg_only"] = True

	elif kwargs.get('policy'):
		recipe_object["pkg_only"] = False

	else:
		recipe_object.setdefault("pkg_only", False)

	if kwargs.get('schedule'):
		recipe_object["schedule"] = kwargs.get('schedule')

	else:
		recipe_object.setdefault("schedule", 0)

	recipe_object["name"] = recipe_object["recipe_id"].rsplit(".", 1)[1]

	# recipe_object.setdefault("last_ran", 0)

	return recipe_object


async def main(run_args=sys.argv[1:]):

	if "manage" in run_args:
		run_args.remove("manage")

	# log.debug('Recipe Manager:\n\tAll calling args:  {}'.format(run_args))
	# log.debug('Recipe Manager:\n\tsys.argv:  {}'.format(sys.argv))

	##################################################
	# Setup Argparse

	parser = argparse.ArgumentParser(description="Manage recipe configuration file.")
	sub_parsers = parser.add_subparsers(dest='action', 
	   title="Available actions", help="Specify which action to perform.")

	parser_import = sub_parsers.add_parser('import', 
		help='Import a recipe configuration file')
	parser_import.add_argument('--input', '-n', metavar='./path/to/recipe_config.yaml', type=str, 
		required=True, help='A file read in defined recipe configurations.')

	parser_generate = sub_parsers.add_parser('generate', 
		help='Generate a recipe configuration file')
	parser_generate.add_argument('--recipes-directory', '-rd', 
		metavar='./path/to/autopkg/recipes/', type=str, required=True, 
		help='The directory where your recipes are stored.')
	parser_generate.add_argument('--output', '-o', metavar='./path/to/recipe_config.yaml', type=str, 
		required=True, help='Where to save generated recipe configurations.')

	parser_manage = sub_parsers.add_parser('single', 
		help='Perform actions on individual recipe configurations')
	parser_manage.add_argument('--recipe-identifier', '-i', metavar='local.Firefox', type=str, 
		required=True, help='A recipe identifier.')
	parser_manage.add_argument('--schedule', '-s', type=int, required=False, 
		help='An integer which will be the number of days between running the recipe.')
	parser_manage.add_argument('--remove', '-rm', default=False, action='store_true', 
		required=False, help='Remove recipe from list.')
	parser_manage.add_argument('--force', '-f', default=False, action='store_true', required=False, 
		help='If recipe config already exists, force the changes without prompting.')

	state = parser_manage.add_mutually_exclusive_group()
	state.add_argument('--enable', '-e', default=False, action='store_true', required=False, 
		help='Enable the recipe to be processed.')
	state.add_argument('--disable', '-d', default=False, action='store_true', required=False, 
		help='Disable the recipe from being processed.')

	jps_handler = parser_manage.add_mutually_exclusive_group()
	jps_handler.add_argument('--pkg-only', '-k', default=False, action='store_true', required=False, 
		help='Only upload the .pkg and do not create a Policy or any other modifications.')
	jps_handler.add_argument('--policy', '-rk', default=False, action='store_true', required=False, 
		help='Remove the `pkg_only` flag.')

	##################################################
	# Parse Script Arguments

	args, unknown = parser.parse_known_args(run_args)

	if len(run_args) == 0:
		parser.print_help()
		sys.exit(0)

	if args.action == "generate":

		save_path = args.output

		log.info("Generating recipe config file:  {}.".format(save_path))

		if os.path.exists(save_path):
			log.warning("WARNING:  This recipe configuration file already exists")
			override_answer = await utils.ask_yes_or_no(
				"Do you want to overwrite your recipe configuration file?")

			if not override_answer:
				log.info("No changes were made.")
				sys.exit(0)

		if not os.path.exists(args.recipes_directory):
			log.error("ERROR:  Unable to locate recipe directory!")
			sys.exit(1)

		recipes = []

		# Walk the directory provided for recipes
		for root, folders, files in os.walk(args.recipes_directory):

			# Loop through the files and perform the changes desired
			for a_file in files:

				# Verify file has a .recipe extension
				if re.search('.recipe', a_file) and re.search(r'^((?!Retired).)*$', os.path.join(root, a_file)):

					recipes.append(os.path.join(root, a_file))

		log.info("Found {} recipes.".format(len(recipes)))

		recipe_configs = {}

		for recipe_item in recipes:

			# Read in the recipe
			plist_contents = await utils.plist_reader(recipe_item)

			# Pull information that will be checked later
			identifier = plist_contents.get('Identifier')

			recipe_config = create_recipe_config({"recipe_id": identifier}, **args.__dict__)

			recipe_configs[identifier] = recipe_config

		all_recipe_configurations = {}
		all_recipe_configurations["recipes"] = dict(sorted(recipe_configs.items()))

		await utils.save_yaml(all_recipe_configurations, save_path)

		log.info("Recipe config file saved.")

	elif args.action == "import":

		log.info("Importing recipe config file from:  {}.".format(args.input))

		# Load the recipe config
		recipe_configurations = await utils.load_yaml(args.input)

		# Get the recipes object
		recipes = recipe_configurations.get("recipes")

		for recipe_item in recipes:

			recipe_config = recipes.get(recipe_item)
			recipe_config["recipe_id"] = recipe_item
			recipe_config["name"] = recipe_item.rsplit(".", 1)[1]

			await api_helper.create_recipe(recipe_config)

		log.info("All recipe configurations have been imported!")

	else:

		recipe_id = args.recipe_identifier

		recipe_object = ( await api_helper.get_recipe_by_recipe_id(recipe_id) ).json()

		if recipe_object.get("detail") == "Object does not exist":
			# Recipe does not exist in the database.
			recipe_object = None

		if args.remove:

			if not recipe_object:
				log.info("Recipe does not exist in the database.")

			else:

				if not args.force:

					log.warning("WARNING:  The recipe `{}` is about to be removed.".format(recipe_id))
					remove_answer = await utils.ask_yes_or_no(
						"Do you want to remove this recipe's definition?")

				if args.force or remove_answer:

					await api_helper.delete_recipe_by_recipe_id(recipe_id)

					log.info("Recipe config removed:  {}.".format(recipe_id))

				else:

					log.info("No changes were made.")

		else:

			if not recipe_object:

				log.info("Creating the recipe config for:  {}.".format(recipe_id))

				# If the recipe does not exist, create an empty dict object for it
				recipe_config = create_recipe_config({"recipe_id": recipe_id}, **args.__dict__)
				await api_helper.create_recipe(recipe_config)

			else:

				# The recipe already exists
				log.info("Updating the recipe config for:  {}.".format(recipe_id))

				recipe_object.pop('id')

				recipe_config = create_recipe_config(recipe_object, **args.__dict__)

				# Confirm changes
				if not args.force:

					log.warning("WARNING:  This recipe already exists")
					override_answer = await utils.ask_yes_or_no(
						"Do you want to override this recipe's definition?")

				# Write changes
				if args.force or override_answer:

					await api_helper.update_recipe_by_recipe_id(recipe_object["recipe_id"], recipe_config)

				else:

					log.info("No changes were made.")

#### SOME ERROR CHECKING SHOULD PROBABLY GO BEFORE HERE
			log.info("Recipe config saved for:  {}".format(recipe_id))


if __name__ == "__main__":
	asyncio.run( main(sys.argv) )
