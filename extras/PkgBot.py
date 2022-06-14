#!/usr/bin/python
#
# Copyright 2022 Zack Thompson
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

from __future__ import absolute_import, print_function

import os
import requests
from datetime import datetime

from autopkglib import Processor, ProcessorError


__all__ = ["PkgBot"]

class PkgBot(Processor):
    description = ("Uses a Slack App (or Bot) to post to a Slack Channel"
    "(or User) based on output of a JSSImporter run.")

    input_variables = {
    }
    output_variables = {
        "pkg_data": {
            "description": "Dictionary of the package details posted to the PkgBot server."
        }
    }

    __doc__ = description


    def authenticate_with_pkgbot(self, server: str, username: str, password: str):

        headers = { 
            "accept": "application/json", 
            "Content-Type": "application/x-www-form-urlencoded"
        }

        # Request a token based on the provided credentials
        response_get_token = requests.post( "{}/auth/token".format(server), 
            headers=headers, 
            data="username={}&password={}".format(username, password)
        )

        if response_get_token.status_code == 200:
            response_json = response_get_token.json()
            return response_json["access_token"]


    def main(self):
        jps_url = self.env.get("JSS_URL")
        prod_name = self.env.get("prod_name")
        pkg_path = self.env.get("pkg_path")
        recipe_id = self.env.get("recipe_id")
        jss_changed_objects = self.env.get("jss_changed_objects")
        jss_importer_summary_result = self.env.get("jss_importer_summary_result")

        if jss_changed_objects:
            jss_uploaded_package = jss_importer_summary_result["data"]["Package"]

        if jss_uploaded_package:

            sw_name = jss_importer_summary_result["data"]["Name"]
            sw_version = jss_importer_summary_result["data"]["Version"]
            jps_icon_id = jss_importer_summary_result["data"]["Icon ID"]
            jps_pkg_id = jss_importer_summary_result["data"]["Package ID"]
            pkg_name = os.path.basename(pkg_path)

            pkgbot_server = "{}:{}".format(self.env.get("PKGBOT_URL"), self.env.get("PKGBOT_PORT"))

            token = self.authenticate_with_pkgbot( 
                pkgbot_server, 
                self.env.get("API_USERNAME"), 
                self.env.get("API_PASSWORD")
            )

            if not token:
                raise ProcessorError(
                    'Failed to authenticate to the PkgBot Server:  {}'.format(pkgbot_server))

            headers = { 
                "Authorization": "Bearer {}".format(token),
                "accept": "application/json", 
                "Content-Type": "application/json"
            }

            if self.env.get("promote"):
                self.output("Promoting to Production...")

                workflow = "prod"
                format_string = "%Y-%m-%d %H:%M:%S.%f"
                promoted_date = datetime.strftime(datetime.now(), format_string)
                pkg_data = {
                    "name": prod_name,
                    "version": sw_version,
                    "jps_id_prod": jps_pkg_id,
                    "recipe_id": recipe_id,
                    "promoted_date": promoted_date
                }

                if jps_icon_id:
                    pkg_data["icon_id"] = jps_icon_id
                    pkg_data["jps_url"] = jps_url

            else:
                self.output("Posting to dev...")

                workflow = "dev"
                pkg_data = {
                    "name": sw_name,
                    "version": sw_version,
                    "icon_id": jps_icon_id,
                    "jps_id_dev": jps_pkg_id,
                    "jps_url": jps_url,
                    "pkg_name": pkg_name,
                    "recipe_id": recipe_id
                }

            # try:
            response = requests.post('{}/autopkg/workflow/{}'.format(pkgbot_server, workflow), 
                headers=headers, json=pkg_data)
            # except:

            self.env["pkg_data"] = pkg_data
            self.env["pkgbot_post_status_code"] = response.status_code
            self.env["pkgbot_post_text"] = response.text
            self.output("PkgBot Server POST Statuscode:  {}".format(
                self.env["pkgbot_post_status_code"]), verbose_level=2)
            self.output("PkgBot Server POST Response:  {}".format(
                self.env["pkgbot_post_text"]), verbose_level=2)
            self.output("pkg_data:  {}".format(
                self.env["pkg_data"]), verbose_level=2)

            if response.status_code != 200:
                raise ProcessorError("ERROR:  POST request to the PkgBot service returned statuscode "
                    "{}, with a response of:\n{}".format(
                        self.env["pkgbot_post_status_code"], self.env["pkgbot_post_text"]))

        else:
            self.output('Package was not uploaded into Jamf Pro.')


if __name__ == "__main__":
    processor = PkgBot()
    processor.execute_shell()
