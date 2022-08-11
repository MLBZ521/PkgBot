#!/usr/bin/env python3

import argparse
import asyncio
import sys

sys.path.insert(0, "/Library/AutoPkg/PkgBot")

import utilities.common as utility
from execute import recipe_manager, recipe_runner


log = utility.log


async def main(run_args=sys.argv[1:]):
	# log.debug("All calling args:  {}".format(sys.argv))
	# log.debug("All calling args:  {}".format(run_args))

	##################################################
	# Parse Script Arguments

	parser = argparse.ArgumentParser(description="PkgBot Main.")
	sub_parsers = parser.add_subparsers(dest="actions", 
		title="Available actions", help="Specify which action to perform.")

	# This group controls switches for the `recipe_runner` module
	parser_run = sub_parsers.add_parser("run", help="Run Recipe(s)")
	parser_run.set_defaults(call_function=recipe_runner.main)
	parser_run.add_argument("--pkgbot-config", "-p", metavar="./config.yaml", type=str, 
		required=False, help="A config file with defined environmental configurations.")
	parser_run.add_argument("--environment", "-e", type=str, default="dev", required=False, 
		help="Which environment to use.")
	parser_run.add_argument("--action", choices=[ "promote", "trust" ], required=False, 
		help="Perform the requested action on the passed recipe id.")
	run_type = parser_run.add_mutually_exclusive_group()
	run_type.add_argument("--all", "-a", action="store_true", required=False, 
		help="Runs all the recipes in the specified recipe_config file.")
	run_type.add_argument("--recipe-identifier", "-i", metavar="local.Firefox", required=False, 
		type=str, help="A recipe identifier.")

	# This group controls switches for the `recipe_manager` module
	parser_manage = sub_parsers.add_parser("manage", 
		help="Manage recipe configuration file.")
	parser_manage.set_defaults(call_function=recipe_manager.main)

	manage_sub_parsers = parser_manage.add_subparsers(dest="action", 
	   title="Available actions", help="Specify which action to perform.")

	parser_import = manage_sub_parsers.add_parser("import", 
		help="Import a recipe configuration file")
	parser_import.add_argument("--input", "-n", metavar="./path/to/recipe_config.yaml", type=str, 
		required=True, help="A file read in defined recipe configurations.")

	parser_generate = manage_sub_parsers.add_parser("generate", 
		help="Generate a recipe configuration file")
	parser_generate.add_argument("--recipes-directory", "-rd", 
		metavar="./path/to/autopkg/recipes/", type=str, required=True, 
		help="The directory where your recipes are stored.")

	parser_single = manage_sub_parsers.add_parser("single", 
		help="Perform actions on individual recipe configurations")
	parser_single.add_argument("--recipe-identifier", "-i", metavar="local.Firefox", type=str, 
		required=True, help="A recipe identifier.")
	parser_single.add_argument("--schedule", "-s", type=int, required=False, 
		help="An integer which will be the number of days between running the recipe.")
	parser_single.add_argument("--remove", "-rm", default=False, action="store_true", 
		required=False, help="Remove recipe from list.")
	parser_single.add_argument("--force", "-f", default=False, action="store_true", required=False, 
		help="If recipe config already exists, force the changes without prompting.")
	state = parser_single.add_mutually_exclusive_group()
	state.add_argument("--enable", "-e", default=False, action="store_true", required=False, 
		help="Enable the recipe to be processed.")
	state.add_argument("--disable", "-d", default=False, action="store_true", required=False, 
		help="Disable the recipe from being processed.")
	jps_handler = parser_single.add_mutually_exclusive_group()
	jps_handler.add_argument("--pkg-only", "-k", default=False, action="store_true", required=False, 
		help="Only upload the .pkg and do not create a Policy or any other modifications.")
	jps_handler.add_argument("--policy", "-rk", default=False, action="store_true", required=False, 
		help="Create a Policy.")

	args, unknown = parser.parse_known_args(run_args)
	# log.debug("Argparse args:  {}".format(args))

	if len(run_args) == 0:
		parser.print_help()
		sys.exit(0)

	else:

		# Load Configuration
		# if args.pkgbot_config:
		#     config.load(pkgbot_config=args.pkgbot_config)

		# else:
		#     config.load()

		await args.call_function()


if __name__ == "__main__":
	asyncio.run(main())
