# PkgBot

PkgBot is an automation framework for the open source project [AutoPkg](https://www.github.com/autopkg/autopkg) that provides a web-based front end and a Slack Bot to send notifications and receive commands.  It helps manage the lifecycle of software packaging through package and version validation and then provides an interactive method to "promote" a specific package version from "development" (or "test") to production environments.

<br>

### **Now with support for Slack Slash Commands _AND_ Shortcuts!**

#### **New Features**

  * Slack Slash Commands ([Help example](/examples/images/Slash%20Command%20-%20Help.png))
    * Run AutoPkg from a Slash Command!  
    * Enable/Disable recipes
    * And more!

    ![Slash Command](/examples/images/Slash%20Command.png)

  * Slack Message Shortcuts
    * Promote packages to Policies from a Slack message!
    
    ![Slack Shortcut - Promote Package](/examples/images/Slack%20Shortcut%20-%20Promote%20Package.png)

<br>

## About

PkgBot provides this workflow utilizing Jamf Pro and the [JamfUploader](https://github.com/grahampugh/jamf-upload) line of Processors.  A Slack Bot is used to send new build notifications and allows a `PkgBot Admin` to interact with those notifications.

![New Software Version Available](/examples/images/New%20Software%20Version%20Available.png)

To "promote" a package to a production Jamf Pro instance without re-running the entire recipe chain, a custom Post Processor (inspired by Graham Pugh's [JSSRecipeReceiptChecker](https://github.com/autopkg/grahampugh-recipes/blob/master/CommonProcessors/JSSRecipeReceiptChecker.py)) is used to find and acquire the matching recipe dev run details.  The values are passed to a "production recipe template" that performs the JamfUploader steps which can be configured to upload the package and optionally, update other various items (e.g. Policies, Groups, Scripts, etc.) _without_ re-downloading nor re-packaging.

A web-based front end is available to review the status and history of all packages as well as the _known_ `AutoPkg` recipe configurations and statuses.

PkgBot has been running in my production environment for over a year now and is working quite well.  During this time, I've been ironing out any kinks and making improvements to the overall processes and workflows to streamline everything.

![New Software Version Available](/examples/images/Approved%20packages.png)


## Backend Design

This project is built around FastAPI, Celery, the Slack SDK, and several other core libraries.  I built it with an API similar to the Jamf Pro (UAPI) and Classic APIs.  So if you've worked with these, this project's API will have a familiar feel.  In a recent refactor, I tried to lay the ground work to support alternative chat services, so pull requests to support other ChatBot services are welcome.

The project has a fully asynchronous code base and utilizes numerous popular Python libraries.

![New Software Version Available](/examples/images/Trust%20Verification%20Failure.png)


## Planned Features

Check out the [PkgBot Project Board](https://github.com/users/MLBZ521/projects/1) for a list of planned features.

![New Software Version Available](/examples/images/Encountered%20an%20Error.png)


## Requirements

PkgBot will typically be written to support the Python3 framework that is shipped with `AutoPkg` (currently supporting AutoPkg 2.6.0's (and newer) bundled Python 3.10.x).  Additional libraries will need to be installed separately that are not included with `AutoPkg`'s bundled Python3.  RabbitMQ is also required.

The major Python libraries are:
  * FastAPI
  * Slack SDK
    * For Notifications
  * Celery
  * Jinja2
    * For the web front-end
  * Tortoise ORM
  * Pydantic
  * Uvicorn

See the [requirements.txt](requirements.txt) file for additional libraries and dependencies.


## How to Setup

The basics to get PkgBot setup and working are covered in the [Wiki](https://github.com/MLBZ521/PkgBot/wiki/%22Basic%22-How-to-Setup).


## The Why(s) and My Thought Process

For my organization, almost every applications that needs to be "packaged," I have AutoPkg _packaging_ it.  This was done for numerous reasons:
  * automation
  * the recipe chain is self documenting of the steps to reproduce a package
    * e.g. for a new version
  * a single "this is the way" (_that we do things_)
    * easier for team members to pick up and go
  * scalability

In addition, there are a large number of Site Admins in my organization and I'm always receiving questions like:
> "When is \<software title\> \<version\> going to be available to deploy in Jamf Pro?"

There are several AutoPkg Post Processors to send webhooks that post messages to Slack for new packages, but I wanted **_more_**.  In addition, we have a dev (i.e. "test") environment that we (attempt to) test everything (packages, configurations, Jamf Pro Suite versions, etc.) in first.  If AutoPkg was uploading new versions into the production instance, then Site Admins could use those versions before they had _actually_ been verified.  So I wanted to ensure packages could be safely tested in the dev environment without the risk of pre-deployment as well as automating the workflow as much as possible (from the several manual steps that I was previously performing to move packages from dev to production).

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

All this without having to ask anyone (aka:  _me_).  All the information is visible within a Slack channel as well as the web front end, which has sortable and filterable tables; and if any Site Admin is feeling ambitious, it's also visible via the PkgBot API.

Plus a quick, or "emergency," promotion of a new software version to production at the _**press of a button**_ within Slack from my phone, from any where.

No, this is not a CI/CD workflow that many organizations are moving their AutoPkg workflows to, but I have a different set of goals that I'm attempting to accomplish.
