import yaml
import json
import re
import six
import settings
import sys, os
from git import Repo
from jinja2 import Environment, FileSystemLoader
from copy import deepcopy
from colorama import init, deinit, Fore, Style
import mmap
import time
import itertools
import difflib
from pathlib import Path
from paramiko import SSHClient, SSHConfig, AutoAddPolicy, ProxyCommand, WarningPolicy, agent
from scp import SCPClient, SCPException


try:
    from collections import OrderedDict
except ImportError: # pragma: no cover # python 2.6 only
    from ordereddict import OrderedDict
import logging
logger = logging.getLogger()
class MultiLineFormatter(logging.Formatter):
    def formatException(self, exc_info):
        """
        Format an exception so that it prints on a single line.
        """
        result = super(MultiLineFormatter, self).formatException(exc_info)
        return repr(result)  # or format into one line however you want to
    def format(self, record):
        s = super(MultiLineFormatter, self).format(record)
        s = s.replace('><', '>\n<')
        return s
logger_handler = logging.FileHandler('app.log', 'w')
logger_handler.setFormatter(MultiLineFormatter('%(asctime)s|%(levelname)s|%(message)s',
                                  '%d/%m/%Y %H:%M:%S'))
logger.addHandler(logger_handler)
logger.setLevel(settings.LOGLEVEL)


init(autoreset=True)

def get_ssh_key_for_hostt(host):
    ssh_config = SSHConfig()
    user_config_file = os.path.expanduser(settings.SSH_CONFIG)
    if os.path.exists(user_config_file):
        with open(user_config_file) as f:
            ssh_config.parse(f)

    user_config = ssh_config.lookup(host)
    return user_config

def paramiko_connect(host):
    client = SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(AutoAddPolicy())

    ssh_config = SSHConfig()
    user_config_file = os.path.expanduser(settings.SSH_CONFIG)
    try:
        with open(user_config_file) as f:
            ssh_config.parse(f)
    except FileNotFoundError:
        print("{} file could not be found. Aborting.".format(user_config_file))
        sys.exit(1)
    options = ssh_config.lookup(host)
    sock = None
    proxycommand = options.get("proxycommand")
    if hasattr(settings, 'IDENTITYFILE'):
        key_filename = settings.IDENTITYFILE
    else:
        key_filename = options.get("identityfile")

    if hasattr(settings, 'USERNAME'):
        username = settings.USERNAME
    else:
        username = options.get("user")
    if proxycommand:
        if not isinstance(proxycommand, six.string_types):
          proxycommand = [os.path.expanduser(elem) for elem in proxycommand]
        else:
          proxycommand = os.path.expanduser(proxycommand)
        sock = ProxyCommand(proxycommand)

    cfg = {'hostname': host,
           'port': 22,
           'username': username,
           'password': None,
           'look_for_keys': True,
           'allow_agent': False,
           'key_filename': key_filename,
           'pkey': None,
           'passphrase': None,
           'timeout': 60,
           'auth_timeout': None,
           'banner_timeout': 15,
           'sock': sock,
            }
    return client, cfg


def check_for_errors(router_output, data):
    for error in settings.EXPECT_LIST_ERRORS:
        if re.search(error, router_output):
            sys.exit(Fore.RED + Style.BRIGHT + "* There was at least one syntax error on device %s" % data['router_hostname'])

def get_prompt(data):

    if data["router_os"] == 'junos':
        expect_prompt = r'.*\n\[RICH_USG]$' #TODO

    elif data["router_os"] in ['huawei', 'huaweiyang']:
        expect_prompt = re.compile(r'^(<|\[).*({}|\S*)(>|\])$'.format(data['system_hostname']))

    elif data["router_os"] == 'iosxr':
        expect_prompt = re.compile(r'^.*:({}|\S*)#$'.format(data['system_hostname'])) #TODO

    return expect_prompt


def get_config_from_router(data):

    if data["router_os"] == 'junos':
        cmd_list = settings.JUNIPER_GET_RUN
        regex_running_search = settings.JUNIPER_REGEX_RUNNING_SEARCH

    elif data["router_os"] in 'huawei':
        cmd_list = settings.HUAWEI_GET_RUN
        regex_running_search = settings.HUAWEI_REGEX_RUNNING_SEARCH

    elif data["router_os"] == 'iosxr':
        cmd_list = settings.CISCO_GET_RUN
        regex_running_search = settings.CISCO_REGEX_RUNNING_SEARCH

    router_output = execute(data, cmd_list)
    router_configuration = re.search(regex_running_search, router_output, re.S)
    return ''.join(router_configuration.group(0))

