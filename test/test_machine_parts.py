import pytest
import yaml
import os
from datetime import datetime, timedelta
from collections import OrderedDict
import re
import time
from bldeif.utils.eif_exception import ConfigurationError, OperationalError, logAllExceptions
from bldeif.utils.klog       import ActivityLogger
from bldeif.utils.konfabulus import Konfabulator
from bldeif.utils.klog       import ActivityLogger
from bldeif.bld_connector import BLDConnector
from bldeif.agicen_bld_connection import AgileCentralConnection
from bldeif.bld_connector_runner import BuildConnectorRunner
from bldeif.utils.time_helper import TimeHelper
from bamboo_test_helper import BambooTestHelper

time_helper = TimeHelper()
TIMEFILE_FORMAT = '%Y-%m-%d %H:%M:%S Z'
ISO_FORMAT      = '%Y-%m-%dT%H:%M:%SZ'

logger = ActivityLogger('logs/test_bamboo_conn.log')

def create_time_file(config_file, secs=None, **kwargs):
    # test for kwargs having hours, minutes, seconds, days - convert to seconds to subract from epoch seconds
    if 'seconds' in kwargs:
        delta = int(int(kwargs['seconds']))
    elif 'minutes' in kwargs:
        delta = int(kwargs['minutes']) * 60
    elif 'hours' in kwargs:
        delta = int(kwargs['hours']) * 3600
    elif 'days' in kwargs:
        delta = int(kwargs['days']) * 86400

    secs_last_run     = secs - delta
    zulu_str_last_run = time_helper.stringFromSeconds(secs_last_run, TIMEFILE_FORMAT)
    time_file_name = "{}_time.file".format(config_file.replace('.yml', ''))

    with open("logs/{}".format(time_file_name), 'w') as tf:
        tf.write(zulu_str_last_run)

    return zulu_str_last_run


def trash_log(file_name):
    try:
        os.unlink('logs/%s.log' % file_name)
    except Exception as ex:
        pass

def test_bld_connector_runner():
    config_file = 'larry.yml'
    trash_log(config_file.replace('.yml',''))
    time.sleep(2)
    args = [config_file]
    runner = BuildConnectorRunner(args)
    assert runner.first_config == config_file

    runner.run()

    assert config_file in runner.config_file_names
    assert 'AgileCentral' in runner.connector.config.topLevels()
    assert 'Rally Fernandel' in runner.connector.target_projects

    log = "logs/{}.log".format(config_file.replace('.yml', ''))
    assert runner.logfile_name == log

    with open(log, 'r') as f:
        log_content = f.readlines()

    line1 = "Connected to Bamboo server"
    line2 = "Connected to Agile Central"

    match1 = [line for line in log_content if "{}".format(line1) in line][0]
    match2 = [line for line in log_content if "{}".format(line2) in line][0]

    assert re.search(r'%s' % line1, match1)
    assert re.search(r'%s' % line2, match2)

def test_times_written_to_log():
    config_file = 'larry.yml'
    trash_log(config_file.replace('.yml', ''))
    time.sleep(2)
    konf = Konfabulator(config_file, logger, True)
    lookback = konf.topLevel('AgileCentral')['Lookback']
    minutes_ago = 10  # pretend last run
    now = time.time()

    pretend_last_run = now - (minutes_ago * 60)
    total_lookback = pretend_last_run - (lookback * 60)

    expected_now                 = time_helper.stringFromSeconds(now,              TIMEFILE_FORMAT)
    expected_old_time_file_value = time_helper.stringFromSeconds(pretend_last_run, TIMEFILE_FORMAT)
    expected_build_creation_date = time_helper.stringFromSeconds(total_lookback,   ISO_FORMAT)

    zulu_str_last_run_zulu = create_time_file(config_file, now, minutes=minutes_ago)
    args = [config_file]
    runner = BuildConnectorRunner(args)

    runner.run()
    log = "logs/{}.log".format(config_file.replace('.yml', ''))
    with open(log, 'r') as f:
        log_content = f.readlines()

    line1 = "Time File value %s --- Now %s" % (expected_old_time_file_value, expected_now)
    line2 = "recent Builds query: CreationDate >= %s" % expected_build_creation_date

    match1 = [line for line in log_content if "{}".format(line1) in line][0]
    match2 = [line for line in log_content if "{}".format(line2) in line][0]

    assert re.search(r'%s' % line1, match1)
    assert re.search(r'%s' % line2, match2)


