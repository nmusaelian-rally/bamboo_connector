import os,sys,platform
import re
import getpass
import subprocess
try:
    from pwd import getpwuid
except:
    pass


class EnvironmentalKey:
    def __init__(self, konf):
        self.konf = konf
        # conf_file_name, conf_path, ac_server, ac_workspace, ac_project, gh_server
        self.ac_server = konf.topLevel('AgileCentral')['Server']

    def executeShellCommand(self, cmd, pattern=None, dosplit=True, re_flags=''):
        pipe = subprocess.Popen(cmd, shell=True, cwd='.', stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, error = pipe.communicate()
        # print (out, error)
        pipe.wait()
        if dosplit:
            output_lines = out.decode().split("\n")
            if pattern:
                lines = [line.strip() for line in output_lines]
                output_lines = [line for line in lines if re.search(pattern, line, re.I | re.M)]
            return output_lines
        else:
            if pattern:
                return re.search(pattern, out.decode(), re.I | re.M)
            return out

    def getMacAddress(self, operating_system):
        macaddr = 'mac address not obtained'
        command = 'ifconfig -a'
        if operating_system == 'mac':
            pattern = r'(e[a-z][a-z0-9]*\d+): .*?\n\s+ether (([a-f0-9]{2}:){5}[a-f0-9]{2})\s*\n'
            # ifc, macaddr = '$1, $2 if output =~ /(e[a-z][a-z0-9]*\d+): .*?\n\s+ether (([a-f0-9]{2}:){5}[a-f0-9]{2})\s*\n/im'
        elif operating_system == 'posix':
            pattern = r'(e[a-z][a-z0-9]*\d+)\s+Link encap:Ethernet \s*HWaddr (([a-f0-9]{2}:){5}[a-f0-9]{2})\s*\n'
            #ifc, macaddr = "$1, $2 if output =~ /(e[a-z][a-z0-9]*\d+)\s+Link encap:Ethernet \s*HWaddr (([a-f0-9]{2}:){5}[a-f0-9]{2})\s*\n/im"
        elif operating_system == 'windows':
            command = 'ipconfig /all'
            pattern = r'Physical Address.*?(([A-F0-9]{2}-){5}[A-F0-9]{2})'
            # pattern = r'macaddr = $1 if output =~ /Physical Address.*?(([A-F0-9]{2}-){5}[A-F0-9]{2})/im'
        else:
            return '89:AF:43:BC:71:DD'

        result = self.executeShellCommand(command, pattern, dosplit=False, re_flags='im')
        if operating_system in ['mac', 'posix']:
            try:
                macaddr = result.group(2)
            except Exception as exc:
                command = 'ip link'
                pattern = r'\s+\w+\/ether\s+([0-9A-Z:]+)\s'
                result = self.executeShellCommand(command, pattern, dosplit=False, re_flags='im')
                macaddr = result.group(1)
        else:
            macaddr = result.group(0).split(':')[1]
        return macaddr

    def getHardwareId(self, operating_system):
        # if operating_system is 'mac' then we can get both hardware_uuid and serial_number (combine them)
        if operating_system == 'mac':
            hardware_uuid, serial_number = '', ''
            cmd    = "system_profiler SPHardwareDataType"
            result = self.executeShellCommand(cmd, pattern='(Serial Number|Hardware UUID)')

            for line in result:
                line = line.lstrip()
                if line.startswith('Serial Number (system):'):
                    serial_number = line.split(': ')[1]
                elif line.startswith('Hardware UUID:'):
                    hardware_uuid = line.split(': ')[1]
            return "-".join([hardware_uuid, serial_number])

        elif operating_system == 'windows':
            pairs = [('Board:', 'baseboard'), ('BIOS:', 'bios'), ('OSL:', 'os')]
            values = []
            for label, target in pairs:
                cmd = "wmic %s get serialnumber" % target
                result = self.executeShellCommand(cmd, dosplit=False)
                value = result.decode().replace('SerialNumber', '').strip()
                values.append('%s%s' % (label, value))
            return '-'.join(values)

        elif operating_system == 'posix':
            values = []
            cmd = "cat /etc/fstab"
            result = self.executeShellCommand(cmd, pattern='UUID=[a-f0-9-]+ /(boot)? ')
            for line in result:
                truncated_line = line.split()[0].replace('UUID=','')
                values.append(truncated_line)
            return '-'.join(values)
        else:
            return "It is hard to make predictions, especially about the future"

    def getOwner(self,operating_system, config=None):
        owner = 'Yogi Berra'
        if operating_system == 'mac' or operating_system == 'posix':
            if not config:
                owner = getpwuid(os.stat(os.getcwd()).st_uid).pw_name
            else:
                owner = getpwuid(os.stat(config).st_uid).pw_name
        elif operating_system == 'windows':
            if not config:
                cmd = "dir /q"
                result = self.executeShellCommand(cmd)
                match = "<DIR>"
                lines = [line for line in result if match in line]
                if len(lines) > 0:
                    first_line = lines[0]
                    owner = first_line.split('>')[1].split()[0]
            else:
                config_dir = os.path.dirname(config)
                config_name = os.path.basename(config)
                os.chdir(config_dir)
                cmd = "dir /q %s" % config_name
                result = self.executeShellCommand(cmd)
                match = config_name
                lines = [line for line in result if match in line]
                if len(lines) > 0:
                    first_line = lines[0]
                    owner = first_line.rsplit(None, 1)[0].rsplit(None, 1)[-1]
                os.chdir('..')
        return owner

    def osFamily(self):
        name = platform.system()
        return {'Darwin' : 'mac',
                'Linux'  : 'posix',
                'Windows': 'windows'
               }[name]

    def identVector(self):
        operating_system = self.osFamily()
        config_path = self.konf.config_file_path
        ac_conf     = self.konf.topLevel('AgileCentral')

        hostname      = self.executeShellCommand('hostname')[0].strip()
        hardware_id   = self.getHardwareId(operating_system)
        mac_address   = self.getMacAddress(operating_system)
        conn_user_id  = getpass.getuser()
        app_base_dir  = os.getcwd()
        # app_crtime    = str(os.path.getctime(app_base_dir))  # this is unreliable
        config_dir    = os.path.split(config_path)[0]
        app_owner_id  = self.getOwner(operating_system)
        conf_owner_id = self.getOwner(operating_system, config_path)
        config_name   = os.path.basename(config_path)
        #ac            = ac_conf.get('Server', 'rally1.rallydev.com')
        ac            = ac_conf['Server']
        workspace     = ac_conf['Workspace']
        project       = ac_conf['Project']

        items = [hostname, hardware_id, mac_address, conn_user_id, app_base_dir, app_owner_id,
                     config_dir, config_name, conf_owner_id, ac, workspace, project]

        key_phrase = "-".join(items)
        #print (repr(items))
        return key_phrase