def get_diff_from_router(data, config_file):
    if data["router_os"] == 'junos':
        cmd_list = settings.JUNIPER_GET_DIFF
        remote_file_patch = settings.JUNIPER_REMOTE_FILE_PATCH
        regex_running_search = settings.JUNIPER_REGEX_RUNNING_SEARCH

    elif data["router_os"] in 'huawei':
        cmd_list = settings.HUAWEI_GET_DIFF
        remote_file_patch = settings.HUAWEI_REMOTE_FILE_PATCH
        regex_running_search = settings.HUAWEI_REGEX_RUNNING_SEARCH

    elif data["router_os"] == 'iosxr':
        cmd_list = settings.CISCO_GET_DIFF
        remote_file_patch = settings.CISCO_REMOTE_FILE_PATCH
        regex_running_search = settings.CISCO_REGEX_RUNNING_SEARCH

    scp_rendered_config(data, config_file, remote_file_patch)
    router_output = execute(data, cmd_list)
    router_candidat_configuration = re.search(regex_running_search, router_output, re.S)
    config_file_candidate = get_file_path(data['router_hostname'], 'candidate.cfg')
    regex = re.compile(r"\n!\s*\n!\s*|\n!\s*")
    router_candidat_configuration = re.sub(regex, r"\n!\r\n", ''.join(router_candidat_configuration.group(0)))
    with open(config_file_candidate, "w") as outfile:
        outfile.write(router_candidat_configuration)
    router_vars = get_router_varibles(data)
    data['system_hostname'] = router_vars['system']['hostname']
    configuration_from_router = get_config_from_router(data)
    regex = re.compile(r"\n!\s*")
    router_current_configuration = re.sub(regex, r"\n!\r\n", ''.join(configuration_from_router))
    config_file_current = get_file_path(data['router_hostname'], 'current.cfg')
    with open(config_file_current, "w") as outfile:
        outfile.write(router_current_configuration)

    before = open(config_file_current).readlines()
    after = open(config_file_candidate).readlines()
    diff = []
    for line in difflib.unified_diff(before, after, fromfile='delete', tofile='add', n=10, lineterm=" \r\n"):
        diff.append(line)

    return ''.join(diff)

def push_config_to_router(data, config_file):
    if data["router_os"] == 'junos':
        cmd_list = settings.JUNIPER_PUSH_CONFIG
        remote_file_patch = settings.JUNIPER_REMOTE_FILE_PATCH

    elif data["router_os"] in 'huawei':
        cmd_list = settings.HUAWEI_PUSH_CONFIG
        remote_file_patch = settings.HUAWEI_REMOTE_FILE_PATCH

    elif data["router_os"] == 'iosxr':
        cmd_list = settings.CISCO_PUSH_CONFIG
        remote_file_patch = settings.CISCO_REMOTE_FILE_PATCH

    scp_rendered_config(data, config_file, remote_file_patch)
    router_output = execute(data, cmd_list, config_file)
    return router_output

def scp_rendered_config(data, config_file, remote_file_patch):
    client, cfg = paramiko_connect(data['router_hostname'])
    client.connect(**cfg)
    with SCPClient(client.get_transport()) as scp:
        try:
            scp.put(config_file, remote_file_patch)
        except SCPException as error:
            logger.error(error)
            raise error

def execute(data, cmd_list):
    client, cfg = paramiko_connect(data['router_hostname'])

    with LazyConnection(client, cfg) as connection:
        agent.AgentRequestHandler(connection)
        return_output = []
        line = line_gen(cmd_list)
        while True:
            if connection.recv_ready():
                router_output =  connection.recv(99999).decode("utf-8")
                return_output.append(router_output)
                check_for_errors(router_output, data)
                logger.info('{1}:\n{0}'.format(router_output.replace('\r', ''), data['router_hostname'].upper()))
                try:
                    cmd = next(line)
                    connection.send(cmd + '\n')
                except StopIteration:
                    last_line = router_output.split("\r\n")[-1]
                    prompt = get_prompt(data)
                    if prompt.match(last_line):
                        check_for_errors(router_output, data)
                        break
                    continue
            time.sleep(1)
    return ''.join(return_output)

class LazyConnection:
    def __init__(self, client, cfg):
        self.client = client
        self.cfg = cfg
        self.connection = None

    def __enter__(self):
        if self.connection is not None:
            raise RuntimeError('Already connected')
        self.client.connect(**self.cfg)
        self.connection = self.client.invoke_shell('xterm')
        self.connection.get_transport().set_keepalive(60)
        return self.connection

    def __exit__(self, exc_ty, exc_val, tb):
        self.connection.close()
        self.connection = None

def notlast(itr):
    itr = iter(itr)
    prev = itr.__next__()
    for item in itr:
        yield prev
        prev = item

