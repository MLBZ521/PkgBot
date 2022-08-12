# PkgBot

PkgBot is a framework to manage the lifecycle of software packaging, testing, and then promotion from development to production environments.  It utilizes the open source project AutoPkg to download and package software and a Slack Bot is utilized to send notifications and receive commands.

<center><img src="extras/examples/New Software Version Available.png" /></center>


## About

PkgBot is currently written to support this workflow utilizing Jamf Pro and the JamfUploader line of Processors.  A Slack Bot is used to send new build notifications and allows a `PkgBot Admin` to interact with those notifications.

To "promote" a package to a production Jamf Pro instance without re-running the entire recipe chain, a custom Post Processor (inspired by Graham Pugh's [JSSRecipeReceiptChecker](https://github.com/autopkg/grahampugh-recipes/blob/master/CommonProcessors/JSSRecipeReceiptChecker.py)) is used find and acquire the matching recipe dev run details.  The values are passed to a "production recipe template" that performs the JamfUploader steps which can be configured to upload the package and optionally, update other various items (e.g. Policy, Group, Scripts, etc.) _without_ re-downloading nor re-packaging.

A web view is also provided where all package status and history can be reviewed as well as `AutoPkg` recipe configurations and status.

PkgBot has been running in my production environment for a little over a year now and working quite well.  I've been ironing out some of the kinks and making improvements to the overall process and workflows as I work to streamline everything.

<center><img src="extras/examples/Approved packages.png" /></center>


## Backend Design

This project is built around FastAPI, Celery and several other core libraries.  I built it with an API workflow similar to that of the Jamf Pro and Classic APIs in-mind.  So, if you've worked with these, this project's API will have a familiar feel.

The project has a fully asynchronous code base and utilizes numerous popular Python libraries.

<center><img src="extras/examples/Trust Verification Failure.png" /></center>


## Planned Features

  * ~~Moving to a proper "backend" system for executing tasks~~
  * (More) Streamlining (of) workflows
  * "Hosting" the icons within PkgBot instead of Jamf Pro
  * Slack slash commands for executing recipes
  * Support for "cleaning up" old notifications
    * e.g. when an app version has been "retired"
  * Code Improvements
    * Better config loading
    * Better log loading/usage
  * A "setup/install" script

<center><img src="extras/examples/Encountered and Error.png" /></center>


## Requirements

PkgBot will be written to support the Python3 framework that is shipped with `AutoPkg`.  It does need numerous additional libraries that will have to be installed separately that are not included with `AutoPkg`'s bundled Python3.  It also requires RabbitMQ.

The major Python libraries are:
  * FastAPI
  * Celery
  * Jinja2
    * For the web views portion
  * Slack SDK
    * For Notifications
  * Tortoise ORM
  * Uvicorn

See the requirements.txt file for additional libraries and dependencies.


## ("_Basic_") How to Setup

Below will be the basics to get PkgBot setup and working.  Everything could easily be customized further if desired.

1. Install the prerequisites:
    * Git
    * AutoPkg
    * JSSImporter
    * RabbitMQ
      * Using the [brew instructions](https://www.rabbitmq.com/install-homebrew.html) or the [standalone binary instructions](https://www.rabbitmq.com/install-standalone-mac.html)
    * ngrok
      * only required if setting up for testing/development work

2. Clone this repo and store it on your AutoPkg Runner.
    * `git clone https://github.com/mlbz521/PkgBot.git "/Library/AutoPkg/"`

3. Install the requirements
    * e.g. `/usr/local/autopkg/python -m pip install -r requirements.txt`
    * Or, if you're simply testing, create a virtual environment and install the requirements

4. Create a Slack Bot/App
    * _Note_:  You can test PkgBot without creating the SlackBot -- obviously expect for the _actual_ Slack notifications part
    * There are numerous tutorials on how to do this and I'm not going to go over the entire process here.  I will simply provide the configuration requirements.  [Official documentation](https://slack.com/help/articles/115005265703-Create-a-bot-for-your-workspace)
    * Features/Functionality required
        * Incoming Webhooks
            * Create a webhook to post to the desired channel
        * Interactive Components
            * Set a `Request URL` that the Bot will send messages too and your server will receive on
                * e.g.  `https://pkgbot.my.server.org/slackbot/receive`
                * or, if using ngrok:  `https://84c5df439d74.ngrok.io/slackbot/receive` (see below)
        * Bots
        * OAuth & Permissions
            * Scopes
                * Bot Token Scopes
                    * chat:write
                    * files:write
                    * reactions:read
                    * reactions:write
                    * incoming-webhook
    * Tokens/Secrets/Keys required:
        * Bot User OAuth Token
        * Signing Secret
        * Bot Name
        * Channel
            * Channel it will be posting into

5. Ensure your PkgBot "server" can communicate with Slack's API
    * For testing, you can utilize ngrok to allow communication from Slack to your dev box.
        * There are numerous tutorials on how to do this and I'm not going to go over the entire process here.  I will simply provide the configuration requirements.  [Official documentation ](https://ngrok.com/docs/getting-started)
          * Follow steps two through four above
            * The port used in step four wil need to be defined in your `pkgbot_config.yaml`
              * e.g. `ngrok http 443`
        * After starting ngrok, grab the forwarding address from your terminal
          * e.g. `Forwarding                    https://84c5df439d74.ngrok.io -> http://localhost:443`
              * the forwarding address is:  `https://84c5df439d74.ngrok.io`
        * The forwarding address will need to be entered into your Slack Bot configuration

6. Optionally, create a private/public certificate for use with Uvicorn (_not required when testing with ngrok_)
  * Generate a private key and a CSR:
    * `openssl req -new -newkey rsa:2048 -nodes -keyout private.key -out pkgbot_csr.csr`
  * Obtain a publicly trusted cert using the CSR
  * Update your `pkgbot_config.yaml` with these values

7. Configure your environments' settings (`/[path/to/PkgBot]/settings/pkgbot_config.yaml`)

8. Start the required services:
  * PkgBot:  `pkgbot.py`
  * Celery:  
  * RabbitMQ:  


An example LaunchDaemon is provided to run PkgBot.  Samples will be provided in the extras directory.


### "_Basic_" Examples

Example command to run via `autopkg` directly with the PkgBot Post Processor

`/usr/local/bin/autopkg run com.github.mlbz521.jss.ProductionTemplate --key recipe_id="com.github.mlbz521.jss.Dropbox" --prefs="/Library/AutoPkg/PkgBotServer/settings/prod_autopkg_prefs.plist" --postprocessor PkgBot -vv`

#### Using the pseudo cli tool

How to import recipes from a yaml file

`python3 -m execute.autopkg manage import --input ./settings/recipe_config.yaml`
```
2021-06-25 15:32:55,781 - PkgBot - INFO - Importing recipe config file from:  ./settings/recipe_config.yaml.
2021-06-25 15:33:52,474 - PkgBot - INFO - All recipe configurations have been imported!
```

Manage a single recipe

`python3 -m execute.autopkg manage single -i com.github.mlbz521.jss.Zoom-ForIT --enable --force`

Run a single recipe via PkgBot

`python3 -m execute.autopkg run -e dev -i com.github.mlbz521.jss.Brother-MFC-J6935DW --pkgbot_config "/Library/AutoPkg/PkgBotServer/settings/pkgbot_config.yaml"`


#### Managing the LaunchAgent for Kicking off AutoPkg runs

Load launchagent to run recipes

`launchctl bootstrap "gui/501" ~/Library/LaunchAgents/com.github.mlbz521.autopkg.service.plist`

Kickstart run of recipes

`launchctl kickstart -p "gui/501/com.github.mlbz521.autopkg.service"`

Stop

`launchctl bootout "gui/501/com.github.mlbz521.autopkg.service"`


#### Managing the PkgBot LaunchDaemon

Start PkgBot

`sudo launchctl bootstrap system /Library/LaunchDaemons/com.github.mlbz521.pkgbot.service.plist`

Stop

`sudo launchctl bootout "system/com.github.mlbz521.pkgbot.service"`


## The Why(s) and My Thought Process

At my organization, I have moved almost everything that needs to be "packaged" to be _packaged_ by AutoPkg.  This was done for numerous reasons:
  * automation
  * the recipe chain is self documenting of the steps to reproduce a package
    * e.g. for a new version
  * a single "this is the way" (_that we do things_)
    * easier for team members to pick up and go
  * scalability

In addition, there are a large number of Site Admins in my organization and I'm always receiving questions like:
> "When is \<software title\> \<version\> going to be available to deploy in Jamf Pro?"

There are several AutoPkg Post Processors to send webhooks that post messages to Slack for new packages, but I wanted **_more_**.  In addition, we have a dev (i.e. "test") environment that we (attempt to) test everything (packages, configurations, Jamf Pro Suite versions, etc.) in first.  If AutoPkg was uploading new versions into the production instance _first_, then Site Admins could use those versions before they had _actually_ been tested.  So I wanted to ensure packages could be tested in the dev environment without the risk of pre-deployment as well as automating the workflow as much as possible (from the several manual steps that I was previously performing to move packages from dev to production).

As it sits, PkgBot provides a fully documented system.  It allows our Site Admins visibility into the following:
  * What software is managed/packaged via AutoPkg (recipes)
    * What the recipe configuration looks like (from the PkgBot perspective)
      * Is it disabled? (e.g. it errored out on the last `autopkg run`)
    * When was the last time a recipe ran?
  * History of software versions
    * What is the last version of "\<software title\>" that was packaged?
      * Has it been "promoted" to production yet?
        * Or was is denied?
  * And more

All this, without having to ask anyone (aka:  _me_).  All the information is visible within a Slack channel as well as a web view, which has sortable and filterable tables, and if any Site Admin is feeling ambitious, it's also visible via the PkgBot API.

Plus a quick, or "emergency," push of a new software version to production at the _**press of a button**_ within Slack from my phone, from any where.

No, this is not a CI/CD workflow that many organizations are moving their AutoPkg workflows to, but I have a different set of goals that I'm attempting to accomplish.
