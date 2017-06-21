import sys, os
import re
import pytest

sys.path.insert(0, 'bldef')
from bldeif.utils.konfabulus    import Konfabulator
from bldeif.utils.klog          import ActivityLogger
from bldeif.utils.eif_exception import ConfigurationError, NonFatalConfigurationError

logger = ActivityLogger('logs/test_db_connection.log')

def trash_log(file_name):
    try:
        os.unlink('logs/%s.log' % file_name)
    except Exception as ex:
        pass

def useConfig(conf_name, cleartext=True):
    cf_name = conf_name if conf_name.endswith('.yml') else "%s.yml" % conf_name
    trash_log(conf_name)
    konf = Konfabulator(cf_name, logger, cleartext)
    if cleartext:
        konf.security_level = 'Cleartext'
    konf.applySecurityPolicy()
    return konf

def test_konfabulator():
    logger = ActivityLogger('logs/defaults.log')
    konf = Konfabulator('camillo.yml', logger, True)
    bamboo_conf = konf.topLevel('Bamboo')
    ac_conf = konf.topLevel('AgileCentral')
    srv_conf = konf.topLevel('Service')
    assert bamboo_conf['Server'] == 'localhost'
    assert ac_conf['Workspace'] == 'Alligators BLD Unigrations'
    assert srv_conf['ShowVCSData'] == False

def test_bad_indent():
    cf_name = 'bad_indent'
    log = 'logs/%s.log' % cf_name
    logger = ActivityLogger(log)
    encode = False
    with pytest.raises(Exception) as exc_info:
        Konfabulator('%s.yml' %cf_name, logger, encode)

    expected1 = 'line 13'
    expected2 = 'mapping values are not allowed here'
    actualErrVerbiage = exc_info.value.args[0]
    pmo1 = re.search(expected1, actualErrVerbiage)
    pmo2 = re.search(expected2, actualErrVerbiage)
    assert pmo1
    assert pmo2

def test_top_levels():
    config_file = 'no_service.yml'
    with open('configs/%s' % config_file, 'r') as sf:
        orig_config_content = sf.read()
    konf = useConfig(config_file, False)
    assert konf.topLevel('AgileCentral').get('Workspace', None)
    assert konf.topLevel('Bamboo').get('AgileCentral_DefaultBuildProject', None)
    assert konf.topLevel('Service')   # This all gets defaulted in Konfabulus instantiation...
    assert konf.topLevel('Service').get('SecurityLevel', None) == 'Encrypt'
    with open('configs/%s' % config_file, 'r') as sf:
        secured_config_content = sf.read()

    assert secured_config_content.count("SECURED-") == 3
    with open('configs/%s' % config_file, 'w') as sf:
        sf.write(orig_config_content)

def test_bad_section():
    config_file = 'bad_section.yml'
    problem = 'Second section in config file must be Bamboo'
    with pytest.raises(ConfigurationError) as excinfo:
        useConfig(config_file, False)
    assert problem in str(excinfo.value)