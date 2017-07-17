import os
import shutil
import re
from bldeif.utils.fuzzer import Fuzzer
from bldeif.utils.environmental_key import EnvironmentalKey
from bldeif.utils.encrypter import Encrypter, DecryptionError
from bldeif.utils.eif_exception import EIFException,OperationalError,ConfigurationError

class SecurityManager:
    def __init__(self, conf, security_level, logger):
        self.level = security_level
        self.conf  = conf
        self.log   = logger
        if self.level == 'Encrypt':
            self.env_key   = EnvironmentalKey(conf).identVector()
            self.encryptor = Encrypter(self.env_key)

    def applyPolicyToSection(self, section):
        section_name    = [k for k in section.keys()][0]
        protected_items = section[section_name]
        if self.level == 'Encode':
             self.defuzz(self.conf.topLevel(section_name), section_name, protected_items)
        elif self.level == 'Encrypt':
             self.decrypt(self.conf.topLevel(section_name), section_name, protected_items)


    def defuzz(self, config, section, secrets):
        for secret in secrets:
            value = config.get(secret, None)
            if value:
                if Fuzzer.isEncoded(value):
                    config[secret] = Fuzzer.defuzz(value)
                elif value.startswith('SECURED-'):
                    problem = "Downgrading SecurityLevel from 'Encrypt' to 'Encode' is not allowed. "
                    remedy  = "Change credentials to clear text in config file manually, and then run the connector with lower SecurityLevel : Encode."
                    raise ConfigurationError(problem + remedy)
                else:
                    protected = Fuzzer.fuzz(value)
                    self.protectCredential(section, secret, protected)

    def decrypt(self, config, section, secrets):
        for secret in secrets:
            value = config.get(secret,None)
            if value:
                if value.startswith('SECURED-'):
                    try:
                        config[secret] = self.encryptor.decrypt(value.replace('SECURED-', ''))
                    except DecryptionError:
                        problem = 'EnvironmentalKey ident_vector not valid for decryption target value.  '
                        action  = 'Reset all credential values to clear text in config file!'
                        raise ConfigurationError( problem + action)
                    continue
                elif value.startswith('encoded-'):
                    cleartext = Fuzzer.defuzz(value)
                    config[secret] = cleartext
                    protected = self.encryptor.encrypt(cleartext)
                else:
                    protected = self.encryptor.encrypt(value)
                self.protectCredential(section, secret, 'SECURED-' + protected)


    def protectCredential(self, section, target, protected_value):
        conf_lines = []
        try:
            cf = open(self.conf.config_file_path, 'r', encoding='utf-8')
        except IOError as msg:
            raise ConfigurationError('Unable to open %s for reading, %s' % (self.conf.config_file_path, msg))
        conf_lines = cf.readlines()
        cf.close()

        out_lines = []
        ix = 0

        # objective:   Find index of conn_section entry in conf_lines
        #              then find index of next occurring Password : xxxx entry
        #              substitute entry for Password : current with Password : encoded_password
        ##
        ##        print "fuzzPassword, conn_section: %s" % conn_section
        ##        print "conf_lines:\n%s" % "\n".join(conf_lines)
        ##        print "-----------------------------------------------------"
        ##
        hits = [ix for ix, line in enumerate(conf_lines) if re.search('^\s+%s\s*:' % section, line)]
        section_ix = hits[0]
        hits = [ix for ix, line in enumerate(conf_lines) if
                re.search('^\s+%s\s*:\s*' % target, line) and ix > section_ix]
        if not hits:
            return True

        pwent_ix = hits[0]
        conf_lines[pwent_ix] = '%s%-10.10s :  %s\n' % (' ' * 8, target, protected_value)

        enc_file_name = '%s.pwenc' % self.conf.config_file_path
        enf = open(enc_file_name, 'w', encoding='utf-8')
        enf.write(''.join(conf_lines))
        enf.close()

        bkup_name = "%s.bak" % self.conf.config_file_path
        try:
            shutil.copy2(self.conf.config_file_path, bkup_name)
        except Exception as msg:
            self.log.warn("Unable to write a temporary backup file '%s' with config info: %s" % (bkup_name, msg))
            return False

        try:
            os.remove(self.conf.config_file_path)
        except Exception as msg:
            self.log.warn(
                "Unable to remove config file prior to replacement with password encoded version of the file: %s" % msg)
            return False

        try:
            os.rename(enc_file_name, self.conf.config_file_path)
        except Exception as msg:
            self.log.error(
                "Unable to rename config file with password encoded to standard config filename of %s: %s" % (
                self.conf.config_file_path, msg))
            return False

        try:
            os.remove(bkup_name)
        except Exception as msg:
            self.log.warn("Unable to remove temporary backup file for config: %s" % msg)
            return False

        return True