def line_gen(itr):
    itr = iter(itr)
    for item in itr:
        yield item

def old_get_data_for_services(data, files_list):

    generic_router_yaml = get_file_path(data['router_hostname'], 'yaml', directory='services/')
    with open(generic_router_yaml, 'w') as outfile:
        for fname in files_list:
            with open(fname) as infile:
                outfile.write(infile.read())
    with open(generic_router_yaml, 'r') as stream:
        try:
            generic_config_data = yaml.safe_load(stream)
        except yaml.YAMLddError as exc:
            print(exc)
    os.remove(generic_router_yaml)

    return generic_config_data

def get_data_for_services(data, files_list):

    generic_config_list_data = []
    for service_file in files_list:
        with open(service_file, 'r') as stream:
            try:
                generic_config_list_data.append(yaml.safe_load(stream))
            except yaml.YAMLddError as exc:
                print(exc)

    return generic_config_list_data

def yaml_service_search(search_list, expression):
    output_list = []
    for search_file in search_list:
        with open(search_file, 'rb', 0) as file, \
             mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as s:
            if s.find(expression) != -1:
                output_list.append(search_file)
    return output_list

#
def search_files(directory, extension):
    output_list = []
    extension = extension.lower()
    for dirpath, dirnames, files in os.walk(directory):
        for name in files:
            if extension and name.lower().endswith(extension):
                output_list.append(os.path.join(dirpath, name))
    return output_list
#
def get_data_from_directories(data, directory, subdirectory=None):

    if subdirectory:
        directory = directory + subdirectory
    generic_router_yaml = get_file_path(data['router_hostname'], 'yaml', directory=directory)
    generic_dir = os.path.dirname(generic_router_yaml)
    generic_router_yamls_list = get_files_list(generic_dir)
    sort_nicely(generic_router_yamls_list)
    with open(generic_router_yaml, 'w') as outfile:
        for fname in generic_router_yamls_list:
            with open(generic_dir+'/'+fname) as infile:
                outfile.write(infile.read())
    with open(generic_router_yaml, 'r') as stream:
        try:
            generic_config_data = yaml.safe_load(stream)
        except yaml.YAMLddError as exc:
            print(exc)
    os.remove(generic_router_yaml)

    return generic_config_data
#
def render_jinja_template(data, config_data):
    '''
    Using data and Jinja2 to generate config files
    '''
    env = Environment(loader = FileSystemLoader(searchpath=settings.TEMPLATES_ENVIRONMENT), trim_blocks=True, lstrip_blocks=True)
    template = env.get_template('global/templates/{0}/main.j2'.format(data['router_os']))
    merged_dict = {**data, **config_data}
    rendered_template = template.render(merged_dict)
#    logger.info('RENDERED TEMPLATE \n{0}'.format(rendered_template))

    return rendered_template
#
def get_changet_files():
    '''
    repo is a Repo instance pointing to the git-python repository,
    get yaml changet files names
    '''
    repo = Repo()
    files_list = []
    diff_files = repo.git.diff('HEAD~1', name_only=True).splitlines()
    for diff_file in diff_files:
        if diff_file.endswith('.cfg'):
            files_list.append(diff_file)

    return files_list
#
def if_router_in_changet_files(data, changet_files):
 
    if data['router_hostname'] in list(itertools.chain.from_iterable([list(filter(None, re.split(".rendered.cfg|/", x))) for x in changet_files])):
        return True
    else:
        return False
#
def get_file_path(name, ext, configuration=None, directory=None):

    if not directory:
        directory = settings.CONFIG_FILES_DIRECTORY
    filename = os.path.join(directory, name+'.'+ext)

    return filename
#
def tryint(s):
    try:
        return int(s)
    except ValueError:
        return s
#
def alphanum_key(s):
    """ Turn a string into a list of string and number chunks.
        "z23a" -> ["z", 23, "a"]
    """
    return [ tryint(c) for c in re.split('([0-9]+)', s) ]
#
def sort_nicely(l):
    """ Sort the given list in the way that humans expect.
    """
    l.sort(key=alphanum_key)
#
def get_files_list(mypath, ext='yaml'):

    f = []
    for (dirpath, dirnames, filenames) in os.walk(mypath):
        for filename in filenames:
            if re.search('.*({0})$'.format(ext), filename) is not None:
                f.append(filename)
        break

    return f
#
def dict_reduce(function, iterable, data):
    it = iter(iterable)
    value = next(it)
    for element in it:
        value = function(value, element, data)
    return value
#

