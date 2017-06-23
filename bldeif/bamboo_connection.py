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

quote = urllib.parse.quote

############################################################################################

__version__ = "1.0.1"

ACTION_WORD_PATTERN = re.compile(r'[A-Z][a-z]+')
ARTIFACT_IDENT_PATTERN = re.compile(r'(?P<art_prefix>[A-Z]{1,4})(?P<art_num>\d+)')
VALID_ARTIFACT_ABBREV = None  # set later after config values for artifact prefixes are known

BUILD_ATTRS = "number,id,fullDisplayName,timestamp,duration,result,url,actions[remoteUrls],changeSet[*[*[*]]]"
FOLDER_JOB_BUILD_ATTRS = "number,id,description,timestamp,duration,result,url,actions[remoteUrls],changeSet[*[*[*]]]"
FOLDER_JOB_BUILDS_MINIMAL_ATTRS = "number,id,timestamp,result"

JENKINS_URL           = "{prefix}/api/json"
ALL_JOBS_URL          = "{prefix}/api/json?tree=jobs[displayName,name,url,jobs[displayName,name,url]]"
#VIEW_JOBS_URL         = "{prefix}/view/{view}/api/json?depth=0&tree=jobs[name]"
#VIEW_JOBS_ENDPOINT    = "/api/json?depth=0&tree=jobs[name]"
VIEW_FOLDERS_URL      = "{prefix}/view/{view}/api/json?tree=jobs[displayName,name,url,jobs[displayName,name,url]]"
JOB_BUILDS_URL        = "{prefix}/view/{view}/job/{job}/api/json?tree=builds[%s]" % BUILD_ATTRS
FOLDER_JOBS_URL       = "{prefix}/job/{folder_name}/api/json?tree=jobs[displayName,name,url]"
FOLDER_JOB_BUILDS_URL = "{prefix}/job/{folder_name}/jobs/{job_name}/api/json?tree=builds[%s]" % FOLDER_JOB_BUILD_ATTRS
FOLDER_JOB_BUILD_URL  = "{prefix}/job/{folder_name}/jobs/{job_name}/{number}/api/json"


############################################################################################

