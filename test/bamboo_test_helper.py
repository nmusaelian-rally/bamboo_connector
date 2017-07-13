import sys
import requests
import json
import yaml


'''
To POST a build in bamboo:

curl -X POST --user bamboozel:rallydev http://koljo03-s4576.ca.com:8085/rest/api/latest/queue/FER-DON?os_authType=basic

curl --user bamboozel:rallydev http://koljo03-s4576.ca.com:8085/rest/api/latest/result/FER-DON.json?expand=results[0].result
'''

class BambooTestHelper():
    def __init__(self, config_file):
        self.conf = self.read_config(config_file)

    def read_config(self, config_file):
        config_path = "configs/{}".format(config_file)
        with open(config_path, 'r') as cf:
            content = cf.read()
            conf = yaml.load(content)
        return conf

    def construct_bamboo_base_url(self):
        bamboo = self.conf['BambooBuildConnector']['Bamboo']
        protocol = bamboo['Protocol']
        server   = bamboo['Server']
        port     = bamboo['Port']
        return "%s://%s:%d/rest/api/latest" % (protocol, server, port)

    def build(self, project, plan):
        bamboo = self.conf['BambooBuildConnector']['Bamboo']
        base_url = self.construct_bamboo_base_url()
        endpoint = "queue/%s-%s" %(project,plan)
        #headers = {'Content-Type':'application/json'}
        url = "%s/%s.json?os_authType=basic" % (base_url, endpoint)
        r = requests.post(url, auth=(bamboo['Username'], bamboo['Password']))#, headers=headers) #content-type header has no effect, added .json
        return r.json()


    def get_latest_bulid(self, project, plan):
        bamboo = self.conf['BambooBuildConnector']['Bamboo']
        base_url = self.construct_bamboo_base_url()
        headers = {'Content-Type': 'application/json'}
        endpoint = "result/%s-%s.json?expand=results[0].result" % (project, plan)
        url = "%s/%s" % (base_url, endpoint)
        r = requests.get(url, auth=(bamboo['Username'], bamboo['Password']), headers=headers)
        return r

####################################### test BambooTestHelper ###########################
config_file = 'camillo.yml'
helper = BambooTestHelper(config_file)

def test_helper():
    bamboo = helper.conf['BambooBuildConnector']['Bamboo']
    ac     = helper.conf['BambooBuildConnector']['AgileCentral']
    serv   = helper.conf['BambooBuildConnector']['Service']

    assert bamboo['Server'] == 'koljo03-s4576.ca.com'
    assert ac['Workspace'] == 'Alligators BLD Unigrations'
    assert serv['ShowVCSData'] == False
    base_url = helper.construct_bamboo_base_url()
    assert base_url == 'http://koljo03-s4576.ca.com:8085/rest/api/latest'

def test_build():
    project_key = 'FER'
    plan_key    = 'DON'
    response = helper.build(project_key, plan_key)
    assert response['buildResultKey'].startswith("%s-%s" %(project_key,plan_key))

def test_get_latest_build():
    project_key = 'FER'
    plan_key = 'DON'
    response = helper.get_latest_bulid(project_key, plan_key)
    assert response.status_code == 200
    result = response.json()['results']['result'][0]
    assert result['projectName'] == 'Fernandel'
    assert result['planName']    == 'DonCamillo'
    assert result['buildNumber'] >= 3
    assert result['buildState']  == 'Successful'
    assert 'buildStartedTime'   in result
    assert 'buildCompletedTime' in result
    assert 'buildDuration'      in result
    assert 'buildDurationInSeconds' in result

