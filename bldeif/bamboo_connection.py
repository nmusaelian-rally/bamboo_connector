import sys, os
#import datetime
import urllib
import socket
import re
import time
import calendar

import requests
from collections import Counter

from bldeif.connection import BLDConnection
from bldeif.utils.eif_exception import ConfigurationError, OperationalError
from bldeif.utils.time_helper import TimeHelper
from bldeif.utils.status_matchmaker import Matchmaker


quote = urllib.parse.quote
time_helper = TimeHelper()

############################################################################################
__version__ = "0.0.1"

############################################################################################


class BambooConnection(BLDConnection):
    def __init__(self, config, logger):
        super().__init__(logger)
        self.bamboo = None
        self.internalizeConfig(config)
        self.backend_version = ""
        self.username_required = False
        self.password_required = False
        self.plans = [] #former self.inventory

    def name(self):
        return "Babmoo"

    def version(self):
        global __version__
        return __version__

    def getBackendVersion(self):
        """
            Conform to Connection subclass protocol and provide the version of the system
            we are "connecting" to.
        """
        return self.backend_version

    def internalizeConfig(self, config):
        super().internalizeConfig(config)
        self.protocol   = config.get('Protocol', 'http')
        self.server     = config.get('Server', socket.gethostname())
        self.port       = config.get('Port', 8080)
        self.prefix     = config.get("Prefix", '')
        self.username       = config.get("Username", '')
        self.password   = config.get("Password", '')
        self.debug      = config.get("Debug", False)
        self.max_items  = config.get("MaxItems", 1000)
        self.projects   = []
        self.ac_project = config.get("AgileCentral_DefaultBuildProject", None)

        self.base_url   = "{0}://{1}:{2}/rest/api/latest".format(self.protocol, self.server, self.port)
        self.creds = (self.username, self.password)

        self.http_proxy = {}
        if self.proxy_server:
            proxy  = "%s://%s:%s" % (self.proxy_protocol, self.proxy_server, self.proxy_port)
            if self.proxy_username and self.proxy_password:
                proxy  = "%s://%s:%s@%s:%s" % (self.proxy_protocol, self.proxy_username, self.proxy_password, self.proxy_server, self.proxy_port)
            self.http_proxy = {self.protocol : proxy}
            self.log.info("Proxy for Bamboo connection:  %s" % proxy)

        valid_config_items = ['Server', 'Protocol', 'Prefix', 'Port',
                              'Username', 'User', 'Password',
                              'ProxyProtocol', 'ProxyServer', 'ProxyPort', 'ProxyUser', 'ProxyUsername',
                              'ProxyPassword',
                              'Debug', 'Lookback',
                              'AgileCentral_DefaultBuildProject',
                              'Projects'
                             ]

        invalid_config_items = [item for item in config.keys() if item not in valid_config_items]
        if invalid_config_items:
            problem = "Bamboo section of the config contained these invalid entries: %s" % ", ".join(
                invalid_config_items)
            raise ConfigurationError(problem)

        for proj_section in config.get("Projects"):
            project = proj_section['Project']
            p = {}
            details = {}
            details['Plans'] = proj_section['Plans']
            details['AgileCentral_Project'] = proj_section['AgileCentral_Project']
            p[project] = details
            self.projects.append(p)
            # an element of that list looks like this:
            #{'Fernandel': {'AgileCentral_Project': 'Rally Fernandel', 'Plans': ['DonCamillo', 'Ludovic Cruchot']}}

        self.builds = {}


    def connect(self):
        self.log.info("Connecting to Bamboo")
        self.backend_version = self._getBambooVersion()
        self.log.info("Connected to Bamboo server: %s running at version %s" % (self.server, self.backend_version))
        self.log.info("Url: %s" % self.base_url)
        return True

    def _getBambooVersion(self):
        version  = None
        response = None
        bamboo_url = "%s/info.json" % self.base_url
        headers = {'Content-Type': 'application/json'}
        self.log.debug(bamboo_url)
        try:
            response = requests.get(bamboo_url, auth=self.creds, proxies=self.http_proxy, headers=headers)
        except Exception as msg:
            self.log.error(msg)
        if response.status_code >= 300:
            raise ConfigurationError('%s  status_code: %s' % (msg, response.status_code))

        # self.log.debug(response.headers)
        result = response.json()
        if 'version' in result:
            return result['version']

    def disconnect(self):
        self.bamboo = None

    def getRecentBuilds(self, ref_time):
        ref_time = calendar.timegm(ref_time)
        recent_builds_count = 0
        all_projects = self.getProjects()

        self.getPlans(all_projects)

        for plan in self.plans:
            self.getBuildsPerPlan(plan.key, ref_time)
        return self.builds


    def getProjects(self):
        """
        Use Bamboo REST API endpoint to obtain all visible/accessible Projects and their Plans:
                curl --user toto:totogithub http://localhost:8085/rest/api/latest/project.json?expand=projects.project.plans | python -m json.tool
        """
        all_projects = []
        endpoint = 'project.json?expand=projects.project.plans'
        headers = {'Content-Type': 'application/json'}
        url = "%s/%s" % (self.base_url, endpoint)
        response = requests.get(url, auth=self.creds, proxies=self.http_proxy, headers=headers)
        if response.status_code == 200:
            result = response.json()
            all_projects = result['projects']['project']
        return all_projects

    def getPlans(self, all_projects):
        plan_keys = []
        conf_project_names = [proj_name for project in self.projects for proj_name in project.keys()]
        selected_projects = [project for project in all_projects if project['name'] in conf_project_names]
        for project in selected_projects:
            for raw_plan in project['plans']['plan']:
                self.plans.append(BambooPlan(raw_plan))


    def getBuildsPerPlan(self, key, ref_time):
        """
        curl --user toto:totogithub -g http://localhost:8085/rest/api/latest/result/FER-DON.json?expand=results[0:5].result | python -m json.tool

        to get more details on vcsRevisions:

        curl --user toto:totogithub -g http://localhost:8085/rest/api/latest/result/FER-DON.json?expand=results[0:5].result.vcsRevisions | python -m json.tool

        vcs data seeps to be limited to:
            "vcsRevision": [
                        {
                            "repositoryId": 360450,
                            "repositoryName": "bamboo-camillo",
                            "vcsRevisionKey": "561b474ef508710944574f4e33ea9f77a2abf69b"
                        }
                    ]
         Is it possible to get revision's commit message and timestamp?
        """
        raw_builds = []
        endpoint = 'result/%s.json?expand=results[0:100].result.vcsRevisions' % key
        headers = {'Content-Type': 'application/json'}
        url = "%s/%s" % (self.base_url, endpoint)
        response = requests.get(url, auth=self.creds, proxies=self.http_proxy, headers=headers)
        if response.status_code == 200:
            result = response.json()
            raw_builds = result['results']['result']
            if raw_builds:
                self.extractQualifyingBuilds(raw_builds, ref_time)

    def extractQualifyingBuilds(self, raw_builds, ref_time):
        build_count = 0
        # ac_project = self.getAgileCentralProject(raw_builds[0]['projectName'])
        # if ac_project not in self.builds:
        #     self.builds[ac_project] = {}
        # plan = BambooPlan(raw_builds[0]['plan'])
        # self.builds[ac_project][plan] = []

        for record in raw_builds:
            timestamp = time_helper.secondsFromString(record['buildCompletedTime'])
            if timestamp >= ref_time:
                build_count += 1
                # prep builds dict when there is at least one qualified build:
                if build_count == 1:
                    ac_project = self.getAgileCentralProject(record['projectName'])
                    if ac_project not in self.builds:
                        self.builds[ac_project] = {}
                    plan = BambooPlan(record['plan'])
                    self.builds[ac_project][plan] = []

                build = BambooBuild(record)
                self.builds[ac_project][plan].append(build)
        if build_count > 1:
            self.builds[ac_project][plan] = self.builds[ac_project][plan][::-1]


    def getAgileCentralProject(self, bamboo_project_name):
        ac_projects = [ac_proj for project in self.projects
                               for key, proj_data in project.items() if key == bamboo_project_name
                                   for key, ac_proj in proj_data.items() if key == 'AgileCentral_Project']
        if ac_projects:
            return ac_projects[0]

    def validate(self):
        """
            Make sure any requisite conditions are satisfied.
            Are credentials needed and supplied?
        """
        satisfactory = True
        if self.username:
            self.log.debug('%s - user entry "%s" detected in config file' % (self.__class__.__name__, self.username))
        else:
            self.log.error("No Username was provided in your configuration in the Bamboo section")
            return False

        if self.password:
            self.log.debug('%s - password entry detected in config file' % self.__class__.__name__)
        else:
            self.log.error("No Password was provided in your configuration in the Bamboo section")
            return False

        if not self.ac_project:
            self.log.error("No AgileCentral_DefaultBuildProject value was provided in your configuration in the Bamboo section")
            return False

        if not (self.projects):
            self.log.error("No Projects were provided in your configuration in the Bamboo section")
            return False

        return satisfactory

    def dumpTargets(self):
        for plan in self.inventory:
            self.log.debug('Plan: %s' % plan)