'''



in jenkins_connection.py
obtainJenkinsInventory() is called from inside connect method
it hits Jenkins endpoint with depth param and gets a tree
the response.json() of this request is passed to fill_bucket method that fills up the buckets (lists)
with JenkinsJob objects. Equivalent of it would be BambooPlan objects. However, for now, we are not aware
or interested in different types of of Plan objects, so we don't need three separate buckets (job, view, folder).
fill_bucket method instantiate JenkinsJob objects e.g.
        for job in non_folders:
            job_bucket.append(JenkinsJob(job, container=container, base_url=self.base_url))

and eventually
        return job_bucket, folder_bucket, view_bucket

The caller of fill_bucket method is obtainInventory, so it gets those buckets back, filled.
After they are filled self.inventory is instantiated:
       self.inventory = JenkinsInventory(self.base_url, job_bucket, folder_bucket, view_bucket)

I am not sure we need BambooInventory since it is a simpler construct (no different buckets)

per comment: "Utilize the Jenkins REST API endpoint to obtain all visible/accessible Jenkins Jobs/Views/Folders"
It gets all jobs, which is equivalent to getting all plans(in Bamboo)

self.inventory = JenkinsInventory(self.base_url, job_bucket, folder_bucket, view_bucket)

---------
inside bld_connector.py we call bld.getRecentBuilds(bld_ref_time)
getRecentBuilds is defined in jenkins_connection.py

getRecentBuilds --> getBuildHistory --> extractQualifyingBuilds

in getRecentBuilds, we crated empty builds = {},
for each job in the inventory (we will have for each plan in inventory)
    we get the job's AC target project name
    set var 'key' to AC target project name
    if key not in builds:
        create a dict with this key builds[key] = {}
        # and call getBuildHistory
        builds[key][job] = getBuildHistory(self, view, job, ref_time)

getBuildHistory method in the Jenkins connector is the method that makes the request per job to get raw_builds.
raw_builds = requests.get(job_builds_url, auth=self.creds, proxies=self.http_proxy).json()['builds']

Then, in getBuildHistory a call is made to extractQualifyingBuilds:
qualifying_builds = self.extractQualifyingBuilds(job.name, None, ref_time, raw_builds)

In extractQualifyingBuilds the builds are filtered by time and then the raw data of qualified builds
is used to create instances of JenkinsBuild. For each raw record in raw_builds we instantiate JenkinsBuild object
and append it to build list if time condition is met. Finally we reverse order biulds[::-1]

def extractQualifyingBuilds(self, job_name, folder_name, ref_time, raw_builds):
        builds = []
        for brec in raw_builds:
            # print(brec)
            build = JenkinsBuild(job_name, brec, job_folder=folder_name)
            if build.id_as_ts < ref_time:  # when true build time is older than ref_time, don't consider this job
                break
            builds.append(build)
        return builds[::-1]

The builds list returned by getBuildHistory in jenkins_connection.py looks like this:

{'All::N1':
    {
           http://localhost:8080::domovoi's first job  FreeStyleProject:
           [
                name: domovoi's first job  id_str: 1498182360624  number: 1  result: SUCCESS  finished: 2017-06-23 01:46:00  duration: 60  ,
                name: domovoi's first job  id_str: 1498183202874  number: 2  result: SUCCESS  finished: 2017-06-23 02:00:02  duration: 20  ,
                name: domovoi's first job  id_str: 1498183299136  number: 3  result: SUCCESS  finished: 2017-06-23 02:01:39  duration: 17  ,
                name: domovoi's first job  id_str: 1498183861799  number: 4  result: SUCCESS  finished: 2017-06-23 02:11:01  duration: 16  ,
                name: domovoi's first job  id_str: 1498183912460  number: 5  result: SUCCESS  finished: 2017-06-23 02:11:52  duration: 16  ,
                name: domovoi's first job  id_str: 1498184257158  number: 6  result: SUCCESS  finished: 2017-06-23 02:17:37  duration: 17
            ]
    }
}

These builds are returned to the caller of the getRecentBuilds in bld_connector.py.
Next, the unrecorded builds in AC are identified...
'''

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
        #self.job_class_exists = self._checkJenkinsJobClassProp()

        #self.obtainRawInventory()
        self.getRawBuilds()
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

    def makeFieldsString(self, depth):
        basic_fields = '_class,name,displayName,views[name,jobs[name]],jobs'
        detailed_fetch = basic_fields[:]
        if depth <= 1:
            return basic_fields

        for i in range(1, depth):
            detailed_fetch = "%s[%s]" % (basic_fields, detailed_fetch)
        return detailed_fetch

    #def obtainBambooInventory(self):
    #def obtainRawInventory(self):
    def getRawBuilds(self):
        raw_builds = []
        all_projects = self.getProjects()
        plan_keys = self.getPlans(all_projects)
        for key in plan_keys:
            plan_builds = self.getBuilds(key)
            raw_builds.extend(plan_builds)
        # print(len(raw_builds))


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


    def getBuilds(self, key):
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
        builds = []
        endpoint = 'result/%s.json?expand=results[0:5].result.vcsRevisions' % key
        headers = {'Content-Type': 'application/json'}
        url = "%s/%s" % (self.base_url, endpoint)
        response = requests.get(url, auth=self.creds, proxies=self.http_proxy, headers=headers)
        if response.status_code == 200:
            result = response.json()
            builds = result['results']['result']
        return builds


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
        for job in self.jobs:
            self.log.debug('Job: %s' % job)
        for view in self.views:
            self.log.debug('View: %s' % view)
        for folder in self.folders:
            self.log.debug('Folder: %s' % folder)


    # def getQualifyingViewJobs(self, view):
    #
    #     jenkins_view = self.inventory.getView(view['View'])
    #     all_view_jobs = jenkins_view.jobs
    #
    #     include_patt = view.get('include', '*')
    #     include_patt = include_patt.replace('*', '\.*')
    #     included_jobs = [job for job in all_view_jobs if re.search(include_patt, job.name) != None]
    #     excluded_jobs = []
    #     if 'exclude' in view:
    #         exclusions = re.split(',\s*', view['exclude'])
    #         for job in included_jobs:
    #             for exclusion in exclusions:
    #                 exclusion = exclusion.replace('*', '\.*')
    #                 if re.search(exclusion, job.name):
    #                     excluded_jobs.append(job)
    #                     break
    #
    #     qualifying_jobs = list(set(included_jobs) - set(excluded_jobs))
    #     return qualifying_jobs

    # def showQualifiedJobs(self):
    #     self.log.debug('Configured top level Jobs')
    #     for job in self.jobs:
    #         #jenkins_job = self.inventory.getJob(job['Job'])
    #         self.log.debug("    %s" % job['Job']) # used to be jenkins_job.name
    #
    #     self.log.debug('Configured Views and Jobs')
    #     for view_name, jobs in self.vetted_view_jobs.items():
    #         self.log.debug("    View: %s" % view_name)
    #         for job in jobs:
    #             self.log.debug("        %s" % job.name)
    #     self.log.debug('Configured Folders and Jobs')
    #     for folder_name, jobs in self.vetted_folder_jobs.items():
    #         self.log.debug("    Folder: %s" % folder_name)
    #         for job in jobs:
    #             self.log.debug("        %s" % job.name)


    def getRecentBuilds(self, ref_time):
        """
            Obtain all Builds created in Jenkins at or after the ref_time parameter
            which is a struct_time object of:
               (tm_year, tm_mon, tm_mday, tm_hour, tm_min, tm_sec, tm_wday, tm_yday, tm_isdst)

            Construct a dict keyed by Jenkins-View-Name::AgileCentral_ProjectName
            with a list of JenkinsBuild items for each key
        """
        zulu_ref_time = time.localtime(time.mktime(ref_time))  # ref_time is already in UTC, so don't convert again (hence use of time.localtime()
        ref_time_readable = time.strftime("%Y-%m-%d %H:%M:%S Z", zulu_ref_time)
        pending_operation = "Detecting recently added Jenkins Builds (added on or after %s)"
        self.log.info(pending_operation % ref_time_readable)

        builds = {}
        recent_builds_count = 0

        # for job in self.jobs:
        #     jenkins_job = self.inventory.getJob(job['Job'])
        #     ac_project = job.get('AgileCentral_Project', self.ac_project)
        #     key = 'All::%s' % ac_project
        #     if key not in builds:
        #         builds[key] = {}
        #     builds[key][jenkins_job] = self.getBuildHistory('All', jenkins_job, zulu_ref_time)
        #     self.log.debug("retrieved %d builds for Folder Job %s that occured after %s" % (len(builds[key][jenkins_job]), jenkins_job.fully_qualified_path(), ref_time_readable))
        #     recent_builds_count += len(builds[key][jenkins_job])
        #
        # log_msg = "recently added Jenkins Builds detected: %s"
        # self.log.info(log_msg % recent_builds_count)
        #
        # if self.debug:
        #     jbf = open('jenkins.blds.hist', 'w+')
        #     jbf.write((log_msg % recent_builds_count) + "\n")
        #     jbf.close()

        for project in self.projects:
            # an element of that list looks like this:
            '''
            {'Fernandel': {'AgileCentral_Project': 'Rally Fernandel', 'Plans': ['DonCamillo', 'Ludovic Cruchot']}}
            '''
            for project_name, project_info in project.items():
                for plan in project_details['Plans']:
                    bamboo_plan = self.inventory.getPlan(plan, project_name)
                    ac_project = project_details['AgileCentral_Project']  #, self.ac_project)
                    key = '%s::%s' % (project_name, ac_project)
                    if key not in builds:
                        builds[key] = {}
                    builds[key][bamboo_plan] = self.getBuildHistory('All', bamboo_plan, zulu_ref_time)


        return builds

    def getBuildHistory(self, view, job, ref_time):
        JOB_BUILDS_ENDPOINT = "/api/json?tree=builds[%s]" % BUILD_ATTRS
        urlovals = {'prefix': self.base_url, 'view': quote(view), 'job': quote(job.name)}
        job_builds_url = job.url + (JOB_BUILDS_ENDPOINT.format(**urlovals))
        if job._type == 'WorkflowJob':
            job_builds_url = job_builds_url.replace('changeSet', 'changeSets')
        self.log.debug("view: %s  job: %s  req_url: %s" % (view, job, job_builds_url))
        raw_builds = requests.get(job_builds_url, auth=self.creds, proxies=self.http_proxy).json()['builds']
        qualifying_builds = self.extractQualifyingBuilds(job.name, None, ref_time, raw_builds)
        return qualifying_builds

    def getFolderJobBuildHistory(self, folder_name, job, ref_time):
        folder_job_builds_url = job.url + ('/api/json?tree=builds[%s]' % FOLDER_JOB_BUILD_ATTRS)
        if job._type == 'WorkflowJob':
            folder_job_builds_url = folder_job_builds_url.replace('changeSet', 'changeSets')
        self.log.debug("folder: %s  job: %s  req_url: %s" % (folder_name, job.name, folder_job_builds_url))
        raw_builds = requests.get(folder_job_builds_url, auth=self.creds, proxies=self.http_proxy).json()['builds']
        qualifying_builds = self.extractQualifyingBuilds(job.name, folder_name, ref_time, raw_builds)
        return qualifying_builds

    def extractQualifyingBuilds(self, job_name, folder_name, ref_time, raw_builds):
        builds = []
        for brec in raw_builds:
            # print(brec)
            build = JenkinsBuild(job_name, brec, job_folder=folder_name)
            if build.id_as_ts < ref_time:  # when true build time is older than ref_time, don't consider this job
                break
            builds.append(build)
        return builds[::-1]


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


