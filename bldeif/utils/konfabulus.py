__doc__ = """
This module contains a class and a couple of functions.
The Konfabulator class handles loading up a config file (which must be in YAML format)
and checks for basic structure validity.
"""

#################################################################################################

import sys, os
import re
import shutil

import yaml

from bldeif.utils.eif_exception import ConfigurationError, NonFatalConfigurationError
from bldeif.utils.security_manager import SecurityManager
from bldeif.utils.fuzzer import Fuzzer


#################################################################################################

class Konfabulator:
    """
        An instance of this class provides a means to read a configuration file
        in YAML format and separate the various sections out for easy consumption by
        holders of a Konfabulator instance.
        An instance also offers the capability to "fuzz" clear-text passwords in a
        configs file into an encoded (but not encrypted) form and to be able to handle
        defuzzing those encoded passwords for holders of the instance when they access
        those values via a dict like access.
    """

    def __init__(self, config_file_name, logger, cleartext_flag):
        config_dir = 'configs'
        self.config_file_name = config_file_name
        self.log = logger
        self.cleartext_flag = cleartext_flag
        self.top_level_sequence = []
        self.config_file_path =  '%s/%s' %(config_dir, self.config_file_name)
        self.security_level = 'Encrypt'

        # check for existence, file-ness, readability of config_file_name
        if not os.path.exists(self.config_file_path):
            raise ConfigurationError('config file: %s not found' % self.config_file_path)
        if not os.path.isfile(self.config_file_path):
            raise ConfigurationError('config file: %s is not a file' % self.config_file_path)
        if not os.access(self.config_file_path, os.F_OK | os.R_OK):
            raise ConfigurationError('config file: %s not a readable file' % self.config_file_path)

        try:
            cf = open(self.config_file_path, 'r', encoding='utf-8')
        except IOError as msg:
            raise ConfigurationError('Unable to open %s for reading, %s' % (self.config_file_path, msg))
        self.content = cf.read()
        cf.close()

        basic_sanity, problem = self._checkConfigFileContentSanity()
        if not basic_sanity:
            raise ConfigurationError('Config file (%s) syntax/structure is incorrect, %s' % (self.config_file_path, problem),
                                     logger=logger)

        try:
            complete_config = yaml.load(self.content)
            top_key = list(complete_config.keys())[0]
            self.config = complete_config[top_key]
        except Exception as msg:
            raise ConfigurationError('Unable to parse %s successfully, %s' % (self.config_file_path, msg), logger=logger)

        conf_lines = [line for line in self.content.split('\n') if line and not re.search(r'^\s*#', line)]
        connector_header = [line for line in conf_lines if re.search(r'^[A-Z][A-Za-z_]+.+\s*:', line)]
        section_headers = [line for line in conf_lines if re.search(r'^    [A-Z][A-Za-z_]+.*\s*:', line)]
        ##
        # print(repr(self.configs))
        ##

        # set up defaults for the Service section if that section isn't in the configs file
        if 'Service' not in self.config:
            self.config['Service'] = {}
            self.config['Service']['LogLevel'] = 'Info'
            self.config['Service']['Preview'] = False
            self.config['Service']['MaxBuilds'] = 50
            self.config['Service']['ShowVCSData'] = True
            self.config['Service']['SecurityLevel'] = self.security_level
            section_headers.append('    Service:')
        if not 'LogLevel' in self.config['Service']:
            self.config['Service']['LogLevel'] = 'Info'
        if not 'Preview' in self.config['Service']:
            self.config['Service']['Preview'] = False
        if 'SecurityLevel' not in self.config['Service']:
            self.config['Service']['SecurityLevel'] = self.security_level
        else:
            if self.config['Service']['SecurityLevel'] in ['Cleartext', 'Encode', 'Encrypt']:
                self.security_level = self.config['Service']['SecurityLevel']
            else:
                problem = 'Invalid Security level: %s is used in the configuration' % self.config['Service'][
                    'SecurityLevel']
                raise ConfigurationError(problem)
        if self.cleartext_flag:
            self.security_level = 'Cleartext'

        if len(section_headers) < 2:
            raise ConfigurationError('Insufficient content in configs file: %s' % self.config_file_path)
        if len(section_headers) > 3:
            raise NonFatalConfigurationError('Excess or unrecognized content in configs file: %s' % self.config_file_path)

        self.agicen_header = section_headers.pop(0).strip().replace(':', '')
        if not self.agicen_header.startswith('AgileCentral'):
            raise ConfigurationError('First section in configs file must be AgileCentral section')
        self.top_level_sequence.append('AgileCentral')

        self.bld_header = section_headers.pop(0).strip().replace(':', '')

        if self.bld_header not in ['Bamboo']:
            problem = 'Second section in config file must be Bamboo'
            raise ConfigurationError(problem)
        self.top_level_sequence.append(self.bld_header)

        # because the EnvironmentKey needs an AgileCentral Workspace and Project, set that up here
        workspace = self.config['AgileCentral']['Workspace']
        self.config['AgileCentral']['Workspace'] = workspace
        self.config['AgileCentral']['Project'] = workspace[::-1]

        while section_headers:
            header = section_headers.pop(0).replace(':', '').strip()
            try:
                if header not in ['Service']:
                    problem = 'configs section header "%s" not recognized, ignored...' % header
                    raise ConfigurationError(problem)
                else:
                    self.top_level_sequence.append(header)
            except ConfigurationError as msg:
                pass

        if 'Service' not in self.top_level_sequence:
            self.top_level_sequence.append('Service')

    def applySecurityPolicy(self):
        if self.security_level.upper() != 'Cleartext'.upper():
            self.sec_mgr = SecurityManager(self, self.security_level, self.log)
            target_sections = [{'AgileCentral': ['Username', 'Password', 'APIKey', 'ProxyUsername', 'ProxyPassword']},
                               {'Bamboo'      : ['Username',     'Password']}]

            for section in  target_sections:
                self.sec_mgr.applyPolicyToSection(section)

        # now, get rid of the artifically added
        #del self.config['AgileCentral']['Workspace']
        #del self.config['AgileCentral']['Project']


    def _checkConfigFileContentSanity(self):
        sanity = True
        problem = ''
        has_tabs = [char for char in self.content if char == "\t"]
        if has_tabs:
            sanity = False
            problem = "Your config file contains tab characters which are not allowed in a YML file."
            return sanity, problem

        config_lines = self.content.split("\n")
        yaml_lines = [line for line in config_lines if line and not re.search(r'^\s*#', line)]
        yaml_lines = [line for line in yaml_lines if not re.search(r'^---|\.\.\.$', line)]
        yee = r' (include|exclude|Project)\s*:'  # yee --> YAML entry exclusions
        yaml_major_lines = [line for line in yaml_lines if not re.search(yee, line)]
        line_indents = [re.search(r'^(?P<indent>\s*)', line).group('indent') for line in yaml_major_lines]
        indent_levels = sorted(list(set([len(indent) for indent in line_indents])))
        outer_start = indent_levels[0]
        if outer_start:
            first_item = 0
        else:
            first_item = 1

        indent = indent_levels[first_item]
        line_indent = 4
        # for line_indent in indent_levels[first_item + 1:]:
        #     if line_indent % indent:
        #         # check to see if the "violation" involves one of 'exclude', 'include', 'AgileCentral_Project'
        #         #   parent ident = line_indent - 2
        #         #   if parent_ident is not  a violator  parent_ident % indent == 0, then skip calling this a problem...
        #         sanity = False
        #         problem = 'The file does not contain consistent indentation for the sections and section contents. '
        #         break

        if not sanity:
            first_offender_indent = line_indent
            for ix, config_line in enumerate(config_lines):
                mo = re.search("^(?P<spaces>\s+)(?P<non_space>\S)", config_line)
                if mo and mo.group('non_space') == '#':
                    continue
                if mo and len(mo.group('spaces')) == first_offender_indent:
                    offending_line_index = ix + 1
                    problem = problem + "The first occurrence of the problem is on line: %d" % offending_line_index
                    break

        return sanity, problem

    def topLevels(self):
        return self.top_level_sequence

    def topLevel(self, section_name):
        if section_name in self.top_level_sequence: #and section_name in self.config:
            return self.config[section_name]
        else:
            problem = 'Attempt to retrieve non-existent top level configs section for %s'
            raise ConfigurationError(problem % section_name)

    def connectionClassName(self, section_name):
        if section_name not in self.config:
            raise ConfigurationError('Attempt to identify connection class name for %s, operation not supported'% section_name)
        if section_name not in ['AgileCentral', self.bld_header]:
            raise ConfigurationError('Candidate connection class name "%s" not viable for operation'% section_name)
        section = self.config[section_name]
        if 'Class' in section:
            class_name = section['Class']
        else:
            class_name = 'AgileCentralConnection'
            if section_name != 'AgileCentral':
                class_name = '%sConnection' % self.bld_header

        return class_name