def test_reflect_builds():
    config_file = "camillo.yml"
    bamboo_helper = BambooTestHelper(config_file)

    project_key = 'FER'
    plan_key    = 'RET'
    plan_name   = 'ReturnOfDonComillio'
    response = bamboo_helper.build(project_key, plan_key)

    trash_log(config_file.replace('.yml', ''))

    args = [config_file]
    runner = BuildConnectorRunner(args)

    runner.run()

    log = "logs/{}.log".format(config_file.replace('.yml', ''))
    assert runner.logfile_name == log

    with open(log, 'r') as f:
        log_content = f.readlines()

    line1 = "Created Build: %s" % plan_name
    match1 = [line for line in log_content if "{}".format(line1) in line][0]
    assert re.search(r'%s' % line1, match1)


def test_dont_duplicate_builds():
    config_file = "camillo.yml"
    bamboo_helper = BambooTestHelper(config_file)

    project_key = 'FER'
    plan_key = 'RET'
    plan_name = 'ReturnOfDonComillio'
    response = bamboo_helper.build(project_key, plan_key)

    trash_log(config_file.replace('.yml', ''))

    args = [config_file]
    runner = BuildConnectorRunner(args)

    runner.run()

    log = "logs/{}.log".format(config_file.replace('.yml', ''))
    assert runner.logfile_name == log

    with open(log, 'r') as f:
        log_content = f.readlines()

    str = "Created Build: %s" % plan_name
    line1 = [line for line in log_content if "{}".format(str) in line][-1]

    assert re.search(r'%s' % str, line1)
    build_number = re.search(r'\s*\d+', line1.split(' #')[1]).string.split()[0]