# class JenkinsInventory:
#     def __init__(self, base_url, job_bucket, folder_bucket, view_bucket):
#         self.base_url = base_url
#         self.jobs     = job_bucket
#         self.folders  = folder_bucket
#         self.views    = view_bucket
#
#     def getFolder(self, name):
#         target = name if name.startswith('/') else '/%s' % name
#         folder = next((self.folders[folder] for folder in self.folders.keys() if folder.endswith(target)), None)
#         return folder
#
#     def getView(self, view_path):
#         view_path = '/%s' % view_path if view_path[0] != '/' else view_path
#         target_view = next((self.views[vp] for vp in self.views.keys() if vp.endswith(view_path)), None)
#         return target_view
#
#     def getJob(self, job_name):
#         first_level_jobs = [job for job in self.jobs if job.name == job_name]
#         if first_level_jobs:
#             return first_level_jobs[0]
#
#         jobs = []
#         for folder_path in self.folders.keys():
#            matching_jobs = [job for job in self.folders[folder_path].jobs if job.name == job_name]
#            if matching_jobs: jobs.extend(matching_jobs)
#         for view_path in self.views.keys():
#             matching_jobs = [job for job in self.views[view_path].jobs if job.name == job_name]
#             if matching_jobs: jobs.extend(matching_jobs)
#
#         return jobs[0]
#
#     def getFullyQualifiedFolderMapping(self):
#         # maps folder's path representation from the config file to the folder's path
#         #fm = {" // ".join(re.split(r'\/', key)[1:]) : key for key in self.folders.keys()}
#         fm = {}
#         for fk in sorted(self.folders.keys()):
#             #tfk = fk.replace(self.base_url,'')
#             path_components = re.split(r'\/', fk)[1:]
#             fqpath = " // ".join(path_components)
#             #print(fqpath)
#             fm[fqpath] = fk
#
#         return fm
#
#     def getFolderByPath(self, folder_path):
#         folder_map = self.getFullyQualifiedFolderMapping()
#         if folder_path in folder_map:
#             folder = self.folders[folder_map[folder_path]]
#             return folder
#         return None
#
#
#     def getFullyQualifiedViewMapping(self):
#         # maps view's path representation from the config file to the view's path
#         #vm = {" // ".join(re.split(r'\/', key)[1:]) : key for key in self.views.keys()}
#         vm = {}
#         for vk in sorted(self.views.keys()):
#             path_components = re.split(r'\/', vk)[1:]
#             fqpath = " // ".join(path_components)
#             #print(fqpath)
#             vm[fqpath] = vk
#
#         return vm
#
#     def getViewByPath(self, view_path):
#         view_map = self.getFullyQualifiedViewMapping()
#         if view_path in view_map:
#             folder = self.views[view_map[view_path]]
#             return folder
#         return None


