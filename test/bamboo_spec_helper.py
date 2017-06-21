import sys
import requests
import json
import yaml


'''
To POST a build in bamboo:

curl -X POST --user toto:totogithub http://localhost:8085/rest/api/latest/queue/FER-DON?os_authType=basic

curl --user toto:totogithub http://localhost:8085/rest/api/latest/result/FER-DON.json?expand=results[0].result
'''

def read_config(config_file):
    config_path = "configs/{}".format(config_file)
    with open(config_path, 'r') as cf:
        content = cf.read()
        conf = yaml.load(content)
    return conf

def construct_bamboo_base_url(conf):
    protocol = conf['Protocol']
    server   = conf['Server']
    port     = conf['Port']
    return "%s://%s:%d/rest/api/latest" % (protocol, server, port)

def build(config_file, project, plan):
    config = read_config(config_file)
    bamboo = config['BambooBuildConnector']['Bamboo']
    base_url = construct_bamboo_base_url(bamboo)
    endpoint = "queue/%s-%s" %(project,plan)
    headers = {'Content-Type':'application/xml'}
    url = "%s/%s?os_authType=basic" % (base_url, endpoint)
    r = requests.post(url, auth=(bamboo['Username'], bamboo['Password']), headers=headers)
    return r


def get_latest_bulid(config_file, project, plan):
    config = read_config(config_file)
    bamboo = config['BambooBuildConnector']['Bamboo']
    base_url = construct_bamboo_base_url(bamboo)
    headers = {'Content-Type': 'application/json'}
    endpoint = "result/%s-%s.json?expand=results[0].result" % (project, plan)
    url = "%s/%s" % (base_url, endpoint)
    r = requests.get(url, auth=(bamboo['Username'], bamboo['Password']), headers=headers)
    return r

def test_helper():
    config_file = 'camillo.yml'
    config = read_config(config_file)
    bamboo = config['BambooBuildConnector']['Bamboo']
    ac     = config['BambooBuildConnector']['AgileCentral']
    serv   = config['BambooBuildConnector']['Service']
    assert bamboo['Server'] == 'localhost'
    assert ac['Workspace'] == 'Alligators BLD Unigrations'
    assert serv['ShowVCSData'] == False
    base_url = construct_bamboo_base_url(bamboo)
    assert base_url == 'http://localhost:8085/rest/api/latest'

def test_build():
    config_file = 'camillo.yml'
    project_key = 'FER'
    plan_key    = 'DON'
    response = build(config_file, project_key, plan_key)
    assert response.status_code == 200

def test_get_latest_build():
    config_file = 'camillo.yml'
    project_key = 'FER'
    plan_key = 'DON'
    response = get_latest_bulid(config_file, project_key, plan_key)
    assert response.status_code == 200
    result = response.json()['results']['result'][0]
    assert result['projectName'] == 'Fernandel'
    assert result['planName']    == 'DonCamillo'
    assert result['buildNumber'] >= 45
    assert result['buildState']  == 'Successful'
    assert 'buildStartedTime'   in result
    assert 'buildCompletedTime' in result
    assert 'vcsRevisionKey'     in result
    assert 'buildDuration'      in result
    assert 'buildDurationInSeconds' in result

