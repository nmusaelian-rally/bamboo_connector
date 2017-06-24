import sys, os
import datetime
import urllib
import socket
import re
import time

import requests
from collections import Counter

from bldeif.connection import BLDConnection
from bldeif.utils.eif_exception import ConfigurationError, OperationalError
from bldeif.utils.time_helper import TimeHelper

quote = urllib.parse.quote

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
        #self.api_token  = config.get("API_Token", '')
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
            '''
            {'Fernandel': {'AgileCentral_Project': 'Rally Fernandel', 'Plans': ['DonCamillo', 'Ludovic Cruchot']}}
            '''
        print (self.projects)

    def connect(self):
        """
        """
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
            # mo = re.search(r'<title>.*?</title>', response.text)
            # msg = mo.group(0) if mo else 'Connection error to Jenkins'
            raise ConfigurationError('%s  status_code: %s' % (msg, response.status_code))

        # self.log.debug(response.headers)
        result = response.json()
        if 'version' in result:
            return result['version']

    def disconnect(self):
        """
            Just reset our bamboo instance variable to None
        """
        self.bamboo = None

    def getRecentBuilds(self, ref_time):
        builds = []
        all_projects = self.getProjects()
        plan_keys = self.getPlans(all_projects)
        for key in plan_keys:
            plan_builds = self.getBuildsPerPlan(key, ref_time)
            builds.extend(plan_builds)
        print(len(builds))


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
        plans     = []
        conf_project_names = [proj_name for project in self.projects for proj_name in project.keys()]
        selected_projects = [project for project in all_projects if project['name'] in conf_project_names]
        # populate a list of plan keys that will be used to construct build endpoints for respective project-plan pairs:
        # traverse selected_projects[i]['plans']['plan'][j]['key']
        # to produce ['FER-DON', 'FER-LC', 'FER-RET']
        for project in selected_projects:
            for raw_plan in project['plans']['plan']:
                plans.append(BambooPlan(raw_plan))
                plan_keys.append(raw_plan['key'])
        self.inventory = BambooInventory(plans)
        return plan_keys


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
            qualifying_builds = self.extractQualifyingBuilds(raw_builds, ref_time)
        return qualifying_builds

    def extractQualifyingBuilds(self, raw_builds, ref_time):
        builds = []
        for record in raw_builds:
            # print(record)
            timestamp = TimeHelper(record['buildCompletedTime']).getTimestampFromString()
            # timestamp is int, ref_time is time.struct_time
            if timestamp < ref_time:
                break
            build = BambooBuild(record)
            builds.append(build)
        return builds[::-1]


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




##############################################################################################

class BambooInventory:
    def __init__(self, plans):
        self.plans = plans

    def getPlan(self, plan_name, project_name):
        plans = []
        matching_plans = [plan for plan in self.plans[project_name].plan if plan.name == plan_name]
        if matching_plans:
            plans.extend(matching_plans)
        return plans[0]


###########################################################################################


class BambooPlan:
    def __init__(self, raw):
        self.full_name = raw['name']
        self.name      = raw['shortName']
        self.link      = raw['link']['href']
        self.key       = raw['key']
        self.url       = self.link.replace('rest/api/latest/plan', 'browse')
        self.project   = self.full_name.replace(' - %s' % self.name, '')

        #     def __str__(self):
        #         vj = "%s::%s" % (self.project, self.shortName)
        #         return "%s  %s" % (vj, self._type)
        #
        #     def __repr__(self):
        #         return str(self)

###########################################################################################

class BambooBuild:
    def __init__(self, raw):
        """
        """
        self.id        = raw['id']
        self.number    = int(raw['number'])
        self.result    = raw['state']
        self.result    = 'INCOMPLETE' if self.result == 'ABORTED' else self.result
        self.key       = raw['buildResultKey'] #FER-DON-45
        self.link      = raw['link']['href']  # http://localhost:8085/rest/api/latest/result/FER-DON-45
        self.url       = self.link.replace('rest/api/latest/result','browse')        # localhost:8085/browse/FER-DON-45
        self.finished  = raw['finished']
        self.plan      = BambooPlan(raw['plan'])
        self.completedTime = raw['buildCompletedTime']  # "2017-06-12T13:55:39.712-06:00"
        self.timestamp = TimeHelper(raw['buildCompletedTime']).getTimestampFromString()
        self.project   = ''
        self.duration = int(raw['buildDuration'])



        # revisions    = raw['vcsRevisions']['vcsRevision']
        # self.changeSets   = []
        # for rev in revisions:
        #     self.changeSets.append({'repo':rev['repositoryName'],'revision':rev['vcsRevisionKey']})