##############################################################################################

# class JenkinsJob:
#     def __init__(self, info, container='Root', base_url=''):
#         self.container = container
#         self.name      = info.get('name', 'UNKNOWN-ITEM')
#         self._type     = info['_class'].split('.')[-1]
#         self.url       = "%s/job/%s" % (container, self.name)
#         # job_path is really only for dev purposes of displaying a short, readable job path, e.g. "/frozique::australopithicus"
#         self.job_path  = "%s::%s" % (re.sub(r'%s/?' % base_url, '', container), self.name)
#         self.job_path  = '/'.join(re.split('/?job/?', self.job_path))
#
#     def fully_qualified_path(self):
#         return re.sub('https?://', '', self.url)
#
#     def __str__(self):
#         vj = "%s::%s" % (self.container, self.name)
#         return "%s  %s" % (vj, self._type)
#
#     def __repr__(self):
#         return str(self)

#############################################################################################

# class JenkinsView:
#     def __init__(self, info, container='/', base_url=''):
#         self.name = '/%s' % info['name']
#         if container == '/':
#             job_container  = "%s/view%s" % (base_url, self.name)
#         else:
#             job_container = "%s/view%s" % (container, self.name)
#
#         self.url  = job_container
#         self.jobs = [JenkinsJob(job, job_container, base_url=base_url) for job in info['jobs'] if not job['_class'].endswith('.Folder')]
#
#     def __str__(self):
#         vj = "%s::%s" % (self.container, self.name)
#         return "%-80.80s  %s" % (vj, self._type)
#
#     def __repr__(self):
#         return str(self)

