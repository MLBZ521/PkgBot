#!/usr/local/autopkg/python
#
# Copyright 2022 Zack Thompson (MLBZ521)
#
# Inspired by Graham R Pugh's `JSSRecipeReceiptChecker.py`
#   https://github.com/autopkg/grahampugh-recipes/blob/main/CommonProcessors/JSSRecipeReceiptChecker.py
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""See docstring for PkgBotPromoter class"""

import plistlib
import re

from glob import iglob
from os.path import basename, exists, expanduser, getmtime

from autopkglib import Processor, ProcessorError


__all__ = ["PkgBotPromoter"]


class PkgBotPromoter(Processor):
	"""An AutoPkg processor which works out the latest receipt from a different AutoPkg recipe,
	and provides useful values from its contents, which can be used to run a different recipe
	based on those values."""

	description = __doc__
	input_variables = {
		"name": {
			"description": (
				"This value should be the same as the NAME in the recipe from which we want "
				"to read the receipt. This is all we need to construct the override path."
				"Assumes the Recipe ID is in the format of:  local.jamf.<name>"
			),
			"required": False
		},
		"recipe_id": {
			"description": (
				"If the recipe name does not match the NAME variable, "
				"this value can be used to override NAME."
			),
			"required": False
		},
		"match_pkg": {
			"description": (
				"The name of the package to match within a receipt.  This is to "
				"ensure the version that is promoted matches what is intended."
			),
			"required": False
		},
		"cache_dir": {
			"description": "Path to the cache dir.",
			"default": "~/Library/AutoPkg/Cache",
			"required": False
		},
		"custom_variables": {
			"description": (
				"An array of custom input variables that should be pulled from the latest "
				"receipt.  These would generally be unique to your environment."
			),
			"required": False
		}
	}
	output_variables = {
		"version": {
			"description": "The current package version."
		},
		"pkg_path": {
			"description": "The package path."
		},
		"PARENT_RECIPES": {
			"description": "The parent recipes, used to locate the self service icon."
		}
	}


	def get_recipe_receipts(self, cache_dir, name):
		"""Get the receipts for the passed recipe name.

		Args:
			cache_dir (str): Path to the AutoPkg cache directory.
			name (str): Recipe NAME or ID.

		Raises:
			ProcessorError: Unable to locate receipts for the provided recipe.

		Returns:
			list: A list of recipe receipts.
		"""

		self.output(f"Checking for receipts in folder {cache_dir}/{name}")

		try:
			files = list(iglob(f"{cache_dir}/*{name}/receipts/*.plist"))
			files.sort(key=lambda x: getmtime(x), reverse=True)
			return files

		except IOError as error:
			raise ProcessorError("No receipts found!") from error


	def main(self):
		"""Find the latest receipt that contains all the information we're looking for.

		Raises:
			ProcessorError: Proper input variables must be supplied.
			ProcessorError: Package does not exist at the path found.
			ProcessorError: Unable to locate a receipt with the desired information.
		"""

		name = self.env.get("name")
		recipe_id = self.env.get("recipe_id")
		match_pkg = self.env.get("match_pkg")
		custom_variables = self.env.get("custom_variables", [])
		cache_dir = expanduser(self.env.get("cache_dir", "~/Library/AutoPkg/Cache"))
		version_found = False
		found_parent_recipes = False

		# Do not pull these values incase they're different
		ignore_keys = [ "API_PASSWORD", "API_USERNAME", "JSS_REPOS", "JSS_URL", "JSS_VERIFY_SSL" ]

		if name:
			name = f"local.jamf.{name}"

		elif recipe_id:
			name = recipe_id

		else:
			raise ProcessorError("Either 'name' or 'recipe_id' must be provided.")

		receipts = self.get_recipe_receipts(cache_dir, name)

		for receipt in receipts:

			try:
				self.output(f"Scanning receipt:  {receipt}")

				with open(receipt, 'rb') as plist_receipt:
					plist = plistlib.load(plist_receipt)

				# Check the last step, if it's a Error, skip it
				if str(plist[-1].keys()) == "dict_keys(['RecipeError'])":
					self.output("  -> Skipping as this receipt had an error...")
					continue

				for step in plist:

					processor = step.get("Processor")
					processor_input = step.get("Input", None)
					processor_output = step.get("Output", None)

					if step.get("Recipe input"):
						self.output("Checking the  Recipe input section...", verbose_level=3)
						recipe_input = step.get("Recipe input")

						if parent_recipes := recipe_input.get("PARENT_RECIPES"):
							found_parent_recipes = True
							parent_recipes.extend(
								[recipe_input.get("RECIPE_DIR"), recipe_input.get("RECIPE_PATH")])

						for key in custom_variables:
							self.env[key] = recipe_input.get(key)
							self.output(f"{key}:  {self.env[key]}", verbose_level=3)

						self.env["NAME"] = recipe_input.get("NAME")
						self.output(f'NAME:  {self.env["NAME"]}', verbose_level=2)

					elif re.search("InputVariableTextSubstituter", processor, re.IGNORECASE):

						self.output(f"Checking the {processor} section...", verbose_level=2)
						key = processor_output.get("return_variable")
						value = processor_output.get("return_variable_value")
						self.output(f"{key}:  {value}", verbose_level=3)
						self.env[key] = value

					elif re.search("JamfCategoryUploader", processor, re.IGNORECASE):
						self.output(f"Checking the {processor} section...", verbose_level=2)

						for key, value in processor_input.items():
							if key not in ignore_keys:
								self.env[key] = value
								self.output(f"{key}:  {self.env[key]}", verbose_level=3)

					elif re.search("JamfPackageUploader", processor, re.IGNORECASE):
						self.output(f"Checking the {processor} section...", verbose_level=2)

						for key, value in processor_input.items():
							if key not in ignore_keys:
								self.env[key] = value
								self.output(f"{key}:  {self.env[key]}", verbose_level=3)

						jamfpackageuploader_data = processor_output.get(
							"jamfpackageuploader_summary_result").get("data")

						for key, value in jamfpackageuploader_data.items():
							if key not in ignore_keys:
								self.env[key] = value
								self.output(f"{key}:  {self.env[key]}", verbose_level=3)

						if self.env["version"] and basename(self.env["pkg_path"]) == match_pkg:
							version_found = True

					elif re.search("JamfPolicyUploader", processor, re.IGNORECASE):
						self.output(f"Checking the {processor} section...", verbose_level=2)

						for key, value in processor_input.items():
							if key not in ignore_keys:
								self.env[key] = value
								self.output(f"{key}:  {self.env[key]}", verbose_level=3)

			except Exception:
				self.output("Missing required information...")
				continue

			if found_parent_recipes and version_found:
				break

		self.env["PARENT_RECIPES"].extend(parent_recipes)

		if not version_found:
			raise ProcessorError("Unable to locate a receipt with a matching version!")

		# Ensure the package actually exists
		if not exists(self.env["pkg_path"]):
			raise ProcessorError(f'Package does not exist:  {self.env["pkg_path"]}')


if __name__ == "__main__":
	PROCESSOR = PkgBotPromoter()
	PROCESSOR.execute_shell()