#     def extractChangeSetInformation(self, json, cs_label):
#         """
#              A FreestyleJob build has changeset info in the json under the 'changeSet' element, but
#              WorkflowRun build has the equivalent changeset info under the 'changeSets' element as a list.
#              Here we transform the FreestyleJob changeset info into the one element 'changeSets' list so
#              that the processing is conistent.
#         """
#         try:
#             if cs_label == 'changeSet':
#                 json['changeSets'] = [json['changeSet']]
#             if len(json[cs_label]) == 0:
#                 return
#             try:
#                 self.vcs = json['changeSets'][0]['kind']
#             except Exception as msg:
#                 self.log.warning(
#                     'JenkinsBuild constructor unable to determine VCS kind, %s, marking vcs type as unknown' % (msg))
#                 self.log.warning(
#                     "We accessed your job's build JSON with this param %s and did not see 'kind' value" % BUILD_ATTRS)
#             self.revisions = json['changeSets'][0]['revisions'] if cs_label in json and 'revisions' in json['changeSets'][0] else None
#             getRepoName = {'git': self.ripActionsForRepositoryName,
#                            'svn': self.ripRevisionsForRepositoryName,
#                            None: self.ripNothing
#                            }
#             self.repository = getRepoName[self.vcs]()
#             if self.vcs != 'unknown':
#                 for ch in json['changeSets']:
#                     self.changeSets.extend(self.ripChangeSets(self.vcs, ch['items']))
#             csd = {changeset.commitId: changeset for changeset in self.changeSets}
#             self.changeSets = [chgs for chgs in csd.values()]
#         except Exception as msg:
#             self.log.warning('JenkinsBuild constructor unable to process %s information, %s' % (cs_label, msg))
#
#
#     def ripActionsForRepositoryName(self):
#         repo = ''
#         repo_info = [self.makeup_scm_repo_name(item['remoteUrls'][0]) for item in self.actions if 'remoteUrls' in item]
#         if repo_info:
#             repo = repo_info[0]
#         return repo
#
#     def ripRevisionsForRepositoryName(self):
#         """ for use with Subversion VCS
#         """
#         if not self.revisions:
#             return ''
#         repo_info = self.revisions[0]['module']
#         repo_name = repo_info.split('/')[-1]
#         return repo_name
#
#     def ripNothing(self):
#         return ''
#
#     def makeup_scm_repo_name(self, remote_url):
#         remote_url = re.sub(r'\/\.git$', '', remote_url)
#         max_length = 256
#         return remote_url.split('/')[-1][-max_length:]
#
#     def ripChangeSets(self, vcs, changesets):
#         tank = [JenkinsChangeset(vcs, cs_info) for cs_info in changesets]
#         return tank
#
#     def as_tuple_data(self):
#         start_time = datetime.datetime.utcfromtimestamp(self.timestamp / 1000.0).strftime('%Y-%m-%dT%H:%M:%SZ')
#         build_data = [('Number', self.number),
#                       ('Status', str(self.result)),
#                       ('Start', start_time),
#                       ('Duration', self.duration / 1000.0),
#                       ('Uri', self.url)]
#         return build_data
#
#     def __repr__(self):
#         name = "name: %s" % self.name
#         ident = "id_str: %s" % self.id_str
#         number = "number: %s" % self.number
#         result = "result: %s" % self.result
#         finished = "finished: %s" % self.finished
#         duration = "duration: %s" % self.duration
#         nothing = ""
#         pill = "  ".join([name, ident, number, result, finished, duration, nothing])
#         return pill
#
#     def __str__(self):
#         elapsed = self.elapsed[:]
#         if elapsed.startswith('00:'):
#             elapsed = '   ' + elapsed[3:]
#         if elapsed.startswith('   00:'):
#             elapsed = '      ' + elapsed[6:]
#         bstr = "%s Build # %5d   %-10.10s  Started: %s  Finished: %s   Duration: %s  URL: %s" % \
#                (self.name, self.number, self.result, self.started, self.finished, elapsed, self.url)
#         return bstr
#
#
# #############################################################################################
#
# class JenkinsChangeset:
#     def __init__(self, vcs, commit):
#         self.vcs       = vcs
#         self.commitId  = commit['commitId']
#         self.timestamp = commit['timestamp']
#         self.message   = commit['msg']
#         self.uri       = commit['paths'][0]['file'] if commit['paths'] else '.'
#
#     def __str__(self):
#         changeset = "   VCS %s  Commit ID # %s  Timestamp: %s  Message: %s " % \
#                     (self.vcs, self.commitId, self.timestamp, self.message)
#         return changeset
#
#
# class JenkinsChangesetFile:
#     def __init__(self, item):
#         self.action    = item['editType']
#         self.file_path = item['file']