#############################################################################################

# class JenkinsJobsFolder:
#     def __init__(self, info, container='/',  folder_url=''):
#         self.name      = '/%s' % info['name']
#         job_container  = "%s/job%s" % (container, self.name)
#         self.url       = job_container
#         self.jobs      = [JenkinsJob(job, job_container, base_url=folder_url) for job in info['jobs'] if not job['_class'].endswith('.Folder')]
#
#     def __str__(self):
#         sub_jobs = len(self.jobs)
#         return "name: %-24.24s   sub-jobs: %3d   url: %s " % \
#                (self.name, sub_jobs, self.url)
#
#     def info(self):
#         return str(self)

    ###########################################################################################

class BambooPlan:
    def __init__(self, raw):
        self.full_name = raw['name']
        self.name      = raw['shortName']
        self.link      = raw['link']['href']
        self.key       = raw['key']
        self.url       = self.link.replace('rest/api/latest/plan', 'browse')
        self.project   = self.full_name.replace(' - %s' % self.name, '')

class BambooBuild:
    def __init__(self, raw):
        """
        """
        self.number    = int(raw['number'])
        self.result    = raw['state']
        self.result    = 'INCOMPLETE' if self.result == 'ABORTED' else self.result
        self.key       = raw['buildResultKey'] #FER-DON-45
        self.started   = raw['buildStartedTime'] # "2017-06-12T13:55:39.712-06:00"
        self.completed = raw['buildCompletedTime']
        self.link      = raw['link']['href']  # http://localhost:8085/rest/api/latest/result/FER-DON-45
        self.url       = self.link.replace('rest/api/latest/result','browse')        # localhost:8085/browse/FER-DON-45
        self.finished  = raw['finished']

        if re.search('^\d+$', self.id_str):
            self.id_as_ts = time.gmtime(self.timestamp / 1000)
            self.id_str = str(self.timestamp)
            self.Id = self.id_str
        else:
            self.id_as_ts = time.strptime(self.id_str, '%Y-%m-%d_%H-%M-%S')

        #self.started   = time.strftime('%Y-%m-%d %H:%M:%SZ', time.gmtime(self.startes / 1000))
        #self.completed = time.strftime('%Y-%m-%d %H:%M:%SZ', time.gmtime(self.completed / 1000))
        self.duration = int(raw['buildDuration'])
        whole, millis = divmod(self.duration, 1000)
        hours, leftover = divmod(whole, 3600)
        minutes, secs = divmod(leftover, 60)
        if hours:
            duration = "%d:%02d:%02d.%03d" % (hours, minutes, secs, millis)
        else:
            if minutes >= 10:
                duration = "%02d:%02d.%03d" % (minutes, secs, millis)
            else:
                duration = " %d:%02d.%03d" % (minutes, secs, millis)

        self.elapsed = "%12s" % duration


        revisions    = raw['vcsRevisions']['vcsRevision']
        self.changeSets   = []
        for rev in revisions:
            self.changeSets.append({'repo':rev['repositoryName'],'revision':rev['vcsRevisionKey']})