class BambooPlan:
    def __init__(self, raw):
        self.full_name = raw['name']
        self.name      = raw['shortName']
        self.link      = raw['link']['href']
        self.key       = raw['key']
        self.url       = self.link.replace('rest/api/latest/plan', 'browse')
        self.project   = self.full_name.replace(' - %s' % self.name, '')

        def __str__(self):
            return "%s::%s" % (self.project, self.shortName)

        def __repr__(self):
            return str(self)

###########################################################################################

class BambooBuild:
    def __init__(self, raw):
        """
        """
        self.id        = raw['id']
        self.number    = int(raw['number'])
        self.state     = raw['state']
        self.key       = raw['buildResultKey'] #FER-DON-45
        self.link      = raw['link']['href']  # http://localhost:8085/rest/api/latest/result/FER-DON-45
        self.url       = self.link.replace('rest/api/latest/result','browse')        # localhost:8085/browse/FER-DON-45
        self.finished  = raw['finished']
        self.plan      = BambooPlan(raw['plan'])
        self.started_time   = raw['buildStartedTime']
        self.completed_time = raw['buildCompletedTime']  # "2017-06-12T13:55:39.712-06:00"
        #self.started_timestamp = TimeHelper(self.started_time).getTimestampFromString()
        self.started_timestamp = time_helper.secondsFromString(self.started_time)
        #self.timestamp = TimeHelper(self.completed_time).getTimestampFromString()
        self.timestamp = time_helper.secondsFromString(self.completed_time)
        self.project   = raw['projectName']
        self.duration = int(raw['buildDuration'])

    def as_tuple_data(self):
        iso_str_start = time_helper.stringFromSeconds(self.started_timestamp, '%Y-%m-%dT%H:%M:%SZ')
        matching_status = Matchmaker('Bamboo').matchStatus(str(self.state))
        build_data = [('Number', self.number),
                      ('Status', matching_status),
                      ('Start', iso_str_start),
                      ('Duration', self.duration / 1000.0),
                      ('Uri', self.url)]
        return build_data