#
# def test_identify_unrecorded_builds():
#     config_path = 'config/dupes.yml'
#     config_name = config_path.replace('config/', '')
#     config_lookback = 0 # in minutes
#     last_run_zulu = create_time_file(config_name, minutes=1)
#     t = int(time.mktime(time.strptime(last_run_zulu, '%Y-%m-%d %H:%M:%S Z'))) - config_lookback
#     last_run_minus_lookback_zulu = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.localtime(t))
#     args = [config_name]
#     runner = BuildConnectorRunner(args)
#     config = runner.getConfiguration(config_path)
#
#     job_name = 'black-swan-2'
#     folder1 = 'Parkour'
#     folder2 = 'abacab/job/bontamy'
#     jenk_conf = config.topLevel('Jenkins')
#     jenkins_url = jsh.construct_jenkins_url(jenk_conf)
#
#     r1 = jsh.build(jenk_conf, jenkins_url, job_name)
#     assert r1.status_code in [200, 201]
#     r2 = jsh.build(jenk_conf, jenkins_url, job_name, folder=folder1)
#     assert r2.status_code in [200, 201]
#     r3 = jsh.build(jenk_conf, jenkins_url, job_name, folder=folder2)
#     assert r3.status_code in [200, 201]
#     time.sleep(45)
#
#     connector = BLDConnector(config, runner.log)
#     connector.validate()
#
#     print("our ref time: %s" % last_run_minus_lookback_zulu)
#     agicen_ref_time = bld_ref_time = time.localtime(t)
#     recent_agicen_builds = connector.agicen_conn.getRecentBuilds(agicen_ref_time, connector.target_projects)
#     recent_bld_builds = connector.bld_conn.getRecentBuilds(bld_ref_time)
#     unrecorded_builds = connector._identifyUnrecordedBuilds(recent_agicen_builds, recent_bld_builds)
#     runner.log.info("unrecorded Builds count: %d" % len(unrecorded_builds))
#
#     # sort the unrecorded_builds into build chrono order, oldest to most recent, then project and job
#     unrecorded_builds.sort(key=lambda build_info: (build_info[1].timestamp, build_info[2], build_info[1]))
#     paths = []
#     for job, build, project, view in unrecorded_builds:
#         print ("build %s" % build)
#         paths.append(job.fully_qualified_path())
#
#     assert 'tiema03-u183073.ca.com:8080/job/abacab/job/bontamy/view/dark flock/job/black-swan-2' in paths
#     assert 'tiema03-u183073.ca.com:8080/job/black-swan-2' in paths
#     assert 'tiema03-u183073.ca.com:8080/job/Parkour/job/black-swan-2' in paths
#
#
# def test_builds_same_repo():
#     #default_lookback = 3600  # 1 hour in seconds
#     config_lookback = 7200  # this is in seconds, even though in the config file the units are minutes
#     config_file = 'same_scmrepo.yml'
#     z = "2017-01-24 17:17:10 Z"
#     last_run_zulu = create_time_file(config_file, zulu_time=z, minutes=60)
#     t = int(time.mktime(time.strptime(last_run_zulu, '%Y-%m-%d %H:%M:%S Z')))
#     last_run_minus_lookback_zulu = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.localtime(t))
#     args = [config_file]
#     runner = BuildConnectorRunner(args)
#     assert runner.first_config == config_file
#
#     runner.run()
#     target_projects = runner.connector.target_projects
#     assert 'Jenkins // Salamandra' in target_projects
#     assert 'Jenkins // Corral // Salamandra' in target_projects
#
#
# def test_special_chars():
#     config_file = 'aouch.yml'
#     z = "2017-01-24 17:17:10 Z"
#     last_run_zulu = create_time_file(config_file, zulu_time=z, minutes=60)
#     t = int(time.mktime(time.strptime(last_run_zulu, '%Y-%m-%d %H:%M:%S Z')))
#     args = [config_file]
#     runner = BuildConnectorRunner(args)
#     assert runner.first_config == config_file
#
#     runner.run()
#     log = "log/{}.log".format(config_file.replace('.yml', ''))
#     assert runner.logfile_name == log
#
#     with open(log, 'r', encoding='utf-8') as f:
#         log_content = f.readlines()
#
#     target_line = "showQualifiedJobs -     áâèüSørençñ"
#     match = [line for line in log_content if target_line in line][0]
#     assert re.search(r'%s' % target_line, match)
#
#     target_line = "東方青龍"
#     match = [line for line in log_content if target_line in line][0]
#     assert re.search(r'%s' % target_line, match)
#
#
# def test_lock():
#     lock = 'LOCK.tmp'
#     config_path = 'config/wombat.yml'
#     config_name = config_path.replace('config/', '')
#     args = [config_name]
#     runner = BuildConnectorRunner(args)
#     assert runner.acquireLock()
#     assert os.path.isfile(lock)
#     assert os.path.abspath(lock) == "%s/%s" % (os.getcwd(), lock)
#     runner.releaseLock()
#     assert not os.path.isfile(lock)
#
# def test_two_runners():
#     lock = 'LOCK.tmp'
#     config_path = 'config/wombat.yml'
#     config_name = config_path.replace('config/', '')
#     args = [config_name]
#     runner1 = BuildConnectorRunner(args)
#     assert runner1.acquireLock()
#     assert os.path.isfile(lock)
#     assert os.path.abspath(lock) == "%s/%s" % (os.getcwd(), lock)
#     runner2 = BuildConnectorRunner(args)
#     expectedErrPattern = "Simultaneous processes for this connector are prohibited"
#     with pytest.raises(Exception) as excinfo:
#         runner2.acquireLock()
#     actualErrVerbiage = excinfo.value.args[0]
#     assert re.search(expectedErrPattern, actualErrVerbiage) is not None
#     runner1.releaseLock()
#    assert not os.path.isfile(lock)