class JenkinsBuild(object):
    def __init__(self, name, raw, job_folder=None):
        """
        """
        self.name = name
        self.number = int(raw['number'])
        self.result = str(raw['result'])
        self.actions = raw['actions']
        self.result = 'INCOMPLETE' if self.result == 'ABORTED' else self.result
        cs_label = 'changeSet'
        if str(raw['_class']).endswith('.WorkflowRun'):
            cs_label = 'changeSets'

        self.id_str = str(raw['id'])
        self.Id     = self.id_str
        self.timestamp = raw['timestamp']
        self.url    = str(raw['url'])

        if re.search('^\d+$', self.id_str):
            self.id_as_ts = time.gmtime(self.timestamp / 1000)
            self.id_str = str(self.timestamp)
            self.Id = self.id_str
        else:
            self.id_as_ts = time.strptime(self.id_str, '%Y-%m-%d_%H-%M-%S')

        self.started = time.strftime('%Y-%m-%d %H:%M:%SZ', time.gmtime(self.timestamp / 1000))
        self.duration = raw['duration']
        whole, millis = divmod(self.duration, 1000)
        hours, leftover = divmod(whole, 3600)
        minutes, secs = divmod(leftover, 60)
        if hours:
            duration = "%d:%02d:%02d.%03d" % (hours, minutes, secs, millis)
        else:
            if minutes >= 10:
                duration = "%02d:%02d.%03d" % (minutes, secs, millis)
            else:
                duration = " %d:%02d.%03d" % (minutes, secs, millis)

        self.elapsed = "%12s" % duration

        total = (self.timestamp + self.duration) / 1000
        self.finished = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(total))

        self.vcs        = 'unknown'
        self.revisions  = ''
        self.repository = ''
        self.changeSets = []
        self.extractChangeSetInformation(raw, cs_label)


    def extractChangeSetInformation(self, json, cs_label):
        """
             A FreestyleJob build has changeset info in the json under the 'changeSet' element, but
             WorkflowRun build has the equivalent changeset info under the 'changeSets' element as a list.
             Here we transform the FreestyleJob changeset info into the one element 'changeSets' list so
             that the processing is conistent.
        """
        try:
            if cs_label == 'changeSet':
                json['changeSets'] = [json['changeSet']]
            if len(json[cs_label]) == 0:
                return
            try:
                self.vcs = json['changeSets'][0]['kind']
            except Exception as msg:
                self.log.warning(
                    'JenkinsBuild constructor unable to determine VCS kind, %s, marking vcs type as unknown' % (msg))
                self.log.warning(
                    "We accessed your job's build JSON with this param %s and did not see 'kind' value" % BUILD_ATTRS)
            self.revisions = json['changeSets'][0]['revisions'] if cs_label in json and 'revisions' in json['changeSets'][0] else None
            getRepoName = {'git': self.ripActionsForRepositoryName,
                           'svn': self.ripRevisionsForRepositoryName,
                           None: self.ripNothing
                           }
            self.repository = getRepoName[self.vcs]()
            if self.vcs != 'unknown':
                for ch in json['changeSets']:
                    self.changeSets.extend(self.ripChangeSets(self.vcs, ch['items']))
            csd = {changeset.commitId: changeset for changeset in self.changeSets}
            self.changeSets = [chgs for chgs in csd.values()]
        except Exception as msg:
            self.log.warning('JenkinsBuild constructor unable to process %s information, %s' % (cs_label, msg))


    def ripActionsForRepositoryName(self):
        repo = ''
        repo_info = [self.makeup_scm_repo_name(item['remoteUrls'][0]) for item in self.actions if 'remoteUrls' in item]
        if repo_info:
            repo = repo_info[0]
        return repo

    def ripRevisionsForRepositoryName(self):
        """ for use with Subversion VCS
        """
        if not self.revisions:
            return ''
        repo_info = self.revisions[0]['module']
        repo_name = repo_info.split('/')[-1]
        return repo_name

    def ripNothing(self):
        return ''

    def makeup_scm_repo_name(self, remote_url):
        remote_url = re.sub(r'\/\.git$', '', remote_url)
        max_length = 256
        return remote_url.split('/')[-1][-max_length:]

    def ripChangeSets(self, vcs, changesets):
        tank = [JenkinsChangeset(vcs, cs_info) for cs_info in changesets]
        return tank

    def as_tuple_data(self):
        start_time = datetime.datetime.utcfromtimestamp(self.timestamp / 1000.0).strftime('%Y-%m-%dT%H:%M:%SZ')
        build_data = [('Number', self.number),
                      ('Status', str(self.result)),
                      ('Start', start_time),
                      ('Duration', self.duration / 1000.0),
                      ('Uri', self.url)]
        return build_data

    def __repr__(self):
        name = "name: %s" % self.name
        ident = "id_str: %s" % self.id_str
        number = "number: %s" % self.number
        result = "result: %s" % self.result
        finished = "finished: %s" % self.finished
        duration = "duration: %s" % self.duration
        nothing = ""
        pill = "  ".join([name, ident, number, result, finished, duration, nothing])
        return pill

    def __str__(self):
        elapsed = self.elapsed[:]
        if elapsed.startswith('00:'):
            elapsed = '   ' + elapsed[3:]
        if elapsed.startswith('   00:'):
            elapsed = '      ' + elapsed[6:]
        bstr = "%s Build # %5d   %-10.10s  Started: %s  Finished: %s   Duration: %s  URL: %s" % \
               (self.name, self.number, self.result, self.started, self.finished, elapsed, self.url)
        return bstr


#############################################################################################

class JenkinsChangeset:
    def __init__(self, vcs, commit):
        self.vcs       = vcs
        self.commitId  = commit['commitId']
        self.timestamp = commit['timestamp']
        self.message   = commit['msg']
        self.uri       = commit['paths'][0]['file'] if commit['paths'] else '.'

    def __str__(self):
        changeset = "   VCS %s  Commit ID # %s  Timestamp: %s  Message: %s " % \
                    (self.vcs, self.commitId, self.timestamp, self.message)
        return changeset


class JenkinsChangesetFile:
    def __init__(self, item):
        self.action    = item['editType']
        self.file_path = item['file']