class check_config_data:
    def __init__(self,  initial=None):
        self._z = initial if initial is not None else OrderedDict()
        self.initial = initial

    def _atoi(self, text):
        return int(text) if text.isdigit() else text

    def _natural_keys(self, text):
        return [ self._atoi(c) for c in re.split('(\d+)',text) ]

    def _sort_natural_keys(self, x):
        _z = OrderedDict()
        for key in x.keys():
            list_sorted = sorted(x[key].keys())
            list_sorted.sort(key=self._natural_keys)
            _z[key] = OrderedDict()
            for name in list_sorted:
                _z[key][name] = deepcopy(x.get(key)[name])
        return _z
    def _sort_keys(self, x):
        _z = OrderedDict()
        for key in x.keys():
            list_sorted = sorted(x[key].keys())
            _z[key] = OrderedDict()
            for name in list_sorted:
                _z[key][name] = deepcopy(x.get(key)[name])
        return _z

    def get(self):
        return self._z

    def sort_interfaces(self):
        for key in self.initial.keys():
            if key == 'interfaces':
                self._z[key] = self._sort_natural_keys(self.initial[key])
            else:
                self._z[key] = deepcopy(self.initial[key])
    def sort_prefix_sets(self):
        for key in self.initial.keys():
            if key == 'routing_policy':
                if self.initial[key]['sets']['prefix_sets']:
                    self._z[key]['sets'] = self._sort_keys(self.initial[key]['sets'])
                else:
                    self._z[key]['sets'] = deepcopy(self.initial[key]['sets'])
            else:
                self._z[key] = deepcopy(self.initial[key])
        logger.debug('DATA \n{0}'.format(json.dumps(self._z, indent=2)))

#
def search_for_key(x, y):
    z = OrderedDict()
    overlapping_keys = x.keys() & y.keys()
    for key in overlapping_keys:
        try:
            y[key].keys()
            x[key].keys()
            z[key] = search_for_key(x[key], y[key])
        except:
            z[key] = deepcopy(x[key] + y[key])
    for key in x.keys() - overlapping_keys:
        z[key] = deepcopy(x[key])
    for key in y.keys() - overlapping_keys:
        z[key] = deepcopy(y[key])
    return z

#
def dict_of_dicts_merge(x, y, data):
    z = OrderedDict()
    overlapping_keys = x.keys() & y.keys()
    for key in overlapping_keys:
        if key == 'l3vpn':
            z[key] = search_for_key(x[key], y[key])
        elif x[key].get(settings.LIST_MERGE_KEY) or y[key].get(settings.LIST_MERGE_KEY):
            try:
                z[key] = deepcopy(x[key].get(settings.LIST_MERGE_KEY) + y[key].get(settings.LIST_MERGE_KEY))
            except:
                try:
                    z[key] = deepcopy(x[key] + y[key].get(settings.LIST_MERGE_KEY))
                except:
                    z[key] = deepcopy(x[key].get(settings.LIST_MERGE_KEY) + y[key])
        else:
            try:
                y[key].keys()
                x[key].keys()
                z[key] = dict_of_dicts_merge(x[key], y[key], data)
            except:
                z[key] = deepcopy(y[key])
    for key in x.keys() - overlapping_keys:
        z[key] = deepcopy(x[key])
    for key in y.keys() - overlapping_keys:
        if key == data['router_hostname']:
            overlapping_keys = x.keys() & y[key].keys()
            for o_0 in overlapping_keys:
                z[o_0] = dict_of_dicts_merge(x[o_0], y[key][o_0], data)
            for ykey in y[key].keys() - overlapping_keys:
                z[ykey] = deepcopy(y[key][ykey])
        else:
            z[key] = deepcopy(y[key])
    return z


def get_router_varibles(data):
## generate configuration from YAMLs

    generic_config_data = get_data_from_directories(data, 'global/')
    router_specific_config_data = get_data_from_directories(data, 'router_specific/', data['router_hostname'])

    search_expression ='{0}:'.format(data['router_hostname']).encode()
    service_yamls = search_files('services/', 'yaml')
    router_specific_service_file_list = yaml_service_search(service_yamls, search_expression)
    router_specific_service_data_list = get_data_for_services(data, router_specific_service_file_list)

    merged_config_data_list = []
    merged_config_data_list.append(generic_config_data)
    if router_specific_config_data:
        merged_config_data_list.append(router_specific_config_data)
    if router_specific_service_data_list:
        for element in router_specific_service_data_list:
            merged_config_data_list.append(element)

    merged_config_data = dict_reduce(dict_of_dicts_merge, merged_config_data_list, data)
    checked_config_data = check_config_data(merged_config_data)
    checked_config_data.sort_interfaces()
    checked_config_data.sort_prefix_sets()

    return checked_config_data.get()
