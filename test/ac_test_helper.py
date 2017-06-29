import sys, os
import re
import time
from pyral import Rally, rallyWorkset, RallyRESTAPIError

APIKEY = '_2QFAQA0wQoSKiORUOsVlMjeQfFr1JkawtItGFHtrtx8'
class RallyHelper():
    def __init__(self, workspace, project):
        self.workspace = workspace
        self.project   = project
        self.rally     = Rally("rally1.rallydev.com", apikey=APIKEY, workspace=self.workspace, project=self.project)
        self.scm_repo_name = "wombat_%s" % int(time.time())

    def find_scm_repo(self, name):
        fields = "ObjectID"
        query = '(Name = "{}")'.format(name)
        scm_repos = []
        response = self.rally.get('SCMRepository', fetch=fields, query=query, order="Name", project=None, pagesize=20, limit=20)
        if response.resultCount > 0:
            for item in response:
                scm_repos.append(item)
            return scm_repos[0]
        return None

    def create_scm_repo(self, name, scm_type):
        repo = self.find_scm_repo(name)
        if repo:
            print ("SCMRepository %s already exists" %name)
            return repo

        scm_repo_payload = {
            'Name'    : name,
            'SCMType' : scm_type
        }
        try:
            scm_repo = self.rally.create('SCMRepository', scm_repo_payload)
            print("Created SCMRepository %s" % scm_repo.ObjectID)
        except RallyRESTAPIError as msg:
            sys.stderr.write('ERROR: %s \n' % msg)
            sys.exit(4)

        return scm_repo

    def delete_scm_repo(self, name):
        result = self.find_scm_repo(name)
        if not result:
            print ("SCMRepository %s does not exists" %name)
            return False
        else:
            self.delete_changesets_of_scm_repo(name)
            try:
                scm_repo = self.rally.delete('SCMRepository', result.ObjectID, project=None)
                print("Deleted SCMRepository %s" % result.ObjectID)
            except RallyRESTAPIError as msg:
                sys.stderr.write('ERROR: %s \n' % msg)
                raise
        return True

    def get_all_scm_repos(self):
        fields    = "Name,ObjectID" # REMEMBER: no spaces in the fetch list!!!!
        response = self.rally.get('SCMRepository', fetch=fields, order="CreationDate", project=None, pagesize=200)
        return response

    def bulk_delete_scm_repos(self):
        scm_repos = self.get_all_scm_repos()
        if scm_repos.resultCount == 0:
            return False

        for repo in scm_repos:
            print("\n%s: %s" % (repo.Name, repo.ObjectID))
            try:
                print("deleting SCMRepository %s" %repo.Name)
                self.rally.delete("SCMRepository", repo.ObjectID, "Alligators BLD Unigrations", project=None)
            except Exception as msg:
                print("Problem deleting SCMRepository %s" %repo.Name)
                raise RallyRESTAPIError(msg)

        return True

    def get_changesets_of_scm_repo(self, repo_name):
        fields = "ObjectID"
        query = "(SCMRepository.Name = {})".format(repo_name)
        changesets = []
        response = self.rally.get('Changeset', fetch=fields, query=query, order="Name", project=None, pagesize=20, limit=20)
        if response.resultCount:
            for item in response:
                changesets.append(item)
            return changesets
        return None


    def delete_changesets_of_scm_repo(self,repo_name):
        changesets = self.get_changesets_of_scm_repo(repo_name)
        if not changesets:
            return False

        for changeset in changesets:
            print("\n%s: %s" % (changeset.Name, changeset.ObjectID))
            try:
                print("deleting Changeset %s" %changeset.ObjectID)
                self.rally.delete("Changeset", changeset.ObjectID)
            except Exception as msg:
                print("Problem deleting Changeset %s" %changeset.ObjectID)
                raise RallyRESTAPIError(msg)

        return True


    def get_build_definition(self, build_def_name, project='Static'):
        fields = "Name,ObjectID,Project,Builds"
        query = ('Name = "%s"' % build_def_name)
        response = self.rally.get('BuildDefinition', fetch=fields, query=query, project=project, pagesize=200)
        if response.resultCount == 0:
            return []
        return [item for item in response]


    def get_ac_builds(self, build_def, project='Static'):
        fields = "ObjectID,BuildDefinition,Number,Status,Uri"
        query = ("BuildDefinition.ObjectID = %s" %(build_def.ObjectID))
        response = self.rally.get('Build', fetch=fields, query=query, project=project, pagesize=200)
        return [item for item in response]

    def get_ac_build(self, build_def_name, build_num, project='Static'):
        fields = "ObjectID,BuildDefinition,Number,Status,Uri"
        condition1 = "BuildDefinition.Name = %s" % build_def_name
        condition2 = "Number = %s" % build_num
        query = [condition1,condition2]
        response = self.rally.get('Build', fetch=fields, query=query, project=project, pagesize=200)
        return [item for item in response]

    def delete_ac_build_definition(self, build_def):
        try:
            #print("deleting Build Definition %s" % build_def.ObjectID)
            self.rally.delete("BuildDefinition", build_def.ObjectID)
        except Exception as msg:
            print(msg)
            raise RallyRESTAPIError(msg)


    def delete_ac_builds(self, job_name):
        fields = "Name,ObjectID"
        query = ('Name = "%s"' % job_name)
        response = self.rally.get('BuildDefinition', fetch=fields, query=query, project=None, pagesize=200)
        for build_def in response:
            builds = self.get_ac_builds(build_def)
            self.delete_ac_builds(builds)
            self.delete_ac_build_definition(build_def)
        return []


    def create_change(self, changeset_ref, path_n_filename):
        change_payload = {
            'Changeset': changeset_ref,
            'PathAndFilename': path_n_filename
        }
        try:
            change = self.rally.create('Change', change_payload)
            print("Created Change %s" % change.ObjectID)
        except RallyRESTAPIError as msg:
            print(msg)
            raise RallyRESTAPIError(msg)

        return change

    def update_changeset(self, payload):
        try:
            changeset = self.rally.update('Changeset', payload)
            print("Updated Changeset %s" % changeset.ObjectID)
        except RallyRESTAPIError as msg:
            print(msg)
            raise RallyRESTAPIError(msg)
        return changeset

ac_helper  = RallyHelper(workspace="Alligators BLD Unigrations", project="Jenkins")

########################## tests ###########################################
def test_find_scm_repo():
    name = "test_centaurus"
    oid  = 88782854296
    result = ac_helper.find_scm_repo(name)
    assert result.ObjectID == oid

def test_create_and_delete_scm_repo():
    name = ac_helper.scm_repo_name
    scm_type = 'git'
    assert ac_helper.create_scm_repo(name, scm_type)
    assert ac_helper.delete_scm_repo(name)

def test_backslash_in_name():
    name = r'C:\some\local\path'  # created "_refObjectName": "C:\\some\\local\\path"
    scm_type = 'git'
    assert ac_helper.create_scm_repo(name, scm_type)
    assert ac_helper.delete_scm_repo(name)

def test_create_change():
    changeset_ref = '/changeset/79718865700'
    path_n_file = '/home/n/venison/foobar'
    result = ac_helper.create_change(changeset_ref, path_n_file)
    assert result

def test_update_changeset():
    payload = {
        'ObjectID': 79718865700,
        'Uri'     : 'http://bogus/path'
    }
    result = ac_helper.update_changeset(payload)
    assert result

def test_get_ac_builds():
    build_def = ac_helper.get_build_definition("DonCamillo", project="Rally Fernandel")[0]
    builds = ac_helper.get_ac_builds(build_def, project='Rally Fernandel')
    assert len(builds) > 10
    build_number = builds[0].Number
    assert builds[0].Uri == 'http://localhost:8085/browse/FER-DON-%s' % build_number

def test_get_ac_build():
    build_def = "DonCamillo"
    build_num = '50'
    builds = ac_helper.get_ac_build(build_def, build_num, project='Rally Fernandel')
    assert len(builds) == 1
    assert builds[0].Number == build_num
    assert builds[0].BuildDefinition.Name == "DonCamillo"

# def test_bulk_delete_scm_repos():
#     assert ac_helper.bulk_delete_scm_repos()

# def test_delete_changesets_of_scm_repo():
#     scm_repo = "MockBuildsRepo"
#     ac_helper.delete_changesets_of_scm_repo(scm_repo)


################## parsing formatted id from commit message

def extract_fids(message):
    prefixes = ['S', 'US', 'DE', 'TA', 'TC', 'DS', 'TS']
    fid_pattern = r'((%s)\d+)' % '|'.join(prefixes)
    result = re.findall(fid_pattern, message, re.IGNORECASE)
    return [item[0].upper() for item in result]


def test_extract_fids():
    commit_message = "US123, US456 done!"
    assert extract_fids(commit_message) == ['US123', 'US456']
    commit_message = "US123DE4"
    assert extract_fids(commit_message) == ['US123', 'DE4']
    commit_message = "s123, de456 foo666 done!"
    assert extract_fids(commit_message) == ['S123', 'DE456']
    commit_message = "Jojo did [DE543-S123421-TAX123];TC098/DE3412(BA23,S543)"
    assert extract_fids(commit_message) == ['DE543', 'S123421', 'TC098', 'DE3412', 'S543']
    commit_message = "!US123, US456 done!\n adfadsfafTC999[PFI7878]DDE2344"
    assert extract_fids(commit_message) == ['US123', 'US456', 'TC999', 'DE2344']
    commit_message = "<b>US123:</b> done, <b>DE1:</b> fixed"
    assert extract_fids(commit_message) == ['US123', 'DE1']

